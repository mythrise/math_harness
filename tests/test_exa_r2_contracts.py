"""R2 policy, source and outbound-scope contracts; no network/model execution."""
import copy
import json
from pathlib import Path
from datetime import datetime,timezone
import pytest
from cumcm_harness.common import IntegrityError,Blocked,read_json,write_json,digest,ROOT
from cumcm_harness.exa_defaults import DEFAULT_POLICY
from cumcm_harness.exa_policy import validate_policy,freeze_policy,RequestCompiler,date_bounds
from cumcm_harness.exa_contract import validate_request,ContractError,BETA
from cumcm_harness.exa_evidence import normalize_sources,source_packet,locate_audit,merge_sources
from cumcm_harness.exa_authorization import ExaAuthorization,checked_url
from cumcm_harness.intake import create_workspace,verify_inputs
from cumcm_harness.controller import DEFAULT_CONFIG,validate_config


def snapshot(policy=None):
    return freeze_policy(copy.deepcopy(policy or DEFAULT_POLICY),cutoff='2026-09-08T00:00:00Z',started_at='2026-09-08T01:00:00Z')


def test_compatible_overlay_only_changes_exa_limits_and_preserves_models():
    old=read_json(ROOT/'configs/exa-resilient.json');new=read_json(ROOT/'configs/exa-modeling-compatible.json')
    assert new=={**old,'exa_max_requests':80,'exa_results_per_query':6,'exa_timeout':45}
    validate_config({**DEFAULT_CONFIG,**new})


@pytest.mark.parametrize('path,value',[
    (['unknown'],1),(['auth_mode'],'both'),(['http','max_concurrent_requests'],True),
    (['http','default_timeout_seconds'],float('inf')),(['budget','max_total_http_attempts'],81),
    (['http','backoff_base_seconds'],-1),(['opt_in','dynamic'],'yes'),
    (['profiles','foundations','request_template','contents','highlights','maxCharacters'],True),
    (['fetch','subpages'],False),(['profiles','foundations','request_template','useAutoprompt'],True)])
def test_strict_policy_rejects_bad_values(path,value):
    policy=copy.deepcopy(DEFAULT_POLICY);node=policy
    for key in path[:-1]:node=node[key]
    node[path[-1]]=value
    with pytest.raises(IntegrityError):validate_policy(policy)


def test_utc_calendar_routes_and_fixed_anchor():
    assert date_bounds('2024-02-29T12:00:00Z','LAST_24_CALENDAR_MONTHS')['startPublishedDate']=='2022-02-28T12:00:00Z'
    assert date_bounds('2026-08-31T00:00:00Z','LAST_24_CALENDAR_MONTHS')['startPublishedDate']=='2024-08-31T00:00:00Z'
    assert date_bounds('2024-08-27T00:00:00Z','LAST_180_DAYS')['startPublishedDate']=='2024-02-29T00:00:00Z'
    assert 'startPublishedDate' not in date_bounds('2026-09-08T00:00:00Z','NO_LOWER_BOUND')
    with pytest.raises(IntegrityError):date_bounds('2026-09-08','NO_LOWER_BOUND')


def test_new_sidecar_is_frozen_and_cannot_be_added_to_legacy_workspace(tmp_path):
    problem=tmp_path/'problem.md';problem.write_text('Synthetic Exa configuration fixture')
    data=tmp_path/'data';data.mkdir();(data/'input.txt').write_text('fixture data')
    config={**DEFAULT_CONFIG,**read_json(ROOT/'configs/exa-modeling-compatible.json')}
    old=tmp_path/'old';create_workspace(old,problem,data,config);verify_inputs(old)
    new=tmp_path/'new';create_workspace(new,problem,data,config,exa_policy=DEFAULT_POLICY,research_cutoff='2026-09-08T00:00:00Z')
    original=read_json(new/'exa-policy.json');verify_inputs(new)
    write_json(old/'exa-policy.json',original)
    with pytest.raises(IntegrityError):verify_inputs(old)
    changed=copy.deepcopy(original);changed['research_cutoff']='2026-09-07T00:00:00Z';write_json(new/'exa-policy.json',changed)
    with pytest.raises(IntegrityError):verify_inputs(new)


@pytest.mark.parametrize('mutate',[
    lambda r:r['body'].update(text=True),
    lambda r:r['body']['contents']['highlights'].update(dynamic=True),
    lambda r:r['public_headers'].update(Authorization='Bearer fake-fixture'),
    lambda r:r['body']['contents'].update(livecrawl='always'),
    lambda r:r['body'].update(additionalQueries=['alternative mathematical method']),
    lambda r:r['body'].update(numResults=True),
    lambda r:r['body']['contents']['highlights'].update(max_characters=1000),
    lambda r:r['body'].update(stream=True)])
def test_rest_shape_rejects_unsupported_and_cross_layer_fields(mutate):
    r=RequestCompiler(snapshot()).search('generic mathematical method');mutate(r)
    with pytest.raises((ContractError,IntegrityError)):validate_request(r['endpoint'],r['body'],r['public_headers'])


