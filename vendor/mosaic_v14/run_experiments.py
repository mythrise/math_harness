import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys,json,time,hashlib,datetime,argparse,traceback,gzip
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np,pandas as pd
from mosaic14.bootstrap import ROOT,V13,make_problem,enumerate_reference,EvaluationLedger,run_fast_v10,run_typed_nsga2_unique,score_trace
from mosaic14.engine import run_fast_h0
from mosaic14.variants import CONFIGS,SearchHarness
from mosaic14.nsga import run_nsga_local
from mosaic14.fast import PolicyCodec
from harnesslab.efficient_engine import run_efficient
from harnesslab.efficient import FAST_CONFIGS

def hashes():
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'mosaic14').glob('*.py'))}|{'run_experiments.py':hashlib.sha256((ROOT/'run_experiments.py').read_bytes()).hexdigest()}|{'protocol/instances.json':hashlib.sha256((ROOT/'protocol/instances.json').read_bytes()).hexdigest()}
def freeze(stage,meta):
 p=ROOT/'protocol'/f'{stage}_FREEZE.json';d=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=hashes(),**meta)
 if p.exists():
  prev=json.loads(p.read_text())
  if prev['files']!=d['files'] or any(prev.get(k)!=v for k,v in meta.items()):raise RuntimeError('Frozen stage differs; start a new stage')
  return prev
 p.write_text(json.dumps(d,indent=2));return d

def warm():
 specs=json.loads((ROOT/'protocol/instances.json').read_text());rows=[]
 for k in ['rgv','tour','job']:
  s=next(s for s in specs if s['kind']==k);p=make_problem(s);p.evaluate(p.codec.encode([0]));rows.append(dict(kind=k,physical_evals=p.calls))
 f=ROOT/'results/warmup';f.mkdir(parents=True,exist_ok=True)
 (f/f'{os.getpid()}_{time.time_ns()}.json').write_text(json.dumps(rows))

def run_one(job):
 spec,alg,seed,budget,stage=job;d=ROOT/'results'/stage;d.mkdir(parents=True,exist_ok=True)
 stem=f"{spec['id']}__{alg}__{seed}";path=d/(stem+'.json')
 if path.exists():return json.loads(path.read_text())
 try:
  p=make_problem(spec);ledger=EvaluationLedger(p,budget);start=time.perf_counter()
  if alg=='fast_v10':result=run_fast_v10(ledger,p.codec,seed,32,budget)
  elif alg=='nsga2_typed':result=run_typed_nsga2_unique(ledger,p.codec,seed,32,budget)
  elif alg=='fast_v10_codec':result=run_fast_v10(ledger,PolicyCodec(p.codec),seed,32,budget)
  elif alg=='nsga_local24':result=run_nsga_local(ledger,p.codec,seed,32,budget,CONFIGS['local24'])
  elif alg=='h0':result=run_efficient(ledger,p.codec,seed,32,budget,FAST_CONFIGS['no_uncertainty_linear'])
  else:result=run_fast_h0(ledger,p.codec,seed,32,budget,CONFIGS[alg],harness_type=SearchHarness)
  sec=time.perf_counter()-start
  if not(result.evaluations==ledger.spent==p.calls==budget):raise AssertionError('FE accounting')
  X=np.asarray(ledger.X);F=np.asarray(ledger.F)
  if not np.isfinite(F).all():raise AssertionError('Nonfinite F')
  row=dict(task=spec['id'],kind=spec['kind'],algorithm=alg,seed=seed,budget=budget,fe=ledger.spent,physical_calls=p.calls,seconds=sec)
  refpath=ROOT/'results/references'/(spec['id']+'.npz')
  if refpath.exists():row.update(score_trace(F,result.F,np.load(refpath)['F'],budget))
  diag=result.diagnostics;h=diag.get('harness',{})
  row.update(overrides=h.get('overrides',0),extra_pure_proposals=h.get('extra_pure_proposals',0),neighbor_builds=h.get('neighbor_builds',0),neighbor_cache_hits=h.get('neighbor_cache_hits',0),neighbor_filter_checks=h.get('neighbor_filter_checks',0),model_fits=len(h.get('model_fits',[])),predictions=h.get('surrogate_predictions',0),unique_evaluated=diag.get('unique_evaluated',0))
  np.savez_compressed(d/(stem+'.npz'),X=X,F=F,output_X=result.X,output_F=result.F)
  with gzip.open(d/(stem+'.log.json.gz'),'wt',encoding='utf8') as f:json.dump(diag,f,default=lambda x:x.item() if isinstance(x,np.generic) else x.tolist(),allow_nan=False)
  tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(row,indent=2));tmp.replace(path);return row
 except Exception:
  row=dict(task=spec['id'],algorithm=alg,seed=seed,error=traceback.format_exc());(d/(stem+'.error.json')).write_text(json.dumps(row,indent=2));return row

