import os
os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1';os.environ['NUMEXPR_NUM_THREADS']='1'
from pathlib import Path
import sys,json,time,datetime,hashlib,traceback,argparse,gzip
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R))
from harnesslab.bootstrap import EvaluationLedger,run_fast_v10,run_typed_nsga2_unique
from harnesslab.engine import CONFIGS,run_harness
from harnesslab.residual import RESIDUAL_CONFIGS
from harnesslab.residual_engine import run_residual
from harnesslab.efficient import FAST_CONFIGS
from harnesslab.efficient_engine import run_efficient
from harnesslab.nsga_residual import run_nsga_residual
from harnesslab.residual import ResidualConfig
from harnesslab.problems import make_problem,enumerate_reference
from harnesslab.metrics import score_trace

def fileshash():
 return {str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((R/'harnesslab').glob('*.py'))}|{'protocol/instances.json':hashlib.sha256((R/'protocol/instances.json').read_bytes()).hexdigest()}
def freeze(stage,meta):
 p=R/'protocol'/f'{stage.upper()}_FREEZE.json'
 if p.exists():
  d=json.loads(p.read_text())
  for f,h in d['files'].items():
   if hashlib.sha256((R/f).read_bytes()).hexdigest()!=h:raise RuntimeError(f'Frozen file changed: {f}; use a new stage')
  return d
 d=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=fileshash(),**meta);p.write_text(json.dumps(d,indent=2));return d

def work(job):
 spec,alg,seed,budget,stage=job;folder=R/'results'/stage;folder.mkdir(parents=True,exist_ok=True)
 name=f"{spec['id']}__{alg}__{seed}";dest=folder/(name+'.json')
 if dest.exists():return json.loads(dest.read_text())
 try:
  p=make_problem(spec);ledger=EvaluationLedger(p,budget);start=time.perf_counter()
  if alg=='fast_v10':result=run_fast_v10(ledger,p.codec,seed,32,budget)
  elif alg=='nsga2_typed':result=run_typed_nsga2_unique(ledger,p.codec,seed,32,budget)
  elif alg=='v10':
   from mosaic.graph_search import run_graph
   result=run_graph(ledger,p.codec,seed,32,budget,mode='no_memory',ties_per_objective=1)
  elif alg=='nsga2_guarded':result=run_nsga_residual(ledger,p.codec,seed,32,budget,ResidualConfig(model='linear'))
  elif alg=='nsga2_off':result=run_nsga_residual(ledger,p.codec,seed,32,budget,ResidualConfig(enabled=False))
  elif alg in FAST_CONFIGS:result=run_efficient(ledger,p.codec,seed,32,budget,FAST_CONFIGS[alg])
  elif alg in RESIDUAL_CONFIGS:result=run_residual(ledger,p.codec,seed,32,budget,RESIDUAL_CONFIGS[alg])
  else:result=run_harness(ledger,p.codec,seed,32,budget,CONFIGS[alg])
  seconds=time.perf_counter()-start
  if not (result.evaluations==ledger.spent==p.calls==budget):raise AssertionError('FE mismatch')
  X=np.asarray(ledger.X);F=np.asarray(ledger.F)
  row=dict(task=spec['id'],kind=spec['kind'],partition=spec['partition'],algorithm=alg,seed=seed,budget=budget,fe=ledger.spent,physical_calls=p.calls,seconds=seconds,unique_evaluated=len({tuple(p.codec.decode(x)) for x in X}),audit_pass=True)
  refpath=R/'results/references'/(spec['id']+'.npz')
  # Reference data can only be loaded after the complete optimizer call.
  if refpath.exists():row.update(score_trace(F,result.F,np.load(refpath)['F'],budget))
  diag=result.diagnostics
  if 'harness'in diag:diag=diag['harness']
  row['audit_fallbacks']=sum(d.get('reason')=='audit_fallback' for d in diag.get('contracts',[]))
  row['model_authorized']=sum(bool(d.get('allowed',False)) for d in diag.get('contracts',[]))
  row['overrides']=diag.get('overrides',0)
  row['model_fits']=len(diag.get('model_fits',[]));row['surrogate_predictions']=diag.get('surrogate_predictions',0)
  np.savez_compressed(folder/(name+'.npz'),X=X,F=F,output_X=result.X,output_F=result.F)
  with gzip.open(folder/(name+'.log.json.gz'),'wt',encoding='utf8') as f:json.dump(diag,f,default=lambda x:x.item() if isinstance(x,np.generic) else x.tolist(),allow_nan=False)
  tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(row,indent=2));tmp.replace(dest);return row
 except Exception:
  row=dict(task=spec['id'],algorithm=alg,seed=seed,error=traceback.format_exc());(folder/(name+'.error.json')).write_text(json.dumps(row));return row

