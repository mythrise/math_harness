"""Fault-injected R2 network/ledger tests. No real Exa requests or model calls."""
import copy
import json
import random
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
import pytest
from cumcm_harness.common import IntegrityError,Blocked,digest,read_json
from cumcm_harness.store import Store
from cumcm_harness.exa_defaults import DEFAULT_POLICY
from cumcm_harness.exa_policy import freeze_policy
from cumcm_harness.exa_transport import R2ExaClient,HTTPFailure,optional_feature_error
from cumcm_harness.exa_ledger import ExaWait,SharedHTTPGate
from cumcm_harness.exa_authorization import ExaAuthorization

TEXT='Original synthetic evidence, with explicitly limited scope and no scientific claim.'
PAYLOAD={'results':[{'url':'https://example.org/paper','title':'Synthetic source','text':TEXT}],
         'requestId':'synthetic-request','costDollars':{'total':.01}}


class Clock:
    def __init__(self):self.t=1000.;self.delays=[]
    def time(self):return self.t
    def sleep(self,n):self.delays.append(n);self.t+=n


def client(tmp_path, transport=None, *, policy=None, clock=None, live=False, **kwargs):
    policy=copy.deepcopy(policy or DEFAULT_POLICY);clock=clock or Clock()
    snap=freeze_policy(policy,cutoff='2026-09-08T00:00:00Z',started_at='2026-09-08T01:00:00Z')
    return R2ExaClient(Store(tmp_path),snap,transport=None if live else transport or (lambda *a:copy.deepcopy(PAYLOAD)),
        shared_path=tmp_path/'shared.sqlite3',cross_cache=tmp_path/'cross-cache',clock=clock.time,sleep=clock.sleep,rng=random.Random(9),**kwargs)


@pytest.mark.parametrize('failure',[HTTPFailure(429,retry_after='3'),HTTPFailure(503)])
def test_transient_attempts_are_counted_and_retry_after_is_honored(tmp_path,failure):
    calls=[];clock=Clock()
    def transport(*args):
        calls.append(args)
        if len(calls)==1:raise failure
        return copy.deepcopy(PAYLOAD)
    c=client(tmp_path,transport,clock=clock);state=random.getstate()
    a=c.search('generic mathematical method');b=c.search('generic mathematical method')
    assert a==b and len(calls)==2 and c.ledger.summary()['http_attempts_reserved']==2
    assert random.getstate()==state
    if isinstance(failure,HTTPFailure) and failure.code==429:assert 3 in clock.delays


@pytest.mark.parametrize('code',[401,403,400,422])
def test_auth_and_unknown_validation_errors_never_switch_or_loop(tmp_path,code):
    calls=[]
    def fail(*args):calls.append(args);raise HTTPFailure(code)
    c=client(tmp_path,fail)
    with pytest.raises(ExaWait) as e:c.search('generic mathematical method')
    assert len(calls)==1
    if code in (401,403):assert e.value.status=='WAITING_EXA_AUTH'
    assert c.ledger.summary()['unknown_cost_attempts']==1


def test_retry_after_beyond_wait_bound_preserves_wait_state(tmp_path):
    c=client(tmp_path,lambda *a:(_ for _ in ()).throw(HTTPFailure(429,retry_after='120')))
    with pytest.raises(ExaWait,match='RETRY_AFTER'):c.search('generic mathematical method')
    with pytest.raises(ExaWait,match='RETRY_AFTER'):c.search('generic mathematical method')
    assert c.ledger.summary()['http_attempts_reserved']==1


def test_empty_is_cached_and_a_distinct_query_can_proceed(tmp_path):
    calls=[]
    c=client(tmp_path,lambda *a:calls.append(a) or {'results':[]})
    assert c.search('generic missing method')==c.search('generic missing method')==[]
    assert len(calls)==1
    c.search('different theoretical angle');assert len(calls)==2
    assert any(e['kind']=='EXA_EMPTY' for e in c.store.events())


