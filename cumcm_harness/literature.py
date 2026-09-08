"""Exa evidence collection + independent adversarial hypothesis review.

The network layer retrieves evidence; it cannot establish empirical hypotheses.
No API key, request headers or private input rows enter the evidence registry.
"""
from __future__ import annotations
import ipaddress
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from .common import Blocked, IntegrityError, canonical, digest, read_json, write_json
from .contracts import SCHEMAS, S, I, B, ID, obj, arr, validate
from .credentials import get_exa_api_key
from .review_board import ReviewUnavailable

QUERY = obj(query={'type':'string','minLength':4,'maxLength':220}, purpose={'enum':['background','support','counterexample','limitations']})
SCHEMAS['research_queries'] = obj(queries={**arr(QUERY,1),'maxItems':4})
CARD = obj(id=ID, assumption_index=I, statement=S,
           kind={'enum':['structural','empirical','simplification']},
           falsification_test=S, acceptance_rule=S, failure_action=S)
SCHEMAS['hypotheses'] = obj(hypotheses={**arr(CARD,1),'maxItems':24})
EVIDENCE = obj(source_id=ID, quote={'type':'string','minLength':12,'maxLength':400},
               relation={'enum':['supports','opposes','scope_limit']})
CHECK = obj(hypothesis_id=ID, judgment={'enum':['supported_with_scope','explicit_simplification','inconclusive','contradicted']},
            rationale=S, evidence=arr(EVIDENCE), requires_execution=B, required_test=S)
SCHEMAS['hypothesis_audit'] = obj(decision={'enum':['ACCEPT_FOR_TESTING','REVISE']},
    checks=arr(CHECK,1), limitations=arr(S,1), citation_ids=arr(ID))


class ResearchUnavailable(Blocked):
    pass


