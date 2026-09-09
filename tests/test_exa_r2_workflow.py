"""R2 stages through the real controller with deterministic source/model fixtures."""
import copy
import pytest
from cumcm_harness.common import ROOT,Blocked,IntegrityError,read_json
from cumcm_harness.controller import Controller,DEFAULT_CONFIG
from cumcm_harness.intake import create_workspace
from cumcm_harness.store import Store
from cumcm_harness.providers import FixtureProvider
from cumcm_harness.exa_defaults import DEFAULT_POLICY
from cumcm_harness.exa_policy import load_frozen
from cumcm_harness.exa_transport import R2ExaClient
from cumcm_harness.exa_r2_demo import r2_responder,r2_transport
from cumcm_harness.resilience_demo import PLAN,OutageProvider
from cumcm_harness.literature import LiteratureAssessmentFailure


def controller(tmp_path,responder=r2_responder,transport=r2_transport):
    problem=tmp_path/'problem.md';problem.write_text('Synthetic job scheduling integration fixture')
    data=tmp_path/'data';data.mkdir();(data/'input.txt').write_text('Synthetic data')
    root=tmp_path/'workspace'
    config={**DEFAULT_CONFIG,**read_json(ROOT/'configs/exa-modeling-compatible.json'),'review_backoff_seconds':0}
    create_workspace(root,problem,data,config,exa_policy=DEFAULT_POLICY)
    provider=FixtureProvider(responder);client=R2ExaClient(Store(root),load_frozen(root),transport=transport,sleep=lambda _:None)
    c=Controller(root,fixture_provider=provider,exa_client=client);c.providers['claude']=OutageProvider()
    return c,provider


def test_mapped_primary_reads_located_export_and_replay(tmp_path):
    packets=[]
    def responder(role,schema,packet):
        packets.append((role,schema,copy.deepcopy(packet)))
        return r2_responder(role,schema,packet)
    c,provider=controller(tmp_path,responder);wf=c.literature;wf.collect_initial({'research_focus':[]})
    accepted=wf.assess(PLAN)
    assert accepted['retrieval']=='FIXTURE_EXA_TRANSPORT' and accepted['empirical_tests']=='NOT_RUN'
    assert [t['name'] for t in accepted['required_tests']]==['hypothesis_H2','hypothesis_H3']
    assert all('text' not in s and s['quoted_evidence'] for s in accepted['evidence'])
    ids={h['id'] for h in accepted['hypotheses']['hypotheses']}
    for purpose in ('background','counterexample'):
        assert {h for link in accepted['query_links'] if link['purpose']==purpose for h in link['hypothesis_ids']}==ids
    opponent=[p for role,schema,p in packets if role=='hypothesis_critic' and schema=='research_queries_r2']
    assert opponent and all('audit' not in p and 'author_verdict' not in p for p in opponent)
    count=provider.count;attempts=wf.client.ledger.summary()['http_attempts_reserved']
    assert wf.assess(PLAN)==accepted and provider.count==count and wf.client.ledger.summary()['http_attempts_reserved']==attempts
    with pytest.raises(Blocked):wf.require_tests({'cases':[]})


def test_negative_semantic_review_after_outage_is_binding_and_preserved(tmp_path):
    def responder(role,schema,packet):
        out=r2_responder(role,schema,packet)
        if role=='literature_reviewer':
            out['verdict']='FAIL';out['findings']=[{'severity':'P1','location':'H1 quotation',
                'issue':'Exact words do not entail the claimed scope','required_fix':'Revise claim and supporting context'}]
        return out
    c,provider=controller(tmp_path,responder);wf=c.literature;wf.collect_initial({'research_focus':[]})
    with pytest.raises(LiteratureAssessmentFailure):wf.assess(PLAN)
    count=provider.count
    with pytest.raises(LiteratureAssessmentFailure):wf.assess(PLAN)
    assert provider.count==count and list((c.root/'literature/audits').glob('*.json'))
    assert wf.accepted is None and list((c.root/'reviews').glob('*.json'))


def test_missing_hypothesis_mapping_blocks_before_http(tmp_path):
    c,_=controller(tmp_path);wf=c.literature
    proposal={'queries':[{'query':'generic mathematical method','profile':'counterexamples','purpose':'counterexample',
                          'hypothesis_ids':['H1'],'additional_queries':[]}]}
    with pytest.raises(IntegrityError):wf.retrieve(proposal,opponent=True,hypotheses=['H1','H2'])
    assert wf.client.ledger.summary()['http_attempts_reserved']==0