def test_dynamic_and_deep_remain_off_by_default():
    c=RequestCompiler(snapshot())
    with pytest.raises(Blocked):c.search('generic mathematical method','discovery_beta')
    with pytest.raises(Blocked):c.search('generic mathematical method','deep_escalation',parent_lane='NO_LOWER_BOUND')
    p=copy.deepcopy(DEFAULT_POLICY);p['opt_in']['dynamic']=True
    request=RequestCompiler(snapshot(p)).search('generic mathematical method','discovery_beta')
    assert request['public_headers']['Exa-Beta']==BETA
    assert request['body']['contents']['highlights']=={'dynamic':True}


def test_long_text_and_generated_outputs_have_separate_provenance():
    snap=snapshot();request=RequestCompiler(snap).contents(['https://example.org/paper'])
    text='A'*12000+'The original late passage is retained.'+'B'*12000
    payload={'results':[{'url':'https://example.org/paper','title':'Synthetic paper','text':text,
                         'highlights':['Extractive highlight'],'summary':'Generated invented summary'}],
             'output':{'content':{'limitations':['Generated synthesis']},'grounding':[{'confidence':'high'}]}}
    source=normalize_sources(payload,request,snap,live=False)[0]
    assert len(source['text'])==24000 and 'original late passage' in source['text']
    assert source['coverage']['limit_hit'] and not source['coverage']['full_source_read']
    assert source['generated_summary']=='Generated invented summary'
    assert source['provider_output']==payload['output']
    assert source['temporal_status']=='UNKNOWN_DATE'
    packet=source_packet([source]*3)
    assert sum(len(s['text']) for s in packet)<=40000
    assert any(s['packet_coverage']['truncated'] for s in packet)


def test_missing_highlight_future_dates_and_arxiv_mirrors_remain_visible():
    snap=snapshot();request=RequestCompiler(snap).search('generic mathematical method')
    payload={'results':[{'url':'https://arxiv.org/abs/2401.12345v1','title':'Synthetic paper'},
        {'url':'https://arxiv.org/pdf/2401.12345v2','title':'Synthetic paper','text':'different version text','publishedDate':'2027-01-01'}]}
    sources=normalize_sources(payload,request,snap,live=False)
    assert len(sources)==2 and sources[0]['source_coverage_state']=='RETRIEVED_NO_EXCERPT'
    assert sources[0]['work_id']==sources[1]['work_id'] and sources[0]['snapshot_id']!=sources[1]['snapshot_id']
    assert sources[1]['temporal_status']=='KNOWN_FUTURE_EXCLUDED'
    assert len(merge_sources(sources[:1],sources[1:]))==2


def test_generated_summary_and_stale_quote_cannot_enter_original_text_audit():
    snap=snapshot();request=RequestCompiler(snap).contents(['https://example.org/paper'])
    sources=normalize_sources({'results':[{'url':'https://example.org/paper','title':'Fixture','text':'Original source passage with finite scope.'}]},request,snap,live=False)
    s=sources[0];cards={'hypotheses':[{'id':'H1','assumption_index':0,'statement':'Finite scope','kind':'structural',
        'falsification_test':'check finite scope','acceptance_rule':'correct','failure_action':'revise'}]}
    ref={'source_id':s['id'],'snapshot_id':s['snapshot_id'],'quote':s['text'],'quote_start':0,'quote_end':len(s['text']),'relation':'scope_limit'}
    audit={'decision':'ACCEPT_FOR_TESTING','checks':[{'hypothesis_id':'H1','judgment':'explicit_simplification','rationale':'Synthetic contract',
        'evidence':[ref],'requires_execution':False,'required_test':'not_applicable'}],'limitations':['Fixture only'],'citation_ids':[s['id']]}
    assert locate_audit(cards,audit,sources)[1][0]['quote_start']==0
    stale=copy.deepcopy(audit);stale['checks'][0]['evidence'][0]['snapshot_id']='f'*64
    with pytest.raises(IntegrityError):locate_audit(cards,stale,sources)
    invented=copy.deepcopy(audit);invented['checks'][0]['evidence'][0]['quote']='Generated invented statement'
    with pytest.raises(IntegrityError):locate_audit(cards,invented,sources)


def test_privacy_checks_every_outbound_text_field(tmp_path):
    snap=snapshot();auth=ExaAuthorization(tmp_path,snap,problem='Sensitive problem paragraph that must remain entirely inside the local workspace.',
        profiles=[{'name':'private-data.csv','preview':[['secret-row-alpha','secret-row-beta']]}],identities=['PrivateTeam'])
    request=RequestCompiler(snap).search('generic mathematical method')
    request['body']['contents']['highlights']['query']='PrivateTeam modeling method'
    with pytest.raises(IntegrityError):auth.check(request)
    request['body']['contents']['highlights']['query']='secret-row-alpha secret-row-beta regression'
    with pytest.raises(IntegrityError):auth.check(request)
    request['body']['contents']['highlights']['query']='Sensitive problem paragraph that must remain entirely inside the local workspace.'
    with pytest.raises(IntegrityError):auth.check(request)


def test_public_url_dns_and_credentials_rejected():
    resolver=lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))]
    with pytest.raises(IntegrityError):checked_url('https://public-looking.example',resolve=True,resolver=resolver)
    for url in ('https://example.org?Authorization=secret','http://127.1/a','https://example.org:8080/a'):
        with pytest.raises((IntegrityError,Blocked)):checked_url(url,resolve=True,resolver=resolver)