def main():
 a=argparse.ArgumentParser();a.add_argument('stage');a.add_argument('--algs',default='');a.add_argument('--seeds',type=int,default=0);a.add_argument('--workers',type=int,default=3);a.add_argument('--budget',type=int,default=0);args=a.parse_args()
 specs=json.loads((ROOT/'protocol/instances.json').read_text());plan=json.loads((ROOT/'protocol/PLAN.json').read_text())
 if args.stage=='reference':
  out=ROOT/'results/references';out.mkdir(parents=True,exist_ok=True);rows=[]
  for s in specs:
   if s['partition']=='stress':continue
   path=out/(s['id']+'.npz')
   if path.exists():continue
   st=time.perf_counter();F,o,sz,c=enumerate_reference(s);np.savez_compressed(path,F=F,orders=o,sizes=sz)
   row=dict(task=s['id'],oracle_vectors=c,front_size=len(F),seconds=time.perf_counter()-st);rows.append(row);print(row,flush=True)
  (out/'ACCOUNTING.json').write_text(json.dumps(rows,indent=2));return
 if args.stage.startswith('dev'):
  tasks=[s for s in specs if s['partition']=='development'];seeds=plan['development']['seeds'];budget=512;algs=plan['development']['variants']
 elif args.stage.startswith('parity'):
  tasks=[s for s in specs if s['partition'] in ['development','holdout']];seeds=[74011,74029];budget=1024;algs=['h0','fast_h0']
 elif args.stage=='serial':
  tasks=[next(s for s in specs if s['kind']==k and s['partition']=='holdout') for k in ['rgv','tour','job']];seeds=list(range(74601,74605));budget=1024;algs=['fast_v10','nsga2_typed','h0','fast_h0'];args.workers=1
 elif args.stage=='stress':
  tasks=[s for s in specs if s['partition']=='stress'];seeds=list(range(74701,74707));budget=2048;algs=['fast_v10','nsga2_typed','fast_h0']
 elif args.stage=='original':
  tasks=[dict(id=f'rgv_g{g}',kind='rgv',group=g,partition='original') for g in [1,2,3]];seeds=list(range(74801,74809));budget=1024;algs=['fast_v10','nsga2_typed','fast_h0']
 else:
  tasks=[s for s in specs if s['partition']=='holdout'];seeds=plan['confirmation']['seeds'];budget=1024;algs=['fast_v10','nsga2_typed','h0','fast_h0']
 if args.algs:algs=args.algs.split(',')
 if args.seeds:seeds=seeds[:args.seeds]
 if args.budget:budget=args.budget
 meta=dict(algorithms=algs,seeds=seeds,budget=budget,tasks=[s['id'] for s in tasks]);freeze(args.stage,meta)
 jobs=[(s,al,se,budget,args.stage) for s in tasks for se in seeds for al in algs];np.random.default_rng(140905).shuffle(jobs)
 print('START',args.stage,len(jobs),flush=True);t=time.perf_counter();rows=[]
 if args.workers==1:
  warm()
  for i,j in enumerate(jobs,1):
   row=run_one(j);rows.append(row)
   if 'error'in row:print(row['error'],flush=True)
   if i%12==0:print('DONE',i,'/',len(jobs),round(time.perf_counter()-t,1),flush=True)
 else:
  with ProcessPoolExecutor(max_workers=args.workers,initializer=warm) as pool:
   for i,f in enumerate(as_completed([pool.submit(run_one,j) for j in jobs]),1):
    row=f.result();rows.append(row)
    if 'error'in row:print(row['error'],flush=True)
    if i%16==0 or i==len(jobs):print('DONE',i,'/',len(jobs),round(time.perf_counter()-t,1),flush=True)
 d=ROOT/'results'/args.stage;d.mkdir(exist_ok=True,parents=True)
 errors=[r for r in rows if 'error'in r];(d/'ERRORS.json').write_text(json.dumps(errors,indent=2))
 df=pd.DataFrame([{k:v for k,v in r.items() if k!='trace'} for r in rows if 'error'not in r]);df.to_csv(d/'raw.csv',index=False)
 (d/'RUN_METADATA.json').write_text(json.dumps(dict(planned=len(jobs),complete=len(df),errors=len(errors),fe=int(df.fe.sum()) if len(df) else 0,elapsed=time.perf_counter()-t),indent=2))
 if len(df):print(df.groupby('algorithm')[[c for c in ['auc','final_gap','igd','hit','seconds','extra_pure_proposals','neighbor_builds'] if c in df]].mean().to_string(),flush=True)
 if errors:raise RuntimeError(f'{len(errors)} failed runs')
if __name__=='__main__':main()