def test_narrower_proposal_limit_is_enforced_before_http(tmp_path):
    c,_=controller(tmp_path);wf=c.literature
    wf.policy['budget']['max_queries_per_model_proposal']=1
    row={'query':'generic mathematical method','profile':'foundations','purpose':'background',
         'hypothesis_ids':['H1'],'additional_queries':[]}
    with pytest.raises(IntegrityError,match='query limit'):wf.retrieve({'queries':[row,copy.deepcopy(row)]},hypotheses=['H1'])
    assert wf.client.ledger.summary()['http_attempts_reserved']==0


def test_invented_initial_hypothesis_ids_are_repaired_before_http(tmp_path):
    packets=[]
    def responder(role,schema,packet):
        packets.append(copy.deepcopy(packet))
        assert packet['allowed_hypothesis_ids']==[]
        assert c.literature.client.ledger.summary()['http_attempts_reserved']==0
        result=r2_responder(role,schema,packet)
        if len(packets)==1:
            for query in result['queries']:query['hypothesis_ids']=['H_INVENTED']
        return result
    c,provider=controller(tmp_path,responder)
    c.literature.collect_initial({'research_focus':[]})
    assert provider.count==2 and len(packets[1]['query_mapping_repairs'])==1
    assert packets[1]['query_mapping_repairs'][0]['http_dispatched'] is False
    assert packets[1]['query_mapping_repairs'][0]['proposal']['queries'][0]['hypothesis_ids']==['H_INVENTED']
    count=provider.count;attempts=c.literature.client.ledger.summary()['http_attempts_reserved']
    from cumcm_harness.literature_r2 import R2LiteratureWorkflow
    c.literature=R2LiteratureWorkflow(c,c.literature.client)
    c.literature.collect_initial({'research_focus':[]})
    assert provider.count==count and c.literature.client.ledger.summary()['http_attempts_reserved']==attempts


def test_query_mapping_repairs_are_bounded_without_any_http(tmp_path):
    def responder(role,schema,packet):
        result=r2_responder(role,schema,packet)
        for query in result['queries']:query['hypothesis_ids']=['H_INVENTED']
        return result
    c,provider=controller(tmp_path,responder);c.config['repair_attempts']=1
    with pytest.raises(IntegrityError,match='current H-IDs'):
        c.literature.collect_initial({'research_focus':[]})
    assert provider.count==2
    assert c.literature.client.ledger.summary()['http_attempts_reserved']==0


def test_query_repair_does_not_retry_provider_failures(tmp_path):
    from cumcm_harness.review_board import ProviderFailure
    c,_=controller(tmp_path);calls=[]
    def fail(*args,**kwargs):
        calls.append(args);raise ProviderFailure('codex','TIMEOUT')
    c.call=fail
    with pytest.raises(ProviderFailure):c.literature.collect_initial({'research_focus':[]})
    assert len(calls)==1 and c.literature.client.ledger.summary()['http_attempts_reserved']==0


def test_critic_sees_limitations_from_support_lane_even_when_excluded(tmp_path):
    packets={}
    def responder(role,schema,packet):
        if schema in ('source_selection_r2','hypothesis_audit_r2'):
            packets[schema]=copy.deepcopy(packet)
        return r2_responder(role,schema,packet)
    c,_=controller(tmp_path,responder);wf=c.literature;original=wf._queries
    def queries(*args,**kwargs):
        sources,links=original(*args,**kwargs)
        if not kwargs.get('opponent'):
            for source in sources:source['purpose']='limitations'
        return sources,links
    wf._queries=queries
    wf.collect_initial({'research_focus':[]});wf.assess(PLAN)
    required={s['id'] for s in packets['source_selection_r2']['sources']
              if s.get('purpose') in ('counterexample','limitations')}
    audit=packets['hypothesis_audit_r2']
    assert {s['id'] for s in audit['opposing_candidates']}==required
    assert {s['source_id'] for s in audit['opposing_dispositions']}==required
    assert any(s['purpose']=='limitations' for s in audit['opposing_candidates'])
