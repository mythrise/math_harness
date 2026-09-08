"""Integration boundaries using synthetic requests, clocks and test-only attestations."""
import copy
from datetime import datetime,timezone
import pytest
from cumcm_harness.common import IntegrityError,Blocked,digest
from cumcm_harness import approval
from cumcm_harness.exa_defaults import DEFAULT_POLICY
from cumcm_harness.exa_policy import freeze_policy,RequestCompiler
from cumcm_harness.exa_authorization import ExaAuthorization
from cumcm_harness.exa_evidence import normalize_sources,merge_sources
from cumcm_harness.exa_transport import R2ExaClient
from cumcm_harness.exa_ledger import ExaWait
from cumcm_harness.store import Store
from test_exa_r2_transport import client,Clock,PAYLOAD


@pytest.mark.parametrize('change',[
    lambda r:r['body'].update(endPublishedDate='2027-01-01T00:00:00Z'),
    lambda r:r['body'].update(includeDomains=['different.example']),
    lambda r:r['body'].update(numResults=100),
    lambda r:r['body']['contents']['highlights'].update(maxCharacters=9999),
    lambda r:r['body'].update(category='news')])
def test_direct_request_cannot_widen_frozen_profile(tmp_path,change):
    c=client(tmp_path);request=c.compiler.search('generic mathematical method');change(request)
    with pytest.raises(IntegrityError):c.execute(request)
    assert c.ledger.summary()['http_attempts_reserved']==0


def test_contents_batch_and_expansion_are_strict(tmp_path):
    c=client(tmp_path)
    for urls,expanded in [([],False),(['https://example.org/'+str(i) for i in range(5)],False),
                          (['https://example.org/a']*2,False),(['https://example.org/a'],1)]:
        with pytest.raises(IntegrityError):c.compiler.contents(urls,expanded=expanded)


def test_cross_run_ttl_replay_and_changed_cutoff(tmp_path):
    clock=Clock();calls=[]
    def make(name):
        c=client(tmp_path/name,lambda *a:calls.append(a) or copy.deepcopy(PAYLOAD),clock=clock)
        c.cross_cache=tmp_path/'cache';return c
    a=make('a');a.search('generic mathematical method')
    b=make('b');b.search('generic mathematical method');assert len(calls)==1
    clock.t+=168*3600+1
    a.search('generic mathematical method');assert len(calls)==1 # immutable same-run replay
    make('c').search('generic mathematical method');assert len(calls)==2
    d=make('d');d.snapshot['research_cutoff']='2026-09-07T00:00:00Z'
    d.search('generic mathematical method');assert len(calls)==3


@pytest.mark.parametrize('profile,expiry',[('official_rules',0),('implementation',24*3600)])
def test_current_rules_and_api_docs_refresh_across_runs(tmp_path,profile,expiry):
    policy=copy.deepcopy(DEFAULT_POLICY)
    policy['profiles']['implementation']['request_template']['includeDomains']=['example.org']
    calls=[];clock=Clock()
    def run(name):
        c=client(tmp_path/name,lambda *a:calls.append(a) or copy.deepcopy(PAYLOAD),clock=clock,policy=policy)
        c.cross_cache=tmp_path/'cache'
        c.search('2026 mathematical modeling rules' if profile=='official_rules' else 'official optimization documentation',
                 profile=profile,**({'competition_year':2026} if profile=='official_rules' else {}))
        return c
    a=run('a');clock.t+=expiry+1;run('b');assert len(calls)==2


def test_cross_response_versions_are_one_work_with_conflict(tmp_path):
    c=client(tmp_path);r=c.compiler.search('generic mathematical method')
    def sources(version,text):
        return normalize_sources({'results':[{'url':'https://arxiv.org/abs/2401.12345v'+version,
            'title':'Synthetic work','text':text}]},r,c.snapshot,live=False)
    merged=merge_sources(sources('1','Original limited text'),sources('2','Changed limited text'))
    assert all(s['version_or_content_conflict'] and s['independent_source_count']==1 and len(s['same_work_snapshots'])==2 for s in merged)


def test_deep_requires_two_completed_auto_queries_and_keeps_negative(tmp_path):
    p=copy.deepcopy(DEFAULT_POLICY);p['opt_in']['deep']=True;c=client(tmp_path,policy=p)
    negative={'decision':'REVISE','checks':[{'judgment':'contradicted'}]}
    kwargs={'profile':'deep_escalation','parent_lane':'NO_LOWER_BOUND','stage':'repair_reserve'}
    with pytest.raises(Blocked):c.search('unresolved mathematical conflict',**kwargs)
    with pytest.raises(IntegrityError):c.search('unresolved mathematical conflict',conflict_audit=negative,
            prior_query_digests=[digest('first generic method'),digest('second generic method')],**kwargs)
    c.search('first generic method');c.search('second generic method')
    prior=[digest('first generic method'),digest('second generic method')]
    with pytest.raises(IntegrityError):c.search('unresolved mathematical conflict',conflict_audit={'decision':'ACCEPT_FOR_TESTING'},prior_query_digests=prior,**kwargs)
    for query in ('first unresolved conflict','second unresolved conflict'):
        c.search(query,conflict_audit=negative,prior_query_digests=prior,**kwargs)
    with pytest.raises(ExaWait):c.search('third unresolved conflict',conflict_audit=negative,prior_query_digests=prior,**kwargs)
    assert negative['decision']=='REVISE' and c.ledger.summary()['http_attempts_reserved']==4


