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
