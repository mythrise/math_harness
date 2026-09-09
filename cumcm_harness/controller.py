"""Executable end-to-end research DAG. LLMs propose; deterministic contracts and
independent reviewers decide whether artifacts may advance. No automatic contest
submission exists. Recovery replays completed receipts rather than conversation.
"""
from __future__ import annotations
import os, shutil, math
from pathlib import Path
from .common import *
from .contracts import validate, SCHEMAS
from .store import Store,controller_lock
from .providers import CLIProvider,review_quorum,PromptPacketTooLarge
from .sandbox import Executor,Limits,resource_gate
from .intake import verify_inputs
from .research import ResearchRunner,freeze_protocol,choose_development,paired_effect
from .algorithms import route_methods
from . import approval
from .review_board import NeedsClarification, ReviewBoard, ProviderFailure, ReviewUnavailable
from .literature import LiteratureWorkflow, ResearchUnavailable, LiteratureAssessmentFailure

DEFAULT_CONFIG={
 'mode':'practice','workers':2,'cpu_threads':1,'total_cpu_threads':2,'memory_mb':2048,'total_memory_mb':4096,
 'trial_timeout':120,'fe_budget':192,'development_seeds':[101,202,303],
 'confirmation_seeds':[701,702,703,704,705],'bootstrap_seed':41821,
 'max_candidates':2,'repair_attempts':2,'max_model_calls':180,'model_timeout':600,'claude_timeout':None,'claude_call_budget_usd':None,
 'codex_model':None,'claude_model':'claude-opus-5','claude_effort':'max','docker_image':'cumcm-egoharness:0.5.0-rc3',
 'allow_research_algorithms':False,'deadline_iso':None,'paper_reserve_seconds':7200,
 'identity_denylist':[],'input_data_origin':'include-in-support','network_policy':'LOCAL_EVIDENCE_ONLY',
 'review_members_per_role':2,'review_attempts_per_provider':2,'review_cooldown_seconds':60,
 'review_backoff_seconds':0.25,'review_timeout':180,
 'materials_workflow':False,'brief_pipeline':'legacy','literature_enabled':False,'exa_timeout':35,'exa_results_per_query':4,'exa_max_requests':32,'exa_approved_queries':[]}

IO_CONTRACT={
 'solver_entry':'main.py --input PUBLIC_DATA_DIR --out EMPTY_OUTPUT_DIR --seed INT --budget INT --variant ID',
 'solver_outputs':'answer.json plus any raw predictions/tables needed. Budget is an upper bound on expensive model/objective calls; record exact counts honestly. All plan variants must be implemented.',
 'evaluator_entry':'evaluate.py --input EVAL_DATA_DIR --answer SOLVER_OUTPUT_DIR --out EMPTY_OUTPUT_DIR --seed INT --budget INT --variant ID',
 'evaluator_layout':'EVAL_DATA_DIR/public contains the public phase data; EVAL_DATA_DIR/private contains optional hidden reference labels. Solver never mounts private data.',
 'evaluator_output':'evaluation.json with the supplied evaluation schema. Every quantitative question needs a measurement. Declare qualitative questions with answer_type=qualitative and supply question_evidence (hash-bound text or solver/evaluation relative file evidence), never placeholder numbers. Recompute objective and constraints; never trust score reported by solver. Explicitly return valid=false for malformed answers, rather than crashing.',
 'test_entry':'test_solver.py uses evaluator arguments and writes tests.json: {"cases":[{"name":"...","passed":true,"detail":"..."}],"all_passed":true}. At least three substantive distinct tests, including a deliberately wrong answer and a boundary case.',
 'verifier_preflight_entry':'The independent verifier bundle must ALSO include test_evaluator.py --input EVAL_DATA_DIR --out EMPTY_OUTPUT_DIR --seed INT --budget INT --variant ID. It runs without a solver answer BEFORE evaluator freeze. Write tests.json with at least three distinct substantive cases, all_passed and per-case name/passed/detail. Exercise actual evaluator primitives with analytically known positive, negative and boundary inputs; include array-shape/indexing and direction conventions when applicable. Do not run optimization or the full-size field in this bounded preflight. The controller separately tests missing, malformed and fabricated answers. A failing preflight is returned to the author with exact source and execution logs; passing it does not certify full numerical accuracy.',
 'environment':'Python 3.11+, numpy, scipy, pandas, scikit-learn, numba, matplotlib, jsonschema. Do not install packages or use network in trials.',
 'filesystem':'Only the output directory and ephemeral /tmp are writable. Code/input data are read-only. Do not write pycache under /code; use PYTHONDONTWRITEBYTECODE / in-memory work.',
 'bounded_task_dag':'For a long trial, implement task shards with cumcm_harness.task_dag.execute(tasks, handlers, checkpoint_dir, identity={code/input/protocol digests}). Tasks have id, depends_on and bounded shards; handlers run inside the solver Docker process. Completed shards verify manifests; an interrupted RUNNING shard must be explicitly reconciled. A resources.checkpointing declaration alone does not prove runtime use.',
 'custom_algorithm':'from cumcm_harness.algorithms import mosaic_solve, mosaic_modules. Attached algorithm is already installed. Do not retype or replace MOSAIC with a generic GA.'}

from .review_stages import REVIEW_STAGES

