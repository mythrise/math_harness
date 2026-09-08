"""Executable end-to-end research DAG. LLMs propose; deterministic contracts and
independent reviewers decide whether artifacts may advance. No automatic contest
submission exists. Recovery replays completed receipts rather than conversation.
"""
from __future__ import annotations
import os, shutil
from pathlib import Path
from .common import *
from .contracts import validate, SCHEMAS
from .store import Store,controller_lock
from .providers import CLIProvider,review_quorum
from .sandbox import Executor,Limits,resource_gate
from .intake import verify_inputs
from .research import ResearchRunner,freeze_protocol,choose_development,paired_effect
from .algorithms import route_methods
from . import approval
from .review_board import ReviewBoard, ProviderFailure, ReviewUnavailable
from .literature import LiteratureWorkflow, ResearchUnavailable

DEFAULT_CONFIG={
 'mode':'practice','workers':2,'cpu_threads':1,'total_cpu_threads':2,'memory_mb':2048,'total_memory_mb':4096,
 'trial_timeout':120,'fe_budget':192,'development_seeds':[101,202,303],
 'confirmation_seeds':[701,702,703,704,705],'bootstrap_seed':41821,
 'max_candidates':2,'repair_attempts':2,'max_model_calls':180,'model_timeout':600,'claude_call_budget_usd':None,
 'codex_model':None,'claude_model':'claude-fable-5','docker_image':'cumcm-egoharness:0.1.0',
 'allow_research_algorithms':False,'deadline_iso':None,'paper_reserve_seconds':7200,
 'identity_denylist':[],'input_data_origin':'include-in-support','network_policy':'LOCAL_EVIDENCE_ONLY',
 'review_members_per_role':2,'review_attempts_per_provider':2,'review_cooldown_seconds':60,
 'review_backoff_seconds':0.25,'review_timeout':180,
 'literature_enabled':False,'exa_timeout':35,'exa_results_per_query':4,'exa_max_requests':32,'exa_approved_queries':[]}

IO_CONTRACT={
 'solver_entry':'main.py --input PUBLIC_DATA_DIR --out EMPTY_OUTPUT_DIR --seed INT --budget INT --variant ID',
 'solver_outputs':'answer.json plus any raw predictions/tables needed. Budget is an upper bound on expensive model/objective calls; record exact counts honestly. All plan variants must be implemented.',
 'evaluator_entry':'evaluate.py --input EVAL_DATA_DIR --answer SOLVER_OUTPUT_DIR --out EMPTY_OUTPUT_DIR --seed INT --budget INT --variant ID',
 'evaluator_layout':'EVAL_DATA_DIR/public contains the public phase data; EVAL_DATA_DIR/private contains optional hidden reference labels. Solver never mounts private data.',
 'evaluator_output':'evaluation.json with the supplied evaluation schema. Recompute objective and constraints; never trust score reported by solver. Explicitly return valid=false for malformed answers, rather than crashing.',
 'test_entry':'test_solver.py uses evaluator arguments and writes tests.json: {"cases":[{"name":"...","passed":true,"detail":"..."}],"all_passed":true}. At least three substantive distinct tests, including a deliberately wrong answer and a boundary case.',
 'verifier_preflight_entry':'The independent verifier bundle must ALSO include test_evaluator.py --input EVAL_DATA_DIR --out EMPTY_OUTPUT_DIR --seed INT --budget INT --variant ID. It runs without a solver answer BEFORE evaluator freeze. Write tests.json with at least three distinct substantive cases, all_passed and per-case name/passed/detail. Exercise actual evaluator primitives with analytically known positive, negative and boundary inputs; include array-shape/indexing and direction conventions when applicable. Do not run optimization or the full-size field in this bounded preflight. The controller separately tests missing, malformed and fabricated answers. A failing preflight is returned to the author with exact source and execution logs; passing it does not certify full numerical accuracy.',
 'environment':'Python 3.11+, numpy, scipy, pandas, scikit-learn, numba, matplotlib, jsonschema. Do not install packages or use network in trials.',
 'filesystem':'Only the output directory and ephemeral /tmp are writable. Code/input data are read-only. Do not write pycache under /code; use PYTHONDONTWRITEBYTECODE / in-memory work.',
 'custom_algorithm':'from cumcm_harness.algorithms import mosaic_solve, mosaic_modules. Attached algorithm is already installed. Do not retype or replace MOSAIC with a generic GA.'}

