"""R2 literature workflow: mapped discovery, primary reads and located citations."""
from __future__ import annotations
import copy
from collections import defaultdict
from .common import Blocked, IntegrityError, digest, read_json, write_json
from .contracts import SCHEMAS, S, I, B, ID, obj, arr, validate
from .literature import LiteratureWorkflow, LiteratureAssessmentFailure, ResearchUnavailable, check_hypotheses, CHECK
from .review_board import ReviewUnavailable
from .exa_defaults import DEFAULT_POLICY
from .exa_policy import POLICY_SCHEMA, load_frozen
from .exa_authorization import ExaAuthorization
from .exa_transport import R2ExaClient
from .exa_ledger import ExaWait
from .exa_evidence import merge_sources, source_packet, locate_audit, citation_export

R2_QUERY=obj(query={'type':'string','minLength':4,'maxLength':220},
    purpose={'enum':['background','support','counterexample','limitations']},
    profile={'enum':list(DEFAULT_POLICY['profiles'])},hypothesis_ids={**arr(ID),'uniqueItems':True,'maxItems':24},
    additional_queries={**arr({'type':'string','minLength':4,'maxLength':220}),'maxItems':2})
SCHEMAS['research_queries_r2']=obj(queries={**arr(R2_QUERY,1),'maxItems':4})
SCHEMAS['source_selection_r2']=obj(selections={**arr(obj(source_id=ID,hypothesis_ids={**arr(ID,1),'uniqueItems':True},
    critical=B,expanded=B,reason={'type':'string','minLength':12,'maxLength':1000}),1),'maxItems':24})
evidence=obj(source_id=ID,snapshot_id={'type':'string','pattern':'^[0-9a-f]{64}$'},
    quote={'type':'string','minLength':12,'maxLength':400},quote_start=I,quote_end=I,
    relation={'enum':['supports','opposes','scope_limit']})
check=copy.deepcopy(CHECK);check['properties']['evidence']=arr(evidence)
SCHEMAS['hypothesis_audit_r2']=obj(decision={'enum':['ACCEPT_FOR_TESTING','REVISE']},
    checks=arr(check,1),limitations=arr(S,1),citation_ids=arr(ID))
SCHEMAS['exa_policy']=POLICY_SCHEMA


