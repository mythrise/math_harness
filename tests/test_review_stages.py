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
    c.store=Store(tmp_path);c.demo=True;c.literature=None;c.review_cycle=0
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
