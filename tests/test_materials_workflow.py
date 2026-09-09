import copy, json
from types import SimpleNamespace
import pytest
from cumcm_harness.common import digest,IntegrityError,ScientificRejection,write_json
from cumcm_harness.store import Store
from cumcm_harness.materials_workflow import MaterialsWorkflow,plan_attestation_target
from cumcm_harness.materials_contracts import claim_tokens,STEPS
from cumcm_harness.review_board import ProviderFailure
from materials_samples import samples,PROBLEM

class StubController:
    """Explicit unit fixture: no service, authentication or scientific review."""
    def __init__(self,root):
        self.root=root;self.store=Store(root);self.problem=PROBLEM;self.config={'repair_attempts':2}
        b,d,a,p,m,*_=samples();self.base={'methods':m};self.calls=[];self.behavior={}
    def call(self,key,role,schema,packet):
        def invoke():
            self.calls.append((key,role,schema))
            if schema in self.behavior:return self.behavior[schema](packet)
            b,d,a,p,m,plan,draft,claims,e,pm=samples()
            v={'problem_brief':b,'data_plan':d,'model_portfolio':p}.get(schema)
            if schema=='abstract_revision':v={'abstract':'误差为{{claim:result_error}}，只说明当前数据。','keywords':['预测核验'],
                'claim_ids':['result_error'],'remaining_limitations':['不作外推。']}
            if schema=='paper_map':
                v=pm;v['draft_digest']=packet['draft_digest']
                v['questions'][1]['qualitative_evidence_ids']=[packet['question_evidence'][0]['id']]
            return {'result':copy.deepcopy(v),'receipt':{'fixture':True,'digest':digest(v)}}
        return self.store.step('stub-call:'+key,packet,invoke)
    def reviews(self,key,value,**kwargs):
        if self.behavior.get('negative'):raise ScientificRejection('fixture negative',records=[{'defect':'known'}])
        return [{'fixture':True,'target':digest(value)}]


def test_preparation_is_replayable_readonly(tmp_path):
    data=tmp_path/'inputs/development';data.mkdir(parents=True);(data/'history.csv').write_text('t,y\n1,2\n2,3\n')
    c=StubController(tmp_path);w=MaterialsWorkflow(c)
    one=w.prepare({'objective':'test'});count=len(c.calls)
    assert count==3
    assert w.prepare({'objective':'test'})==one and len(c.calls)==count
    assert one['data_audit']['files'][0]['observed_rows']==2
    assert one['empirical_validation']=='NOT_RUN'
    assert c.base['modeling_coverage_contract']['page_minimum'] is None


def test_stage_negative_not_waived(tmp_path):
    c=StubController(tmp_path);c.behavior['negative']=True;w=MaterialsWorkflow(c)
    with pytest.raises(ScientificRejection):w._stage('negative','problem_analyst','problem_brief',{},lambda x:x,('math_reviewer',))
    assert len(c.calls)==3


def test_brief_receives_exact_source_offsets_without_weakening_the_checker(tmp_path):
    data=tmp_path/'inputs/development';data.mkdir(parents=True);(data/'history.csv').write_text('t,y\n1,2\n2,3\n')
    c=StubController(tmp_path)
    def brief(packet):
        assert packet['exact_anchor_candidates']
        for anchor in packet['exact_anchor_candidates']:
            assert c.problem[anchor['start']:anchor['end']]==anchor['quote']
        value=copy.deepcopy(samples()[0]);value['requirements'][0]['anchor']['start']+=1
        return {'result':value,'receipt':{'fixture':True}}
    c.behavior['problem_brief']=brief
    with pytest.raises(ScientificRejection):MaterialsWorkflow(c).prepare({'objective':'test'})
    assert len(c.calls)==3


def test_provider_outage_not_counted_as_model_repair(tmp_path):
    c=StubController(tmp_path);c.behavior['problem_brief']=lambda p:(_ for _ in ()).throw(ProviderFailure('codex','TIMEOUT'))
    with pytest.raises(ProviderFailure):MaterialsWorkflow(c)._stage('outage','problem_analyst','problem_brief',{},lambda x:x,('math_reviewer',))
    assert len(c.calls)==1


def test_abstract_is_generated_after_body_and_replayable(tmp_path):
    c=StubController(tmp_path);b,d,a,p,m,plan,draft,claims,e,pm=samples()
    c.base['materials_preparation']={'brief':b};w=MaterialsWorkflow(c)
    qev=[{'job_id':'j1','evidence':e}]
    new,artifact=w.prepare_paper(draft,plan,claims,qev,0)
    assert new['sections']==draft['sections'] and new['abstract']!=draft['abstract']
    assert artifact['diagnostic']['status'].startswith('STRUCTURAL')
    n=len(c.calls);assert w.prepare_paper(draft,plan,claims,qev,0)==(new,artifact) and len(c.calls)==n


def test_abstract_cannot_add_unmeasured_value(tmp_path):
    c=StubController(tmp_path);b,d,a,p,m,plan,draft,claims,e,pm=samples();c.base['materials_preparation']={'brief':b}
    c.behavior['abstract_revision']=lambda p:{'result':{'abstract':'{{claim:invented}}','keywords':['x'],'claim_ids':['invented'],'remaining_limitations':['x']},'receipt':{}}
    with pytest.raises(IntegrityError):MaterialsWorkflow(c).prepare_paper(draft,plan,claims,[{'job_id':'j','evidence':e}],0)


def test_plan_human_target_covers_preparation():
    *_,plan,draft,claims,e,pm=samples()  # overwritten explicitly below
    b,d,a,p,m,plan,*_=samples()
    assert plan_attestation_target(plan,{})==digest(plan)
    first=plan_attestation_target(plan,{'materials_preparation':{'brief':b}})
    b['unit_risks'].append('单位变化')
    assert first!=plan_attestation_target(plan,{'materials_preparation':{'brief':b}})


def test_brief_repair_receives_exact_invalid_reference_and_latest_artifact(tmp_path):
    from cumcm_harness.materials_contracts import check_brief
    c=StubController(tmp_path);good=copy.deepcopy(samples()[0]);bad=copy.deepcopy(good)
    bad['questions'][0]['constraint_ids'].append('R1')
    packets=[]
    def proposer(packet):
        packets.append(copy.deepcopy(packet))
        return {'result':bad if not packet['repair_feedback'] else good,'receipt':{'fixture':True}}
    c.behavior['problem_brief']=proposer
    result=MaterialsWorkflow(c)._stage('brief','problem_analyst','problem_brief',{'problem':PROBLEM},lambda v:check_brief(v,PROBLEM),('math_reviewer',))
    assert result==good and len(packets)==2
    feedback=packets[1]['repair_feedback'][-1]
    assert 'Q1' in feedback['error'] and 'R1' in feedback['error'] and 'deliverable' in feedback['error']
    assert feedback['prior_artifact']==bad
    assert not packets[0]['repair_feedback']
    assert 'prior_artifact' not in __import__('json').loads(next(e['payload'] for e in c.store.events() if e['kind']=='MATERIALS_REPAIR'))['diagnostic']