def warm():
 specs=json.loads((R/'protocol/instances.json').read_text());entries=[]
 for kind in ['rgv','tour','job']:
  s=next(x for x in specs if x['kind']==kind);p=make_problem(s);p.evaluate(p.codec.encode([0]));entries.append(dict(kind=kind,physical_calls=p.calls))
 d=R/'results/warmups';d.mkdir(exist_ok=True,parents=True);(d/f'{os.getpid()}.json').write_text(json.dumps(entries))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage');ap.add_argument('--workers',type=int,default=4);ap.add_argument('--algs',default='');ap.add_argument('--seeds',type=int,default=0);ap.add_argument('--budget',type=int,default=0);a=ap.parse_args()
 specs=json.loads((R/'protocol/instances.json').read_text());plan=json.loads((R/'protocol/PLAN.json').read_text())
 if a.stage=='reference':
  out=R/'results/references';out.mkdir(parents=True,exist_ok=True);rows=[]
  for s in specs:
   if s['partition']=='stress':continue
   start=time.perf_counter();F,orders,sizes,count=enumerate_reference(s)
   np.savez_compressed(out/(s['id']+'.npz'),F=F,orders=orders,sizes=sizes)
   row=dict(task=s['id'],fe=count,front_size=len(F),seconds=time.perf_counter()-start);rows.append(row);print(row,flush=True)
  (out/'ACCOUNTING.json').write_text(json.dumps(rows,indent=2));return
 isdev=a.stage.startswith('dev') or a.stage=='pilot'
 if isdev:
  tasks=[s for s in specs if s['partition']=='development'];seeds=plan['dev']['seeds'];budget=plan['dev']['budget'];algs=['fast_v10','nsga2_typed']+(list(RESIDUAL_CONFIGS) if a.stage=='dev2' else list(CONFIGS))
 elif a.stage=='serial':
  tasks=[s for s in specs if s['id'] in ['rgv_h1','tour_h1','job_h1']];seeds=list(range(13701,13705));budget=1024;algs=['fast_v10','nsga2_typed','harness','surrogate_hvi']
 elif a.stage=='original':
  tasks=[dict(id=f'rgv_g{g}',kind='rgv',group=g,partition='original') for g in [1,2,3]];seeds=list(range(13801,13809));budget=1024;algs=['fast_v10','nsga2_typed','harness']
 elif a.stage=='stress':
  tasks=[s for s in specs if s['partition']=='stress'];seeds=list(range(13901,13907));budget=2048;algs=['fast_v10','nsga2_typed','harness']
 else:
  tasks=[s for s in specs if s['partition']=='holdout'];seeds=plan['confirm']['seeds'];budget=plan['confirm']['budget'];algs=['fast_v10','nsga2_typed']+list(CONFIGS)
 if a.algs:algs=a.algs.split(',')
 if a.seeds:seeds=seeds[:a.seeds]
 if a.budget:budget=a.budget
 frozen=freeze(a.stage,dict(algorithms=algs,seeds=seeds,budget=budget,tasks=[s['id'] for s in tasks]))
 # Frozen stage command must not silently change its job matrix.
 if any(frozen[k]!=v for k,v in dict(algorithms=algs,seeds=seeds,budget=budget,tasks=[s['id'] for s in tasks]).items()):raise RuntimeError('Matrix differs from freeze')
 jobs=[(s,alg,seed,budget,a.stage) for s in tasks for seed in seeds for alg in algs];np.random.default_rng(130905).shuffle(jobs)
 print('PLANNED',a.stage,len(jobs),flush=True);start=time.perf_counter();rows=[]
 if a.workers==1:
  warm()
  for i,j in enumerate(jobs,1):
   rows.append(work(j))
   if i%12==0:print('COMPLETE',i,round(time.perf_counter()-start,1),flush=True)
 else:
  with ProcessPoolExecutor(max_workers=a.workers,initializer=warm) as pool:
   for i,f in enumerate(as_completed([pool.submit(work,j) for j in jobs]),1):
    rows.append(f.result())
    if i%16==0 or i==len(jobs):print('COMPLETE',i,'/',len(jobs),round(time.perf_counter()-start,1),flush=True)
 folder=R/'results'/a.stage;errors=[r for r in rows if 'error'in r];(folder/'ERRORS.json').write_text(json.dumps(errors,indent=2))
 df=pd.DataFrame([{k:v for k,v in r.items() if k!='trace'} for r in rows if 'error'not in r]);df.to_csv(folder/'raw.csv',index=False)
 (folder/'RUN_METADATA.json').write_text(json.dumps(dict(stage=a.stage,planned=len(jobs),complete=len(df),errors=len(errors),search_fe=int(df.fe.sum()) if len(df) else 0,elapsed_seconds=time.perf_counter()-start),indent=2))
 if len(df):print(df.groupby('algorithm')[[k for k in ['auc','final_gap','igd','hit','seconds','audit_fallbacks'] if k in df]].mean().to_string(),flush=True)
 if errors:print(errors[0]);raise RuntimeError(f'{len(errors)} errors')
if __name__=='__main__':main()