REVIEW_STAGES={
 'plan_design':{
  'certifies_execution':False,
  'scope':'Review the prospective mathematical model and executable experimental specification before code exists.',
  'required':'Check derivations, dimensions, explicit assumptions, decoder construction, objective fidelity, frozen budgets/seeds, resource strategy, test design and measurable acceptance criteria. Missing definitions or unsupported mathematical claims remain P0/P1.',
  'boundary':'Do not require future solver runs, measured convergence, profiling or final paper artifacts to exist at this gate. Require the plan to specify how they will be tested and blocked on failure. PASS authorizes implementation only; it does not certify numerical correctness, runtime feasibility or scientific results.'},
 'source_code':{
  'certifies_execution':False,
  'scope':'Review exact implementation source before scientific experiments. Supplied bounded preflight receipts are real execution evidence for those tests only.',
  'required':'Check mathematical fidelity, executable interfaces, algorithm applicability, FE accounting, adversarial tests and evaluator independence. Missing essential source or an identifiable defect remains blocking.',
  'boundary':'Distinguish static source evidence, any supplied preflight receipts, and future scientific execution. A known failing preflight remains blocking. Do not demand future field/solver receipts here. PASS authorizes the bounded pilot only; later experiment gates still require actual successful execution.'},
 'execution':{
  'certifies_execution':True,
  'scope':'Review actual execution evidence for the current completed stage.',
  'required':'Require real outputs, independent checks and receipts for every in-scope empirical claim. Proposed tests or source alone are not evidence of passing. Missing required execution, unknown checks, invalid measurements and unsupported claims must FAIL/BLOCK.',
  'boundary':'Do not infer later-stage completion or waive P0/P1. Review only the supplied stage; paper completion still requires actual compilation and visual review.'}}