class LiteratureAssessmentFailure(Blocked):
    """Rejected evidence remains available to the bounded model-repair loop."""
    def __init__(self, reason, dossier):
        super().__init__(reason)
        self.diagnostic={**dossier,'validation_status':'REJECTED_NOT_ACCEPTED',
                         'validation_error':reason}

    def repair_summary(self):
        # Preserve all objections, exact quoted passages, hypothesis tests and
        # source identities. Full source bodies belong in the immutable dossier,
        # not in every subsequent repair prompt.
        return {**self.diagnostic,
                'validation_error':str(self).split(': {',1)[0],
                'sources':[{k:v for k,v in s.items() if k!='text'} for s in self.diagnostic['sources']],
                'source_text_policy':'FULL_BODIES_IN_DIAGNOSTIC_OBJECT; EXACT_QUOTES_IN_AUDIT'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the Exa credential to a redirected host.
        return None


def public_url(value):
    if not isinstance(value,str):raise IntegrityError('Source URL must be text')
    try:
        p = urllib.parse.urlsplit(value)
        host = (p.hostname or '').lower().rstrip('.')
        p.port  # Reject malformed ports before storing or forwarding a URL.
    except ValueError:raise IntegrityError('Malformed source URL') from None
    if p.scheme not in ('https','http') or not host or p.username or p.password:
        raise IntegrityError('Source URL must be public HTTP(S), without credentials')
    if host == 'localhost' or host.endswith(('.localhost','.local','.internal')) or host in ('metadata.google.internal',):
        raise IntegrityError('Private source URL refused')
    try:
        if not ipaddress.ip_address(host).is_global:raise IntegrityError('Private source URL refused')
    except ValueError:pass
    if any(k.lower() in ('api_key','apikey','token','access_token','key') for k,v in urllib.parse.parse_qsl(p.query)):
        raise IntegrityError('Credential-like URL query refused')
    return urllib.parse.urlunsplit((p.scheme, p.netloc.lower(), p.path or '/', p.query, ''))


class ExaClient:
    live = True
    def __init__(self, cache: Path, *, timeout=35, retries=2, max_results=4,
                 transport=None, sleep=time.sleep, before_request=None):
        self.cache=Path(cache);self.timeout=timeout;self.retries=retries;self.max_results=max_results
        self.transport=transport or self._http;self.sleep=sleep;self.before_request=before_request
        self.live=transport is None

    def _http(self, endpoint, body):
        key=get_exa_api_key()
        if not key:raise ResearchUnavailable('EXA_API_KEY_NOT_CONFIGURED; use set-exa-key or the environment, not config.json')
        request=urllib.request.Request('https://api.exa.ai/'+endpoint, data=canonical(body),
            headers={'Content-Type':'application/json','x-api-key':key},method='POST')
        for attempt in range(self.retries):
            if self.before_request:self.before_request()
            try:
                with urllib.request.build_opener(NoRedirect).open(request,timeout=self.timeout) as response:
                    raw=response.read(2_000_001)
                    if len(raw)>2_000_000:raise ResearchUnavailable('EXA_RESPONSE_TOO_LARGE')
                    data=json.loads(raw)
                    # Unexpected echoes must not turn credentials into artifacts.
                    if key in json.dumps(data,ensure_ascii=False):raise IntegrityError('Credential echo detected; response not persisted')
                    return data
            except urllib.error.HTTPError as exc:
                if exc.code not in (408,429,500,502,503,504) or attempt+1>=self.retries:
                    raise ResearchUnavailable(f'EXA_HTTP_{exc.code}; no result fabricated') from None
            except (urllib.error.URLError,TimeoutError,OSError):
                if attempt+1>=self.retries:raise ResearchUnavailable('EXA_NETWORK_UNAVAILABLE') from None
            except (ValueError,UnicodeError):
                raise ResearchUnavailable('EXA_INVALID_JSON') from None
            self.sleep(min(2.0,0.5*2**attempt))
        raise ResearchUnavailable('EXA_RETRY_LIMIT')

    def request(self, endpoint, body):
        if endpoint not in ('search','contents'):raise IntegrityError('Unsupported Exa endpoint')
        identity={'endpoint':endpoint,'body':body,'transport':'LIVE_EXA_HTTP' if self.live else 'FIXTURE_EXA_TRANSPORT'}
        path=self.cache/(digest(identity)+'.json')
        if path.exists():
            saved=read_json(path)
            if saved['identity']!=identity or digest(saved['response'])!=saved['response_digest']:
                raise IntegrityError('Exa cache digest mismatch')
            return saved['response']
        data=self.transport(endpoint,body)
        if not isinstance(data,dict) or not isinstance(data.get('results'),list):
            raise ResearchUnavailable('EXA_MISSING_RESULTS')
        if not data['results']:raise ResearchUnavailable('EXA_EMPTY_RESULTS; absence of hits is not proof of absence')
        statuses=data.get('statuses',[])
        if not isinstance(statuses,list):raise ResearchUnavailable('EXA_INVALID_STATUSES')
        for status in statuses:
            if not isinstance(status,dict) or status.get('status')!='success':raise ResearchUnavailable('EXA_PARTIAL_CONTENT_FAILURE')
        # Unusable responses must remain retryable, rather than poisoning the
        # request cache with an HTTP-200 failure forever.
        self.normalize(data)
        # Persist successful responses only. Errors can be retried on resume.
        write_json(path,{'identity':identity,'response':data,'response_digest':digest(data)})
        return data

    def search(self, query):
        body={'query':query,'type':'auto','numResults':self.max_results,
              'contents':{'text':{'maxCharacters':10000},'highlights':True}}
        return self.normalize(self.request('search',body))

    def contents(self, urls):
        urls=[public_url(x) for x in urls]
        if not urls or len(urls)>8:raise IntegrityError('Bounded contents request required')
        return self.normalize(self.request('contents',{'urls':urls,'text':{'maxCharacters':10000}}))

    def normalize(self, payload):
        results=[];seen=set()
        for item in payload['results']:
            if not isinstance(item,dict):raise ResearchUnavailable('EXA_INVALID_RESULT')
            url=public_url(item.get('url',''))
            text=item.get('text')
            if not text:
                highlights=item.get('highlights') or []
                if not isinstance(highlights,list) or any(not isinstance(x,str) for x in highlights):
                    raise ResearchUnavailable('EXA_INVALID_HIGHLIGHTS')
                text='\n'.join(highlights)
            if not isinstance(text,str) or len(text.strip())<30:continue
            title=item.get('title')
            if not isinstance(title,str) or not title.strip():continue
            if url in seen:continue
            seen.add(url);text=text[:10000]
            results.append({'id':'exa_'+digest(url)[:16], 'title':title,'url':url,
                'author':item.get('author') or '', 'published':item.get('publishedDate') or '',
                'text':text,'content_sha256':digest(text),'retrieval':'LIVE_EXA_HTTP' if self.live else 'FIXTURE_EXA_TRANSPORT',
                'status':'RETRIEVED_NOT_VALIDATED'})
        if not results:raise ResearchUnavailable('EXA_NO_USABLE_EVIDENCE')
        return results


def validate_query(query, *, problem='', filenames=(), approved=None):
    if not 4<=len(query)<=220:raise IntegrityError('Search query length out of bounds')
    if re.search(r'://|[\w.+-]+@[\w.-]+|(?:api[_ -]?key|token)\s*[:=]|[\\/]|\d{8,}',query,re.I):
        raise IntegrityError('Query may expose URLs, paths, identifiers or credentials')
    if len(query)>=40 and query in problem:raise IntegrityError('Do not send verbatim problem text to Exa')
    if any(len(x)>4 and x.lower() in query.lower() for x in filenames):raise IntegrityError('Input filenames must not be sent to Exa')
    secret=get_exa_api_key()
    if secret and secret in query:raise IntegrityError('Credential in research query')
    if approved is not None and query not in approved:
        raise Blocked('Contest query is not in the operator-approved exa_approved_queries list')
    return query


def check_hypotheses(plan, cards):
    validate('hypotheses',cards)
    expected=set(range(len(plan['assumptions'])))
    indices=[h['assumption_index'] for h in cards['hypotheses']]
    ids=[h['id'] for h in cards['hypotheses']]
    if set(indices)!=expected or len(indices)!=len(expected) or len(set(ids))!=len(ids):
        raise IntegrityError('Hypothesis register must cover every assumption exactly once')
    for h in cards['hypotheses']:
        if h['statement']!=plan['assumptions'][h['assumption_index']]:
            raise IntegrityError('Hypothesis text is not the exact frozen assumption')
    return cards


def check_audit(cards, audit, sources):
    validate('hypothesis_audit',audit)
    known={s['id']:s for s in sources};hyp={h['id']:h for h in cards['hypotheses']}
    checks=audit['checks'];ids=[c['hypothesis_id'] for c in checks]
    if set(ids)!=set(hyp) or len(ids)!=len(hyp):raise IntegrityError('Critic omitted or duplicated a hypothesis')
    used=set();tests=[]
    for c in checks:
        for ref in c['evidence']:
            source=known.get(ref['source_id'])
            if source is None:
                raise IntegrityError('Unknown source in hypothesis audit: '+ref['source_id']+
                    '; only retrieved sources are citable; problem/protocol metadata is not a literature source')
            if digest(source['text'])!=source['content_sha256']:
                raise IntegrityError('Modified source in hypothesis audit: '+ref['source_id'])
            if ref['quote'] not in source['text']:raise IntegrityError('Fabricated or non-exact evidence quotation')
            used.add(ref['source_id'])
        if c['judgment']=='supported_with_scope' and not any(e['relation']=='supports' for e in c['evidence']):
            raise IntegrityError(c['hypothesis_id']+': supported hypothesis requires an exact supporting passage')
        if hyp[c['hypothesis_id']]['kind']!='structural' and not c['requires_execution']:
            raise IntegrityError('Empirical/simplifying assumption cannot be validated by search alone')
        if c['requires_execution']:
            if c['required_test']!='hypothesis_'+c['hypothesis_id']:
                raise IntegrityError('Required executable hypothesis test name mismatch')
            tests.append({'name':c['required_test'],**hyp[c['hypothesis_id']]})
    if set(audit['citation_ids'])!=used or len(audit['citation_ids'])!=len(used):
        raise IntegrityError('Citation set must equal the exact quoted source set')
    if audit['decision']!='ACCEPT_FOR_TESTING' or any(c['judgment'] in ('inconclusive','contradicted') for c in checks):
        raise Blocked('Hypothesis critic requests model revision: '+canonical(audit).decode())
    if not used:raise Blocked('No grounded literature evidence; do not fabricate a bibliography')
    return tests


class LiteratureWorkflow:
    def __init__(self, controller, client=None):
        self.c=controller
        self.client=client or ExaClient(controller.root/'literature/exa-cache',
            timeout=controller.config.get('exa_timeout',35),max_results=controller.config.get('exa_results_per_query',4),
            before_request=self.reserve)
        if not controller.demo and not self.client.live:raise IntegrityError('Fixture retrieval cannot enter a live run')
        self.initial=[];self.accepted=None
        self.original_sources=list(controller.base.get('source_registry',[]))

    def reserve(self):
        self.c.check_deadline();n=self.c.store.get('exa_requests_reserved',0)
        if n>=self.c.config.get('exa_max_requests',32):raise ResearchUnavailable('EXA_REQUEST_BUDGET_EXHAUSTED')
        self.c.store.set('exa_requests_reserved',n+1)

    def retrieve(self, proposal, *, opponent=False):
        validate('research_queries',proposal)
        purposes={q['purpose'] for q in proposal['queries']}
        if opponent and 'counterexample' not in purposes:raise IntegrityError('Adversary must search explicitly for counterexamples')
        if not opponent and not purposes.intersection({'background','support'}):raise IntegrityError('Initial research must include method/background evidence')
        collected={}
        for row in proposal['queries']:
            query=validate_query(row['query'],problem=self.c.problem,
                filenames=[p.get('name',p.get('path','')) for p in self.c.intake['profiles']],
                approved=self.c.config.get('exa_approved_queries',[]) if self.c.config['mode']=='contest' else None)
            results=self.client.search(query)
            for source in results:collected[source['id']]=source
            self.c.store.event('EXA_EVIDENCE',{'query_digest':digest(query),'purpose':row['purpose'],
                'source_digests':[s['content_sha256'] for s in results], 'transport':'LIVE_EXA_HTTP' if self.client.live else 'FIXTURE_EXA_TRANSPORT'})
        return list(collected.values())

    def collect_initial(self, pi):
        if self.c.config['network_policy']!='EXA_ABSTRACT_QUERIES':
            raise Blocked('Exa research requires network_policy=EXA_ABSTRACT_QUERIES in a newly initialized workspace')
        proposal=self.c.call('literature:initial-queries','literature_scout','research_queries',{
            'problem':self.c.problem,'method_cards':self.c.base['methods'],'research_focus':pi['research_focus'],
            'requirements':'Return at most four generic method queries, including background/support and applicability limits. Never send problem text or data to the search service.',
            'approved_queries':self.c.config.get('exa_approved_queries',[])})['result']
        self.initial=self.retrieve(proposal)
        write_json(self.c.root/'literature/initial.json',{'queries':proposal,'sources':self.initial})
        self.c.base['research_evidence']=self.initial

    def assess(self, plan):
        key=digest(plan);cached=self.c.store.get('literature:accepted:'+key)
        if cached:
            self.accepted=self.c.store.load(cached)
            self._apply();return self.accepted
        context={k:self.c.base[k] for k in ('methods','experiment_contract','io_contract','limits') if k in self.c.base}
        specification={'problem':self.c.problem,'context':context}
        cards=self.c.call('hypotheses:'+key,'modeler','hypotheses',{
            **specification,'plan':plan,'sources':self.initial,
            'requirements':'One card per exact plan.assumptions string in order. IDs H1, H2, etc. State executable falsification tests, acceptance rules and failure actions. Search is not an empirical test.'})['result']
        check_hypotheses(plan,cards)
        counter=self.c.call('counterqueries:'+key,'hypothesis_critic','research_queries',{
            **specification,'plan':plan,'hypotheses':cards,'sources':self.initial,
            'approved_queries':self.c.config.get('exa_approved_queries',[]),
            'requirements':'Independently seek counterexamples, limitations and competing explanations with generic Exa queries. Include purpose=counterexample. Do not merely repeat the modeler search.'})['result']
        opposing=self.retrieve(counter,opponent=True)
        sources=list({s['id']:s for s in self.initial+opposing}.values())
        audit=self.c.call('hypothesis-audit:'+key,'hypothesis_critic','hypothesis_audit',{
            **specification,'plan':plan,'hypotheses':cards,'sources':sources,
            'citation_contract':{
                'allowed_source_ids':[s['id'] for s in sources],
                'context_is_not_literature':True,
                'rule':'Only sources[] IDs and exact text may appear in evidence or citation_ids. Do not cite problem IDs, method-card IDs or invented context-* IDs. Task definitions and frozen protocol choices are declared specifications, not literature-supported empirical findings. They may be explicit_simplification judgments, with rationale scoped to the supplied contract and executable consistency checks; use no fabricated reference. An unresolved contradiction must still be REVISE.'},
            'requirements':'Cover every hypothesis. Exact source quotations only. Every supported_with_scope judgment, including a structural one, requires an exact quote with relation=supports; scope_limit alone is insufficient. Do not claim that literature proves local execution or internal contracts. Use required_test=hypothesis_H1 etc for execution-required checks. Review the prospective specification: use supplied problem/method/experiment context, distinguish planned tests from completed execution, and require later evidence at the relevant gate. Accept only FOR TESTING; never claim empirical validity from Exa. Retain contradictions as REVISE.'})['result']
        # Save even negative reports, before a deterministic gate raises.
        dossier={'plan_digest':key,'hypotheses':cards,'audit':audit,'sources':sources,
                 'counterqueries':counter,'empirical_tests':'NOT_RUN'}
        write_json(self.c.root/'literature/audits'/(key+'.json'),dossier)
        try:
            tests=check_audit(cards,audit,sources)
            self.c.reviews('literature:'+key,dossier,roles=('literature_reviewer',),stage='plan_design',context=context)
        except (ReviewUnavailable,ResearchUnavailable):
            raise
        except (Blocked,IntegrityError) as exc:
            # Keep the complete rejected report even when an early integrity
            # check masks later substantive objections. This is repair input,
            # never an accepted hypothesis contract or permission to advance.
            raise LiteratureAssessmentFailure(str(exc),dossier) from exc
        used=set(audit['citation_ids'])
        bibliography=[{'id':s['id'],'title':s['title'],'url':s['url'],'verified':True,
            'verification_note':'Exa source snapshot + exact-quotation checks + independent source/relevance board. Not proof of a hypothesis. Content digest '+s['content_sha256']} for s in sources if s['id'] in used]
        self.accepted={'plan_digest':key,'hypotheses':cards,'audit':audit,'required_tests':tests,
                       'bibliography':bibliography,'source_digests':{s['id']:s['content_sha256'] for s in sources},
                       'empirical_tests':'NOT_RUN','retrieval':'LIVE_EXA_HTTP' if self.client.live else 'FIXTURE_EXA_TRANSPORT'}
        self.c.store.set('literature:accepted:'+key,self.c.store.put(self.accepted))
        self._apply();return self.accepted

    def _apply(self):
        self.c.base['hypothesis_contract']=self.accepted
        original=self.original_sources
        self.c.base['source_registry']=list({s['id']:s for s in original+self.accepted['bibliography']}.values())
        write_json(self.c.root/'literature/accepted.json',self.accepted)

    def require_tests(self, report):
        if not self.accepted:raise IntegrityError('Hypotheses not accepted before execution')
        cases={x['name']:x for x in report.get('cases',[])}
        for test in self.accepted['required_tests']:
            case=cases.get(test['name'])
            if not case or case.get('passed') is not True:
                raise Blocked('Missing or failed mandatory hypothesis falsification test: '+test['name'])
        write_json(self.c.root/'literature/execution.json',{
            'plan_digest':self.accepted['plan_digest'],'test_report_digest':digest(report),
            'status':'DECLARED_DIAGNOSTICS_PASSED_NOT_PROOF',
            'tests':[cases[x['name']] for x in self.accepted['required_tests']]})
