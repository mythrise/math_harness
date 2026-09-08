"""Executable baseline library plus an unmodified MOSAIC adapter.
Cards are applicability checks, NOT a promise every implementation fits every task.
"""
from __future__ import annotations
import sys
import numpy as np
from .common import ROOT, IntegrityError

METHODS=[
 {'id':'linear-programming','family':'optimization','keywords':['线性','资源','linear','allocation'],'implementation':'scipy.optimize.linprog(method="highs")','assumptions':['linear objective and constraints'],'checks':['primal residual','bound feasibility','solver status','dual information when available']},
 {'id':'mixed-integer','family':'optimization','keywords':['整数','调度','分配','integer','scheduling'],'implementation':'scipy.optimize.milp','assumptions':['explicit integer variables; linear constraints'],'checks':['integrality','feasibility','solver bound and MIP gap']},
 {'id':'mosaic-multiobjective','family':'optimization','keywords':['多目标','帕累托','multiobjective','Pareto'],'implementation':'cumcm_harness.algorithms.mosaic_solve','assumptions':['deterministic objectives; continuous box or approved feasible ordered-subset codec'],'checks':['FE ledger','objective recomputation','Pareto dominance','equal-budget baseline','small exact oracle if finite']},
 {'id':'regression','family':'prediction','keywords':['回归','拟合','regression'],'implementation':'cumcm_harness.algorithms.linear_fit','assumptions':['identified design; split before fitting preprocessing'],'checks':['rank','holdout error','residuals','leakage','coefficient sensitivity']},
 {'id':'time-series','family':'prediction','keywords':['时序','预测','forecast','trend'],'implementation':'cumcm_harness.algorithms.linear_forecast','assumptions':['ordered observations; linear extrapolation is only a baseline'],'checks':['rolling-origin split','last-value baseline','drift','no future leakage']},
 {'id':'topsis','family':'evaluation','keywords':['评价','排序','topsis'],'implementation':'cumcm_harness.algorithms.topsis','assumptions':['explicit benefit/cost directions; justified nonnegative weights'],'checks':['constant columns','weight sensitivity','rank reversal','units']},
 {'id':'graph-path','family':'graph','keywords':['图论','路径','network','shortest'],'implementation':'scipy.sparse.csgraph.dijkstra','assumptions':['nonnegative edge weights; specified connectivity'],'checks':['route feasibility','total path cost','disconnected cases']},
 {'id':'ode','family':'dynamics','keywords':['微分','动力学','ode','dynamic'],'implementation':'scipy.integrate.solve_ivp','assumptions':['specified initial conditions and physically meaningful RHS'],'checks':['convergence under step refinement','conservation','stability','units']},
 {'id':'monte-carlo','family':'simulation','keywords':['模拟','随机','Monte','simulation'],'implementation':'numpy.random.Generator','assumptions':['specified distribution and independent replication unit'],'checks':['seed ledger','sampling error','variance reduction','rare-event coverage']},
 {'id':'statistics','family':'statistics','keywords':['统计','检验','聚类','statistics'],'implementation':'scipy.stats / sklearn clustering','assumptions':['explicit sampling unit and hypotheses'],'checks':['multiple testing','effect size','confounding','group/time split']},
]
def route_methods(query:str,top_k=6):
    text=query.casefold()
    ranked=sorted(METHODS,key=lambda m:(-sum(k.casefold() in text for k in m['keywords']),m['id']))
    from .algorithm_library import enrich_method
    return [enrich_method(card) for card in ranked[:top_k]]

def linear_fit(X,y):
    X=np.asarray(X,float);y=np.asarray(y,float)
    if X.ndim==1:X=X[:,None]
    if X.ndim!=2 or y.shape!=(len(X),) or not (np.isfinite(X).all() and np.isfinite(y).all()):raise ValueError('Invalid regression data')
    A=np.c_[np.ones(len(X)),X];beta,res,rank,s=np.linalg.lstsq(A,y,rcond=None)
    if rank<A.shape[1]:raise ValueError('Unidentified/rank-deficient regression')
    return beta

def linear_forecast(y,horizon):
    y=np.asarray(y,float)
    if y.ndim!=1 or len(y)<3 or horizon<1:raise ValueError('At least three ordered observations required')
    beta=linear_fit(np.arange(len(y)),y)
    return beta[0]+beta[1]*np.arange(len(y),len(y)+horizon)

