"""Exa transport contracts, credential isolation and evidence controls."""
import copy,json,urllib.error
from types import SimpleNamespace
import pytest
from cumcm_harness.common import Blocked,IntegrityError,digest,read_json,write_json
from cumcm_harness.literature import ExaClient,ResearchUnavailable,validate_query,check_hypotheses,check_audit,public_url,LiteratureWorkflow
from cumcm_harness.process import clean_env

TEXT='A sequence dependent setup time is part of this synthetic evidence fixture. No scientific correctness claim.'
PAYLOAD={'results':[{'url':'https://example.org/test-paper','title':'Synthetic evidence contract fixture','text':TEXT}]}

def data(tmp_path):
    source=ExaClient(tmp_path,transport=lambda *a:copy.deepcopy(PAYLOAD)).search('generic optimization')
    cards={'hypotheses':[{'id':'H1','assumption_index':0,'statement':'Times fixed within this synthetic scenario','kind':'simplification','falsification_test':'perturb times','acceptance_rule':'explicit scope and finite response','failure_action':'revise model'}]}
    audit={'decision':'ACCEPT_FOR_TESTING','checks':[{'hypothesis_id':'H1','judgment':'explicit_simplification','rationale':'Not proven empirically','evidence':[{'source_id':source[0]['id'],'quote':'A sequence dependent setup time','relation':'scope_limit'}],'requires_execution':True,'required_test':'hypothesis_H1'}], 'limitations':['Search is not a statistical test'], 'citation_ids':[source[0]['id']]}
    return source,cards,audit


def test_search_payload_cache_and_provenance(tmp_path):
    calls=[]
    client=ExaClient(tmp_path,transport=lambda ep,body:calls.append((ep,body)) or copy.deepcopy(PAYLOAD))
    a=client.search('generic scheduling assumptions');b=client.search('generic scheduling assumptions')
    assert a==b and len(calls)==1 and a[0]['status']=='RETRIEVED_NOT_VALIDATED'
    assert calls[0][1]['contents']['text']['maxCharacters']==10000
    assert a[0]['retrieval']=='FIXTURE_EXA_TRANSPORT'
    p=next(tmp_path.glob('*.json'));v=read_json(p);v['response']['results'][0]['text']='tampered';write_json(p,v)
    with pytest.raises(IntegrityError):client.search('generic scheduling assumptions')

@pytest.mark.parametrize('value',[{'results':[]},{'results':None},{'results':[{'url':'https://example.org','text':'short'}]}, {'results':PAYLOAD['results'],'statuses':[{'status':'error'}]}])
def test_empty_partial_or_malformed_exa_blocks(tmp_path,value):
    with pytest.raises(ResearchUnavailable):ExaClient(tmp_path,transport=lambda *a:value).search('generic method')
    assert not list(tmp_path.glob('*.json'))


def test_unusable_http_success_can_be_retried_without_removing_cache(tmp_path):
    responses=iter([{'results':[{'url':'https://example.org','text':'short'}]}, copy.deepcopy(PAYLOAD)])
    client=ExaClient(tmp_path,transport=lambda *a:next(responses))
    with pytest.raises(ResearchUnavailable):client.search('generic method')
    assert client.search('generic method')[0]['text']==TEXT


@pytest.mark.parametrize('change',[{'statuses':None},{'statuses':[None]},
    {'results':[{'url':'https://example.org','highlights':[{}]}]}])
def test_bad_exa_response_shapes_are_recoverable(tmp_path,change):
    with pytest.raises(ResearchUnavailable):
        ExaClient(tmp_path,transport=lambda *a:{**PAYLOAD,**change}).search('generic method')
    assert not list(tmp_path.glob('*.json'))

@pytest.mark.parametrize('url',['file:///etc/passwd','http://127.0.0.1/a','http://169.254.169.254','https://localhost/x','https://user:pass@example.org','https://example.org?api_key=secret','http://localhost./x','http://[broken','https://example.org:invalid',None])
def test_private_and_credential_urls_refused(url):
    with pytest.raises(IntegrityError):public_url(url)

@pytest.mark.parametrize('query',['mail test@example.org','method /etc/secret','identifier 123456789','api_key=secret'])
def test_sensitive_queries_refused(query):
    with pytest.raises(IntegrityError):validate_query(query)


