"""Controller-managed Exa REST with durable attempts, bounded retries and snapshots."""
from __future__ import annotations
import copy
import email.utils
import json
import math
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from .common import ROOT, Blocked, IntegrityError, canonical, digest, read_json, write_json
from .credentials import get_exa_api_key
from .literature import NoRedirect
from .exa_contract import BETA, validate_request, dynamic_fallback
from .exa_policy import RequestCompiler, date_bounds
from .exa_ledger import ExaLedger, ExaWait, SharedHTTPGate
from .exa_authorization import ExaAuthorization, checked_url
from .exa_evidence import normalize_sources

TRANSIENT = {408,429,500,502,503,504}
TRANSIENT_SOURCE = {'CRAWL_TIMEOUT','CRAWL_LIVECRAWL_TIMEOUT','CRAWL_UNKNOWN_ERROR'}


def response_metadata(payload):
    cost=payload.get('costDollars',{}).get('total') if isinstance(payload.get('costDollars'),dict) else None
    known=type(cost) in (int,float) and math.isfinite(cost) and cost>=0
    request_id=payload.get('requestId')
    return {'provider_request_id':request_id if isinstance(request_id,str) else 'UNKNOWN',
            'cost_dollars':cost if known else 'UNKNOWN'}


class HTTPFailure(Exception):
    def __init__(self, code, *, reason=None, retry_after=None, metadata=None):
        super().__init__('EXA_HTTP_'+str(code));self.code=code;self.reason=reason
        self.retry_after=retry_after;self.metadata=metadata or {'provider_request_id':'UNKNOWN','cost_dollars':'UNKNOWN'}


def optional_feature_error(payload):
    """Only explicit feature rejection may cause the frozen, authorized fallback."""
    raw=payload.get('error',payload.get('message','')) if isinstance(payload,dict) else ''
    if isinstance(raw,dict):raw=' '.join(str(raw.get(k,'')) for k in ('code','message','type'))
    code=str(payload.get('code','')) if isinstance(payload,dict) else ''
    text=(str(raw)+' '+code).lower()
    unsupported=bool(re.search(r'unsupported|not supported|not enabled|not available for (?:this|your) (?:account|api)',text))
    if unsupported and ('dynamic_highlights' in text or 'dynamic highlights' in text):return 'UNSUPPORTED_DYNAMIC_HIGHLIGHTS'
    if unsupported and 'publication' in text and 'categor' in text:return 'UNSUPPORTED_PUBLICATION_CATEGORY'
    return None


def retry_seconds(value, now):
    if value is None:return 0
    try:return max(0,float(value))
    except (ValueError,TypeError):
        try:return max(0,email.utils.parsedate_to_datetime(value).timestamp()-now)
        except (ValueError,TypeError,OverflowError):return 0


