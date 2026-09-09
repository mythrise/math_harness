"""Failure injection, never a claim of live model review quality."""
import copy
from types import SimpleNamespace
import pytest
from cumcm_harness.common import Blocked, IntegrityError, digest
from cumcm_harness.store import Store
from cumcm_harness.review_board import ReviewBoard, ProviderFailure, ReviewUnavailable, check_board
from cumcm_harness.providers import FixtureProvider
from cumcm_harness.demo import responder


def board(tmp_path, fail=None):
    c=SimpleNamespace(root=tmp_path,store=Store(tmp_path),demo=True,review_cycle=1,
        config={'review_members_per_role':2,'review_attempts_per_provider':2,'review_cooldown_seconds':10,'review_backoff_seconds':0},
        providers={'claude':SimpleNamespace(model='c'),'codex':SimpleNamespace(model='g')})
    calls=[];fp=FixtureProvider(responder)
    def invoke(key,role,schema,packet,*,provider_kind,images=(),managed_failure=False):
        calls.append((provider_kind,role,packet))
        if fail: fail(provider_kind,role,packet,len(calls))
        return fp.invoke(role,schema,packet,tmp_path/'calls'/str(len(calls)),images=images)
    c._call_one=invoke
    c.review_board=ReviewBoard(c,clock=lambda:100,sleep=lambda _:None)
    packet={'artifact':{'test':'fixture'},'target_digest':digest({'test':'fixture'}),'review_stage':'execution'}
    return c,c.review_board,calls,packet

@pytest.mark.parametrize('code',['TIMEOUT','EXIT_NONZERO','REMOTE_ERROR','INVALID_JSON','MISSING_STRUCTURED_OUTPUT','OUTPUT_SCHEMA_INVALID','NOT_INSTALLED'])
def test_claude_outage_takes_over_and_circuit_breaks(tmp_path,code):
    def fail(kind,*_):
        if kind=='claude':raise ProviderFailure(kind,code,retryable=code!='NOT_INSTALLED')
    c,b,calls,p=board(tmp_path,fail)
    r=b.review('a',p,('math_reviewer','experiment_reviewer'))
    assert len(r)==4
    assert all(x['receipt']['availability']['selected']=='codex' for x in r)
    assert sum(k=='claude' for k,*_ in calls)==(1 if code=='NOT_INSTALLED' else 2)
    count=len(calls);c.review_cycle+=1
    assert b.review('changed-parent-key',p,('math_reviewer','experiment_reviewer'))==r
    assert len(calls)==count


def test_standalone_success_replays_after_resume(tmp_path):
    c,b,calls,p=board(tmp_path)
    first=b.invoke('critic','math_reviewer','review',p)
    c.review_cycle=99
    assert b.invoke('critic','math_reviewer','review',p)==first
    assert len(calls)==1


def test_negative_verdict_survives_reentry_and_other_positive_votes(tmp_path):
    c,b,calls,p=board(tmp_path)
    orig=c._call_one
    def invoke(*a,**kw):
        r=orig(*a,**kw)
        if kw['provider_kind']=='claude':
            r['result']['verdict']='FAIL'
            r['result']['findings']=[{'severity':'P1','location':'assumption','issue':'Counterexample exists','required_fix':'Change the model'}]
            r['receipt']['response_digest']=digest(r['result'])
        return r
    c._call_one=invoke
    with pytest.raises(Blocked,match='Counterexample') as first:b.review('negative',p,('math_reviewer',))
    assert [x[0] for x in calls]==['claude','codex']
    count=len(calls)
    with pytest.raises(Blocked) as replay:b.review('different-key',p,('math_reviewer',))
    assert str(first.value)==str(replay.value)
    assert len(calls)==count
    assert len(list((tmp_path/'reviews').glob('*.json')))==1


def test_integrity_or_budget_error_never_switches(tmp_path):
    for error in (IntegrityError('tampered source'),Blocked('Model-call budget exhausted'),Blocked('RUNNING unknown')):
        def fail(*_):raise error
        c,b,calls,p=board(tmp_path/f'case{type(error).__name__}{len(str(error))}',fail)
        with pytest.raises(type(error)):b.review('x',p,('math_reviewer',))
        assert len(calls)==1


def test_both_unavailable_resume_after_cooldown(tmp_path):
    def fail(kind,*_):raise ProviderFailure(kind,'TIMEOUT')
    c,b,calls,p=board(tmp_path,fail)
    with pytest.raises(ReviewUnavailable):b.review('x',p,('math_reviewer',))
    assert len(calls)==4
    with pytest.raises(ReviewUnavailable):b.review('x',p,('math_reviewer',))
    assert len(calls)==4
    b.clock=lambda:111;c.review_cycle+=1
    fp=FixtureProvider(responder)
    c._call_one=lambda key,role,schema,packet,**kw:fp.invoke(role,schema,packet,tmp_path/'resumed'/str(fp.count))
    assert len(b.review('x',p,('math_reviewer',)))==2


def test_two_gpt_seats_distinct_and_not_live(tmp_path):
    c,b,_,p=board(tmp_path)
    r=b.review('x',p,('math_reviewer',))
    assert len({x['receipt']['invocation_id'] for x in r})==2
    with pytest.raises(Blocked):check_board(r,p['target_digest'],('math_reviewer',),allow_fixture=False)
    bad=copy.deepcopy(r);bad[1]['receipt']['invocation_id']=bad[0]['receipt']['invocation_id']
    with pytest.raises(IntegrityError):check_board(bad,p['target_digest'],('math_reviewer',),allow_fixture=True)


def test_modified_target_or_packet_does_not_reuse_board(tmp_path):
    c,b,calls,p=board(tmp_path)
    b.review('x',p,('math_reviewer',));assert len(calls)==2
    p={**p,'artifact':{'test':'changed'},'target_digest':digest({'test':'changed'})}
    b.review('x',p,('math_reviewer',));assert len(calls)==4


def test_images_only_codex_not_fake_claude_vision(tmp_path):
    c,b,calls,p=board(tmp_path)
    image=tmp_path/'page.png';image.write_bytes(b'fixture-image')
    b.review('x',p,('paper_reviewer',),images=[image])
    assert all(k=='codex' for k,*_ in calls)