class R2LiteratureWorkflow(LiteratureWorkflow):
    def __init__(self, controller, client=None):
        self.c=controller;self.snapshot=load_frozen(controller.root)
        if self.snapshot is None:raise IntegrityError('R2 workflow requires a frozen Exa sidecar')
        self.policy=self.snapshot['policy']
        auth=ExaAuthorization(controller.root,self.snapshot,mode=controller.config['mode'],problem=controller.problem,
             profiles=controller.intake['profiles'],identities=controller.config['identity_denylist'],
             approved_queries=controller.config['exa_approved_queries'],live=not controller.demo)
        self.client=client or R2ExaClient(controller.store,self.snapshot,authorization=auth,deadline=controller.check_deadline,
            max_attempts=controller.config['exa_max_requests'],timeout=controller.config['exa_timeout'])
        if not isinstance(self.client,R2ExaClient):raise IntegrityError('R2 policy cannot use the legacy Exa adapter')
        if self.client.snapshot!=self.snapshot:raise IntegrityError('Exa client uses a different frozen policy')
        if not controller.demo and not self.client.live:raise IntegrityError('Fixture retrieval cannot enter a live run')
        self.initial=[];self.accepted=None;self.original_sources=list(controller.base.get('source_registry',[]))

    def packet(self, sources):
        return source_packet(sources,self.policy['budget']['max_source_characters_per_model_packet'])

    def allowed_profiles(self, opponent=False):
        if opponent:return ['counterexamples']
        names=['foundations','recent_methods','frontier_refresh','unfiltered_scholarly_fallback']
        if self.policy['profiles']['implementation']['request_template'].get('includeDomains'):names.append('implementation')
        capability=self.c.store.get('exa:capability:dynamic',{})
        if self.policy['opt_in']['dynamic'] and capability.get('live') and capability.get('status')=='SUPPORTED_RESPONSE':names.append('discovery_beta')
        return names

    def retrieve(self, proposal, *, opponent=False, hypotheses=(), stage=None):
        validate('research_queries_r2',proposal)
        if len(proposal['queries'])>self.policy['budget']['max_queries_per_model_proposal']:
            raise IntegrityError('Research proposal exceeds the frozen query limit')
        expected=set(hypotheses);covered=set();sources=[];links=[]
        for row in proposal['queries']:
            if row['profile'] not in self.allowed_profiles(opponent):raise IntegrityError('Exa profile is outside this role/stage')
            if opponent and row['purpose'] not in ('counterexample','limitations'):raise IntegrityError('Adversary query requires counterexample/limitations purpose')
            if not opponent and row['purpose'] not in ('background','support','limitations'):raise IntegrityError('Support query has an adversarial purpose')
            ids=set(row['hypothesis_ids'])
            if ids-expected or (expected and not ids):raise IntegrityError('Every hypothesis query needs explicit current H-IDs')
            covered|=ids
        if covered!=expected:raise IntegrityError('Research query mapping does not cover every critical hypothesis')
        if opponent and not any(r['purpose']=='counterexample' for r in proposal['queries']):raise IntegrityError('Explicit counterexample query required')
        if not opponent and not any(r['purpose'] in ('background','support') for r in proposal['queries']):raise IntegrityError('Support/background query required')
        for row in proposal['queries']:
            found=self.client.search(row['query'],profile=row['profile'],stage=stage or ('adversary' if opponent else 'scouting'),
                                     additional_queries=row['additional_queries'])
            for source in found:
                source['hypothesis_ids']=row['hypothesis_ids'];source['purpose']=row['purpose']
            sources=merge_sources(sources,found)
            link={'query_digest':digest(row['query']),'query':row['query'],'profile':row['profile'],
                  'hypothesis_ids':row['hypothesis_ids'],'purpose':row['purpose'],
                  'snapshot_ids':[s['snapshot_id'] for s in found],'status':'RETRIEVED' if found else 'EMPTY',
                  'empty_is_not_proof':True}
            links.append(link);self.c.store.event('EXA_HYPOTHESIS_QUERY',link)
        return sources,links

    def _queries(self, key, *, hypotheses=(), plan=None, opponent=False, initial=False, pi=None):
        seen=[];history=[];result=[];all_links=[]
        for round_index in range(self.policy['budget']['max_query_rounds_per_phase']):
            round_id=key+':'+str(round_index)
            self.client.ledger.resource('query-round:'+key,[round_id],self.policy['budget']['max_query_rounds_per_phase'])
            packet={'problem':self.c.problem,'hypotheses':list(hypotheses),'method_cards':self.c.base['methods'],
                'research_focus':pi['research_focus'] if pi else [],'plan':plan,
                'sources':self.packet(self.initial),'allowed_profiles':self.allowed_profiles(opponent),
                'frozen_cutoff':self.snapshot['research_cutoff'],'earlier_queries':seen,'empty_rounds':history,
                'approved_queries':self.c.config['exa_approved_queries'],
                'requirements':'Return at most four generic method queries; no problem, data, filenames, identity or credentials. '
                    'Use additional_queries=[] for auto profiles. Map each current hypothesis ID explicitly; a query can cover multiple. '
                    'Cover every current H-ID. A missing counterexample is not proof. Propose a different angle after EMPTY. '+
                    ('Independently seek counterexamples; use only counterexamples profile; include counterexample purpose. No author PASS judgments are supplied.' if opponent else
                     'Include background/support. '+('Use both foundations and unfiltered_scholarly_fallback profiles.' if initial else 'Match the theory/recent-method lane to the claim; recency is not source quality.'))}
            proposal=self.c.call(round_id,'hypothesis_critic' if opponent else 'literature_scout','research_queries_r2',packet)['result']
            validate('research_queries_r2',proposal)
            if initial and not {'foundations','unfiltered_scholarly_fallback'}<=set(r['profile'] for r in proposal['queries']):
                raise IntegrityError('Initial research needs foundations plus an unfiltered scholarly pass')
            if any(r['query'] in seen for r in proposal['queries']):raise IntegrityError('EMPTY query must be reformulated, not repeated')
            ids=[h['id'] for h in hypotheses]
            found,links=self.retrieve(proposal,opponent=opponent,hypotheses=ids)
            result=merge_sources(result,found);all_links+=links;seen += [r['query'] for r in proposal['queries']]
            covered={h for link in links if link['status']=='RETRIEVED' for h in link['hypothesis_ids']}
            if found and (not ids or covered==set(ids)):return result,all_links
            history.append({'round':round_index,'links':links,'interpretation':'EMPTY_IS_NOT_ABSENCE'})
        write_json(self.c.root/'literature/r2-blockers'/(digest(key)+'.json'),{'query_links':all_links,'sources':self.packet(result)})
        raise ExaWait('EXA_NO_REQUIRED_EVIDENCE_AFTER_DISTINCT_QUERY_ANGLES')

    def collect_initial(self, pi):
        self.initial,links=self._queries('literature:r2:initial',initial=True,pi=pi)
        write_json(self.c.root/'literature/initial.json',{'query_links':links,'sources':self.packet(self.initial),
                   'policy_digest':self.snapshot['policy_digest'],'raw_sources':'CONTROLLER_PRIVATE_SNAPSHOTS'})
        self.c.base['research_evidence']=self.packet(self.initial)
        self.c.base['exa_research_scope']={k:self.snapshot[k] for k in ('policy_digest','research_cutoff','adapter_version','extraction_version','capability_version')}

    def _read_selected(self, key, cards, candidates):
        packet={'hypotheses':cards,'sources':self.packet(candidates),
            'requirements':'Select known source IDs to read primary text. Cover every hypothesis with material sources, including relevant opposing evidence. '
                'Set critical=true only for evidence needed at the acceptance gate. Set expanded=true only when a material method/assumption passage needs more than the bounded initial read; explain why. '
                'Do not count mirrors as independent works. No excerpt does not mean irrelevant. Source selection is not scientific acceptance.'}
        selection=self.c.call('source-selection:'+key,'literature_scout','source_selection_r2',packet)['result']
        validate('source_selection_r2',selection)
        known={s['id']:s for s in candidates};ids={h['id'] for h in cards['hypotheses']};covered=set();groups=defaultdict(list);chosen=set()
        for row in selection['selections']:
            if row['source_id'] not in known or row['source_id'] in chosen:raise IntegrityError('Unknown/duplicate primary source selection')
            chosen.add(row['source_id']);linked=set(row['hypothesis_ids'])
            if linked-ids:raise IntegrityError('Primary source selection refers to unknown hypothesis')
            covered|=linked;source=known[row['source_id']]
            if source['temporal_status']=='KNOWN_FUTURE_EXCLUDED':raise IntegrityError('Selected source is after the frozen cutoff')
            groups[digest(source['origin_request'])].append((source,row))
        if covered!=ids:raise IntegrityError('Primary source selection misses a critical hypothesis')
        read=[];failures=[]
        for group in groups.values():
            origin=group[0][0]['origin_request']
            for offset in range(0,len(group),self.policy['fetch']['batch_size']):
                batch=group[offset:offset+self.policy['fetch']['batch_size']]
                urls=list(dict.fromkeys(s['url'] for s,row in batch))
                fetched,statuses=self.client.contents(urls,origin=origin)
                for source in fetched:
                    source['hypothesis_ids']=sorted({h for selected,row in batch if selected['url']==source['url'] for h in row['hypothesis_ids']})
                    if any(row['expanded'] and selected['url']==source['url'] for selected,row in batch):
                        if source['coverage']['limit_hit']:
                            more,more_status=self.client.contents([source['url']],origin=origin,expanded=True)
                            for extended in more:extended['hypothesis_ids']=source['hypothesis_ids']
                            read=merge_sources(read,more);statuses+=more_status
                        else:self.c.store.event('EXA_EXPANSION_NOT_NEEDED',{'snapshot':source['snapshot_id'],'initial_limit_not_hit':True})
                read=merge_sources(read,fetched)
                for source,row in batch:
                    success=any(s['url']==source['url'] and s['text'] for s in read)
                    if not success:failures.append({'source_id':source['id'],'hypothesis_ids':row['hypothesis_ids'],'critical':row['critical'],'status':'NEEDS_MORE_CONTENT'})
                write_json(self.c.root/'literature/reads'/(key+'.json'),{'selection':selection,'sources':self.packet(read),'failures':failures})
        if any(f['critical'] for f in failures):raise ExaWait('EXA_CRITICAL_SOURCE_CONTENT_MISSING; other successful reads were preserved')
        return read,selection,failures

    def assess(self, plan):
        key=digest({'plan':plan,'policy_snapshot':self.snapshot})
        cached=self.c.store.get('literature:r2:accepted:'+key)
        if cached:
            self.accepted=self.c.store.load(cached);self._apply();return self.accepted
        cards=self.c.call('hypotheses:r2:'+key,'modeler','hypotheses',{'problem':self.c.problem,'plan':plan,
            'sources':self.packet(self.initial),'requirements':'One H-ID for every exact assumption. Distinguish structural, empirical and simplifying assumptions; declare falsification tests. No search result proves an empirical claim.'})['result']
        check_hypotheses(plan,cards)
        supporting,support_links=self._queries('support:r2:'+key,hypotheses=cards['hypotheses'],plan=plan)
        opposing,counter_links=self._queries('counter:r2:'+key,hypotheses=cards['hypotheses'],plan=plan,opponent=True)
        candidates=merge_sources(self.initial,supporting,opposing)
        sources,selection,failures=self._read_selected(key,cards,candidates)
        audit_packet={'problem':self.c.problem,'plan':plan,'hypotheses':cards,'sources':self.packet(sources),
            'query_links':support_links+counter_links,'reading_failures':failures,
            'citation_contract':{'allowed_source_ids':[s['id'] for s in sources],
                'rule':'Only original SOURCE_TEXT is citable. Every quote needs exact source_id, snapshot_id and zero-based [quote_start, quote_end) offsets in the original source text. '
                    'Packet text is a marked bounded window; do not invent missing passages. Generated summary/output/highlights are not original-text quote evidence. '
                    'Check semantic entailment and distinguish support, opposition and scope limits. Provider confidence is not proof. '
                    'Estimated/unknown dates do not establish publication-version or as-of claims. Future sources are excluded. '
                    'Mirrors share one work and cannot count as independent corroboration. Task definitions are specifications, not empirical literature evidence.'},
            'requirements':'Independently review each hypothesis; preserve contradictions as REVISE. Supported_with_scope requires a supporting original passage. '
                'Every empirical/simplification hypothesis requires execution test hypothesis_H<ID>. Only ACCEPT_FOR_TESTING is possible, never empirical proof.'}
        audit=self.c.call('hypothesis-audit:r2:'+key,'hypothesis_critic','hypothesis_audit_r2',audit_packet)['result']
        validate('hypothesis_audit_r2',audit)
        dossier={'plan_digest':digest(plan),'policy_snapshot_digest':digest(self.snapshot),'hypotheses':cards,'audit':audit,
            'sources':self.packet(sources),'query_links':support_links+counter_links,'selection':selection,
            'source_snapshot_digests':{s['id']:s['snapshot_id'] for s in sources},'empirical_tests':'NOT_RUN'}
        write_json(self.c.root/'literature/audits'/(key+'.json'),dossier)
        try:
            tests,locations=locate_audit(cards,audit,sources)
            reviews=self.c.reviews('literature:r2:'+key,dossier,roles=('literature_reviewer',),stage='plan_design',context={
                'required':'Verify semantic entailment, source/work/version identity, exact location, scope and limitations for every material quote. '
                    'Reject a true string used to support the wrong claim. Search cannot replace executable hypothesis diagnostics. '
                    'The source windows and quoted locations are bounded; missing required context is blocking.',
                'future_execution':'The empirical tests must be executed later; this gate certifies only the proposed evidence contract.'})
        except (ReviewUnavailable,ResearchUnavailable):raise
        except (Blocked,IntegrityError) as exc:
            if self.policy['opt_in']['deep'] and not isinstance(exc,IntegrityError) and audit['decision']=='REVISE':
                prior=sorted({link['query_digest'] for link in support_links+counter_links})
                if len(prior)>=2:
                    navigation=self.client.search(counter_links[0]['query'],profile='deep_escalation',stage='repair_reserve',
                        parent_lane='NO_LOWER_BOUND',conflict_audit=audit,prior_query_digests=prior)
                    dossier['deep_navigation']={'status':'NAVIGATION_ONLY_NEGATIVE_VERDICT_PRESERVED',
                        'sources':self.packet(navigation),
                        'generated_output':[{'digest':digest(s['provider_output']),
                            'preview':str(s['provider_output'])[:4000],'coverage':'BOUNDED_NAVIGATION_PREVIEW'}
                            for s in navigation[:1] if s.get('provider_output')]}
                    write_json(self.c.root/'literature/audits'/(key+'.json'),dossier)
            raise LiteratureAssessmentFailure(str(exc),dossier) from exc
        used=set(audit['citation_ids']);selected=[s for s in sources if s['id'] in used]
        bibliography=[{'id':s['id'],'title':s['title'],'url':s['url'],'verified':True,
            'verification_note':'Located original-text quote plus independent semantic review; bounded source read, date/version not automatically verified. Snapshot '+s['snapshot_id']} for s in selected]
        self.accepted={'plan_digest':digest(plan),'policy_snapshot_digest':digest(self.snapshot),'hypotheses':cards,'audit':audit,
            'required_tests':tests,'bibliography':bibliography,'source_digests':{s['id']:s['content_sha256'] for s in sources},
            'source_snapshots':{s['id']:s['snapshot_id'] for s in sources},'query_links':support_links+counter_links,
            'evidence':[citation_export(s,locations) for s in selected],
            'review_receipt_digests':[digest(r) for r in reviews],'empirical_tests':'NOT_RUN',
            'retrieval':'LIVE_EXA_HTTP' if self.client.live else 'FIXTURE_EXA_TRANSPORT'}
        self.c.store.set('literature:r2:accepted:'+key,self.c.store.put(self.accepted));self._apply();return self.accepted
