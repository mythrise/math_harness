"""Reproducible algorithm-library smoke benchmark. No LLM/weights/network needed.
Run: python -m cumcm_harness.algorithm_lab --out RUN_DIRECTORY
These are smoke/diagnostic experiments, not automatic promotion or a SOTA leaderboard.
"""
from __future__ import annotations
import argparse,json,hashlib,time,platform,importlib.metadata
from pathlib import Path
import numpy as np
from .algopt import solve_linear
from .algpredict import fit_tabular,forecast_portfolio,forecast_candidate,conformal_interval
from .algscience import integrate_unit,checked_ivp,adjust_pvalues
from .alggraph import shortest_path
from .algdecision import fixed_topsis
from .algorithm_library import FAMILIES,external_manifest


def clean(x):
    if isinstance(x,np.ndarray):return clean(x.tolist())
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)):return [clean(v) for v in x]
    return x

def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(clean(x),ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf8')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run(out,seeds=8,seed_start=201):
    if isinstance(seeds,bool) or not isinstance(seeds,int) or not 2<=seeds<=30:
        raise ValueError('seeds must be 2..30')
    if isinstance(seed_start,bool) or not isinstance(seed_start,int) or seed_start<0:
        raise ValueError('seed_start must be a nonnegative integer')
    out=Path(out)
    if out.exists() and any(out.iterdir()):raise ValueError('Output directory must be empty; preserve previous results')
    out.mkdir(parents=True,exist_ok=True)
    protocol={'version':'0.3.0-algorithms','kind':'LOCAL_SMOKE_NOT_SOTA','seeds':list(range(seed_start,seed_start+seeds)),
        'families':['linear','nonlinear','outliers','heteroskedastic'],
        'series':['trend','seasonal','seasonal_trend','random_walk','white_noise'],
        'regression':{'train':144,'calibration':64,'test':256,'features':4,'fit_budget_cap':36},
        'forecast':{'history':144,'horizon':12,'season':12,'rolling_origins':3,'fit_budget_cap':16},
        'integration':{'dimension':4,'evaluation_budget':1024,'replicates':8},
        'promotion':'NOT_ELIGIBLE: handcrafted small families and external frontier baselines NOT_RUN',
        'cost_policy':'Same data and upper budget caps; actual fits differ and are recorded. No equal-walltime superiority claim.',
        'source_hashes':{p.name:sha(p) for p in sorted(Path(__file__).parent.glob('alg*.py'))}}
    dump(out/'protocol.json',protocol)  # Written BEFORE observing benchmark outcomes.
    rows=[];beg=time.perf_counter()
    for seed in protocol['seeds']:
        rng=np.random.default_rng(seed)
        for family in protocol['families']:
            X=rng.normal(size=(464,4));noise=rng.normal(size=464)*.25
            y=2*X[:,0]-X[:,1]+noise
            if family=='nonlinear':y=2*X[:,0]**2+np.sin(2*X[:,1])+noise
            if family=='outliers':y=y.copy();ids=rng.choice(144,20,replace=False);y[ids]+=rng.normal(0,12,20)
            if family=='heteroskedastic':y=2*X[:,0]-X[:,1]+rng.normal(size=464)*(.1+abs(X[:,2]))
            models={};tm={}
            for label,residual,gate in [('classical_portfolio',False,'all_folds'),('residual_ungated',True,'disabled'),('residual_gated',True,'all_folds')]:
                t=time.perf_counter();models[label]=fit_tabular(X[:144],y[:144],seed=seed,include_residual=residual,residual_gate=gate,max_fits=36);tm[label]=time.perf_counter()-t
            ytest=y[208:]
            for label,m in models.items():
                pred=m.predict(X[208:]);cal=m.predict(X[144:208]);interval=conformal_interval(pred,y[144:208],cal,exchangeable=True)
                rows.append(dict(domain='regression',family=family,seed=seed,method=label,
                    rmse=float(np.sqrt(np.mean((pred-ytest)**2))),selected=m.report['selected'],fits=m.report['fits'],
                    seconds=tm[label],coverage90=float(np.mean((ytest>=interval['lower'])&(ytest<=interval['upper']))),
                    interval_width=float(2*interval['quantile']),train_sha=hashlib.sha256(X[:144].tobytes()+y[:144].tobytes()).hexdigest()))
        for family in protocol['series']:
            t=np.arange(156);noise=rng.normal(size=156)*.2
            y={'trend':.08*t+noise,'seasonal':2*np.sin(2*np.pi*t/12)+noise,
                'seasonal_trend':.04*t+2*np.sin(2*np.pi*t/12)+noise,
                'random_walk':np.cumsum(rng.normal(size=156)),
                'white_noise':rng.normal(size=156)}[family]
            out_pred=forecast_portfolio(y[:144],12,season=12)
            for method in ['linear','naive','seasonal','seasonal_residual','ridge_lags','portfolio']:
                p=out_pred['prediction'] if method=='portfolio' else forecast_candidate(y[:144],12,method,12)
                rows.append(dict(domain='forecast',family=family,seed=seed,method=method,
                    mae=float(np.mean(abs(y[144:]-p))),selected=out_pred['selected'] if method=='portfolio' else method,
                    fits=out_pred['fits'] if method=='portfolio' else 1))
        fns={'smooth_exp':(lambda x:np.exp(np.mean(x,axis=1)),(4*np.expm1(.25))**4),
             'rare_indicator':(lambda x:(x[:,0]>.99).astype(float),.01)}
        for family,(fn,truth) in fns.items():
            for method in ['mc','sobol']:
                result=integrate_unit(fn,4,points_per_rep=128,replicates=8,method=method,seed=seed,budget=1024)
                rows.append(dict(domain='integration',family=family,seed=seed,method=method,
                    error=abs(result['estimate']-truth),estimate=result['estimate'],truth=truth,
                    evaluations=result['evaluations'],standard_error=result['standard_error']))
    # Actual public in-package dataset, no network. Repeated splits are NOT independent datasets.
    from sklearn.datasets import load_diabetes
    from sklearn.model_selection import train_test_split
    X,y=load_diabetes(return_X_y=True)
    for seed in protocol['seeds'][:4]:
        tr,te=train_test_split(np.arange(len(y)),test_size=.25,random_state=seed)
        for label,residual,gate in [('classical_portfolio',False,'all_folds'),('residual_ungated',True,'disabled'),('residual_gated',True,'all_folds')]:
            m=fit_tabular(X[tr],y[tr],seed=seed,include_residual=residual,residual_gate=gate)
            rows.append(dict(domain='public_dataset',family='sklearn_diabetes',seed=seed,method=label,
                rmse=float(np.sqrt(np.mean((y[te]-m.predict(X[te]))**2))),selected=m.report['selected'],fits=m.report['fits'],
                scope='DESCRIPTIVE_REPEATED_SPLITS_NOT_CLINICAL_USE_OR_INDEPENDENT_DATASETS'))
    # Analytic, exact small-instance and metamorphic checks exercise remaining families.
    diagnostics=[]
    import itertools
    for seed in protocol['seeds']:
        rng=np.random.default_rng(seed);profits=rng.integers(1,10,size=6);weights=rng.integers(1,8,size=6);cap=int(weights.sum()*.4)
        exact=max(float(profits@x) for xx in itertools.product([0,1],repeat=6)
                    if weights@(x:=np.array(xx))<=cap)
        r=solve_linear(-profits,[weights],None,[cap],[(0,1)]*6,integrality=[1]*6)
        diagnostics.append(dict(family='mixed-integer',seed=seed,passed=abs(r['objective']+exact)<1e-7,objective=r['objective'],exact=-exact))
    lp=solve_linear([-1,-2],[[1,1]],[0],[4],[(0,3),(0,3)])
    diagnostics.append(dict(family='linear-programming',passed=lp['feasible'] and abs(lp['objective']+7)<1e-8))
    graph=shortest_path(4,[(0,1,0),(1,2,-1),(2,3,3),(0,3,8)],0,3)
    diagnostics.append(dict(family='graph-path',passed=graph['distance']==2))
    scores=fixed_topsis([[2,4],[4,2]],[.4,.6],[1,1],[[0,10],[0,10]])
    extra=fixed_topsis([[2,4],[4,2],[0,0]],[.4,.6],[1,1],[[0,10],[0,10]])
    diagnostics.append(dict(family='topsis',passed=bool(np.array_equal(scores,extra[:2]))))
    for stiff in [False,True]:
        tt=np.linspace(0,1,30);rate=30 if stiff else 1
        r=checked_ivp(lambda t,y:-rate*y,[1],tt,stiff=stiff)
        diagnostics.append(dict(family='ode',stiff=stiff,passed=r['valid'],max_error=float(np.max(abs(r['solution'][0]-np.exp(-rate*tt)))),rhs_calls=r['rhs_evaluations']))
    diagnostics.append(dict(family='statistics',passed=bool(np.allclose(adjust_pvalues([.01,.04,.03]),[.03,.06,.06]))))
    # Preserve existing real MOSAIC objective evaluation and full FE ledger, no new operator invented.
    from .algorithms import mosaic_solve,mosaic_modules
    class BiObjective:
        name='biquadratic-smoke';n_var=2;n_obj=2;xl=np.zeros(2);xu=np.ones(2)
        def evaluate(self,X):
            X=np.asarray(X);return np.column_stack([np.sum(X*X,axis=1),np.sum((X-1)**2,axis=1)])
    try:
        run_moo=mosaic_solve(BiObjective(),budget=64,population=16,seed=101)
        result,ledger=run_moo.result,run_moo.ledger
        diagnostics.append(dict(family='mosaic-multiobjective',passed=result.evaluations==ledger.spent==64,fe=ledger.spent))
    except Exception as e:
        diagnostics.append(dict(family='mosaic-multiobjective',passed=False,error=type(e).__name__+': '+str(e)))
    dump(out/'raw_results.json',rows);dump(out/'diagnostics.json',diagnostics)
    summary=[]
    for domain in sorted({r['domain'] for r in rows}):
        metric={'regression':'rmse','forecast':'mae','integration':'error','public_dataset':'rmse'}[domain]
        for family in sorted({r['family'] for r in rows if r['domain']==domain}):
            for method in sorted({r['method'] for r in rows if r['domain']==domain and r['family']==family}):
                group=[r for r in rows if r['domain']==domain and r['family']==family and r['method']==method]
                summary.append(dict(domain=domain,family=family,method=method,metric=metric,n=len(group),
                    mean=float(np.mean([r[metric] for r in group])),
                    selected_counts={k:sum(r.get('selected')==k for r in group) for k in sorted({r['selected'] for r in group if 'selected'in r})}))
    dump(out/'summary.json',dict(status='LOCAL_SMOKE_COMPLETED' if all(d['passed'] for d in diagnostics) else 'DIAGNOSTIC_FAILED',
        rows=len(rows),seconds=time.perf_counter()-beg,summary=summary,diagnostics=diagnostics,
        external_candidates_run=0,global_promotions=0,protocol_sha256=sha(out/'protocol.json')))
    dump(out/'external_candidates.json',external_manifest())
    dump(out/'environment.json',{'python':platform.python_version(),**{x:importlib.metadata.version(x) for x in ['numpy','scipy','scikit-learn']}})
    return json.loads((out/'summary.json').read_text())


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--seeds',type=int,default=8);ap.add_argument('--seed-start',type=int,default=201)
    a=ap.parse_args()
    if not 2<=a.seeds<=30:ap.error('seeds must be 2..30')
    r=run(a.out,a.seeds,a.seed_start);print(json.dumps({k:r[k] for k in ['status','rows','seconds','external_candidates_run','global_promotions']},indent=2))
    if r['status']!='LOCAL_SMOKE_COMPLETED':raise SystemExit(2)
if __name__=='__main__':main()
