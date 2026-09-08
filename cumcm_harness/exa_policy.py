"""Strict local policy, frozen UTC scope and REST request compilation for Exa R2."""
from __future__ import annotations
import calendar
import copy
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import jsonschema
from .common import IntegrityError, Blocked, canonical, digest, read_json
from .exa_contract import BETA, ContractError, validate_request
from .exa_defaults import DEFAULT_POLICY

ADAPTER_VERSION = 'exa-rest-r2/1'
EXTRACTION_VERSION = 'exa-source-snapshot/2'
CAPABILITY_VERSION = 'exa-r2-reference-plus-receipted-probes/1'
STAGES = tuple(DEFAULT_POLICY['budget']['stage_allocations'])


def strict_template(value):
    if isinstance(value, dict):
        return {'type':'object','properties':{k:strict_template(v) for k,v in value.items()},
                'required':list(value),'additionalProperties':False}
    if isinstance(value, list):
        return {'type':'array','const':value}
    return {'const':value}


def integer(lo, hi):
    return {'type':'integer','minimum':lo,'maximum':hi}


def strings(max_items=1200):
    return {'type':'array','maxItems':max_items,'uniqueItems':True,
            'items':{'type':'string','minLength':1,'maxLength':2000}}


POLICY_SCHEMA = strict_template(DEFAULT_POLICY)
P = POLICY_SCHEMA['properties']
P['auth_mode'] = {'enum':['bearer','legacy_x_api_key']}
for section in ('opt_in','fallbacks'):
    for key in P[section]['properties']:P[section]['properties'][key]={'type':'boolean'}
for key,lo,hi in [('default_timeout_seconds',1,45),('deep_timeout_seconds',1,90),
                 ('max_attempts_per_logical_request',1,3),('backoff_base_seconds',0,8),
                 ('backoff_cap_seconds',0,8),('max_total_backoff_seconds_per_request',0,60),
                 ('max_concurrent_requests',1,2),('soft_requests_per_second',1,1),
                 ('circuit_breaker_consecutive_transient_failures',1,3),
                 ('circuit_breaker_cooldown_seconds',1,3600),('max_response_bytes',1024,4000000)]:
    P['http']['properties'][key]=integer(lo,hi)
for key,lo,hi in [('max_total_http_attempts',1,80),('max_queries_per_model_proposal',1,4),
                 ('max_query_rounds_per_phase',1,3),('max_fulltext_urls',1,24),
                 ('max_deep_logical_requests',0,2),('max_search_results_total',1,400),
                 ('max_source_characters_per_model_packet',1000,40000)]:
    P['budget']['properties'][key]=integer(lo,hi)
for key in STAGES:P['budget']['properties']['stage_allocations']['properties'][key]=integer(0,80)
for key in P['cache']['properties']:P['cache']['properties'][key]=integer(0,168 if key.endswith('hours') else 10)
P['cache']['properties']['cross_run_current_docs_ttl_hours']=integer(0,24)
P['cache']['properties']['cross_run_rules_ttl_hours']={'const':0}
SCOPE_FIELDS = {
    'query':{'type':'string','minLength':4,'maxLength':220},
    'profile':{'enum':list(DEFAULT_POLICY['profiles'])},
    'include_domains':strings(),'exclude_domains':strings(),
    'start':{'type':'string','maxLength':40},'end':{'type':'string','minLength':1,'maxLength':40},
    'fetch_urls':strings(24),'expiry':{'type':'string','minLength':1,'maxLength':40},
    'allow_dynamic_fallback':{'type':'boolean'},'allow_publication_fallback':{'type':'boolean'},
    'allow_expanded_fetch':{'type':'boolean'}}
P['authorization_scopes']={'type':'array','maxItems':80,'items':{
    'type':'object','properties':SCOPE_FIELDS,'required':list(SCOPE_FIELDS),'additionalProperties':False}}
