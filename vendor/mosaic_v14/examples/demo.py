import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys,argparse,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mosaic_solve import solve,ProblemContract
from mosaic.rgv import RGVProblem

a=argparse.ArgumentParser();a.add_argument('--strategy',choices=['incumbent','incumbent_cached','fast_h0','local24','refit32'],default='fast_h0');a.add_argument('--group',type=int,choices=[1,2,3],default=1);a.add_argument('--seed',type=int,default=74501);a.add_argument('--budget',type=int,default=1024);args=a.parse_args()
p=RGVProblem(group=args.group)
r=solve(p,seed=args.seed,budget=args.budget,contract=ProblemContract(representation='ordered_subset',codec=p.codec,constraints='feasible_decoder'),strategy=args.strategy)
print('Actual function-evaluation vectors:',r.ledger.spent)
for x,f in zip(r.result.X,r.result.F):print(json.dumps(dict(policy=(p.codec.decode(x)+1).tolist(),products=-float(f[0]),travel_seconds=float(f[1])),ensure_ascii=False))
print('Scope: inherited no-fault, one-process, cyclic ordered-subset RGV model; not all official subproblems.')