def test_contents_preserves_success_and_retries_only_transient_urls(tmp_path):
    urls=['https://example.org/'+str(i) for i in range(4)];calls=[]
    def transport(endpoint,body,*a):
        calls.append(body['urls'])
        passed=body['urls'][:2] if len(calls)==1 else body['urls']
        failed=body['urls'][2:] if len(calls)==1 else []
        return {'results':[{'url':u,'title':'Fixture','text':TEXT} for u in passed],
                'statuses':[{'id':u,'status':'success'} for u in passed]+[{'id':u,'status':'error','error':{'tag':'CRAWL_TIMEOUT'}} for u in failed],
                'requestId':'request-'+str(len(calls))}
    c=client(tmp_path,transport);origin=c.compiler.search('generic mathematical method')
    sources,statuses=c.contents(urls,origin=origin)
    assert calls==[urls,urls[2:]] and len(sources)==4
    assert {s['request_id'] for s in sources if s['url'] in urls[:2]}=={'request-1'}
    assert c.contents(urls,origin=origin)==(sources,statuses) and len(calls)==2


def test_partial_progress_survives_interruption_without_refetching_success(tmp_path):
    urls=['https://example.org/a','https://example.org/b'];calls=[]
    def transport(endpoint,body,*a):
        calls.append(body['urls'])
        if len(calls)==2:raise KeyboardInterrupt('injected unknown interruption')
        success=body['urls'][:1]
        return {'results':[{'url':u,'title':'Fixture','text':TEXT} for u in success],
            'statuses':[{'id':u,'status':'success'} for u in success]+([{'id':urls[1],'status':'error','error':{'tag':'CRAWL_TIMEOUT'}}] if len(calls)==1 else [])}
    c=client(tmp_path,transport);origin=c.compiler.search('generic mathematical method')
    with pytest.raises(KeyboardInterrupt):c.contents(urls,origin=origin)
    with pytest.raises(ExaWait,match='UNKNOWN_INFLIGHT'):c.contents(urls,origin=origin)
    assert len(calls)==2
    key=c.ledger.summary()['requests'][0]['id'];attempts=c.ledger.reconcile(key,'Synthetic test confirmed the injected process has stopped')
    c.gate.reconcile(c.snapshot['run_id'],attempts)
    sources,_=c.contents(urls,origin=origin)
    assert len(sources)==2 and calls==[urls,[urls[1]],[urls[1]]]


def test_last_atomic_budget_slot_under_two_concurrent_requests(tmp_path):
    policy=copy.deepcopy(DEFAULT_POLICY);policy['budget']['max_total_http_attempts']=1
    policy['budget']['stage_allocations']={k:int(k=='scouting') for k in policy['budget']['stage_allocations']}
    calls=[];c=client(tmp_path,lambda *a:calls.append(a) or copy.deepcopy(PAYLOAD),policy=policy)
    def run(query):
        try:c.search(query);return 'done'
        except ExaWait:return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,['first generic method','second generic method']))
    assert sorted(results)==['blocked','done'] and len(calls)==1
    assert c.ledger.summary()['http_attempts_reserved']==1


def test_single_flight_same_request_is_only_sent_once(tmp_path):
    calls=[]
    def transport(*args):calls.append(args);time.sleep(.05);return copy.deepcopy(PAYLOAD)
    c=client(tmp_path,transport)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:c.search('generic mathematical method'),range(2)))
    assert len(calls)==1 and results[0]==results[1]


def test_circuit_half_open_has_one_owner(tmp_path):
    clock=Clock();gate=SharedHTTPGate(tmp_path/'gate.sqlite3',clock=clock.time,sleep=clock.sleep);p=DEFAULT_POLICY
    for i in range(3):gate.release(gate.acquire('fixture','run',p),p,outcome='transient')
    with pytest.raises(ExaWait,match='CIRCUIT_OPEN'):gate.acquire('fixture','run',p)
    clock.t+=61;lease=gate.acquire('fixture','run',p)
    with pytest.raises(ExaWait,match='HALF_OPEN'):gate.acquire('fixture','other-run',p)
    gate.release(lease,p,outcome='success')
    other=gate.acquire('fixture','other-run',p);gate.release(other,p)


