"""Immutable experimental protocol, deterministic selection and honest inference."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from .common import *
from .contracts import validate
from .sandbox import Limits

def freeze_protocol(plan,config,intake,evaluator_digest):
    dev=config['development_seeds'];confirm=config['confirmation_seeds']
    if len(dev)!=len(set(dev)) or len(confirm)!=len(set(confirm)) or set(dev)&set(confirm):raise IntegrityError('Seeds must be unique and disjoint')
    if not dev or not confirm or any(type(s)!=int or s<0 for s in dev+confirm):raise IntegrityError('Invalid seeds')
    p={'metric':plan['primary_metric'],'direction':plan['direction'],'min_effect':plan['min_effect'],
       'development_seeds':dev,'confirmation_seeds':confirm,'fe_budget':config['fe_budget'],
       'evaluator_digest':evaluator_digest,'bootstrap_seed':config['bootstrap_seed'],'bootstrap_replicates':5000,
       'scope':intake['confirmation_scope'],'max_candidates':config['max_candidates'],
       'variants':['full']+[x['id'] for x in plan['ablations']+plan['sensitivity']],
       'intake_digest':digest(intake),'config_digest':digest(config),'plan_digest':digest(plan),
       'selection':'development only; baseline remains immutable','inference':'one pre-registered selected-vs-baseline confirmation; other variants descriptive'}
    return p

def paired_effect(baseline,candidate,*,direction='maximize',seed=1729,min_effect=0.,reps=5000):
    b=np.asarray(baseline,float);c=np.asarray(candidate,float)
    if b.shape!=c.shape or b.ndim!=1 or not len(b) or not np.isfinite(b).all() or not np.isfinite(c).all():raise IntegrityError('Invalid paired samples')
    d=(c-b)*(1 if direction=='maximize' else -1);mean=float(d.mean())
    if len(d)<5:return {'decision':'INCONCLUSIVE','n':len(d),'mean_improvement':mean,'ci95':None,'reason':'fewer than five paired replication units'}
    rng=np.random.default_rng(seed);boot=d[rng.integers(0,len(d),(reps,len(d)))].mean(axis=1);lo,hi=np.quantile(boot,[.025,.975])
    decision='KEEP_CANDIDATE' if lo>min_effect else ('RETAIN_BASELINE' if hi<0 else 'INCONCLUSIVE')
    return {'decision':decision,'n':len(d),'mean_improvement':mean,'ci95':[float(lo),float(hi)],
            'reason':'percentile paired bootstrap; applies only to declared replication unit, not a universal claim'}

def choose_development(rows,protocol):
    # Require the entire pre-registered matrix; no cherry-picking missing trials.
    scores={}
    for candidate in sorted({r['candidate'] for r in rows}):
        selected=[r for r in rows if r['candidate']==candidate and r['variant'] in ('full','baseline')]
        seeds=[r['seed'] for r in selected]
        if sorted(seeds)!=sorted(protocol['development_seeds']):raise IntegrityError('Incomplete/duplicate development matrix')
        if not all(r['evaluation']['valid'] for r in selected):raise Blocked('Invalid development candidate cannot be selected')
        scores[candidate]=float(np.mean([r['evaluation']['score'] for r in selected]))
    if 'baseline' not in scores:raise IntegrityError('Missing baseline')
    sign=1 if protocol['direction']=='maximize' else -1
    # Baseline wins exact ties, then stable lexical order.
    winner=sorted(scores,key=lambda k:(-sign*scores[k],k!='baseline',k))[0]
    if sign*(scores[winner]-scores['baseline'])<=protocol['min_effect']:winner='baseline'
    return {'winner':winner,'development_means':scores,'protocol_digest':digest(protocol),'confirmation_seen':False}

class ResearchRunner:
    def __init__(self,store,executor,config,protocol,plan):
        self.store=store;self.executor=executor;self.config=config;self.protocol=protocol;self.plan=plan
    def cell(self,candidate,bundle,verifier,phase,seed,variant):
        root=self.store.root;code=self.store.publish_bundle(bundle);evaluation=self.store.publish_bundle(verifier)
        data=root/'inputs'/phase;edata=root/'evaluation_inputs'/phase
        intent={'candidate':candidate,'code':digest(bundle),'evaluation':digest(verifier),'phase':phase,'seed':seed,'variant':variant,
                'protocol':digest(self.protocol),'data':digest(tree_manifest(data)),
                'environment':digest(environment()),'backend':self.executor.probe()}
        job_id=digest(intent);base=root/'jobs'/job_id
        prior=self.store.job(job_id)
        if prior:
            if prior['status']!='DONE':raise Blocked(f'Job {job_id} is {prior["status"]}; reconcile explicitly, never duplicate silently')
            receipt=__import__('json').loads(prior['receipt'])
            verify_tree(base/'solver',receipt['solver']['output_manifest']);verify_tree(base/'evaluation',receipt['evaluator']['output_manifest'])
            if receipt['intent']!=intent:raise IntegrityError('Job intent changed')
            if not receipt['result']['evaluation']['valid']:raise Blocked('Cached evaluator rejection remains a rejection')
            return receipt['result']
        token=self.store.grant(job_id,intent);self.store.consume(token,job_id)
        lim=Limits(seconds=self.config['trial_timeout'],cpu_threads=self.config['cpu_threads'],memory_mb=self.config['memory_mb'])
        args=['--seed',str(seed),'--budget',str(self.protocol['fe_budget']),'--variant',variant]
        try:
            sr=self.executor.execute(code,'main.py',data,base/'solver',args,lim,logdir=base/'solver_logs')
            if not (base/'solver/answer.json').is_file():raise IntegrityError('Solver must publish answer.json')
            er=self.executor.execute(evaluation,'evaluate.py',edata,base/'evaluation',args,lim,answer=base/'solver',logdir=base/'eval_logs')
        except (Blocked,IntegrityError) as exc:
            self.store.fail_job(job_id,f'{type(exc).__name__}: {exc}');raise
        ev=validate('evaluation',read_json(base/'evaluation/evaluation.json'))
        if ev['metric']!=self.protocol['metric']:raise IntegrityError('Evaluator changed primary metric')
        if set(ev['question_coverage'])!=set(q['id'] for q in self.plan['questions']):raise IntegrityError('Incomplete subquestion coverage')
        result={'candidate':candidate,'variant':variant,'phase':phase,'seed':seed,'job_id':job_id,
                'evaluation':ev,'code_digest':digest(bundle),'evaluator_digest':digest(verifier),'scope':self.protocol['scope']}
        receipt={'intent':intent,'solver':sr,'evaluator':er,'result':result};write_json(base/'receipt.json',receipt)
        self.store.finish_job(job_id,receipt)
        if not ev['valid']:raise Blocked(f'Independent evaluator rejected {job_id}')
        return result
    def matrix(self,candidate,bundle,verifier,phase,variants):
        seeds=self.protocol[phase+'_seeds'];cells=[(s,v) for v in sorted(variants) for s in sorted(seeds)]
        def run(pair):return self.cell(candidate,bundle,verifier,phase,pair[0],pair[1])
        with ThreadPoolExecutor(max_workers=self.config['workers']) as pool:rows=list(pool.map(run,cells))
        return sorted(rows,key=lambda r:(r['variant'],r['seed']))
    def negative_controls(self,verifier):
        """Trusted controller creates malformed answers; evaluator must reject them.
        This verifies basic evaluator behavior, not all semantic correctness.
        """
        root=self.store.root;code=self.store.publish_bundle(verifier);reports=[]
        for name,answer in [('empty',{}),('fabricated_score',{'score':1e200,'valid':True,'fabricated':True})]:
            key=digest({'verifier':digest(verifier),'control':name});base=root/'negative_controls'/key
            prior=base/'report.json'
            if prior.exists():
                saved=read_json(prior);verify_tree(base/'evaluation',saved['output_manifest']);reports.append(saved);continue
            write_json(base/'answer/answer.json',answer)
            lim=Limits(seconds=self.config['trial_timeout'],cpu_threads=self.config['cpu_threads'],memory_mb=self.config['memory_mb'])
            self.executor.execute(code,'evaluate.py',root/'evaluation_inputs/development',base/'evaluation',
                ['--seed','0','--budget',str(self.protocol['fe_budget']),'--variant','full'],lim,answer=base/'answer',logdir=base/'logs')
            ev=validate('evaluation',read_json(base/'evaluation/evaluation.json'));rejected=not ev['valid']
            if not rejected:raise Blocked('Evaluator accepted controller-generated malformed answer: '+name)
            report={'control':name,'rejected':True,'verifier_digest':digest(verifier),'output_manifest':tree_manifest(base/'evaluation')};write_json(prior,report);reports.append(report)
        return reports
