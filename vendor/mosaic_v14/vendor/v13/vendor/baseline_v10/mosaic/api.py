from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
import sys
import numpy as np
# Isolate the old public imports while preserving file contents and RNG behavior.
LEGACY=Path(__file__).resolve().parents[1]/'legacy'
if str(LEGACY) not in sys.path:sys.path.insert(0,str(LEGACY))
import moo_core as core
from mosaic_sqmoe_v9 import run_mosaic_sqmoe,FROZEN_FLAGS
from .extended_core import run_mosaic_lqmoe
from .extensions import TypedRouter,ExtensionConfig

@dataclass(frozen=True)
class ProblemContract:
    representation:str='continuous_box'
    codec:object|None=None
    constraints:str='box' # box or feasible_decoder; unsupported -> explicit error
    deterministic:bool=True

class EvaluationLedger:
    """Count evaluated vectors, not Python batch calls. No caching in benchmarks."""
    def __init__(self,problem,budget:int):
        self._problem=problem;self.budget=int(budget);self.spent=0;self.batch_calls=0
        self.name=problem.name;self.n_var=problem.n_var;self.n_obj=problem.n_obj
        self.xl=np.array(problem.xl);self.xu=np.array(problem.xu)
        self.X=[];self.F=[];self.checkpoints=[]
    def evaluate(self,X):
        X=np.atleast_2d(np.asarray(X,float))
        if X.shape[1]!=self.n_var or not np.isfinite(X).all():raise ValueError('Invalid designs')
        if np.any(X<self.xl-1e-10) or np.any(X>self.xu+1e-10):raise ValueError('Out-of-bounds proposal')
        if self.spent+len(X)>self.budget:raise RuntimeError('Evaluation budget exceeded')
        # Charge attempted evaluations before calling the oracle; exceptions are not free.
        self.spent+=len(X);self.batch_calls+=1
        F=np.asarray(self._problem.evaluate(X),float)
        if F.shape!=(len(X),self.n_obj) or not np.isfinite(F).all():raise ValueError('Invalid evaluator output')
        self.X.extend(X.copy());self.F.extend(F.copy());return F
    def pareto_front(self,*args,**kwargs):
        raise RuntimeError('Test front must never be used during optimization')

@dataclass
class AuditedRun:
    result:object
    ledger:EvaluationLedger

def optimize(problem, seed=1, budget=2080, population=32,
             contract=ProblemContract(), extension_config=ExtensionConfig(), algorithm='mosaic_v10'):
    if budget<population or population<8:raise ValueError('Require budget >= population >= 8')
    if not contract.deterministic or contract.constraints not in ('box','feasible_decoder'):
        raise NotImplementedError('Noise and general nonlinear constraints require independent certified adapters')
    ledger=EvaluationLedger(problem,budget);ext=None
    if algorithm=='mosaic_v9':
        result=run_mosaic_sqmoe(ledger,seed,population,budget,T=min(12,population))
    elif algorithm=='typed_residual_research':
        if contract.representation=='continuous_box' and contract.codec is None:
            result=run_mosaic_sqmoe(ledger,seed,population,budget,T=min(12,population))
        elif contract.codec is not None:
            ext=TypedRouter(contract.codec,seed,budget,extension_config)
            result=run_mosaic_lqmoe(ledger,seed,population,budget,T=min(12,population),
                ablation=FROZEN_FLAGS,recovery_cooldown=12,max_recoveries=2,extension=ext)
        else:raise ValueError('Structured representation needs a pure codec')
    elif algorithm=='mosaic_v10':
        if contract.representation=='continuous_box' and contract.codec is None:
            result=run_mosaic_sqmoe(ledger,seed,population,budget,T=min(12,population))
            result.diagnostics['backend']='frozen_v9'
        elif contract.representation=='ordered_subset' and contract.codec is not None:
            from .graph_search import run_graph
            result=run_graph(ledger,contract.codec,seed,population,budget,mode='uniform',ties_per_objective=4)
            result.diagnostics['backend']='behavior_archive_structured'
        else:
            raise NotImplementedError('Representation is not yet validated; provide a tested adapter')
        result.algorithm='MOSAIC-v10'
    elif algorithm in ['nsga2_port','moead_port','rdex_port','rvea_port','nsga3_port']:
        if budget%population:raise ValueError('Legacy generation baselines need budget multiple of population')
        funcs={'nsga2_port':core.run_nsga2,'moead_port':core.run_moead,'rdex_port':core.run_rdex,
               'rvea_port':core.run_rvea,'nsga3_port':core.run_nsga3}
        result=funcs[algorithm](ledger,seed,population,budget)
    elif algorithm in ('typed_nsga2','typed_nsga2_unique'):
        from .typed_baseline import run_typed_nsga2,run_typed_nsga2_unique
        if contract.codec is None:raise ValueError('typed_nsga2 needs codec')
        result=(run_typed_nsga2 if algorithm=='typed_nsga2' else run_typed_nsga2_unique)(ledger,contract.codec,seed,population,budget)
    elif algorithm=='random':
        rng=np.random.default_rng(seed);X=ledger.xl+rng.random((budget,ledger.n_var))*(ledger.xu-ledger.xl)
        F=ledger.evaluate(X);archive=core.Archive(max_size=population);archive.update(X,F)
        x,f=archive.output(population)
        result=core.RunResult('random',ledger.name,seed,x,f,budget,[],{})
    else:raise ValueError('Unknown algorithm')
    if result.evaluations!=ledger.spent or ledger.spent!=budget:
        raise AssertionError((result.evaluations,ledger.spent,budget))
    if ext is not None:result.diagnostics['typed_extension']=ext.diagnostics()
    result.diagnostics.update(actual_evaluated_vectors=ledger.spent,batch_calls=ledger.batch_calls,
        official_baseline=False, implementation='inherited source, not official upstream binaries')
    return AuditedRun(result,ledger)
