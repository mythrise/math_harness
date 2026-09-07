import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys,json,cProfile,pstats,time,io
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'vendor/v13'))
from harnesslab.problems import make_problem
from harnesslab.bootstrap import EvaluationLedger,run_fast_v10
from harnesslab.efficient_engine import run_efficient
from harnesslab.efficient import FAST_CONFIGS
out=R/'results/profile';out.mkdir(parents=True,exist_ok=True)
specs=json.loads((R/'vendor/v13/protocol/instances.json').read_text())
rows=[]
for kind in ['rgv','tour','job']:
 spec=next(s for s in specs if s['kind']==kind and s['partition']=='development')
 warm=make_problem(spec);warm.evaluate(warm.codec.encode([0]))
 for alg in ['fast_v10','h0']:
  p=make_problem(spec);l=EvaluationLedger(p,1024);start=time.perf_counter()
  r=run_fast_v10(l,p.codec,74001,32,1024) if alg=='fast_v10' else run_efficient(l,p.codec,74001,32,1024,FAST_CONFIGS['no_uncertainty_linear'])
  rows.append(dict(kind=kind,algorithm=alg,seconds=time.perf_counter()-start,fe=l.spent))
  print(rows[-1],flush=True)
 p=make_problem(spec);l=EvaluationLedger(p,1024);pr=cProfile.Profile();pr.enable()
 r=run_efficient(l,p.codec,74001,32,1024,FAST_CONFIGS['no_uncertainty_linear']);pr.disable()
 pr.dump_stats(str(out/f'{kind}.prof'))
 s=io.StringIO();pstats.Stats(pr,stream=s).strip_dirs().sort_stats('cumtime').print_stats(45)
 (out/f'{kind}.txt').write_text(s.getvalue());print(s.getvalue()[:4400],flush=True)
(out/'unprofiled_timing.json').write_text(json.dumps(rows,indent=2))
