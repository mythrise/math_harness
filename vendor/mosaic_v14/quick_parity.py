import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import json,time,numpy as np
from mosaic14.bootstrap import ROOT,V13,make_problem,EvaluationLedger
from mosaic14.engine import run_fast_h0
from harnesslab.efficient_engine import run_efficient
from harnesslab.efficient import FAST_CONFIGS
specs=json.loads((V13/'protocol/instances.json').read_text());rows=[]
for kind in ['rgv','tour','job']:
 spec=next(s for s in specs if s['kind']==kind and s['partition']=='development')
 p=make_problem(spec);p.evaluate(p.codec.encode([0]))
 for seed in [74001,74003]:
  runs=[]
  for a,fn in [('h0',run_efficient),('fast_h0',run_fast_h0)]:
   p=make_problem(spec);l=EvaluationLedger(p,1024);t=time.perf_counter()
   result=fn(l,p.codec,seed,32,1024,FAST_CONFIGS['no_uncertainty_linear']);sec=time.perf_counter()-t
   runs.append((np.asarray(l.X),np.asarray(l.F),result.X,result.F,sec))
  eq=all(np.array_equal(x,y) for x,y in zip(runs[0][:4],runs[1][:4]))
  row=dict(kind=kind,seed=seed,equal=eq,h0=runs[0][4],fast=runs[1][4]);rows.append(row);print(row,flush=True)
  if not eq:
   diff=np.flatnonzero(np.any(runs[0][0]!=runs[1][0],axis=1));print('FIRST_DIFF',diff[:5]);raise RuntimeError('Parity failed')
  (ROOT/'results/quick_parity.json').write_text(json.dumps(rows,indent=2))
