from pathlib import Path
import sys,argparse,json
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from harnesslab.api import solve,ProblemContract
from mosaic.rgv import RGVProblem

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--group',type=int,choices=[1,2,3],default=1)
    ap.add_argument('--seed',type=int,default=13801);ap.add_argument('--budget',type=int,default=1024)
    ap.add_argument('--strategy',choices=['incumbent','audited_infill'],default='incumbent');a=ap.parse_args()
    p=RGVProblem(group=a.group)
    r=solve(p,seed=a.seed,budget=a.budget,contract=ProblemContract('ordered_subset',p.codec,'feasible_decoder'),strategy=a.strategy)
    print(json.dumps({'algorithm':r.result.algorithm,'physical_search_FE':p.calls,'ledger_FE':r.ledger.spent,'policies':[{'cycle':(p.codec.decode(x)+1).tolist(),'products':-float(f[0]),'movement_seconds':float(f[1])}for x,f in zip(r.result.X,r.result.F)]},indent=2))
if __name__=='__main__':main()