def validate_config(c):
    if set(c)!=set(DEFAULT_CONFIG):raise IntegrityError('Unexpected/missing configuration keys')
    if c['mode'] not in ('practice','contest'):raise IntegrityError('Invalid mode')
    for key in ('workers','cpu_threads','total_cpu_threads','memory_mb','total_memory_mb','trial_timeout','fe_budget','max_candidates','repair_attempts','max_model_calls','model_timeout'):
        if not isinstance(c[key],(int,float)) or isinstance(c[key],bool) or c[key]<=0:raise IntegrityError('Invalid config '+key)
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
                        'claude':fixture_provider or CLIProvider('claude',model=self.config['claude_model'],timeout=self.config['model_timeout'],max_budget_usd=self.config['claude_call_budget_usd'])}
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
        self.literature=LiteratureWorkflow(self,exa_client) if self.config['literature_enabled'] else None
        self.review_cycle=0
    def status(self,label):self.store.set('status',label)
    def check_deadline(self,*,research=False):
        if not self.config['deadline_iso']:return
        from datetime import datetime,timezone
        deadline=datetime.fromisoformat(self.config['deadline_iso'])
        if deadline.tzinfo is None:raise IntegrityError('Deadline requires timezone offset, normally +08:00')
        remaining=(deadline-datetime.now(timezone.utc)).total_seconds()
        if remaining<=0:raise Blocked('Configured deadline has passed; no new live operations')
        if research and remaining<=self.config['paper_reserve_seconds']:raise Blocked('Paper time reserve reached; freeze research scope')
    def call(self,key,role,schema,packet,*,images=()):
        if role in ('verifier_author','hypothesis_critic'):
            return self.review_board.invoke(key,role,schema,packet,primary='claude',images=images)
        return self._call_one(key,role,schema,packet,provider_kind='codex',images=images)
    def _call_one(self,key,role,schema,packet,*,provider_kind,images=(),managed_failure=False):
        kind=provider_kind;provider=self.providers[kind]
        if isinstance(provider,CLIProvider) and (schema=='review' or role=='hypothesis_critic'):
            provider=__import__('copy').copy(provider)
            provider.timeout=min(provider.timeout,self.config['review_timeout'])
        image_refs=[{'name':p.name,'sha256':file_hash(p)} for p in images]
        inputs={'role':role,'schema':schema,'packet':packet,'provider':kind,'model':getattr(provider,'model','FIXTURE'),'images':image_refs}
        def invoke():
            self.check_deadline();count=self.store.get('model_calls_reserved',0)
            if count>=self.config['max_model_calls']:raise Blocked('Model-call budget exhausted; no success fabricated')
            self.store.set('model_calls_reserved',count+1)
            log=self.root/'model_calls'/digest({'key':key,'input':inputs})
            try:record=provider.invoke(role,schema,packet,log,images=images)
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
            record['receipt']['call_index']=count+1
            write_json(log/'receipt.json',record['receipt'])
            self.store.memory(role,{'key':key,'input_digest':digest(inputs),'output_digest':digest(record['result']),
                                     'receipt':record['receipt'],'next_action':'consume explicit downstream contract'})
            return record
        record=self.store.step('model:'+key,inputs,invoke)
        if 'provider_failure' in record:
            failure=record['provider_failure']
            raise ProviderFailure(failure['provider'],failure['code'],retryable=failure['retryable'])
        return record
    def reviews(self,key,target,*,roles=('math_reviewer','experiment_reviewer'),context=None,images=(),stage='execution'):
        if stage not in REVIEW_STAGES:raise IntegrityError('Unknown review stage')
        packet={'problem':self.problem,'artifact':target,'target_digest':digest(target),
                'review_stage':stage,'stage_requirements':REVIEW_STAGES[stage],
                'required_check':'PASS only when all in-scope checks are supported; unresolved P0/P1 or unknown required checks must FAIL/BLOCK.',
                'context':context or {}}
        return self.review_board.review(key,packet,roles,images=images)
    def produce_reviewed(self,key,role,schema,packet,*,extra_review=None,entry=None):
        feedback=[]
        for attempt in range(self.config['repair_attempts']+1):
            full={**packet,'repair_feedback':feedback}
            diagnostic=None;artifact=None
            try:
                record=self.call(f'{key}:r{attempt}',role,schema,full);artifact=record['result']
                if entry and entry not in [f['path'] for f in artifact['files']]:raise IntegrityError('Required entrypoint missing: '+entry)
                if role=='modeler':
                    resource_gate(artifact,self.config)
                    if self.literature:self.literature.assess(artifact)
                review_context={k:self.base[k] for k in ('experiment_contract','source_registry','io_contract','limits','hypothesis_contract') if k in self.base}
                if 'plan' in packet:review_context['plan']=packet['plan']
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
            except (ReviewUnavailable,ResearchUnavailable):
                raise
            except (Blocked,IntegrityError) as e:
                feedback.append({'attempt':attempt,'failure':str(e),
                                 **({'prior_artifact':artifact,'runtime_diagnostic':diagnostic} if role=='verifier_author' and artifact else {})})
                self.store.event('REPAIR_REQUEST',{'key':key,'attempt':attempt,'failure':str(e)})
                # Missing infrastructure cannot be repaired by inventing LLM responses.
                if any(x in str(e) for x in ('NOT_INSTALLED','budget exhausted','lacks required CLI','deadline','RUNNING',
                                            'Docker','Output directory is not empty','claude failed','codex failed')):raise
        raise Blocked(f'{key} failed after bounded repairs: {feedback}')
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
            self.executor.execute(code,'test_solver.py',self.root/'evaluation_inputs/development',base/'out',
                ['--seed',str(answer_row['seed']),'--budget',str(self.config['fe_budget']),'--variant','baseline'],lim,
                answer=self.root/'jobs'/answer_row['job_id']/'solver',logdir=base/'logs')
            report=read_json(base/'out/tests.json');cases=report.get('cases',[])
            if len(cases)<3 or len({x['name'] for x in cases})!=len(cases) or report.get('all_passed') is not True or any(x.get('passed') is not True for x in cases):
                raise Blocked('Independent tests failed or are incomplete')
            return {'unit_tests':report,'negative_controls':runner.negative_controls(verifier),'output_path':str((base/'out').relative_to(self.root)),'output_manifest':tree_manifest(base/'out')}
        result=self.store.step('independent-selftests:'+answer_row['job_id'],{'verifier':digest(verifier),'answer':answer_row['job_id']},action)
        verify_tree(self.root/result['output_path'],result['output_manifest'])
        if self.literature:self.literature.require_tests(result['unit_tests'])
        return result
    def all_ai_records(self):
        records=[]
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
            raise Blocked('Unknown RUNNING work; reconcile external processes before explicit recovery: '
                          + str({'steps':pending_steps,'jobs':pending_jobs}))
        verify_vendor();backend=self.executor.probe()
        current_sources=read_json(self.root/'sources.json') if (self.root/'sources.json').exists() else []
        self.store.step('freeze-sources',{'sources':current_sources},lambda:current_sources)
        fingerprint={'environment':environment(),'backend':backend,
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
        self.status('PLANNING')
        pi=self.call('pi-initial','supervisor','supervisor',self.base)['result']
        if self.literature:
            self.status('EXA_LITERATURE_AND_HYPOTHESES')
            self.literature.collect_initial(pi)
        plan,_=self.produce_reviewed('plan','modeler','plan',{**self.base,'pi_priorities':pi})
        self.store.step('resource-gate',{'plan':plan,'config':self.config},lambda:resource_gate(plan,self.config))
        if self.config['mode']=='contest':
            p=approval.request(self.root,'plan',digest(plan),[digest(plan)],'Team must lead and verify core model before implementation')
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
                smoke=runner.cell('baseline',bundle,verifier,'development',protocol['development_seeds'][0],'baseline')
                tests=self.selftests(runner,verifier,smoke)
                self.reviews('smoke-review:'+digest(bundle),{'smoke':smoke,'tests':tests,'code':bundle,'verifier':verifier},context={'plan':plan})
                break
            except (ReviewUnavailable,ResearchUnavailable):
                raise
            except (Blocked,IntegrityError) as exc:
                # Never repair an unknown external process, evaluator, protocol or
                # confirmation data. Only a new producer bundle may be proposed.
                if runtime_attempt>=self.config['repair_attempts'] or any(x in str(exc) for x in ('NOT_INSTALLED','RUNNING','budget exhausted','required','RESOURCE_GATE')):raise
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
        baseline_rows=runner.matrix('baseline',bundle,verifier,'development',['baseline'])
        development=list(baseline_rows)
        current=bundle
        for index in range(self.config['max_candidates']):
            try:self.check_deadline(research=True)
            except Blocked as e:
                if 'Paper time reserve' in str(e):
                    self.store.event('SEARCH_STOP',{'reason':str(e),'remaining_candidates_skipped':self.config['max_candidates']-index});break
                raise
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
            try:rows=runner.matrix(name,current,verifier,'development',protocol['variants'])
            except (Blocked,IntegrityError) as exc:
                if 'RUNNING' in str(exc):raise
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
        self.status('WRITING')
        source_registry=self.base.get('source_registry',[])
        self.store.step('freeze-paper-sources',{'sources':source_registry},lambda:source_registry)
        packet={'hypothesis_contract':self.base.get('hypothesis_contract'),
                'hypothesis_execution':read_json(self.root/'literature/execution.json') if (self.root/'literature/execution.json').exists() else None,
                'problem':self.problem,'plan':plan,'claims':claims,'inference':inference,'selection':selection,
                'source_registry':source_registry,'scope':protocol['scope'],'demo':self.demo,
                'requirements':'Chinese text; first section 问题重述. All empirical numbers use {{claim:ID}}; mathematical constants use equation fields. Do not invent citations. This research is NOT a claim of global superiority.'}
        feedback=[];built=None;draft=None
        for attempt in range(self.config['repair_attempts']+1):
            record=self.call(f'paper:r{attempt}','writer','paper',{**packet,'repair_feedback':feedback});draft=record['result']
            try:
                built=self.store.step(f'paper-build:r{attempt}',{'draft':draft,'claims':claims,'rows':confirm,'bundles':bundles,'verifier':digest(verifier),'sources':source_registry},
                    lambda:build_paper(self.root,draft,claims,confirm,ai_records=self.all_ai_records(),code_bundles={**bundles,'verifier':verifier},source_registry=source_registry,demo=self.demo))
                if file_hash(self.root/'paper/main.pdf')!=built['paper_sha256']:raise IntegrityError('Frozen PDF was changed')
                break
            except (IntegrityError,Blocked) as e:
                feedback.append(str(e));self.store.event('PAPER_REPAIR',{'attempt':attempt,'error':str(e)})
        if not built:raise Blocked('Paper build did not pass within repair budget')
        # Review all body pages; appendices are code-bound, mechanically checked,
        # and remain subject to explicit human full-document visual attestation.
        n=built['preflight']['body_pages']+1
        total_pages=built['preflight']['pages']
        indices=list(range(min(n+1,total_pages)))+[total_pages-1]
        selected_pages=render_pages(self.root/'paper/main.pdf',self.root/'paper/rendered',page_indices=indices)
        visual=[]
        for j in range(0,len(selected_pages),6):
            batch=selected_pages[j:j+6]
            visual+=self.reviews(f'paper-visual:{j//6}',{'draft':draft,'claims':claims,'pdf_sha256':built['paper_sha256'],
                   'preflight':built['preflight'],'pages':[p.name for p in batch],
                   'appendix_policy':'Full custom source included and hashed. These images cover body + sampled appendix, not a claim of model visual review of every appendix page.'},
                   roles=('paper_reviewer',),images=batch)
        self.store.event('PAPER_VISUAL_SCOPE',{'body_pages':n,'image_pages':[p.name for p in selected_pages],'full_appendix_human_review_required':True})
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
        status='DEMO_COMPLETE_NOT_LIVE_VALIDATED' if self.demo else ('CONTEST_REVIEWED_LOCAL_PACKAGE' if self.config['mode']=='contest' else 'PRACTICE_COMPLETE_HUMAN_REVIEW_REQUIRED')
        result={'status':status,'live_llm_calls':not self.demo,'plan_digest':digest(plan),'verifier_digest':digest(verifier),
                'development_cells':len(development),'confirmation_cells':len(confirm),'selection':selection,'inference':inference,
                'paper':built,'package':package,'world_best_claim':'NOT_ESTABLISHED','auto_submission':False,
                'review_failovers':[__import__('json').loads(e['payload']) for e in self.store.events() if e['kind']=='PROVIDER_FAILOVER'],
                'literature_status':self.literature.accepted['retrieval'] if self.literature and self.literature.accepted else 'DISABLED_EXPLICITLY'}
        write_json(self.root/'run_summary.json',result);self.status(status);self.store.audit();return result
    def run(self):
        with controller_lock(self.root):
            try:return self._run()
            except Exception as e:
                self.store.event('BLOCKER',{'type':type(e).__name__,'message':str(e)});self.status('WAITING_REVIEW_PROVIDERS' if isinstance(e,ReviewUnavailable) else 'WAITING_RESEARCH_PROVIDER' if isinstance(e,ResearchUnavailable) else 'BLOCKED')
                write_json(self.root/'blocker.json',{'type':type(e).__name__,'message':str(e),'completed_artifacts_preserved':True})
                raise
