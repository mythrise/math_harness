from pathlib import Path
import sys,json,time,os,csv,argparse,traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from mosaic.api import *
from mosaic.rgv import RGVProblem
from mosaic.extensions import ExtensionConfig
from mosaic.metrics import score

def job(j):
    group,seed,budget,name=j
    modes={'v10':('mosaic_v10','disabled'),'v9':('mosaic_v9','disabled'),'typed_uniform':('typed_residual_research','uniform'),
        'typed_contextual':('typed_residual_research','contextual'),'typed_quantile':('typed_residual_research','quantile'),
        'typed_nsga2':('typed_nsga2','disabled'),'typed_nsga2_unique':('typed_nsga2_unique','disabled'),'nsga2_port':('nsga2_port','disabled'),
        'moead_port':('moead_port','disabled'),'rdex_port':('rdex_port','disabled')}
    p=RGVProblem(group);start=time.perf_counter()
    if name=='v10_r1':
        from mosaic.final import solve
        r=solve(p,seed,budget,32,ProblemContract('ordered_subset',p.codec,'feasible_decoder'))
    elif name.startswith('graph_'):
        from mosaic.graph_search import run_graph
        ledger=EvaluationLedger(p,budget)
        result=run_graph(ledger,p.codec,seed,32,budget,mode=name[6:])
        r=AuditedRun(result,ledger)
    else:
        alg,mode=modes[name]
        r=optimize(p,seed=seed,budget=budget,population=32,algorithm=alg,
            contract=ProblemContract('ordered_subset',p.codec,'feasible_decoder'),
            extension_config=ExtensionConfig(mode=mode))
    assert p.calls == r.ledger.spent == r.result.evaluations == budget
    duration=time.perf_counter()-start
    R=np.load(ROOT/f'results/oracles/rgv_g{group}.npz')['F']
    row={'problem':p.name,'group':group,'seed':seed,'budget':budget,'algorithm':name,
         'seconds':duration,'calls':p.calls,'ledger':r.ledger.spent,**score(r.result.F,R)}
    detail={'row':row,'X':r.result.X.tolist(),'F':r.result.F.tolist(),
            'extension':r.result.diagnostics.get('typed_extension',r.result.diagnostics)}
    return row,detail

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--stage',default='development');a.add_argument('--groups',default='1')
    a.add_argument('--seeds',default='101,102,103,104,105,106');a.add_argument('--budgets',default='256,1056')
    a.add_argument('--algorithms',default='v9,typed_uniform,typed_contextual,typed_quantile,typed_nsga2')
    a.add_argument('--workers',default=4,type=int);args=a.parse_args()
    out=ROOT/'results'/args.stage;out.mkdir(exist_ok=True,parents=True)
    jobs=[(g,s,b,m) for g in map(int,args.groups.split(',')) for s in map(int,args.seeds.split(','))
          for b in map(int,args.budgets.split(',')) for m in args.algorithms.split(',')]
    rows=[];errors=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(job,j):j for j in jobs}
        for fut in as_completed(futures):
            j=futures[fut]
            try:
                row,detail=fut.result();rows.append(row)
                (out/f'g{j[0]}_s{j[1]}_b{j[2]}_{j[3]}.json').write_text(json.dumps(detail))
            except Exception:
                errors.append({'job':j,'error':traceback.format_exc()});print(errors[-1],flush=True)
            print('completed',len(rows),'/',len(jobs),'errors',len(errors),flush=True)
    if rows:
        with (out/'raw.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (out/'errors.json').write_text(json.dumps(errors,indent=2))