def test_publication_fallback_preserves_query_domains_dates_and_budget(tmp_path):
    calls=[]
    def transport(endpoint,body,*a):
        calls.append(copy.deepcopy(body))
        if len(calls)==1:raise HTTPFailure(400,reason='UNSUPPORTED_PUBLICATION_CATEGORY')
        return copy.deepcopy(PAYLOAD)
    p=copy.deepcopy(DEFAULT_POLICY);p['profiles']['foundations']['request_template']['includeDomains']=['example.org']
    c=client(tmp_path,transport,policy=p);c.search('generic mathematical method')
    assert len(calls)==2 and 'category' not in calls[1]
    for field in ('query','includeDomains','endPublishedDate'):assert calls[0][field]==calls[1][field]
    assert optional_feature_error({'error':'Publication category is not supported'})=='UNSUPPORTED_PUBLICATION_CATEGORY'
    assert optional_feature_error({'error':'Invalid parameter'}) is None


def test_dynamic_probe_is_opt_in_and_fixture_cannot_certify_live_capability(tmp_path):
    p=copy.deepcopy(DEFAULT_POLICY);p['opt_in']['dynamic']=True
    c=client(tmp_path,policy=p)
    with pytest.raises(ExaWait,match='capability probe'):c.search('generic mathematical method',profile='discovery_beta')
    cap=c.probe_dynamic('generic mathematical method');assert cap['live'] is False
    with pytest.raises(ExaWait,match='capability probe'):c.search('generic mathematical method',profile='discovery_beta')
    assert c.ledger.summary()['http_attempts_reserved']==2


def test_dynamic_explicit_fallback_keeps_beta_on_retry_and_removes_it_on_stable(tmp_path):
    p=copy.deepcopy(DEFAULT_POLICY);p['opt_in']['dynamic']=True;p['fallbacks']['dynamic']=True;calls=[]
    def transport(endpoint,body,headers,*a):
        calls.append((copy.deepcopy(body),dict(headers)))
        if len(calls)==1:raise HTTPFailure(503)
        if len(calls)==2:raise HTTPFailure(400,reason='UNSUPPORTED_DYNAMIC_HIGHLIGHTS')
        return copy.deepcopy(PAYLOAD)
    c=client(tmp_path,transport,policy=p);cap=c.probe_dynamic('generic mathematical method')
    assert len(calls)==3 and calls[0][1]==calls[1][1] and 'Exa-Beta' in calls[0][1]
    assert 'Exa-Beta' not in calls[2][1] and calls[2][0]['contents']['highlights']=={'maxCharacters':2000}
    assert cap['status']=='FALLBACK_OR_MISSING_EXCERPTS_NOT_DYNAMIC_SUPPORT'


@pytest.mark.parametrize('mode,expected',[('bearer','Authorization'),('legacy_x_api_key','X-api-key')])
def test_real_http_boundary_injects_only_selected_auth_and_never_persists_it(tmp_path,monkeypatch,mode,expected):
    secret='synthetic-exa-key-not-real';monkeypatch.setenv('EXA_API_KEY',secret);captured=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,n):return json.dumps(PAYLOAD).encode()
    class Opener:
        def open(self,request,timeout):captured.append(request);return Response()
    monkeypatch.setattr('urllib.request.build_opener',lambda *a:Opener())
    p=copy.deepcopy(DEFAULT_POLICY);p['auth_mode']=mode;c=client(tmp_path,policy=p,live=True)
    c.search('generic mathematical method')
    assert captured[0].get_header(expected)==('Bearer '+secret if mode=='bearer' else secret)
    assert captured[0].get_header('X-api-key' if mode=='bearer' else 'Authorization') is None
    assert all(secret.encode() not in path.read_bytes() for path in tmp_path.rglob('*') if path.is_file())


def test_missing_cost_is_unknown_and_generated_output_is_preserved_for_auto(tmp_path):
    payload=copy.deepcopy(PAYLOAD);payload.pop('costDollars');payload['output']={'content':{'limitations':['navigation only']},'grounding':[{'confidence':'high'}]}
    c=client(tmp_path,lambda *a:payload);sources=c.search('generic mathematical method')
    assert c.ledger.summary()['unknown_cost_attempts']==1
    assert sources[0]['provider_output']==payload['output'] and 'navigation only' not in sources[0]['text']