class R2ExaClient:
    def __init__(self, store, snapshot, *, transport=None, authorization=None, deadline=None,
                 max_attempts=None, timeout=None, shared_path=None, cross_cache=None,
                 sleep=time.sleep, clock=time.time, rng=None):
        self.store=store;self.snapshot=snapshot;self.compiler=RequestCompiler(snapshot);self.policy=self.compiler.policy
        self.live=transport is None;self.transport=transport or self._http
        self.sleep=sleep;self.clock=clock;self.rng=rng or random.SystemRandom();self.deadline=deadline or (lambda:None)
        self.timeout=min(timeout or 45,self.policy['http']['default_timeout_seconds'])
        self.ledger=ExaLedger(store,self.policy,max_attempts=max_attempts)
        # Fixtures use workspace-local limits/cache. They cannot populate the
        # credential-shared live cache or certify a live feature probe.
        default_shared=ROOT/'.runtime/exa/shared.sqlite3' if self.live else store.root/'literature/fixture-shared.sqlite3'
        self.gate=SharedHTTPGate(shared_path or default_shared,clock=clock,sleep=sleep)
        self.cross_cache=Path(cross_cache) if cross_cache else ROOT/'.runtime/exa/research-cache' if self.live else None
        self.authorization=authorization or ExaAuthorization(store.root,snapshot,live=self.live)
        self.credential_source='ENVIRONMENT' if os.getenv('EXA_API_KEY') else 'LOCAL_PRIVATE_FILE'
        if not self.live:self.credential_source='FIXTURE'

    def _http(self, endpoint, body, public_headers, timeout):
        key=get_exa_api_key()
        if not key:raise ExaWait('EXA_API_KEY_NOT_CONFIGURED',status='WAITING_EXA_AUTH')
        headers=dict(public_headers)
        if self.policy['auth_mode']=='bearer':headers['Authorization']='Bearer '+key
        else:headers['x-api-key']=key
        request=urllib.request.Request('https://api.exa.ai/'+endpoint,data=canonical(body),headers=headers,method='POST')
        cap=self.policy['http']['max_response_bytes']
        try:
            with urllib.request.build_opener(NoRedirect).open(request,timeout=timeout) as response:
                raw=response.read(cap+1)
                if len(raw)>cap:raise HTTPFailure(200,reason='RESPONSE_TOO_LARGE')
                value=json.loads(raw)
                if key in json.dumps(value,ensure_ascii=False):raise IntegrityError('Credential echo rejected before persistence')
                canonical(value)
                return value
        except urllib.error.HTTPError as exc:
            # Never persist arbitrary headers or provider error text. Store only
            # allowlisted metadata, an explicit feature code and response hash.
            raw=exc.read(cap+1) if exc.fp is not None else b''
            try:value=json.loads(raw) if len(raw)<=cap else {}
            except (ValueError,UnicodeError):value={}
            if not isinstance(value,dict):value={}
            if key in json.dumps(value,ensure_ascii=False):raise IntegrityError('Credential echo rejected before persistence') from None
            raise HTTPFailure(exc.code,reason=optional_feature_error(value),
                retry_after=exc.headers.get('Retry-After') if exc.headers else None,metadata=response_metadata(value)) from None
        except (urllib.error.URLError,TimeoutError,OSError):raise HTTPFailure(0,reason='NETWORK_TIMEOUT_OR_UNAVAILABLE') from None
        except (ValueError,UnicodeError):raise HTTPFailure(200,reason='INVALID_JSON') from None

    def _identity(self, request, probe):
        capabilities={'version':self.snapshot['capability_version']}
        if request['body'].get('type','auto').startswith('deep'):
            grant=self.store.get('exa:deep-grant:'+digest(request))
            if not grant:raise Blocked('Deep search requires a recorded unresolved conflict after two distinct auto queries')
            capabilities['deep_conflict_evidence']=digest(grant)
        if request['profile']=='discovery_beta' and not probe:
            cap=self.store.get('exa:capability:dynamic')
            if not cap or cap.get('live') is not True or cap.get('status')!='SUPPORTED_RESPONSE':
                raise ExaWait('Dynamic Highlights needs an actual live capability probe')
            # A receipted response establishes request acceptance, not source
            # coverage or the provider's internal allocation mechanism.
            capabilities['dynamic_probe_receipt']=cap['receipt_digest']
        return {'request':request,'research_cutoff':self.snapshot['research_cutoff'],
            'adapter_version':self.snapshot['adapter_version'],'extraction_version':self.snapshot['extraction_version'],
            'capabilities_digest':digest(capabilities),'policy_digest':self.snapshot['policy_digest'],
            'authorization_digest':digest({'run_id':self.snapshot['run_id'],'scopes':self.policy['authorization_scopes']}),
            'transport':'LIVE_EXA_HTTP' if self.live else 'FIXTURE_EXA_TRANSPORT',
            'auth_mode':self.policy['auth_mode'],'credential_source':self.credential_source,
            'preview_version':BETA if request['profile']=='discovery_beta' else None,'capability_probe':probe}

    def _cache_path(self, identity):
        public={**identity,'authorization_digest':digest(self.policy['authorization_scopes'])}
        return self.cross_cache/(digest(public)+'.json') if self.cross_cache else None

    def _cross_read(self, path, request):
        if path is None or not path.exists():return None
        saved=read_json(path)
        if digest(saved['result'])!=saved['result_digest']:raise IntegrityError('Exa cross-workspace cache digest mismatch')
        profile=request['profile'];c=self.policy['cache']
        hours=c['cross_run_rules_ttl_hours'] if profile=='official_rules' else c['cross_run_current_docs_ttl_hours'] if profile=='implementation' else c['cross_run_search_ttl_hours']
        seconds=c['cross_run_empty_result_ttl_minutes']*60 if saved['result']['status']=='EMPTY' else hours*3600
        if seconds<=0 or not 0<=self.clock()-saved['created_at']<=seconds:return None
        return saved['result']

    def _check_shape(self, request):
        if set(request)-{'endpoint','body','public_headers','profile','expanded'}:raise IntegrityError('Unknown local Exa request fields')
        validate_request(request['endpoint'],request['body'],request['public_headers'])
        if request['profile'] not in self.policy['profiles']:raise IntegrityError('Unknown Exa profile')
        content=request['body'].get('contents',{})
        high=content.get('highlights')
        dynamic=isinstance(high,dict) and high.get('dynamic') is True
        if dynamic and (request['profile']!='discovery_beta' or not self.policy['opt_in']['dynamic']):raise Blocked('Dynamic Highlights outside explicit discovery opt-in')
        if request['body'].get('type','auto').startswith('deep') and not self.policy['opt_in']['deep']:raise Blocked('Deep search outside explicit opt-in')
        if request['endpoint']=='contents':
            expected=self.compiler.contents(request['body']['urls'],expanded=request.get('expanded',False),profile=request['profile'])
            if request!=expected:raise IntegrityError('Contents request differs from its frozen profile')
        else:
            spec=self.policy['profiles'][request['profile']]
            lanes=('NO_LOWER_BOUND','LAST_24_CALENDAR_MONTHS','LAST_180_DAYS') if spec['date_policy']=='MATCH_PARENT_LANE' else (None,)
            candidates=[]
            for lane in lanes:
                body=copy.deepcopy(spec['request_template'])
                body.update(query=request['body']['query'],**date_bounds(self.snapshot['research_cutoff'],spec['date_policy'],parent_lane=lane))
                if 'additionalQueries' in request['body']:body['additionalQueries']=request['body']['additionalQueries']
                # API capability smoke may request the fixed navigation schema on auto.
                if 'outputSchema' in request['body']:body['outputSchema']=self.policy['profiles']['deep_escalation']['request_template']['outputSchema']
                candidates.append(body)
            headers={'Content-Type':'application/json',**({'Exa-Beta':BETA} if dynamic else {})}
            if request['body'] not in candidates or request['public_headers']!=headers or 'expanded' in request:
                raise IntegrityError('Search request differs from its frozen profile or cutoff')
            if request['profile']=='official_rules':
                years=re.findall(r'\b(?:20\d{2})\b',request['body']['query'])
                if len(years)!=1:raise IntegrityError('Official rules request needs one explicit competition year')
                self.compiler.search(request['body']['query'],'official_rules',competition_year=int(years[0]))

    def execute(self, request, *, stage='scouting', origin=None, capability_probe=False):
        request=copy.deepcopy(request);self._check_shape(request);self.authorization.check(request,origin=origin)
        identity=self._identity(request,capability_probe);key=digest(identity)
        with self.ledger.single_flight(key):
            row=self.ledger.prepare(key,identity)
            if row['status']=='DONE':
                result=self.store.load(row['response_digest']);self._account_results(key,request,result);return result
            if row['retry_at']>self.clock():raise ExaWait('EXA_RETRY_AFTER_WAIT',retry_at=row['retry_at'])
            if request['body'].get('type','auto').startswith('deep'):
                self.ledger.resource('deep-logical',[key],self.policy['budget']['max_deep_logical_requests'])
            if request['endpoint']=='contents':
                self.ledger.resource('fulltext-urls',request['body']['urls'],self.policy['budget']['max_fulltext_urls'])
            path=self._cache_path(identity)
            cached=self._cross_read(path,request) if not capability_probe else None
            if cached is not None:
                self.store.event('EXA_CROSS_RUN_CACHE_REUSE',{'request':key,'result_digest':digest(cached)})
                self.ledger.complete(key,cached);self._account_results(key,request,cached);return cached
            result=self._attempts(key,request,stage,origin,capability_probe)
            result['retrieved_at']=self.clock()
            self.ledger.complete(key,result)
            if path is not None and result['status'] in ('OK','EMPTY') and not capability_probe:
                write_json(path,{'created_at':self.clock(),'result':result,'result_digest':digest(result)})
            self._account_results(key,request,result)
            return result

    def _account_results(self, key, request, result):
        if request['endpoint']=='search':
            self.ledger.resource('search-results',[key+':'+str(i) for i in range(len(result['response']['results']))],
                                 self.policy['budget']['max_search_results_total'])

    def _attempts(self, key, request, stage, origin, probe):
        state=self.store.get('exa:progress:'+key,{})
        current=copy.deepcopy(state.get('current',request));responses=state.get('responses',[])
        successful=state.get('successful',[]);final_statuses=state.get('final_statuses',{});provenance=state.get('provenance',{})
        waited=state.get('waited',0);fallback=state.get('fallback');pending_response=state.get('pending_response')
        def checkpoint(pending=None):
            self.store.set('exa:progress:'+key,{'current':current,'responses':responses,
                'successful':successful,'final_statuses':final_statuses,'waited':waited,
                'fallback':fallback,'pending_response':pending,'provenance':provenance})
        max_attempts=self.policy['http']['max_attempts_per_logical_request']
        while pending_response or self.ledger.get(key)['attempts']<max_attempts:
            if pending_response:
                payload=self.store.load(pending_response)
                pending_response=None
            else:
                self.deadline();self.authorization.check(current,for_network=True,origin=origin or request,fallback=fallback)
                if self.live and not get_exa_api_key():raise ExaWait('EXA_API_KEY_NOT_CONFIGURED',status='WAITING_EXA_AUTH')
                lease=self.gate.acquire(self.credential_source,self.snapshot['run_id'],self.policy)
                attempt=None;outcome='cancel'
                try:
                    self.deadline()
                    attempt=self.ledger.reserve(key,stage);self.gate.bind(lease,attempt)
                    timeout=self.policy['http']['deep_timeout_seconds'] if current['body'].get('type','').startswith('deep') else self.timeout
                    try:payload=self.transport(current['endpoint'],copy.deepcopy(current['body']),dict(current['public_headers']),timeout)
                    except (TimeoutError,urllib.error.URLError,OSError):raise HTTPFailure(0,reason='NETWORK_TIMEOUT_OR_UNAVAILABLE') from None
                    if not isinstance(payload,dict) or not isinstance(payload.get('results'),list):raise HTTPFailure(200,reason='MISSING_RESULTS')
                    canonical(payload)
                    key_value=get_exa_api_key()
                    if key_value and key_value in json.dumps(payload,ensure_ascii=False):raise IntegrityError('Credential echo rejected before persistence')
                    # Check source URLs/types before a successful response can enter
                    # the evidence cache. Generated output is preserved separately.
                    normalize_sources(payload,current,self.snapshot,live=self.live)
                    outcome='success'
                    ref=self.store.put(payload)
                    receipt={'status':'HTTP_200','request_digest':digest(current),'public_headers':current['public_headers'],
                             'response_digest':ref,**response_metadata(payload),'capability_probe':probe}
                    responses.append({'response_digest':ref,'request':copy.deepcopy(current),'metadata':response_metadata(payload)})
                    checkpoint(ref)
                    self.ledger.finish_attempt(attempt,receipt);attempt=None
                except HTTPFailure as exc:
                    outcome='transient' if exc.code in TRANSIENT or exc.code==0 else 'nonretryable'
                    remaining=max_attempts-self.ledger.get(key)['attempts']
                    delay=max(retry_seconds(exc.retry_after,self.clock()),self.rng.uniform(0,min(self.policy['http']['backoff_cap_seconds'],
                              self.policy['http']['backoff_base_seconds']*2**max(0,self.ledger.get(key)['attempts']-1))))
                    retry_at=self.clock()+delay if outcome=='transient' else 0
                    self.ledger.finish_attempt(attempt,{'status':'HTTP_ERROR','http_status':exc.code,'reason':exc.reason,
                        'request_digest':digest(current),'public_headers':current['public_headers'],**exc.metadata},retry_at=retry_at)
                    attempt=None
                    if exc.code in (401,403):raise ExaWait('EXA_HTTP_'+str(exc.code),status='WAITING_EXA_AUTH') from None
                    candidate=None;feature=None
                    if remaining and exc.code in (400,422):
                        if exc.reason=='UNSUPPORTED_DYNAMIC_HIGHLIGHTS' and self.policy['fallbacks']['dynamic']:
                            body,headers=dynamic_fallback(current['body'],current['public_headers'],exc.reason)
                            candidate={**current,'body':body,'public_headers':headers};feature='dynamic'
                        elif exc.reason=='UNSUPPORTED_PUBLICATION_CATEGORY' and self.policy['fallbacks']['publication'] and current['body'].get('category')=='publication':
                            candidate=copy.deepcopy(current);candidate['body'].pop('category');feature='publication'
                    if candidate is not None:
                        self.authorization.check(candidate,origin=origin or request,fallback=feature)
                        self.store.event('DYNAMIC_HIGHLIGHTS_FALLBACK' if feature=='dynamic' else 'PUBLICATION_CATEGORY_FALLBACK',
                            {'request':key,'old_request':digest(current),'new_request':digest(candidate),'reason':exc.reason,
                             'scope':'QUERY_DOMAIN_DATE_PRESERVED','authorized':True})
                        current=candidate;fallback=feature
                        checkpoint()
                        continue
                    if outcome!='transient' or not remaining:raise ExaWait('EXA_HTTP_'+str(exc.code)+((': '+exc.reason) if exc.reason else '')) from None
                    if not math.isfinite(delay) or waited+delay>self.policy['http']['max_total_backoff_seconds_per_request']:
                        raise ExaWait('EXA_RETRY_AFTER_WAIT',retry_at=retry_at) from None
                    # Release local concurrency before backoff, without touching the
                    # experiment RNG or erasing the recorded attempt.
                    self.gate.release(lease,self.policy,outcome=outcome);lease=None
                    if delay:self.sleep(delay);waited+=delay
                    checkpoint()
                    continue
                except BaseException:
                    if attempt:
                        self.ledger.finish_attempt(attempt,{'status':'UNKNOWN','request_digest':digest(current),
                            'public_headers':current['public_headers'],'cost_dollars':'UNKNOWN','provider_request_id':'UNKNOWN'},unknown=True)
                    raise
                finally:
                    if lease:self.gate.release(lease,self.policy,outcome=outcome)
            if current['endpoint']=='search':
                status='OK' if payload['results'] else 'EMPTY'
                if status=='EMPTY':self.store.event('EXA_EMPTY',{'request':key,'absence_is_not_proof':True})
                return {'status':status,'response':payload,'effective_request':current,'attempt_responses':responses,'fallback':fallback}
            # A 200 response may fail individual URLs. Preserve each successful
            # result once, and retry only explicitly transient failed URLs.
            requested=current['body']['urls'];by_url={}
            for item in payload['results']:
                url=checked_url(item['url'])
                if url not in requested:raise IntegrityError('Contents response escaped the exact requested URL scope')
                by_url.setdefault(url,[]).append(item)
            statuses=payload.get('statuses')
            if not isinstance(statuses,list):raise IntegrityError('Contents requires explicit per-URL statuses')
            mapped={}
            for status in statuses:
                if not isinstance(status,dict) or status.get('status') not in ('success','error'):raise IntegrityError('Malformed contents status')
                url=checked_url(status.get('id',''))
                if url not in requested or url in mapped:raise IntegrityError('Duplicate/unrequested contents status')
                mapped[url]=status
            retry=[]
            for url in requested:
                status=mapped.get(url,{'id':url,'status':'error','error':{'tag':'MISSING_STATUS'}})
                if status['status']=='success' and not by_url.get(url):status={'id':url,'status':'error','error':{'tag':'MISSING_RESULT'}}
                final_statuses[url]=status
                if status['status']=='success':
                    successful.extend(by_url[url])
                    for item in by_url[url]:provenance[digest(item)]={'response_digest':responses[-1]['response_digest'],
                        'request_id':responses[-1]['metadata']['provider_request_id']}
                elif isinstance(status.get('error'),dict) and (status['error'].get('tag') in TRANSIENT_SOURCE or status['error'].get('httpStatusCode') in TRANSIENT):retry.append(url)
            self.store.event('EXA_CONTENTS_PROGRESS',{'request':key,'successful_urls':sorted({r['url'] for r in successful}),
                             'failed_urls':[u for u,s in final_statuses.items() if s['status']!='success']})
            if retry and self.ledger.get(key)['attempts']<max_attempts:
                current=copy.deepcopy(current);current['body']['urls']=retry
                checkpoint()
                continue
            merged={'results':successful,'statuses':list(final_statuses.values()),
                    'requestId':payload.get('requestId','UNKNOWN'),'output':payload.get('output'),
                    'costDollars':payload.get('costDollars')}
            status='OK' if all(s['status']=='success' for s in final_statuses.values()) else 'PARTIAL'
            return {'status':status,'response':merged,'effective_request':request,'attempt_responses':responses,'fallback':fallback,'source_provenance':provenance}
        raise ExaWait('EXA_LOGICAL_ATTEMPT_LIMIT')

    def authorize_deep(self, request, audit, prior_query_digests):
        if audit.get('decision')!='REVISE' or not any(c.get('judgment') in ('contradicted','inconclusive') for c in audit.get('checks',[])):
            raise IntegrityError('Deep escalation needs an unresolved source conflict, not an author request for a better verdict')
        with self.store.connect() as c:
            records=[json.loads(r['identity']) for r in c.execute("SELECT identity FROM exa_requests WHERE status='DONE'")]
        known={digest(r['request']['body']['query']) for r in records if r['request']['endpoint']=='search' and r['request']['body'].get('type','auto')=='auto'}
        requested=set(prior_query_digests)
        if len(requested)<2 or not requested<=known:raise IntegrityError('Two distinct completed auto queries are required before deep escalation')
        self.store.set('exa:deep-grant:'+digest(request),{'conflict_audit_digest':self.store.put(audit),
            'prior_query_digests':sorted(requested),'authority':'CONTROLLER_OWNED_CONFLICT_EVIDENCE','valid_negative_remains_binding':True})

    def search(self, query, *, profile='foundations', stage='scouting', additional_queries=(), parent_lane=None, competition_year=None,
               conflict_audit=None,prior_query_digests=()):
        request=self.compiler.search(query,profile,additional_queries=additional_queries,parent_lane=parent_lane,competition_year=competition_year)
        if conflict_audit is not None:self.authorize_deep(request,conflict_audit,prior_query_digests)
        result=self.execute(request,stage=stage)
        sources=normalize_sources(result['response'],result['effective_request'],self.snapshot,live=self.live,retrieved_at=result.get('retrieved_at'))
        for source in sources:source['origin_request']=request
        return sources

    def contents(self, urls, *, origin, expanded=False, stage='primary_source_fetch'):
        request=self.compiler.contents([checked_url(u) for u in urls],expanded=expanded,profile=origin['profile'])
        result=self.execute(request,stage=stage,origin=origin)
        sources=normalize_sources(result['response'],request,self.snapshot,live=self.live,
                                  provenance=result.get('source_provenance'),retrieved_at=result.get('retrieved_at'))
        for source in sources:source['origin_request']=origin
        return sources,result['response'].get('statuses',[])

    def probe_dynamic(self, query):
        request=self.compiler.search(query,'discovery_beta')
        result=self.execute(request,stage='scouting',capability_probe=True)
        accepted=result['fallback'] is None and result['status'] in ('OK','EMPTY')
        comparison={};stable=None
        if accepted:
            stable=self.execute(self.compiler.search(query,'foundations'),stage='scouting',capability_probe=True)
            for mode,value in [('dynamic',result),('per_source',stable)]:
                comparison[mode]={'sources':len(value['response']['results']),
                    'sources_with_highlights':sum(bool(s.get('highlights')) for s in value['response']['results']),
                    'highlight_characters':sum(sum(len(h) for h in s.get('highlights',[])) for s in value['response']['results'])}
            accepted=comparison['dynamic']['sources_with_highlights']>0
        cap={'status':'SUPPORTED_RESPONSE' if accepted else 'FALLBACK_OR_MISSING_EXCERPTS_NOT_DYNAMIC_SUPPORT','live':self.live,
             'receipt_digest':digest({'dynamic':result,'stable':stable}),'beta_version':BETA,
             'observed_coverage':comparison,'coverage_mechanism_verified':False,
             'promotion':'NO_DEFAULT_PROMOTION; request acceptance and observed excerpts do not prove superior recall'}
        self.store.set('exa:capability:dynamic',cap)
        return cap