def test_contest_exact_allowlist_and_key_not_in_process_env(monkeypatch):
    monkeypatch.setenv('EXA_API_KEY','not-real-test-key')
    with pytest.raises(Blocked):validate_query('generic method',approved=[])
    assert validate_query('generic method',approved=['generic method'])=='generic method'
    with pytest.raises(IntegrityError):validate_query('method not-real-test-key')
    assert 'EXA_API_KEY' not in clean_env(provider=True) and 'EXA_API_KEY' not in clean_env()


def test_every_assumption_exactly_once(tmp_path):
    _,cards,_=data(tmp_path)
    plan={'assumptions':[cards['hypotheses'][0]['statement']]}
    check_hypotheses(plan,cards)
    cards['hypotheses'][0]['statement']='changed assumption'
    with pytest.raises(IntegrityError):check_hypotheses(plan,cards)

@pytest.mark.parametrize('mutation',['fake_quote','unknown_source','tamper_text','missing_hypothesis','unsupported','missing_test','fake_citation','counterexample'])
def test_hypothesis_evidence_gate(tmp_path,mutation):
    s,c,a=data(tmp_path)
    if mutation=='fake_quote':a['checks'][0]['evidence'][0]['quote']='This sentence is not in the source'
    if mutation=='unknown_source':a['checks'][0]['evidence'][0]['source_id']='unknown'
    if mutation=='tamper_text':s[0]['text']='changed'
    if mutation=='missing_hypothesis':a['checks'].append(copy.deepcopy(a['checks'][0]))
    if mutation=='unsupported':a['checks'][0]['judgment']='supported_with_scope'
    if mutation=='missing_test':a['checks'][0]['requires_execution']=False
    if mutation=='fake_citation':a['citation_ids']=[]
    if mutation=='counterexample':a['checks'][0]['judgment']='contradicted'
    with pytest.raises((Blocked,IntegrityError)):check_audit(c,a,s)


def test_missing_actual_hypothesis_diagnostic_blocks(tmp_path):
    s,c,a=data(tmp_path);tests=check_audit(c,a,s)
    wf=LiteratureWorkflow.__new__(LiteratureWorkflow);wf.c=SimpleNamespace(root=tmp_path)
    wf.accepted={'required_tests':tests,'plan_digest':'a'*64}
    with pytest.raises(Blocked):wf.require_tests({'cases':[]})
    wf.require_tests({'cases':[{'name':'hypothesis_H1','passed':True,'detail':'fixture numerical diagnostic'}]})
    assert read_json(tmp_path/'literature/execution.json')['status']=='DECLARED_DIAGNOSTICS_PASSED_NOT_PROOF'


def test_exa_auth_header_fixed_endpoint_and_no_secret_cache(tmp_path,monkeypatch):
    captured=[];key='not-real-secret-fixture-value'
    monkeypatch.setenv('EXA_API_KEY',key)
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,n):return json.dumps(PAYLOAD).encode()
    class Opener:
        def open(self,request,timeout):captured.append(request);return Response()
    monkeypatch.setattr('urllib.request.build_opener',lambda *a:Opener())
    ExaClient(tmp_path).search('generic method')
    assert captured[0].full_url=='https://api.exa.ai/search'
    assert captured[0].get_header('X-api-key')==key
    assert all(key not in f.read_text() for f in tmp_path.glob('*.json'))


def test_429_retries_and_auth_error_has_no_body_leak(tmp_path,monkeypatch):
    monkeypatch.setenv('EXA_API_KEY','not-real-test-key');calls=[]
    class Opener:
        def open(self,*args,**kw):calls.append(1);raise urllib.error.HTTPError('https://api.exa.ai',429,'SECRET_BODY',{},None)
    monkeypatch.setattr('urllib.request.build_opener',lambda *a:Opener())
    with pytest.raises(ResearchUnavailable,match='EXA_HTTP_429') as e:ExaClient(tmp_path,sleep=lambda _:None).search('generic method')
    assert len(calls)==2 and 'SECRET_BODY' not in str(e.value)
    assert not list(tmp_path.glob('*.json'))
