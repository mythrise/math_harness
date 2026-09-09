"""Lifecycle scopes retained with two seats per role; fixtures are not live reviews."""
import pytest
from cumcm_harness.common import Blocked,IntegrityError
from cumcm_harness.controller import Controller,DEFAULT_CONFIG
from cumcm_harness.demo import responder
from cumcm_harness.providers import FixtureProvider
from cumcm_harness.review_board import ReviewBoard,ProviderFailure
from cumcm_harness.store import Store


def controller(tmp_path,response=responder):
    c=Controller.__new__(Controller);c.root=tmp_path;c.problem='Synthetic scope test'
    c.base={'experiment_contract':{'development_seeds':[101,202,303]},'source_registry':[{'id':'synthetic-source'}]}
    c.config={**DEFAULT_CONFIG,'repair_attempts':0,'review_backoff_seconds':0}
    c.store=Store(tmp_path);c.demo=True;c.literature=None;c.materials=None;c.review_cycle=0
    fp=FixtureProvider(response);c.providers={'claude':fp,'codex':fp};packets=[]
    def call(key,role,schema,packet,**kw):
        packets.append((role,packet));return fp.invoke(role,schema,packet,tmp_path/'calls'/str(len(packets)))
    c.call=call;c._call_one=call;c.review_board=ReviewBoard(c)
    return c,packets

@pytest.mark.parametrize('role,schema,key',[('modeler','plan','plan'),('coder','bundle','candidate:c0')])
def test_pre_execution_reviews_get_explicit_scope(tmp_path,role,schema,key):
    c,packets=controller(tmp_path);c.produce_reviewed(key,role,schema,{})
    reviews=[p for r,p in packets if r.endswith('_reviewer')]
    assert len(reviews)==4
    assert all(p['review_stage']==('plan_design' if role=='modeler' else 'source_code') for p in reviews)
    assert all(p['stage_requirements']['certifies_execution'] is False for p in reviews)
    assert all(p['context']['source_registry']==c.base['source_registry'] for p in reviews)


def test_runtime_review_requires_real_execution_evidence(tmp_path):
    c,packets=controller(tmp_path);c.reviews('smoke',{'smoke':'fixture'})
    assert all(p['stage_requirements']['certifies_execution'] is True for _,p in packets)


def test_valid_negative_is_never_downgraded_or_retried(tmp_path):
    def fail(role,schema,packet):
        r=responder(role,schema,packet)
        if schema=='review':r.update(verdict='FAIL',findings=[{'severity':'P1','location':'equation','issue':'Wrong dimensions','required_fix':'Correct model'}])
        return r
    c,packets=controller(tmp_path,fail)
    with pytest.raises(Blocked,match='Wrong dimensions'):c.produce_reviewed('plan','modeler','plan',{})
    assert c.store.get('plan') is None
    assert len([r for r,p in packets if r.endswith('_reviewer')])==4


def test_contradictory_pass_with_objection_is_not_availability(tmp_path):
    c,packets=controller(tmp_path)
    def invalid(*args,**kwargs):raise IntegrityError('PASS cannot contain blocking findings or unverified required checks')
    c._call_one=invalid
    with pytest.raises(IntegrityError):c.reviews('x',{'test':'fixture'})
    assert not packets


def test_transport_outage_switches_without_changing_scope(tmp_path):
    c,packets=controller(tmp_path);original=c._call_one
    def invoke(*args,**kw):
        if kw['provider_kind']=='claude':raise ProviderFailure('claude','TIMEOUT')
        return original(*args,**kw)
    c._call_one=invoke
    c.reviews('plan',{'model':'fixture'},stage='plan_design')
    assert len(packets)==4 and all(p['review_stage']=='plan_design' for _,p in packets)


def test_failed_prefreeze_execution_reaches_author_before_review(tmp_path):
    c,packets=controller(tmp_path);c.demo=False;c.config['repair_attempts']=1
    attempts=[];contexts=[]
    def preflight(bundle):
        attempts.append(bundle);return {'passed':len(attempts)>1,'stderr':'IndexError: weight array has 4 entries for 64 nodes'}
    c.verifier_preflight=preflight;c.reviews=lambda *a,**kw:contexts.append(kw['context']) or []
    c.produce_reviewed('verifier','verifier_author','bundle',{'plan':{'contract':'fixed'}})
    assert len(attempts)==2 and len(contexts)==1
    author=[p for role,p in packets if role=='verifier_author']
    feedback=author[1]['repair_feedback'][0]
    assert feedback['prior_artifact']==attempts[0] and 'IndexError' in feedback['runtime_diagnostic']['stderr']
    assert contexts[0]['bounded_preflight']['passed'] is True