# Request templates are deliberately restricted to the supplied profiles.
# Domain narrowing is allowed; scope widening requires a new frozen policy.
for profile in P['profiles']['properties'].values():
    template=profile['properties']['request_template']
    for key in ('includeDomains','excludeDomains'):
        if key not in template['properties']:template['properties'][key]=strings()


def utc(value):
    if not isinstance(value,str):raise IntegrityError('UTC timestamp must be text')
    try:dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise IntegrityError('Invalid UTC timestamp') from None
    if dt.tzinfo is None or dt.utcoffset()!=timedelta(0):raise IntegrityError('Explicit UTC offset/Z required')
    return dt.astimezone(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')


def validate_policy(policy):
    try:
        canonical(policy)  # rejects NaN and infinity before schema comparison
        jsonschema.Draft202012Validator(POLICY_SCHEMA).validate(policy)
    except (ValueError, TypeError, jsonschema.ValidationError) as exc:
        raise IntegrityError('Invalid Exa policy: '+type(exc).__name__) from None
    # JSON Schema's const 0/1 can compare equal to Boolean in Python implementations.
    def no_bool_numeric(value, template):
        if type(template) is int and type(value) is not int:raise IntegrityError('Exa policy integer required')
        if isinstance(template,dict):
            for key in template:no_bool_numeric(value[key],template[key])
    no_bool_numeric(policy,DEFAULT_POLICY)
    if sum(policy['budget']['stage_allocations'].values())>policy['budget']['max_total_http_attempts']:
        raise IntegrityError('Exa stage allocations exceed total attempt budget')
    if policy['http']['backoff_base_seconds']>policy['http']['backoff_cap_seconds']:
        raise IntegrityError('Exa backoff base exceeds cap')
    for scope in policy['authorization_scopes']:
        if scope['start'] and utc(scope['start'])>utc(scope['end']):raise IntegrityError('Reversed authorization dates')
        utc(scope['end']);utc(scope['expiry'])
    for name, profile in policy['profiles'].items():
        body={**profile['request_template'],'query':'generic mathematical method'}
        headers={'Content-Type':'application/json',**({'Exa-Beta':BETA} if name=='discovery_beta' else {})}
        try:validate_request('search',body,headers)
        except (ValueError,TypeError) as exc:raise IntegrityError('Invalid Exa request template: '+name) from None
        for key in ('includeDomains','excludeDomains'):
            for host in body.get(key,[]):
                if not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?',host) or '..' in host:
                    raise IntegrityError('Use plain public domain filters')
    return copy.deepcopy(policy)


def freeze_policy(policy, *, cutoff=None, started_at=None):
    policy=validate_policy(policy)
    started=utc(started_at) if started_at else datetime.now(timezone.utc)
    end=utc(cutoff) if cutoff else started
    if end>started:raise IntegrityError('Research cutoff cannot be in the future')
    return {'schema_version':'exa-frozen/2','run_id':str(uuid.uuid4()),'started_at':iso(started),
            'research_cutoff':iso(end),'policy':policy,'policy_digest':digest(policy),
            'adapter_version':ADAPTER_VERSION,'extraction_version':EXTRACTION_VERSION,
            'capability_version':CAPABILITY_VERSION,'preview_version':BETA}


def validate_snapshot(snapshot):
    expected={'schema_version','run_id','started_at','research_cutoff','policy','policy_digest',
              'adapter_version','extraction_version','capability_version','preview_version'}
    if not isinstance(snapshot,dict) or set(snapshot)!=expected:raise IntegrityError('Invalid frozen Exa policy fields')
    validate_policy(snapshot['policy'])
    if snapshot['schema_version']!='exa-frozen/2' or digest(snapshot['policy'])!=snapshot['policy_digest']:
        raise IntegrityError('Exa frozen policy digest/version mismatch')
    if (snapshot['adapter_version'],snapshot['extraction_version'],snapshot['capability_version'],snapshot['preview_version'])!=(ADAPTER_VERSION,EXTRACTION_VERSION,CAPABILITY_VERSION,BETA):
        raise IntegrityError('Exa parser/capability version changed; create a new workspace')
    try:uuid.UUID(snapshot['run_id'])
    except (ValueError,TypeError):raise IntegrityError('Invalid Exa run identity') from None
    if utc(snapshot['research_cutoff'])>utc(snapshot['started_at']):raise IntegrityError('Future frozen cutoff')
    return snapshot


def date_bounds(cutoff, lane, *, parent_lane=None):
    end=utc(cutoff);start=None
    if lane=='MATCH_PARENT_LANE':
        if parent_lane not in ('NO_LOWER_BOUND','LAST_24_CALENDAR_MONTHS','LAST_180_DAYS'):
            raise IntegrityError('Deep search must name its frozen parent date lane')
        lane=parent_lane
    if lane=='LAST_24_CALENDAR_MONTHS':
        year=end.year-2;start=end.replace(year=year,day=min(end.day,calendar.monthrange(year,end.month)[1]))
    elif lane=='LAST_180_DAYS':start=end-timedelta(days=180)
    elif lane not in ('NO_LOWER_BOUND','EXPLICIT_COMPETITION_YEAR_NOT_RECENCY_ONLY'):
        raise IntegrityError('Unknown Exa date lane')
    return {'endPublishedDate':iso(end),**({'startPublishedDate':iso(start)} if start else {})}


class RequestCompiler:
    def __init__(self, snapshot):
        self.snapshot=validate_snapshot(snapshot);self.policy=snapshot['policy']

    def search(self, query, profile='foundations', *, additional_queries=(), parent_lane=None, competition_year=None):
        if profile not in self.policy['profiles']:raise IntegrityError('Unknown Exa profile')
        if profile=='discovery_beta' and not self.policy['opt_in']['dynamic']:raise Blocked('Dynamic Highlights is explicitly disabled')
        if profile=='deep_escalation' and not self.policy['opt_in']['deep']:raise Blocked('Deep escalation is explicitly disabled')
        spec=self.policy['profiles'][profile];body=copy.deepcopy(spec['request_template'])
        if profile=='official_rules':
            if type(competition_year) is not int or not 2000<=competition_year<=utc(self.snapshot['research_cutoff']).year:
                raise IntegrityError('Explicit competition year required for official rules')
            if str(competition_year) not in query:raise IntegrityError('Official rules query must name its competition year')
        body.update(query=query,**date_bounds(self.snapshot['research_cutoff'],spec['date_policy'],parent_lane=parent_lane))
        if additional_queries:body['additionalQueries']=list(additional_queries)
        headers={'Content-Type':'application/json',**({'Exa-Beta':BETA} if profile=='discovery_beta' else {})}
        validate_request('search',body,headers)
        return {'endpoint':'search','body':body,'public_headers':headers,'profile':profile}

    def contents(self, urls, *, expanded=False, profile='foundations'):
        urls=list(urls)
        if type(expanded) is not bool or not 1<=len(urls)<=self.policy['fetch']['batch_size'] or len(set(urls))!=len(urls):
            raise IntegrityError('Contents requires a unique bounded URL batch and boolean expansion flag')
        f=self.policy['fetch'];body={'urls':list(urls),'text':{'maxCharacters':f['expanded_max_characters'] if expanded else f['text']['maxCharacters']},
                                   'livecrawlTimeout':f['livecrawlTimeout'],'subpages':0}
        if profile=='official_rules':body['maxAgeHours']=f['rules_freshness_max_age_hours']
        elif profile=='implementation':body['maxAgeHours']=f['current_api_license_freshness_max_age_hours']
        headers={'Content-Type':'application/json'};validate_request('contents',body,headers)
        return {'endpoint':'contents','body':body,'public_headers':headers,'profile':profile,'expanded':expanded}


def load_frozen(root):
    path=Path(root)/'exa-policy.json'
    return validate_snapshot(read_json(path)) if path.exists() else None