def validate_config(c):
    if set(c)!=set(DEFAULT_CONFIG):raise IntegrityError('Unexpected/missing configuration keys')
    if type(c['materials_workflow']) is not bool:raise IntegrityError('materials_workflow must be Boolean')
    if c['brief_pipeline'] not in ('legacy','source-ledger-v1') or not isinstance(c['brief_pipeline'],str):raise IntegrityError('Unknown brief_pipeline')
    if c['mode'] not in ('practice','contest'):raise IntegrityError('Invalid mode')
    if c['claude_effort'] not in (None,'low','medium','high','xhigh','max'):raise IntegrityError('Invalid config claude_effort')
    for key in ('workers','cpu_threads','total_cpu_threads','memory_mb','total_memory_mb','fe_budget','max_candidates','repair_attempts','max_model_calls'):
        if type(c[key]) is not int or c[key]<=0:raise IntegrityError('Invalid integer config '+key)
    for key in ('trial_timeout','model_timeout','paper_reserve_seconds'):
        if type(c[key]) not in (int,float) or not math.isfinite(c[key]) or c[key]<=0:raise IntegrityError('Invalid positive finite config '+key)
    for key in ('development_seeds','confirmation_seeds'):
        values=c[key]
        if not isinstance(values,list) or not values or any(type(x) is not int or x<0 for x in values) or len(set(values))!=len(values):raise IntegrityError('Invalid integer seeds '+key)
    if set(c['development_seeds']) & set(c['confirmation_seeds']):raise IntegrityError('Development and confirmation seeds must be disjoint')
    if type(c['bootstrap_seed']) is not int or c['bootstrap_seed']<0:raise IntegrityError('Invalid bootstrap_seed')
    budget=c['claude_call_budget_usd']
    if budget is not None and (type(budget) not in (int,float) or not math.isfinite(budget) or budget<=0):raise IntegrityError('Invalid Claude budget')
    timeout=c['claude_timeout']
    if timeout is not None and (type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout<=0):raise IntegrityError('Invalid Claude timeout')
    if type(c['allow_research_algorithms']) is not bool:raise IntegrityError('allow_research_algorithms must be Boolean')
    if c['max_candidates']>20 or c['repair_attempts']>5:raise IntegrityError('Unbounded research/repair is not supported')
    if c['fe_budget']<32:raise IntegrityError('FE budget must support at least one population')
    if c['network_policy'] not in ('LOCAL_EVIDENCE_ONLY','EXA_ABSTRACT_QUERIES'):raise IntegrityError('Unknown network policy')
    if not isinstance(c['literature_enabled'],bool):raise IntegrityError('literature_enabled must be Boolean')
    if c['literature_enabled'] and c['network_policy']!='EXA_ABSTRACT_QUERIES':
        raise IntegrityError('Online literature requires network_policy=EXA_ABSTRACT_QUERIES')
    for key,lo,hi in [('review_members_per_role',2,3),('review_attempts_per_provider',1,3),('exa_results_per_query',1,8),('exa_max_requests',1,100)]:
        if type(c[key]) is not int or not lo<=c[key]<=hi:raise IntegrityError('Invalid bounded config '+key)
    for key in ('review_cooldown_seconds','review_backoff_seconds','review_timeout','exa_timeout'):
        if isinstance(c[key],bool) or not isinstance(c[key],(int,float)) or not 0<=c[key]<=3600:raise IntegrityError('Invalid config '+key)
    if c['review_timeout']<=0 or c['exa_timeout']<=0:raise IntegrityError('Positive timeout required')
    if not isinstance(c['exa_approved_queries'],list) or any(not isinstance(q,str) for q in c['exa_approved_queries']):raise IntegrityError('Approved queries must be a string list')
    return c

