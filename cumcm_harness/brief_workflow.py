"""Source-ledger brief generation: local repairs, typed assembly, complete review.

Only transport failures use provider failover. A scientific FAIL is never an
availability failure. All subsequent modeling/Exa/solver/paper gates stay intact.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from .common import (Blocked,IntegrityError,ScientificRejection,UnknownExternalState,
    BudgetExhausted,DeadlineReached,digest,write_json,read_json,file_hash)
from .brief_sources import (load_snapshot,paragraph_units,make_batches,NeedsSourceInput,source_packet_units)
from .brief_contracts import (check_outline,check_facts,assemble,check_complete,
    check_ambiguities,apply_local_patch,MAX_FACTS_PER_CALL)
from .brief_validation import BriefContractError,definition_conflicts

# This is source work, not a request to derive a complete model before the brief.
SCOPE=('Check only faithful extraction of the original problem. Preserve all given '
       'definitions, whole formulas (including denominators), table fields/units, '
       'mechanism/geometry relations, hard constraints and actual deliverables. '
       'No new model derivation, algorithm implementation or experimental result is '
       'required at this gate. A missing source definition remains blocking. '
       'Do not replace unreadable source content using memory or web search.')

class BriefWorkflow:
    def __init__(self,controller):
        self.c=controller
        self.root=Path(controller.root)
        self.records=[];self.source_units=[]

    def _stop_types(self):
        from .materials_workflow import STOP
        return STOP

    def _diagnostic(self,exc,latest):
        # Original review records stay immutable in CAS. Provide the complete
        # substantive verdicts, not repeated prompts/receipt blobs in every retry.
        records=list(getattr(exc,'records',()))
        ref=self.c.store.put({'error':str(exc),'records':records,
                              'latest_artifact':latest,'findings':getattr(exc,'findings',[])})
        objections=[]
        def extract(value):
            if isinstance(value,dict):
                if isinstance(value.get('result'),dict):
                    objections.append(value['result']);return
                for k in ('records','findings'):
                    if isinstance(value.get(k),list):
                        for child in value[k]:extract(child)
            elif isinstance(value,list):
                for child in value:extract(child)
        extract(records)
        return {'error':str(exc),'findings':getattr(exc,'findings',[]),
                'review_objections':objections,'full_diagnostic_ref':ref}

    def _produce(self,key,schema,packet,checker,*,images=(),review=True,visual=False,stage=None):
        if review and stage is None:raise IntegrityError('Source production requires an explicit review scope')
        feedback=[];latest=None
        for attempt in range(self.c.config['repair_attempts']+1):
            request={**packet,'repair_feedback':deepcopy(feedback),'latest_artifact':deepcopy(latest),
                     'repair_contract':'Repair this bounded source chunk only. Preserve all source content. Never fabricate a missing definition or delete a valid rejection.'}
            try:
                # Managed invocation writes terminated timeouts as durable outcomes.
                # This is not a new unbounded retry loop; ReviewBoard owns its bounded
                # attempts, cooldown, model-call budget and UNKNOWN behavior.
                record=self.c.review_board.invoke(key+f':r{attempt}','problem_analyst',schema,request,
                    primary='codex',images=images)
                latest=deepcopy(record['result'])
                value=checker(latest)
                if review:
                    rs=self.c.reviews(key+':review:'+digest(value),value,
                        roles=('paper_reviewer',) if visual else ('math_reviewer',),
                        images=images if visual else (),stage=stage,
                        context={'source_packet':packet,'required':SCOPE,
                            'visual_review_scope':'Original source page versus transcription; NOT a final-paper layout check.' if visual else None})
                else:rs=[]
                self.records.append({'producer':digest(record),'reviews':[digest(r) for r in rs]})
                return value
            except self._stop_types():raise
            except NeedsSourceInput:raise
            except (Blocked,IntegrityError) as exc:
                diagnostic=self._diagnostic(exc,latest);feedback.append(diagnostic)
                self.c.store.event('BRIEF_CHUNK_REPAIR',{'key':key,'attempt':attempt,**diagnostic})
        raise ScientificRejection('Brief source chunk exhausted bounded repairs: '+key,
                                  records=[{'diagnostic':d} for d in feedback])

    def _source_units(self,snapshot):
        units=[];page_receipts=[]
        for page in snapshot['pages']:
            text=page['anchor']['quote']
            if snapshot['format']=='pdf':
                image=self.root/page['image']
                if file_hash(image)!=page['image_sha256']:raise IntegrityError('Source page image changed')
                packet={'source_id':page['id'],'source_sha256':snapshot['original_sha256'],
                    'image_sha256':page['image_sha256'],'unverified_text_layer':text,
                    'required':('Read the attached original page, not just its text layer. Return a faithful Markdown transcription. '
                        'Preserve whole fractions/exponents, symbols, units, table header AND rows, footnotes, examples vs fixed constants, '
                        'and mechanical axis/control descriptions. Use paragraph breaks between complete semantic units; never inside a formula. '
                        'Describe visible diagrams without inferring new equations. If anything material is unreadable return NEEDS_SOURCE '
                        'and identify it. No OCR engine or remembered domain formula is a substitute for reading this page.')}
                def checker(value):
                    from .contracts import validate
                    validate('brief_page_text',value)
                    if value['status']!='COMPLETE' or value['unreadable']:
                        raise NeedsSourceInput('Unreadable source page '+page['id']+': '+str(value['unreadable']))
                    if len(value['text'].strip())<20:raise IntegrityError('Incomplete source-page transcription')
                    return value
                value=self._produce('brief:page:'+digest(packet),'brief_page_text',packet,checker,
                                    images=(image,),visual=True,stage='source_page')
                text=value['text'];page_receipts.append({'page_id':page['id'],'transcript_digest':digest(value),
                                                       'image_sha256':page['image_sha256']})
            units.extend(paragraph_units(text,page['anchor'],page['id'],
                identity=snapshot['original_sha256'],visual=snapshot['format']=='pdf'))
        if len(units)>512:raise NeedsSourceInput('Source unit budget exceeded; explicitly scope or prepare verified structured inputs')
        if self.c.demo:
            for unit in units:
                if unit['visual']:unit['source_status']='FIXTURE_TRANSCRIPTION_NOT_LIVE_VISION'
        source={'schema_version':'brief-source-ledger/1','original_sha256':snapshot['original_sha256'],
                'problem_sha256':digest(self.c.problem),'units':units,'visual_pages':page_receipts,
                'source_review_receipts':deepcopy(self.records),'ocr_used':False,
                'model_transport':'FIXTURE_NOT_LLM' if self.c.demo else 'LIVE_CLI'}
        self.c.store.step('brief:freeze-source-ledger',source,lambda:source)
        write_json(self.root/'brief/source-ledger.json',source)
        return source

    def _extract(self,batch,outline,key,depth=0):
        owned={u['id'] for u in batch}
        positions=[i for i,u in enumerate(self.source_units) if u['id'] in owned]
        neighborhood=self.source_units[max(0,min(positions)-2):max(positions)+3] if positions else []
        context_units=[u for u in neighborhood if u['id'] not in owned]
        packet={'source_units':source_packet_units(batch),'context_units':source_packet_units(context_units),'questions':outline['questions'],
            'max_facts':MAX_FACTS_PER_CALL,
            'required':('Extract ALL substantive givens, definitions, formulas, hard constraints and deliverables in these source units. '
                'A fact is self-contained: no see G37, no dangling internal IDs. The first source_unit_id must be owned by this batch; '
                'adjacent context_units may supply complete denominators/definitions, not extra context-only output. '
                'Select whole source_unit_ids supplied here; do not invent offsets '
                'or regenerate references. question_ids refer to the given real questions; constraint_ids are computed later by the controller. '
                'Preserve table fields/units/months, complete ratio numerator AND denominator, physical meanings/units and axis-control relations. '
                'For explicitly defined symbols fill declarations with the subject and exact source quote, also present in statement. '
                'A stated convention is a given, not an open interpretation. Exclusions need explicit reasons and independent review. '
                'Return NEEDS_SPLIT with empty facts/exclusions if this packet cannot fit; never truncate or claim COMPLETE on partial output. '
                'Return NEEDS_SOURCE with exact unreadable spans when source material is insufficient; do not use Exa to reconstruct this problem.')}
        value=self._produce(key,'brief_facts',packet,
            lambda v:check_facts(v,batch,{q['id'] for q in outline['questions']},context_units=context_units),review=False)
        if value['status']=='NEEDS_SOURCE':
            raise NeedsSourceInput('Source definitions need clarification: '+value['reason']+' '+str(value['unreadable']))
        if value['status']=='NEEDS_SPLIT':
            if len(batch)<2 or depth>=8:
                raise NeedsSourceInput('One complete source unit exceeds extraction capacity; prepare a verified semantic split, never drop facts')
            self.c.store.event('BRIEF_BATCH_SPLIT',{'key':key,'units':[u['id'] for u in batch]})
            mid=len(batch)//2
            left=self._extract(batch[:mid],outline,key+':left',depth+1)
            right=self._extract(batch[mid:],outline,key+':right',depth+1)
            return {'facts':left['facts']+right['facts'],'exclusions':left['exclusions']+right['exclusions']}
        # Review and repair a rejected extraction in its LOCAL chunk, not an entire
        # hundred-item document. Reuse the already generated value on first review.
        feedback=[];latest=value
        for attempt in range(self.c.config['repair_attempts']+1):
            try:
                if attempt:
                    latest=self._produce(key+f':scientific-repair{attempt}','brief_facts',
                        {**packet,'prior_rejected_chunk':latest,'substantive_objections':feedback},
                        lambda v:check_facts(v,batch,{q['id'] for q in outline['questions']},context_units=context_units),review=False)
                    if latest['status']!='COMPLETE':
                        raise NeedsSourceInput('Rejected batch still lacks complete readable evidence')
                rs=self.c.reviews(key+':review:'+digest(latest),latest,roles=('math_reviewer',),
                    stage='source_facts',context={'source_packet':packet,'required':SCOPE,
                        'coverage_rule':'Every substantive assertion within a source unit must be covered, even when another assertion in the same paragraph has a fact. Verify exclusions, conditional constants and complete equation/table definitions.'})
                self.records.append({'batch':key,'reviews':[digest(r) for r in rs]})
                return {'facts':latest['facts'],'exclusions':latest['exclusions']}
            except self._stop_types():raise
            except NeedsSourceInput:raise
            except (Blocked,IntegrityError) as exc:
                d=self._diagnostic(exc,latest);feedback.append(d)
                self.c.store.event('BRIEF_CHUNK_REPAIR',{'key':key,'attempt':attempt,**d})
        raise ScientificRejection('Source fact chunk rejected after bounded local repairs: '+key)

    def _review_complete(self,brief,units,key,exclusions=()):
        # Per-question packets bound complete evidence without repeating unrelated
        # hundred-item source registers. A final small cross-question gate checks
        # all explicit definitions and ambiguity decisions together.
        for q in brief['questions']:
            facts=[r for r in brief['requirements'] if q['id'] in r['question_ids']]
            used={u for r in facts for u in r['source_unit_ids']}
            target={'question':q,'requirements':facts,'ambiguities':brief['ambiguities']}
            rs=self.c.reviews(key+':question:'+q['id']+':'+digest(target),target,roles=('math_reviewer',),
                stage='source_question',context={'sources':source_packet_units([u for u in units if u['id'] in used]),
                    'required':SCOPE,'scope_boundary':'Check this actual question and its givens. A baseline choice, derivation or future execution is not required here.'})
            self.records.append({'question':q['id'],'reviews':[digest(r) for r in rs]})
        target={'questions':brief['questions'],'ambiguities':brief['ambiguities'],
                'declarations':[{'id':r['id'],'statement':r['statement'],'declarations':r['declarations']} for r in brief['requirements'] if r['declarations']],
                'unit_risks':brief['unit_risks'],'completion_criteria':brief['completion_criteria'],
                'exclusions':list(exclusions)}
        rs=self.c.reviews(key+':global:'+digest(target),target,roles=('math_reviewer',),stage='source_global',
            context={'required':SCOPE+' Check cross-question consistency; a declared source convention may not be reopened as missing information.',
                     'local_source_reviews_completed':True,
                     'excluded_sources':source_packet_units([u for u in units if u['id'] in {e['source_unit_id'] for e in exclusions}])})
        self.records.append({'global_reviews':[digest(r) for r in rs]})

    def run(self,pi,audit):
        snapshot=load_snapshot(self.root,self.c.intake)
        source=self._source_units(snapshot);units=source['units'];self.source_units=units
        self.c.base['problem_source_projection']={'original_sha256':source['original_sha256'],
            'source_ledger_digest':digest(source),'units':[{k:u[k] for k in ('id','text','source_status')} for u in units],
            'authority':'Original frozen pages remain authoritative; visually checked transcription supplies reading evidence, not new assumptions.'}
        if sum(len(u['text']) for u in units)>60000:
            raise NeedsSourceInput('Question-outline packet exceeds 60000 characters. Prepare a verified scoped problem before starting; no silent truncation.')
        # Independent of imported user ideas. Those enter only after the existing
        # materials/data/baseline preparation completes.
        outline_packet={'source_units':source_packet_units(units),'data_schema':[{'file':x['file'],'status':x.get('status','UNREPORTED')} for x in audit.get('files',[])],
            'requirements':'Return a compact outline of actual questions, original goals, input categories/files, outputs and dependencies. '
                'Do not repeat the full fact register or mathematical model in inputs. source_unit_ids locate the original question clauses and dependencies; '
                'shared-given locators may be included but exhaustive fact coverage follows in source batches and final per-question review. '
                'Select exact supplied source_unit_ids with no invented suffixes; never generate constraint IDs. Known conventions remain givens. Preserve original problem count, not tutorial examples.'}
        outline=self._produce('brief:outline:'+digest(source),'brief_outline',outline_packet,
                               lambda v:check_outline(v,units),stage='source_outline')
        facts=[];exclusions=[]
        batches=make_batches(units)
        for i,batch in enumerate(batches):
            chunk=self._extract(batch,outline,'brief:facts:'+digest([source['original_sha256'],[u['id'] for u in batch],outline]))
            facts.extend(chunk['facts']);exclusions.extend(chunk['exclusions'])
        brief=assemble(outline,facts,units,self.c.problem)
        # Explicit definition register prevents ST/local time-like givens being
        # silently reopened as ambiguities. This is generic, not heliostat-specific.
        packet={'questions':brief['questions'],'facts':[{k:r[k] for k in ('id','kind','statement','declarations','question_ids')} for r in brief['requirements']],
            'required':'Identify only genuine missing information or conflicting ORIGINAL declarations. A stated convention is not missing. '
                'Acknowledge each explicit declaration via accepted_definitions. A source_conflict needs at least two source-grounded inconsistent witnesses. '
                'Do not convert implementation choices or later model decisions into ambiguities in the original problem.'}
        consistency=self._produce('brief:consistency:'+digest(brief),'brief_ambiguities',packet,
                                  lambda v:check_ambiguities(v,brief),stage='source_consistency')
        brief['ambiguities']=consistency['ambiguities']
        check_complete(brief,units,self.c.problem)
        feedback=[]
        for attempt in range(self.c.config['repair_attempts']+1):
            try:
                self._review_complete(brief,units,'brief:accept',exclusions)
                break
            except self._stop_types():raise
            except NeedsSourceInput:raise
            except (Blocked,IntegrityError) as exc:
                d=self._diagnostic(exc,brief);feedback.append(d)
                self.c.store.event('BRIEF_GLOBAL_REPAIR',{'attempt':attempt,**d})
                if attempt>=self.c.config['repair_attempts']:
                    raise ScientificRejection('Assembled brief rejected after bounded source-preserving repairs',records=feedback) from exc
                old=deepcopy(brief)
                patch_packet={'base_digest':digest(old),'current_brief':old,'source_units':source_packet_units(units),'objections':feedback,
                    'requirements':'Return bounded updates/additions only (max 12 each); do not rewrite the whole brief. Preserve IDs, source coverage, '
                        'hard constraints, given conventions and original question set. Supply exact before_digest for each updated requirement. '
                        'No unsupported new fact, no deletion, no no-op pass. Resolve only the cited current defects.'}
                holder={}
                def validate_patch(p):
                    holder['brief']=apply_local_patch(old,p,units,self.c.problem);return p
                patch=self._produce('brief:patch:'+digest(old),'brief_local_patch',patch_packet,validate_patch,review=False)
                # On cache replay a checker still runs; reapply only validated patch.
                brief=apply_local_patch(old,patch,units,self.c.problem)
                self.c.store.event('BRIEF_PATCH_APPLIED',{'before':digest(old),'after':digest(brief),'patch':digest(patch)})
        check_complete(brief,units,self.c.problem)
        excluded={e['source_unit_id'] for e in exclusions}
        used={s for r in brief['requirements'] for s in r['source_unit_ids']}
        if used|excluded!={u['id'] for u in units}:raise IntegrityError('Final source ledger lost source units')
        acceptance={'schema_version':'brief-acceptance/1','brief':brief,'source_ledger_digest':digest(source),
            'source_snapshot_manifest':self.c.intake['problem_source_manifest'],'exclusions':exclusions,
            'review_records':deepcopy(self.records),'semantic_correctness':'FIXTURE_REVIEW_ONLY_NOT_LIVE' if self.c.demo else 'INDEPENDENT_REVIEWED_NOT_FORMALLY_PROVEN',
            'stages_bypassed':[],'scientific_experiments_run_by_brief':0}
        self.c.store.step('brief:accepted',acceptance,lambda:acceptance)
        write_json(self.root/'brief/accepted.json',acceptance)
        self.c.store.set('materials:brief',self.c.store.put({'value':brief,'source_acceptance_digest':digest(acceptance)}))
        self.c.base['brief_source_contract']={'accepted_digest':digest(acceptance),'source_digest':digest(source),
            'authoritative_original_sha256':snapshot['original_sha256'],'full_pipeline_required':True}
        return brief