def topsis(X,weights,benefit):
    X=np.asarray(X,float);w=np.asarray(weights,float);b=np.asarray(benefit,bool)
    if X.ndim!=2 or X.shape[1]!=len(w) or len(b)!=len(w) or len(X)<2 or not np.isfinite(X).all():raise ValueError('Invalid TOPSIS input')
    if not np.isfinite(w).all() or np.any(w<0) or w.sum()<=0:raise ValueError('Weights must be finite, nonnegative and nonzero')
    norms=np.linalg.norm(X,axis=0)
    if np.any(norms==0) or np.any(np.ptp(X,axis=0)==0):raise ValueError('Remove constant columns and renormalize weights explicitly')
    V=X/norms*(w/w.sum());ideal=np.where(b,V.max(0),V.min(0));anti=np.where(b,V.min(0),V.max(0))
    a=np.linalg.norm(V-ideal,axis=1);z=np.linalg.norm(V-anti,axis=1)
    if np.any(a+z==0):raise ValueError('Indistinguishable alternatives')
    return z/(a+z)

def mosaic_modules():
    path=ROOT/'vendor/mosaic_v14'
    if not path.is_dir():raise IntegrityError('Source distribution assets missing; use editable source install')
    if str(path) not in sys.path:sys.path.insert(0,str(path))
    import mosaic_solve as m
    return m

def mosaic_solve(problem, *, representation='continuous_box',strategy='incumbent',seed=1,budget=256,population=32,codec=None,deterministic=True,constraints='box',research_opt_in=False):
    """No silent rounding/noise repair. V14 accelerated branches are bi-objective
    ordered subsets. Incumbent also retains the original continuous-box v9 backend.
    """
    if strategy in ('local24','refit32') and not research_opt_in:raise IntegrityError('Research-only branch requires explicit opt-in')
    if representation=='ordered_subset' and codec is None:raise IntegrityError('Ordered subsets require an explicit validated codec')
    m=mosaic_modules();contract=m.ProblemContract(representation=representation,codec=codec,deterministic=deterministic,constraints=constraints)
    run=m.solve(problem,seed=seed,budget=budget,population=population,contract=contract,strategy=strategy)
    if run.ledger.spent!=run.result.evaluations or run.ledger.spent!=budget:raise IntegrityError('MOSAIC FE accounting mismatch')
    return run

def hv2(points,reference):
    """Exact 2D dominated hypervolume for minimization; fixed external reference."""
    F=np.asarray(points,float);r=np.asarray(reference,float)
    if F.ndim!=2 or F.shape[1]!=2 or r.shape!=(2,) or not np.isfinite(F).all() or not np.isfinite(r).all():raise ValueError('Invalid hypervolume input')
    if np.any(F>r):raise ValueError('Reference must weakly dominate all supplied points; do not silently discard')
    F=F[np.argsort(F[:,0],kind='stable')];y=r[1];area=0.
    for x,v in F:
        if v<y:area+=(r[0]-x)*(y-v);y=v
    return float(area)

def mosaic_infill_ablation(problem,*,seed=1,budget=192,population=32,full_strategy='fast_h0'):
    """Single-factor diagnostic: same deployed engine/config, enabled=False only.
    This is a local harness ablation, not an altered vendored production default.
    """
    mosaic_modules()
    from dataclasses import replace
    from mosaic14.bootstrap import EvaluationLedger,AuditedRun
    from mosaic14.engine import run_fast_h0
    from mosaic14.variants import CONFIGS,SearchHarness
    from harnesslab.problems import OrderedSubsetCodec
    from mosaic.rgv import RGVCodec
    if full_strategy not in ('fast_h0','refit32') or type(problem.codec) not in (OrderedSubsetCodec,RGVCodec) or problem.n_obj!=2:
        raise IntegrityError('Unsupported ablation contract')
    if budget<population or population<8:raise IntegrityError('Invalid ablation budget')
    ledger=EvaluationLedger(problem,budget);cfg=replace(CONFIGS[full_strategy],enabled=False)
    result=run_fast_h0(ledger,problem.codec,seed,population,budget,cfg,harness_type=SearchHarness)
    if result.evaluations!=budget or ledger.spent!=budget:raise IntegrityError('Ablation ledger mismatch')
    result.algorithm='MOSAIC-v14-ONE_FACTOR_ABLATION'
    result.diagnostics['ablation']={'base_strategy':full_strategy,'enabled':False,'other_config_unchanged':True}
    return AuditedRun(result,ledger)