class Controller:
    def __init__(self,root:Path,*,fixture_provider=None,executor=None,exa_client=None):
        self.root=Path(root).resolve();self.store=Store(self.root)
        self.intake,raw_config=verify_inputs(self.root)
        self.config={**DEFAULT_CONFIG,**raw_config};validate_config(self.config)
        self.demo=fixture_provider is not None
        if self.demo and self.config['mode']=='contest':raise Blocked('Fixtures cannot run in contest mode')
        self.providers={'codex':fixture_provider or CLIProvider('codex',model=self.config['codex_model'],timeout=self.config['model_timeout']),
                        'claude':fixture_provider or CLIProvider('claude',model=self.config['claude_model'],effort=self.config['claude_effort'],timeout=self.config['claude_timeout'],max_budget_usd=self.config['claude_call_budget_usd'])}
        self.executor=executor or Executor('docker',self.config['docker_image']);self.problem=(self.root/'problem.md').read_text('utf-8')
        self.base={'problem':self.problem,'data_profiles':self.intake['profiles'],'private_data_schema':self.intake['private_schema'],
                   'confirmation_scope':self.intake['confirmation_scope'],'methods':route_methods(self.problem,top_k=10),
                   'io_contract':IO_CONTRACT,'evaluation_schema':SCHEMAS['evaluation'],
                   'limits':{k:self.config[k] for k in ('fe_budget','trial_timeout','cpu_threads','memory_mb','allow_research_algorithms')},
                   'experiment_contract':{
                       'development_seeds':self.config['development_seeds'],
                       'confirmation_seeds':self.config['confirmation_seeds'],
                       'bootstrap_seed':self.config['bootstrap_seed'],
                       'max_candidates':self.config['max_candidates'],
                       'seed_rule':'The controller supplies one --seed to each solver invocation. Do not invent a different matrix or run another seed matrix inside a job.',
                       'budget_rule':'--budget is the total search FE cap for one solver invocation, shared across all subquestions it solves. Specify the allocation before implementation. Independently report fixed-input computations and final verification costs; they cannot be hidden search or used to select a different candidate.',
                       'variant_rule':'The controller runs baseline and full variants plus every plan ablation/sensitivity ID. Each invocation must produce all required subquestion answers. Do not rerun the complete algorithm/seed/variant matrix inside main.py.',
                       'metric_rule':'primary_metric must exactly equal a questions[].metric. The independent evaluator score and metric must use that same frozen primary metric.',
                       'inference_rule':'A complete valid seed matrix is required. Failed cells cannot be dropped to create a success-only comparison. Confirmation is run only after selection is frozen.'},
                   'source_registry':read_json(self.root/'sources.json') if (self.root/'sources.json').exists() else [],
                   'rules':'CUMCM 2026: team-led core modeling and itemized human review required for competition. Use Exa only for generic method queries; never post the current problem or raw/private data publicly.'}
        self.review_board=ReviewBoard(self)
        from .materials_workflow import MaterialsWorkflow
        self.materials=MaterialsWorkflow(self) if self.config['materials_workflow'] else None
        if (self.root/'exa-policy.json').exists():
            from .literature_r2 import R2LiteratureWorkflow
            self.literature=R2LiteratureWorkflow(self,exa_client)
        else:self.literature=LiteratureWorkflow(self,exa_client) if self.config['literature_enabled'] else None
        self.review_cycle=0
        from .entry_inputs import load_entry
        self.entry=load_entry(self.root)
        if self.entry and self.entry['input_mode']=='revise':
            raise Blocked('Existing paper must use the dedicated revision dispatcher, not the research controller')
        self.ideas=None
        if self.entry and self.entry['input_mode']=='idea':
            if not self.materials:raise Blocked('Idea mode requires complete materials preparation')
            from .idea_workflow import IdeaWorkflow
            self.ideas=IdeaWorkflow(self)
            if not self.demo and not self.literature:
                raise Blocked('Idea mode requires the complete literature pathway; use the online materials profile and frozen Exa policy, not a silent research bypass')
    def status(self,label):self.store.set('status',label)
    def check_deadline(self,*,research=False):
        if not self.config['deadline_iso']:return
        from datetime import datetime,timezone
        deadline=datetime.fromisoformat(self.config['deadline_iso'])
        if deadline.tzinfo is None:raise IntegrityError('Deadline requires timezone offset, normally +08:00')
        remaining=(deadline-datetime.now(timezone.utc)).total_seconds()
        if remaining<=0:raise DeadlineReached('Configured deadline has passed; no new live operations')
        if research and remaining<=self.config['paper_reserve_seconds']:raise PaperReserveReached('Paper time reserve reached; freeze research scope')
    def call(self,key,role,schema,packet,*,images=()):
        if schema in ('hypotheses','hypothesis_audit','hypothesis_audit_r2') and self.base.get('brief_source_contract'):
            packet={**packet,'original_problem_reading':self.base['problem_source_projection'],
                    'reading_status':'Checked source projection, not a literature citation or experimental result.'}
        if role in ('writer','abstract_editor') and getattr(self,'ideas',None):self.ideas.require_resolved('paper')
        if role in ('verifier_author','hypothesis_critic','idea_adversary'):
            return self.review_board.invoke(key,role,schema,packet,primary='claude',images=images)
        return self._call_one(key,role,schema,packet,provider_kind='codex',images=images)
    def _call_one(self,key,role,schema,packet,*,provider_kind,images=(),managed_failure=False):
        kind=provider_kind;provider=self.providers[kind]
        from .role_skills import freeze_role_skills
        skill_identity=freeze_role_skills(self.store,role,stage=packet.get('review_stage') if schema=='review' else None)
        if isinstance(provider,CLIProvider) and kind!='claude' and (schema=='review' or role=='hypothesis_critic'):
            provider=__import__('copy').copy(provider)
            provider.timeout=min(provider.timeout,self.config['review_timeout'])
        image_refs=[{'name':p.name,'sha256':file_hash(p)} for p in images]
        inputs={'role':role,'schema':schema,'packet':packet,'provider':kind,'model':getattr(provider,'model','FIXTURE'),'images':image_refs,'skill_digest':skill_identity}
        def invoke():
            self.check_deadline();count=self.store.get('model_calls_reserved',0)
            if count>=self.config['max_model_calls']:raise BudgetExhausted('Model-call budget exhausted; no success fabricated')
            self.store.set('model_calls_reserved',count+1)
            log=self.root/'model_calls'/digest({'key':key,'input':inputs})
            try:record=provider.invoke(role,schema,packet,log,images=images)
            except NeedsClarification as exc:
                receipt={**exc.receipt,'call_index':count+1,'response_digest':exc.signal['signal_digest'],
                         'model_execution_status':'NEEDS_CLARIFICATION'}
                write_json(log/'receipt.json',receipt)
                return {'needs_clarification':exc.signal,'receipt':receipt}
            except ProviderFailure as exc:
                if not managed_failure:
                    # Direct author calls keep the existing explicit recovery
                    # path. Only the board owns durable failure + retry cycles.
                    raise
                # A known terminated/probe failure is a durable outcome, not an
                # unknown RUNNING action. Retry/failover uses a new attempt key.
                raw=read_json(log/'process.json') if (log/'process.json').exists() else {}
                failure={'provider':exc.provider,'code':exc.code,'retryable':exc.retryable}
                receipt={**raw,'provider':kind,'role':role,'transport':raw.get('transport','PROBE_ONLY_NO_MODEL_RESPONSE'),
                    'invocation_id':raw.get('invocation_id',str(__import__('uuid').uuid4())),
                    'cli_version':raw.get('cli_version','NOT_AVAILABLE'),'model_requested':getattr(provider,'model',None) or 'CLI_DEFAULT',
                    'model_reported':raw.get('model_reported','UNREPORTED'),'packet_digest':digest(packet),
                    'prompt_sha256':raw.get('prompt_sha256','NOT_SENT'),'response_digest':digest(failure),
                    'model_execution_status':'NO_VALID_RESPONSE','call_index':count+1}
                write_json(log/'receipt.json',receipt);write_json(log/'failure.json',failure)
                return {'provider_failure':failure,'receipt':receipt}
            if record['receipt'].get('skill_digest')!=skill_identity:raise IntegrityError('Returned prompt skills differ from the frozen invocation')
            record['receipt']['call_index']=count+1
            write_json(log/'receipt.json',record['receipt'])
            self.store.memory(role,{'key':key,'input_digest':digest(inputs),'output_digest':digest(record['result']),
                                     'receipt':record['receipt'],'next_action':'consume explicit downstream contract'})
            return record
        record=self.store.step('model:'+key,inputs,invoke)
        if 'needs_clarification' in record:raise NeedsClarification(record['needs_clarification'],record['receipt'])
        if 'provider_failure' in record:
            failure=record['provider_failure']
            raise ProviderFailure(failure['provider'],failure['code'],retryable=failure['retryable'])
        return record
    def reviews(self,key,target,*,roles=('math_reviewer','experiment_reviewer'),context=None,images=(),stage='execution'):
        if stage not in REVIEW_STAGES:raise IntegrityError('Unknown review stage')
        from .review_stages import SOURCE_REVIEW_STAGES
        if stage!='problem_brief' and stage not in SOURCE_REVIEW_STAGES and self.base.get('brief_source_contract'):
            context={**(context or {}),'original_problem_reading':self.base['problem_source_projection'],
                     'reading_status':'Checked source projection; original frozen pages remain authoritative.'}
        packet={'problem':self.problem,'artifact':target,'target_digest':digest(target),
                'review_stage':stage,'stage_requirements':REVIEW_STAGES[stage],
                'required_check':'PASS only when all in-scope checks are supported; unresolved P0/P1 or unknown required checks must FAIL/BLOCK.',
                'context':context or {}}
        if stage in SOURCE_REVIEW_STAGES:
            packet.pop('problem')
            packet['original_problem_digest']=digest(self.problem)
        return self.review_board.review(key,packet,roles,images=images)
    def produce_reviewed(self,key,role,schema,packet,*,extra_review=None,entry=None):
        if getattr(self,'ideas',None):self.ideas.require_resolved('modeling' if role=='modeler' else 'code')
        feedback=[];latest_plan=None
        for attempt in range(self.config['repair_attempts']+1):
            # Snapshot feedback: previous prompts/receipts must never change as
            # new rounds are appended. Include only the latest prior plan once.
            repairs=__import__('copy').deepcopy(feedback)
            if repairs and latest_plan is not None:repairs[-1]['prior_artifact']=latest_plan
            full={**packet,'repair_feedback':repairs}
            diagnostic=None;artifact=None
            try:
                record=self.call(f'{key}:r{attempt}',role,schema,full);artifact=record['result']
                if entry and entry not in [f['path'] for f in artifact['files']]:raise IntegrityError('Required entrypoint missing: '+entry)
                if role=='modeler':
                    resource_gate(artifact,self.config)
                    if getattr(self,'ideas',None):self.ideas.align_plan(artifact)
                    if self.materials:
                        from .materials_contracts import check_plan_alignment
                        check_plan_alignment(artifact,self.base['materials_preparation'])
                        if any(q['disposition']=='REPLACE' for q in artifact['baseline_binding']['questions']):
                            self.reviews(f'{key}:r{attempt}:baseline-replacement',artifact,roles=('math_reviewer','experiment_reviewer'),stage='model_portfolio',context={'independent_portfolio':self.base['materials_preparation']['portfolio'],'required':'Independently assess each comparator replacement, its applicability and comparison strength. Reject unjustified weaker comparison. A prose assertion of equivalence is not proof.'})
                    if self.literature:
                        self.literature.repairing=attempt>0
                        self.literature.assess(artifact)
                if role=='coder' and 'plan' in packet:
                    from .baseline_binding import check_implementation
                    check_implementation(artifact,packet['plan'].get('baseline_binding'))
                review_context={k:self.base[k] for k in ('experiment_contract','source_registry','io_contract','limits','hypothesis_contract','materials_preparation','modeling_coverage_contract') if k in self.base}
                if 'plan' in packet:
                    review_context['plan']=packet['plan']
                    review_context['baseline_requirement']='Inspect actual baseline source paths and branch against the plan comparator. Metadata alone does not prove fidelity; reject weaker or missing implementations and require independent tests.'
                review_context.update(extra_review or {})
                if role=='verifier_author' and not self.demo:
                    diagnostic=self.verifier_preflight(artifact)
                    if diagnostic['passed'] is not True:raise Blocked('Verifier preflight failed; repair the exact implementation using supplied runtime evidence')
                    review_context['bounded_preflight']=diagnostic
                reviews=self.reviews(f'{key}:r{attempt}:review',artifact,context=review_context,
                                     stage='plan_design' if role=='modeler' else 'source_code')
                self.store.set(key,{'artifact_digest':self.store.put(artifact),'response_digest':record['receipt']['response_digest'],
                                     'review_target':digest(artifact),'attempt':attempt})
                return artifact,reviews
            except (ReviewUnavailable,ResearchUnavailable,ProviderFailure,NeedsClarification,PromptPacketTooLarge,InfrastructureUnavailable,UnknownExternalState,BudgetExhausted,DeadlineReached,PaperReserveReached):
                raise
            except (Blocked,IntegrityError) as e:
                literature_feedback={};failure=str(e)
                if role=='modeler' and artifact is not None:latest_plan=artifact
                if isinstance(e,LiteratureAssessmentFailure):
                    ref=self.store.put(e.diagnostic)
                    summary=e.repair_summary();failure=summary['validation_error']
                    literature_feedback={'literature_diagnostic':summary,'diagnostic_ref':ref}
                feedback.append({'attempt':attempt,'failure':failure,
                                 **literature_feedback,
                                 **({'prior_artifact':artifact,'runtime_diagnostic':diagnostic} if role=='verifier_author' and artifact else {})})
                self.store.event('REPAIR_REQUEST',{'key':key,'attempt':attempt,'failure':failure,
                    **({'diagnostic_ref':literature_feedback['diagnostic_ref']} if literature_feedback else {})})
        failures=[{k:r[k] for k in ('attempt','failure','diagnostic_ref') if k in r} for r in feedback]
        raise Blocked(f'{key} failed after bounded repairs: {failures}')
    def verifier_preflight(self,bundle):
        """Run a bounded verifier test BEFORE freezing it; never repair frozen code.

        Completed failed tests are evidence, not unknown processes. Each new
        source digest gets its own paths and step. Infrastructure failures and
        interrupted RUNNING steps propagate without an implicit retry.
        """
        from .verifier_preflight import run_preflight
        inputs={'verifier':digest(bundle),'development':digest(tree_manifest(self.root/'evaluation_inputs/development')),
                'limits':{k:self.config[k] for k in ('trial_timeout','cpu_threads','memory_mb','fe_budget')}}
        result=self.store.step('verifier-preflight:'+digest(inputs),inputs,
                              lambda:run_preflight(self.root,self.store,self.executor,self.config,bundle))
        verify_tree(self.root/result['output_path'],result['output_manifest'])
        return result
    def algorithm_context(self,bundle):
        for use in bundle['algorithm_usage']:
            if 'mosaic' in use['skill'].lower() and use['strategy'] in ('local24','refit32') and not self.config['allow_research_algorithms']:
                raise Blocked('Experimental MOSAIC branch requires explicit frozen opt-in')
        if not any('mosaic' in x['skill'].lower() for x in bundle['algorithm_usage']):return {}
        # Key deployed files are supplied verbatim to critical reviewers; the full
        # vendor manifest and source tree are preserved for human/reproduction audit.
        base=ROOT/'vendor/mosaic_v14'
        paths=['mosaic_solve.py','mosaic14/engine.py','mosaic14/fast.py','mosaic14/variants.py']
        return {'algorithm_version':'attached MOSAIC v14','sources':[{'path':p,'sha256':file_hash(base/p),'content':(base/p).read_text('utf-8')} for p in paths],
                'vendor_manifest_digest':file_hash(ROOT/'vendor/MANIFEST.json'),
                'scope_warning':'This packet does not reproduce every transitive dependency. Block when omitted code is essential to a claimed proof.'}
    def selftests(self,runner,verifier,answer_row):
        def action():
            base=self.root/'selftests'/digest({'v':digest(verifier),'job':answer_row['job_id']})
            code=self.store.publish_bundle(verifier);lim=Limits(self.config['trial_timeout'],self.config['cpu_threads'],self.config['memory_mb'])
            try:
                self.executor.execute(code,'test_solver.py',self.root/'evaluation_inputs/development',base/'out',
                    ['--seed',str(answer_row['seed']),'--budget',str(self.config['fe_budget']),'--variant',answer_row['variant']],lim,
                    answer=self.root/'jobs'/answer_row['job_id']/'solver',logdir=base/'logs')
                from .verifier_preflight import validate_tests
                report=validate_tests(read_json(base/'out/tests.json'))
            except (ExecutionFailure,ScientificRejection,IntegrityError,ValueError,OSError) as exc:
                return {'passed':False,'failure':str(exc),'output_path':str(base.relative_to(self.root)),
                        'output_manifest':tree_manifest(base)}
            return {'passed':True,'unit_tests':report,'negative_controls':runner.negative_controls(verifier),
                    'output_path':str((base/'out').relative_to(self.root)),'output_manifest':tree_manifest(base/'out')}
        result=self.store.step('independent-selftests:'+answer_row['job_id'],{'verifier':digest(verifier),'answer':answer_row['job_id']},action)
        verify_tree(self.root/result['output_path'],result['output_manifest'])
        if result['passed'] is not True:raise ScientificRejection('Independent tests failed or are incomplete: '+result['failure'])
        if self.literature:self.literature.require_tests(result['unit_tests'])
        return result
    def all_ai_records(self):
        from .entry_inputs import public_external_records
        records=public_external_records(self.root)
        for directory in sorted((self.root/'model_calls').glob('*')):
            if not directory.is_dir():continue
            if (directory/'receipt.json').exists():records.append(read_json(directory/'receipt.json'))
            elif (directory/'process.json').exists():
                r=read_json(directory/'process.json')
                r['response_digest']=r.get('stdout_sha256',digest('NO_RESPONSE'))
                r['model_execution_status']='FAILED_OR_UNKNOWN';records.append(r)
        return sorted(records,key=lambda x:(x.get('call_index',10**9),x['invocation_id']))
    def _run(self):
        self.store.audit()
        with self.store.connect() as c:
            pending_steps=[r['key'] for r in c.execute("SELECT key FROM steps WHERE status='RUNNING'")]
            pending_jobs=[r['id'] for r in c.execute("SELECT id FROM jobs WHERE status='RUNNING'")]
        if pending_steps or pending_jobs:
            raise UnknownExternalState('Unknown RUNNING work; reconcile external processes before explicit recovery: '
                          + str({'steps':pending_steps,'jobs':pending_jobs}))
        verify_vendor();backend=self.executor.probe()
        current_sources=read_json(self.root/'sources.json') if (self.root/'sources.json').exists() else []
        self.store.step('freeze-sources',{'sources':current_sources},lambda:current_sources)
        from .role_skills import skill_fingerprint
        fingerprint={'environment':environment(),'backend':backend,'role_skills':skill_fingerprint(),
            'core_source':{p.name:file_hash(p) for p in sorted((ROOT/'cumcm_harness').glob('*.py'))},
            'vendor_manifest':file_hash(ROOT/'vendor/MANIFEST.json')}
        old=self.store.get('runtime_fingerprint')
        if old is not None and old!=fingerprint:raise IntegrityError('Runtime/code changed since run start; create a fresh run for a new environment')
        if old is None:self.store.set('runtime_fingerprint',fingerprint)
        self.review_cycle=self.store.get('review_cycle',0)+1
        self.store.set('review_cycle',self.review_cycle)
        if not self.demo:
            # Production generation needs Codex. Optional Claude is checked
            # lazily by the board; it is never a startup single point of failure.
            self.providers['codex'].probe()
        if self.config.get('brief_pipeline','legacy')=='source-ledger-v1' and self.materials:
            # Source reading precedes both PI recommendations and paid literature
            # scouting. Later MaterialsWorkflow reuses the exact cached brief.
            # No imported idea, held-out reference or external search enters here.
            self.status('SOURCE_BRIEF')
            from .brief_workflow import BriefWorkflow
            from .materials_data import audit_development
            public=self.root/'inputs/development';manifest=tree_manifest(public)
            audit=self.store.step('materials:data-audit',{'manifest':manifest},lambda:audit_development(public))
            if audit['manifest']!=manifest or tree_manifest(public)!=manifest:raise IntegrityError('Source-stage data audit changed')
            self.base['source_brief']=BriefWorkflow(self).run({},audit)
        self.status('PLANNING')
        pi=self.call('pi-initial','supervisor','supervisor',self.base)['result']
        if self.literature:
            self.status('EXA_LITERATURE_AND_HYPOTHESES')
            self.literature.collect_initial(pi)
        if self.materials:
            self.status('MATERIALS_PREPARATION');self.materials.prepare(pi)
        plan,_=self.produce_reviewed('plan','modeler','plan',{**self.base,'pi_priorities':pi})
        self.store.step('resource-gate',{'plan':plan,'config':self.config},lambda:resource_gate(plan,self.config))
        if self.config['mode']=='contest':
            from .materials_workflow import plan_attestation_target
            items=[digest(plan)]+([digest(self.base['materials_preparation'])] if self.materials else [])
            p=approval.request(self.root,'plan',plan_attestation_target(plan,self.base),items,'Team must lead and verify the requirements, data policy and core model before implementation')
            self.status('WAITING_HUMAN_PLAN');approval.require(self.root,'plan',p,os.getenv('CUMCM_OPERATOR_KEY'))
        self.status('IMPLEMENTATION')
        verifier,_=self.produce_reviewed('verifier','verifier_author','bundle',{**self.base,'plan':plan},entry='evaluate.py')
        if 'test_solver.py' not in [f['path'] for f in verifier['files']]:raise Blocked('Independent verifier must also supply test_solver.py')
        protocol=self.store.step('freeze-protocol',{'plan':plan,'config':self.config,'intake':self.intake,'verifier':digest(verifier)},
               lambda:freeze_protocol(plan,self.config,self.intake,digest(verifier)))
        write_json(self.root/'protocol.json',protocol)
        runner=ResearchRunner(self.store,self.executor,self.config,protocol,plan)
        bundle,_=self.produce_reviewed('candidate:c0','coder','bundle',{**self.base,'plan':plan},extra_review={'independent_verifier':verifier},entry='main.py')
        # Mandatory source-level algorithm review is additional to general bundle review.
        self.reviews('algorithm:c0',{'bundle':bundle,'algorithm':self.algorithm_context(bundle)},context={'plan':plan,'verifier':verifier},stage='source_code')
        if self.demo:self.executor.trusted_hashes.update(digest({f['path']:__import__('hashlib').sha256(f['content'].encode()).hexdigest() for f in b['files']}) for b in (bundle,verifier))
        self.status('SMOKE_AND_TESTS')
        for runtime_attempt in range(self.config['repair_attempts']+1):
            try:
                if self.ideas:self.ideas.require_resolved('experiment')
                smoke=runner.cell('baseline',bundle,verifier,'development',protocol['development_seeds'][0],'baseline')
                tests=self.selftests(runner,verifier,smoke)
                self.reviews('smoke-review:'+digest(bundle),{'smoke':smoke,'tests':tests,'code':bundle,'verifier':verifier},context={'plan':plan})
                break
            except (ReviewUnavailable,ResearchUnavailable,InfrastructureUnavailable,UnknownExternalState,BudgetExhausted,DeadlineReached):
                raise
            except (Blocked,IntegrityError) as exc:
                # Never repair an unknown external process, evaluator, protocol or
                # confirmation data. Only a new producer bundle may be proposed.
                if runtime_attempt>=self.config['repair_attempts']:raise
                diagnostics=[]
                for logfile in sorted((self.root/'jobs').glob('*/solver_logs/stderr.log')):
                    text=logfile.read_text('utf-8',errors='replace')[-16000:]
                    if text:diagnostics.append({'file':str(logfile.relative_to(self.root)),'stderr':text})
                failure={'error':str(exc),'failed_bundle':digest(bundle),'diagnostics':diagnostics[-4:]}
                self.store.event('RUNTIME_REPAIR_REQUEST',failure)
                bundle,_=self.produce_reviewed(f'pilot-repair:{runtime_attempt}','coder','bundle',
                    {**self.base,'plan':plan,'prior_code':bundle,'runtime_failure':failure,
                     'immutable_verifier_digest':digest(verifier),'instruction':'Repair only the solver implementation. Do not modify the evaluator, metrics, inputs or protocol.'},
                    extra_review={'independent_verifier':verifier},entry='main.py')
                self.reviews('algorithm:pilot-repair:'+str(runtime_attempt),{'bundle':bundle,'algorithm':self.algorithm_context(bundle)},context={'plan':plan,'verifier':verifier},stage='source_code')
                if self.demo:self.executor.trusted_hashes.add(digest({f['path']:__import__('hashlib').sha256(f['content'].encode()).hexdigest() for f in bundle['files']}))
        bundles={'baseline':bundle,'c0':bundle}
        self.status('DEVELOPMENT')
        if self.ideas:self.ideas.require_resolved('experiment')
        baseline_rows=runner.matrix('baseline',bundle,verifier,'development',['baseline'])
        development=list(baseline_rows)
        current=bundle
        for index in range(self.config['max_candidates']):
            try:self.check_deadline(research=True)
            except PaperReserveReached as e:
                self.store.event('SEARCH_STOP',{'reason':str(e),'remaining_candidates_skipped':self.config['max_candidates']-index});break
            name=f'c{index}'
            if index:
                proposal=self.call(f'pi-proposal:{index}','supervisor','proposal',{
                    'plan':plan,'development_results':development,'frozen_evaluation_digest':digest(verifier),
                    'request':'Propose ONE falsifiable code change, or stop. You may not change metrics, seeds, data, budgets or verifier.'})['result']
                if proposal['stop']:
                    self.store.event('SEARCH_STOP',proposal);break
                current,_=self.produce_reviewed('candidate:'+name,'coder','bundle',
                    {**self.base,'plan':plan,'prior_code':current,'proposal':proposal,'development_results':development},
                    extra_review={'independent_verifier':verifier},entry='main.py')
                self.reviews('algorithm:'+name,{'bundle':current,'algorithm':self.algorithm_context(current)},context={'plan':plan,'verifier':verifier},stage='source_code')
                bundles[name]=current
                if self.demo:self.executor.trusted_hashes.add(digest({f['path']:__import__('hashlib').sha256(f['content'].encode()).hexdigest() for f in current['files']}))
            try:
                for variant in protocol['variants']:
                    pilot=runner.cell(name,current,verifier,'development',protocol['development_seeds'][0],variant)
                    self.selftests(runner,verifier,pilot)
                rows=runner.matrix(name,current,verifier,'development',protocol['variants'])
            except (InfrastructureUnavailable,UnknownExternalState,BudgetExhausted,DeadlineReached):raise
            except (ExecutionFailure,ScientificRejection,IntegrityError) as exc:
                self.store.event('CANDIDATE_REJECTED',{'candidate':name,'reason':str(exc),'bundle':digest(current),'raw_attempts_preserved':True})
                continue
            development.extend(rows)
            self.reviews('development:'+name,{'rows':rows,'baseline':baseline_rows,'bundle':current,'verifier':verifier,'protocol':protocol},context={'plan':plan})
            self.store.event('LESSON_CANDIDATE',{'candidate':name,'scope':protocol['scope'],'maturity':'DEVELOPMENT_ONLY',
                   'evidence':[r['job_id'] for r in rows],'negative_results_preserved':True,'promoted_to_global_skill':False})
        selection=self.store.step('freeze-selection',{'rows':development,'protocol':protocol},lambda:choose_development(development,protocol))
        write_json(self.root/'selection.json',selection);self.status('CONFIRMATION_FROZEN')
        winner=selection['winner'];confirm=runner.matrix('baseline',bundle,verifier,'confirmation',['baseline'])
        if winner!='baseline':confirm+=runner.matrix(winner,bundles[winner],verifier,'confirmation',['full'])
        b=[r['evaluation']['score'] for r in confirm if r['candidate']=='baseline']
        c=[r['evaluation']['score'] for r in confirm if r['candidate']==winner] if winner!='baseline' else b[:]
        inference=paired_effect(b,c,direction=protocol['direction'],seed=protocol['bootstrap_seed'],min_effect=protocol['min_effect'])
        inference['scope']=protocol['scope'];inference['winner_selected_before_confirmation']=winner
        self.store.step('confirmation-decision',{'selection':selection,'rows':confirm},lambda:inference)
        write_json(self.root/'confirmation.json',{'rows':confirm,'inference':inference})
        self.reviews('confirmation-review',{'rows':confirm,'inference':inference,'selection':selection,'protocol':protocol},context={'plan':plan})
        from .paper import claim_registry,build_paper,render_pages,build_ai_details
        claims,representative=claim_registry(confirm,selection,inference);write_json(self.root/'claims.json',claims)
        if self.literature and hasattr(self.literature,'final_verify'):self.literature.final_verify()
        self.status('WRITING')
        source_registry=self.base.get('source_registry',[])
        self.store.step('freeze-paper-sources',{'sources':source_registry},lambda:source_registry)
        packet={'materials_preparation':self.base.get('materials_preparation'),
                'hypothesis_contract':self.base.get('hypothesis_contract'),
                'hypothesis_execution':read_json(self.root/'literature/execution.json') if (self.root/'literature/execution.json').exists() else None,
                'problem':self.problem,'plan':plan,'claims':claims,'inference':inference,'selection':selection,
                'source_registry':source_registry,'scope':protocol['scope'],'demo':self.demo,
                'question_evidence':[{'job_id':r['job_id'],'evidence':r['evaluation'].get('question_evidence',[])} for r in confirm],
                'requirements':'Chinese text; first section 问题重述. All empirical numbers use {{claim:ID}}; mathematical constants use equation fields. Do not invent citations. This research is NOT a claim of global superiority.'}
        feedback=[];built=None;draft=None;rejected_hashes=set();attempted_drafts=set()
        for attempt in range(self.config['repair_attempts']+1):
            record=self.call(f'paper:r{attempt}','writer','paper',{**packet,'repair_feedback':feedback});draft=record['result']
            if digest(draft) in attempted_drafts:
                feedback.append({'error':'Writer repeated a failed draft; produce a substantive revision.','draft_digest':digest(draft)})
                self.store.event('PAPER_DUPLICATE_DRAFT_REJECTED',{'attempt':attempt,'draft_digest':digest(draft)})
                continue
            attempted_drafts.add(digest(draft))
            folder=self.root/'paper_versions'/digest(draft);materials_context=None
            def compile_draft():
                try:return build_paper(self.root,draft,claims,confirm,ai_records=self.all_ai_records(),code_bundles={**bundles,'verifier':verifier},source_registry=source_registry,demo=self.demo,build_dir=folder,materials=materials_context)
                except (PaperCompilationFailure,IntegrityError) as exc:
                    return {'observed_build_failure':True,'error':str(exc),'error_type':type(exc).__name__}
            try:
                if self.materials:
                    draft,materials_context=self.materials.prepare_paper(draft,plan,claims,packet['question_evidence'],attempt)
                    folder=self.root/'paper_versions'/digest(draft)
                candidate=self.store.step(f'paper-build:r{attempt}',{'draft':draft,'claims':claims,'rows':confirm,'bundles':bundles,'verifier':digest(verifier),'sources':source_registry,'materials':materials_context},
                    compile_draft)
                if candidate.get('observed_build_failure'):raise PaperCompilationFailure(candidate['error'])
                if file_hash(folder/'main.pdf')!=candidate['paper_sha256']:raise IntegrityError('Frozen PDF was changed')
                if candidate['paper_sha256'] in rejected_hashes:raise ScientificRejection('Writer repeated a rejected PDF; revise the artifact')
                n=candidate['preflight']['body_pages']+1;total=candidate['preflight']['pages']
                pages=render_pages(folder/'main.pdf',folder/'rendered',page_indices=list(range(min(n+1,total)))+[total-1])
                negatives=[]
                for j in range(0,len(pages),6):
                    batch=pages[j:j+6]
                    try:
                        self.reviews(f'paper-visual:{attempt}:{j//6}',{'draft':draft,'claims':claims,'pdf_sha256':candidate['paper_sha256'],
                            'preflight':candidate['preflight'],'pages':[p.name for p in batch],
                            'appendix_policy':'Body plus sampled appendix; full appendix requires human review.'},roles=('paper_reviewer',),images=batch)
                    except ScientificRejection as exc:negatives.append({'error':str(exc),'records':list(exc.records)})
                if negatives:
                    rejected_hashes.add(candidate['paper_sha256'])
                    raise ScientificRejection('Compiled paper rejected by independent review',records=negatives)
                self.store.event('PAPER_VISUAL_SCOPE',{'body_pages':n,'image_pages':[p.name for p in pages],'full_appendix_human_review_required':True})
                built=candidate
                # Immutable versions retain every draft, PDF and review. Publish
                # only the accepted projection consumed by packaging.
                import shutil
                destination=self.root/'paper'
                if destination.exists():
                    if not (destination/'main.pdf').exists() or file_hash(destination/'main.pdf')!=built['paper_sha256']:raise IntegrityError('Paper projection conflicts with accepted version')
                else:shutil.copytree(folder,destination)
                break
            except (ScientificRejection,PaperCompilationFailure,IntegrityError) as exc:
                feedback.append({'error':str(exc),'prior_draft':draft,'records':list(getattr(exc,'records',()))})
                self.store.event('PAPER_REPAIR',{'attempt':attempt,'error':str(exc),'draft_digest':digest(draft)})
        if not built:raise ScientificRejection('Paper did not pass build and review within repair budget')
        self.status('RELEASE_REVIEW')
        records=self.all_ai_records();human=None
        release_target=digest({'paper':built['paper_sha256'],'claims':digest(claims),'protocol':digest(protocol),'records':[r['response_digest'] for r in records]})
        if self.config['mode']=='contest':
            pending=approval.request(self.root,'release',release_target,[r['response_digest'] for r in records],
                        'Review adoption/modification/verification for every AI output and visually check the whole PDF')
            self.status('WAITING_HUMAN_RELEASE');human=approval.require(self.root,'release',pending,os.getenv('CUMCM_OPERATOR_KEY'))
        ai=self.store.step('ai-details-build',{'records':records,'human':human,'demo':self.demo},
            lambda:build_ai_details(self.root/'paper',records,human,demo=self.demo))
        if file_hash(self.root/'paper'/ai['path'])!=ai['sha256']:raise IntegrityError('AI details PDF changed after build')
        from .packaging import package_workspace
        package=package_workspace(self.root,built,claims,protocol,confirm,records,ai,contest=self.config['mode']=='contest',human=human)
        from .submission_manifest import seal_deliverables
        submission=seal_deliverables(self.root,package,self.config['mode'])
        status='DEMO_COMPLETE_NOT_LIVE_VALIDATED' if self.demo else ('CONTEST_REVIEWED_LOCAL_PACKAGE' if self.config['mode']=='contest' else 'PRACTICE_COMPLETE_HUMAN_REVIEW_REQUIRED')
        result={'status':status,'materials_workflow':bool(self.materials),'submission_manifest':submission,'live_llm_calls':not self.demo,'plan_digest':digest(plan),'verifier_digest':digest(verifier),
                'development_cells':len(development),'confirmation_cells':len(confirm),'selection':selection,'inference':inference,
                'paper':built,'package':package,'world_best_claim':'NOT_ESTABLISHED','auto_submission':False,
                'review_failovers':[__import__('json').loads(e['payload']) for e in self.store.events() if e['kind']=='PROVIDER_FAILOVER'],
                'literature_status':self.literature.accepted['retrieval'] if self.literature and self.literature.accepted else 'DISABLED_EXPLICITLY'}
        write_json(self.root/'run_summary.json',result);self.status(status);self.store.audit();return result
    def run(self):
        with controller_lock(self.root):
            try:return self._run()
            except Exception as e:
                self.store.event('BLOCKER',{'type':type(e).__name__,'message':str(e)});self.status('WAITING_REVIEW_PROVIDERS' if isinstance(e,ReviewUnavailable) else getattr(e,'status','WAITING_RESEARCH_PROVIDER') if isinstance(e,ResearchUnavailable) else getattr(e,'status','BLOCKED'))
                write_json(self.root/'blocker.json',{'type':type(e).__name__,'message':str(e),'completed_artifacts_preserved':True})
                raise
