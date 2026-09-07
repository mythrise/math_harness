"""Synthetic ordered-subset scheduling demo, NOT an official CUMCM solution."""
from pathlib import Path
import argparse,json
import numpy as np
from cumcm_harness.algorithms import mosaic_modules,mosaic_solve,mosaic_infill_ablation
FULL_STRATEGY = 'refit32'

def nondominated(F):
    return np.array([not np.any(np.all(F<=f,axis=1)&np.any(F<f,axis=1)) for f in F])
def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--budget',type=int,required=True);p.add_argument('--variant',required=True)
    a=p.parse_args();spec=json.loads((a.input/'problem.json').read_text())
    mosaic_modules();from harnesslab.problems import make_problem
    problem=make_problem(spec)
    if a.variant=='baseline':
        rng=np.random.default_rng(a.seed);X=rng.random((a.budget,problem.n_var));F=problem.evaluate(X);spent=problem.calls;backend='uniform_random'
    elif a.variant in ('full','no_infill','population16'):
        if a.variant=='no_infill':run=mosaic_infill_ablation(problem,seed=a.seed,budget=a.budget,full_strategy=FULL_STRATEGY)
        else:run=mosaic_solve(problem,representation='ordered_subset',codec=problem.codec,constraints='feasible_decoder',
                strategy=FULL_STRATEGY,seed=a.seed,budget=a.budget,population=16 if a.variant=='population16' else 32,research_opt_in=True)
        X=np.array(run.ledger.X);F=np.array(run.ledger.F);spent=run.ledger.spent;backend=run.result.algorithm
    else:raise ValueError('unknown variant')
    # Identical postprocessing for every method: nondominated paid observations.
    keep=nondominated(F);frontX=X[keep];frontF=F[keep]
    _,ids=np.unique(frontF,axis=0,return_index=True);frontX=frontX[ids];frontF=frontF[ids]
    n=len(spec['values']);T=sum(spec['process'])+n*float(np.max(spec['setup']))+1
    utility=-frontF[:,0]/sum(spec['values'])-frontF[:,1]/T;selected=int(np.argmax(utility))
    answer={'X':frontX.tolist(),'F':frontF.tolist(),'ledger_X':X.tolist(),'ledger_F':F.tolist(),
            'selected_index':selected,'budget_spent':int(spent),'seed':a.seed,'backend':backend,
            'postprocessing':'nondominated paid observations only; no objective calls or reference-front access'}
    a.out.mkdir(parents=True,exist_ok=True);(a.out/'answer.json').write_text(json.dumps(answer,allow_nan=False))
if __name__=='__main__':main()