@pytest.mark.parametrize('failure',['unsupported','contradicted','board_rejection','board_outage'])
def test_literature_failure_preserves_full_feedback_for_plan_author(tmp_path,failure):
    """A malformed citation must not hide the critic's substantive objections."""
    from cumcm_harness.common import digest,read_json
    from cumcm_harness.literature import LiteratureWorkflow
    c,packets=controller(tmp_path);c.config['repair_attempts']=1
    c.base['methods']=[{'name':'synthetic-card','applicability':'conditional'}]
    source={'id':'source1','text':'Synthetic source supports only a bounded claim.'}
    source['content_sha256']=digest(source['text'])
    wf=LiteratureWorkflow.__new__(LiteratureWorkflow)
    wf.c=c;wf.initial=[source];wf.accepted=None
    wf.retrieve=lambda *a,**kw:[source]
    c.literature=wf;original=c.call;audits=[];critic_packets=[]
    def call(key,role,schema,packet,**kw):
        if schema=='hypotheses':
            return {'result':{'hypotheses':[{
                'id':f'H{i+1}','assumption_index':i,'statement':a,'kind':'structural',
                'falsification_test':'Check the declared boundary','acceptance_rule':'Within scope',
                'failure_action':'Revise the specification'} for i,a in enumerate(packet['plan']['assumptions'])]}}
        if schema=='research_queries':return {'result':{'queries':[]}}
        if schema=='hypothesis_audit':
            critic_packets.append(packet)
            audit={'decision':'ACCEPT_FOR_TESTING' if failure.startswith('board_') else 'REVISE',
                'checks':[{'hypothesis_id':h['id'],
                    'judgment':'supported_with_scope' if failure=='unsupported' else
                        'contradicted' if failure=='contradicted' else 'explicit_simplification',
                    'rationale':'A narrow shadow can be missed by every unshifted grid. Add a Docker preflight counterexample.',
                    'evidence':[{'source_id':'source1','quote':'Synthetic source supports only a bounded claim.',
                        'relation':'scope_limit'}],
                    'requires_execution':True,'required_test':'hypothesis_'+h['id']}
                    for h in packet['hypotheses']['hypotheses']],
                'citation_ids':['source1'],'limitations':['Add shifted-grid counterexamples.']}
            audits.append(audit);return {'result':audit}
        return original(key,role,schema,packet,**kw)
    c.call=call
    def reject(*args,**kwargs):
        if failure=='board_outage':
            from cumcm_harness.review_board import ReviewUnavailable
            raise ReviewUnavailable('All required providers unavailable')
        raise Blocked('Independent literature board requests narrower claims')
    c.reviews=reject
    with pytest.raises(Blocked):c.produce_reviewed('plan','modeler','plan',{})
    authors=[p for role,p in packets if role=='modeler']
    if failure=='board_outage':
        assert len(authors)==1 and not authors[0]['repair_feedback']
        assert c.store.get('plan') is None and wf.accepted is None
        return
    feedback=authors[1]['repair_feedback'][0]
    assert feedback['literature_diagnostic']['audit']==audits[0]
    assert feedback['literature_diagnostic']['validation_status']=='REJECTED_NOT_ACCEPTED'
    assert feedback['prior_artifact']['assumptions']
    assert feedback['literature_diagnostic']['sources']==[{k:v for k,v in source.items() if k!='text'}]
    assert c.store.load(feedback['diagnostic_ref'])['sources']==[source]
    for packet in critic_packets:
        assert packet['context']['methods']==c.base['methods']
        assert packet['context']['experiment_contract']==c.base['experiment_contract']
        assert 'source_registry' not in packet['context']
        assert packet['citation_contract']['allowed_source_ids']==['source1']
        assert packet['citation_contract']['context_is_not_literature'] is True
        assert packet['problem']==c.problem
    path=tmp_path/'literature/audits'/(digest(feedback['prior_artifact'])+'.json')
    assert read_json(path)['audit']==audits[0]
    assert c.store.get('plan') is None and wf.accepted is None


def test_repair_history_keeps_objections_without_repeating_source_bodies(tmp_path):
    import copy
    from types import SimpleNamespace
    from cumcm_harness.common import canonical,digest
    from cumcm_harness.literature import LiteratureAssessmentFailure
    c,_=controller(tmp_path);c.config['repair_attempts']=5
    calls=[];dossiers=[]
    def call(key,role,schema,packet,**kwargs):
        calls.append(copy.deepcopy(packet))
        return {'result':responder(role,schema,packet)}
    c.call=call
    def reject(plan):
        source={'id':'large-source','text':'large archived source '*20000}
        source['content_sha256']=digest(source['text'])
        dossier={'plan_digest':digest(plan),'hypotheses':{},'audit':{
            'decision':'REVISE','checks':[{'rationale':f'Objection {len(dossiers)}: retain this required fix'}]},
            'sources':[source],'empirical_tests':'NOT_RUN'}
        dossiers.append(dossier)
        raise LiteratureAssessmentFailure('Hypothesis critic requests model revision: '+canonical(dossier['audit']).decode(),dossier)
    c.literature=SimpleNamespace(assess=reject)
    with pytest.raises(Blocked) as error:c.produce_reviewed('plan','modeler','plan',{})
    assert len(calls)==6 and len(str(error.value))<4000
    assert all(len(canonical(p))<100000 for p in calls)
    for index,packet in enumerate(calls[1:],1):
        history=packet['repair_feedback']
        assert len(history)==index
        assert sum('prior_artifact' in row for row in history)==1
        for j,row in enumerate(history):
            assert f'Objection {j}' in row['literature_diagnostic']['audit']['checks'][0]['rationale']
            assert c.store.load(row['diagnostic_ref'])['sources']==dossiers[j]['sources']
    assert c.store.audit()['integrity']=='PASS'


@pytest.mark.parametrize('kind',['size','provider'])
def test_direct_author_request_failure_does_not_consume_repair_rounds(tmp_path,kind):
    from cumcm_harness.providers import PromptPacketTooLarge
    c,_=controller(tmp_path);c.config['repair_attempts']=5;calls=[]
    def fail(*args,**kwargs):
        calls.append(1)
        if kind=='size':raise PromptPacketTooLarge('Input exceeds the limit')
        raise ProviderFailure('codex','EXIT_NONZERO')
    c.call=fail
    with pytest.raises(Blocked):c.produce_reviewed('plan','modeler','plan',{})
    assert len(calls)==1
