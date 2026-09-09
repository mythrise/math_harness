"""Reviewed preparation + body-first writing, integrated with the existing Controller.

All model calls still go through Controller.call and the existing independent board.
Proposals are schema checked, tied to source hashes and reviewed before use.
"""
from __future__ import annotations
import copy
import re
from .common import (Blocked, IntegrityError, ScientificRejection, InfrastructureUnavailable,
    UnknownExternalState, BudgetExhausted, DeadlineReached, digest, write_json, tree_manifest)
from .review_board import ReviewUnavailable, ProviderFailure, NeedsClarification
from .literature import ResearchUnavailable
from .providers import PromptPacketTooLarge
from .materials_contracts import (check_brief, check_data_plan, check_portfolio,
    check_paper_map, claim_tokens)
from .materials_data import audit_development
from .contracts import validate

STOP = (InfrastructureUnavailable, UnknownExternalState, BudgetExhausted, DeadlineReached,
        ReviewUnavailable, ProviderFailure, NeedsClarification, ResearchUnavailable, PromptPacketTooLarge)

class MaterialsWorkflow:
    def __init__(self, controller):
        self.c=controller

    def _stage(self,key,role,schema,packet,checker,review_roles):
        feedback=[]
        for attempt in range(self.c.config['repair_attempts']+1):
            try:
                record=self.c.call(f'materials:{key}:{attempt}',role,schema,
                    {**packet,'repair_feedback':copy.deepcopy(feedback)})
                value=checker(record['result'])
                reviews=self.c.reviews(f'materials:{key}:{attempt}',value,roles=review_roles,
                    stage={'problem_brief':'problem_brief','data_plan':'data_policy','model_portfolio':'model_portfolio'}[schema],context={'input_contract':packet,
                        'scope':'Review proposed requirements/methods/data policies, not future experimental success. '
                                'Anchors must entail the requirement; include every actual question and constraint. '
                                'No arbitrary page/algorithm/figure quotas; reject synthetic observations and data leakage.'})
                output={'value':value,'proposal_receipt_digest':digest(record['receipt']),
                        'review_receipt_digests':[digest(r) for r in reviews]}
                self.c.store.set('materials:'+key,self.c.store.put(output))
                return value
            except STOP:raise
            except (Blocked,IntegrityError) as exc:
                feedback.append({'error':str(exc),'records':list(getattr(exc,'records',()))})
                self.c.store.event('MATERIALS_REPAIR',{'stage':key,'attempt':attempt,'diagnostic':feedback[-1]})
        raise ScientificRejection('Materials stage exhausted its bounded repairs: '+key)

    def prepare(self,pi):
        c=self.c;root=c.root/'inputs/development'
        manifest=tree_manifest(root)
        audit=c.store.step('materials:data-audit',{'manifest':manifest},lambda:audit_development(root))
        if manifest!=audit['manifest'] or tree_manifest(root)!=manifest:
            raise IntegrityError('Audited development input has changed')
        packet={'problem':c.problem,'problem_sha256':digest(c.problem),'data_audit':audit,
                'exact_anchor_candidates':[{'start':m.start(),'end':m.end(),'quote':m.group()}
                    for m in re.finditer(r'[^\n]+',c.problem) if m.group().strip()],
                'method_cards':c.base['methods'],'pi_priorities':pi,
                'requirements':'Extract all actual questions, exact original-text spans and constraints. '
                    'Prefer relevant exact_anchor_candidates and copy start/end/quote together verbatim; '
                    'these are Python Unicode character offsets, not bytes. Never guess offsets. '
                    'Never impose three/four questions from a tutorial. Inferred goals are distinct from explicit requirements. '
                    'No results have been computed at this stage.'}
        brief=self._stage('brief','problem_analyst','problem_brief',packet,
                          lambda v:check_brief(v,c.problem),('math_reviewer',))
        data=self._stage('data-plan','data_steward','data_plan',
                        {'brief':brief,'data_audit':audit,'problem':c.problem,
                         'requirements':'Account for each file and observed read limitation. Preserve originals. '
                             'Declare sampling unit, group/time split, training-fold-only transformations. '
                             'Missing data is not permission to synthesize observations. '
                             'No universal MICE/DBSCAN, normality test, deletion or imputation rule.'},
                        lambda v:check_data_plan(v,audit),('experiment_reviewer',))
        if data['required_data']:
            raise Blocked('Required modeling inputs remain missing: '+str(data['required_data']))
        from .materials_catalog import retrieve_reference_models
        references=retrieve_reference_models(' '.join(q['title']+' '+q['direct_goal'] for q in brief['questions']))
        portfolio=self._stage('portfolio','modeler','model_portfolio',
            {'brief':brief,'data_plan':data,'method_cards':c.base['methods'],'source_reference_cards':references,
             'source_registry':c.base.get('source_registry',[]),'research_evidence':c.base.get('research_evidence',[]),
             'requirements':'Choose one admissible installed baseline per question, and only justified challengers. '
                 'A textbook/catalog entry is not an installed implementation. Compare principle, fit, limits, '
                 'resource cost and falsification. A single simple correct model is allowed; never invent novelty.'},
            lambda v:check_portfolio(v,brief,c.base['methods']),('math_reviewer','experiment_reviewer'))
        from .baseline_binding import independent_baselines
        preparation={'baseline_contract':independent_baselines(portfolio),'schema_version':'materials-preparation/1','brief':brief,'data_plan':data,
            'portfolio':portfolio,'reference_catalog_sha256':references['catalog_sha256'],'data_audit':audit,'empirical_validation':'NOT_RUN',
            'reading_limits_are_explicit':True}
        if getattr(c,'ideas',None):
            # The independent brief/data/baseline were already produced without imported ideas.
            external=c.ideas.prepare(copy.deepcopy(preparation))
            preparation['external_idea_contract']={'digest':digest(external),'entry_digest':external['entry_digest'],
                'proposal_count':len(external['items']),'raw_chat_included':False,'full_pipeline_required':True}
        c.store.step('materials:freeze-preparation',preparation,lambda:preparation)
        write_json(c.root/'materials/preparation.json',preparation)
        c.base['materials_preparation']=preparation
        c.base['baseline_binding_contract']='Final plan.baseline_binding must copy independent IDs/digests; KEEP copies method and description exactly, REPLACE needs suitability/strength reasons and independent review. plan.baseline must equal sorted question lines: question_id + ": " + selected_method_card_id + " — " + selected_description. Solver baseline_implementation binds digest, baseline variant and actual source paths; reviewers inspect its implementation.'
        c.base['modeling_coverage_contract']={'actual_question_ids':[q['id'] for q in brief['questions']],
            'required_content':['input_goal_constraints','assumptions','units','derivation',
                                'algorithm','execution','results','validation'],
            'page_minimum':None,'tutorial_counts_are_not_rules':True}
        return preparation

    def prepare_paper(self,draft,plan,claims,question_evidence,attempt):
        """Called INSIDE the existing versioned paper repair loop, before compilation."""
        c=self.c
        body_claims=set().union(*(claim_tokens(s['text']) for s in draft['sections']))
        if not body_claims<=set(claims):raise IntegrityError('Body has an unsupported claim')
        packet={'body':draft['sections'],'title':draft['title'],'limitations':draft['limitations'],
            'claims':{k:claims[k] for k in sorted(body_claims)},'questions':plan['questions'],
            'requirements':'Write the abstract AFTER this body. Cover actual questions and measured findings only. '
                'Use existing {{claim:ID}} tokens; do not introduce novel results or citations. '
                'No minimum word/count/innovation quota. Fit one page including title and keywords; '
                'keep limitations. This step cannot change the body, model or measured results.'}
        revision=c.call(f'materials:abstract:{attempt}:{digest(draft)}','abstract_editor','abstract_revision',packet)['result']
        validate('abstract_revision',revision)
        used=claim_tokens(revision['abstract'])
        if used!=set(revision['claim_ids']) or not used<=body_claims:
            raise IntegrityError('Abstract editor introduced an unsupported/body-absent claim')
        if '{{cite:' in revision['abstract']:
            raise IntegrityError('Abstract editor may not change the bibliography')
        new=copy.deepcopy(draft);new['abstract']=revision['abstract'];new['keywords']=revision['keywords']
        # Existing abstract citations must not leave dead bibliography entries.
        import re
        cited=set(re.findall(r'\{\{cite:([a-zA-Z][a-zA-Z0-9_-]*)\}\}',
              '\n'.join([new['abstract']]+[s['text'] for s in new['sections']]+new['limitations'])))
        new['citation_ids']=[cid for cid in draft['citation_ids'] if cid in cited]
        evidence=[]
        for group in question_evidence:
            for e in group.get('evidence',[]):
                # Evidence IDs used in paper_map are job-qualified to avoid collisions.
                evidence.append({**e,'id':'qe_'+digest([e['id'],group['job_id']])[:32], 'job_id':group['job_id']})
        map_packet={'draft':new,'draft_digest':digest(new),'plan':plan,'claims':claims,
            'question_evidence':evidence,
            'requirements':'Map all actual question IDs to the actual zero-based section indices. '
                'For each question decide each of the eight coverage steps. Steps may share a section; '
                'PRESENT is a location claim, not proof. Justify non-applicable steps; no page quotas. '
                'Quantitative conclusions require the question-specific claim IDs actually used in text. '
                'Copy the global symbol/meaning/unit definitions exactly from plan.variables. '
                'Map all abstract claim tokens; do not invent evidence.'}
        mapping=c.call(f'materials:paper-map:{attempt}:{digest(new)}','writer','paper_map',map_packet)['result']
        diagnostic=check_paper_map(mapping,new,plan,claims,evidence)
        c.reviews('materials:paper-semantics:'+digest(new),{'draft':new,'mapping':mapping,'diagnostic':diagnostic},
            roles=('paper_reviewer',),stage='execution',context={
                'plan':plan,'claims':claims,'question_evidence':evidence,
                'required':'Verify substantive content, units, derivations, every requested answer and limitations. '
                    'A mapping or eight labels is not evidence of adequate content. '
                    'Do not require PDF layout before compilation; the later visual gate does that. '
                    'Do not predict prizes or require invented figures, equations, citations or innovation counts.'})
        artifact={'plan':plan,'brief':c.base['materials_preparation']['brief'],
                  'preparation_digest':digest(c.base['materials_preparation']),
                  'paper_map':mapping,'diagnostic':diagnostic,'draft_digest':digest(new)}
        c.store.step('materials:paper-map:'+digest(new),artifact,lambda:artifact)
        write_json(c.root/'materials/paper-map.json',artifact)
        return new,artifact


def plan_attestation_target(plan,base):
    preparation=base.get('materials_preparation')
    external=base.get('external_idea_alignment')
    if external:return digest({'plan':plan,'preparation':preparation,'external_idea_alignment':external})
    return digest({'plan':plan,'preparation':preparation}) if preparation else digest(plan)