def test_replay_resource_budget_cannot_be_bypassed(tmp_path):
    p=copy.deepcopy(DEFAULT_POLICY);p['budget']['max_search_results_total']=1;c=client(tmp_path,policy=p)
    c.search('first generic method')
    with pytest.raises(ExaWait):c.search('second generic method')
    with pytest.raises(ExaWait):c.search('second generic method')
    assert c.ledger.summary()['http_attempts_reserved']==2


def test_crash_after_response_before_complete_resumes_without_http(tmp_path,monkeypatch):
    calls=[];c=client(tmp_path,lambda *a:calls.append(a) or copy.deepcopy(PAYLOAD))
    original=c.ledger.complete
    def crash(*a):raise KeyboardInterrupt('Synthetic crash after durable response')
    monkeypatch.setattr(c.ledger,'complete',crash)
    with pytest.raises(KeyboardInterrupt):c.search('generic mathematical method')
    monkeypatch.setattr(c.ledger,'complete',original)
    assert c.search('generic mathematical method') and len(calls)==1


def test_contest_exact_signed_scope_expiry_and_no_key(tmp_path,monkeypatch):
    monkeypatch.delenv('CUMCM_OPERATOR_KEY',raising=False)
    p=copy.deepcopy(DEFAULT_POLICY);query='generic mathematical method'
    p['authorization_scopes']=[{'query':query,'profile':'foundations','include_domains':[],
        'exclude_domains':[],'start':'','end':'2026-09-08T00:00:00Z',
        'fetch_urls':['https://example.org/paper'],'expiry':'2026-09-09T00:00:00Z',
        'allow_dynamic_fallback':False,'allow_publication_fallback':False,'allow_expanded_fetch':False}]
    snap=freeze_policy(p,cutoff='2026-09-08T00:00:00Z',started_at='2026-09-08T01:00:00Z');compiler=RequestCompiler(snap)
    auth=ExaAuthorization(tmp_path,snap,mode='contest',approved_queries=[query],now=lambda:datetime(2026,9,8,12,tzinfo=timezone.utc))
    request=compiler.search(query)
    with pytest.raises(Blocked,match='HUMAN_REVIEW_REQUIRED'):auth.check(request)
    # Existing attestation implementation is tested with a synthetic key and a
    # temporary fixture directory only. This does not approve a user workspace.
    from cumcm_harness.common import read_json
    pending=read_json(tmp_path/'approvals/research.pending.json')
    review={'target_digest':pending['target_digest'],'team_led_core_modeling':True,
        'statement':'SYNTHETIC TEST ATTESTATION ONLY','items':[{'id':'scope:0','adopted':True,
        'modification':'Synthetic fixture','verification':'Synthetic test verification'}]}
    key='synthetic-test-key-00000000000000000000';approval.sign(tmp_path,'research',review,key)
    with pytest.raises(Blocked):auth.check(request)
    monkeypatch.setenv('CUMCM_OPERATOR_KEY',key);auth.check(request,for_network=True)
    with pytest.raises(Blocked):auth.check(request,origin=request,fallback='publication')
    with pytest.raises(Blocked):auth.check(compiler.contents(['https://example.org/other']),origin=request)
    with pytest.raises(Blocked):auth.check(compiler.contents(['https://example.org/paper'],expanded=True),origin=request)
    altered=copy.deepcopy(request);altered['body']['endPublishedDate']='2026-09-07T00:00:00Z'
    with pytest.raises(Blocked):auth.check(altered)
    auth.now=lambda:datetime(2026,9,10,tzinfo=timezone.utc)
    auth.check(request)
    with pytest.raises(Blocked,match='expired'):auth.check(request,for_network=True)


def test_provider_credential_echo_is_rejected_before_persistence(tmp_path,monkeypatch):
    secret='synthetic-echo-key-never-real';monkeypatch.setenv('EXA_API_KEY',secret)
    value=copy.deepcopy(PAYLOAD);value['results'][0]['text']=secret
    c=client(tmp_path,lambda *a:value)
    with pytest.raises(IntegrityError):c.search('generic mathematical method')
    assert all(secret.encode() not in path.read_bytes() for path in tmp_path.rglob('*') if path.is_file())
