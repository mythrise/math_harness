"""MOSAIC v10-R1: final interface with explicit, tested capability boundaries.

The held-out failure of equal-objective behavior retention is preserved in the
research branch. R1 keeps only one representative per objective in structured
search, and uses an eligibility/novelty router rather than the unproven quantile
controller. Continuous inputs dispatch to the original frozen SQMoE v9.
"""
from dataclasses import dataclass
from typing import Iterable
import numpy as np
from .api import optimize, ProblemContract, EvaluationLedger, AuditedRun,core
from .graph_search import run_graph

VERSION='MOSAIC-v10-R1'

def solve(problem, seed:int=1, budget:int=2080, population:int=32,
          contract:ProblemContract=ProblemContract())->AuditedRun:
    if budget<population or population<8:
        raise ValueError('Require budget >= population >= 8')
    if not contract.deterministic or contract.constraints not in ('box','feasible_decoder'):
        raise NotImplementedError('Noisy or general nonlinear-constrained models need validated adapters')
    if contract.representation=='continuous_box' and contract.codec is None:
        result=optimize(problem,seed,budget,population,contract,algorithm='mosaic_v9')
        result.result.diagnostics['backend']='frozen_v9_exact_fallback'
    elif contract.representation=='ordered_subset' and contract.codec is not None:
        ledger=EvaluationLedger(problem,budget)
        r=run_graph(ledger,contract.codec,seed,population,budget,mode='no_memory',ties_per_objective=1)
        assert r.evaluations==ledger.spent==budget
        r.diagnostics['backend']='typed_archive_novelty_router'
        result=AuditedRun(r,ledger)
    else:
        raise NotImplementedError('Unsupported representation; silent rounding is forbidden')
    result.result.algorithm=VERSION
    return result

@dataclass
class ExhaustiveResult:
    X:np.ndarray
    F:np.ndarray
    evaluations:int
    certificate:dict

def enumerate_finite(problem,encoded_designs:Iterable[np.ndarray],cardinality:int,
                     budget:int,scope:str,chunk_size:int=2048)->ExhaustiveResult:
    """Exhaustively evaluate a caller-declared finite domain through the ledger.

    A certificate is conditional on the generator enumerating that full domain;
    it does not certify the correctness of the mathematical model or a larger
    policy space. No Pareto oracle is supplied to this routine.
    """
    if cardinality<=0 or budget<cardinality or chunk_size<1:
        raise ValueError('Insufficient budget for full enumeration')
    ledger=EvaluationLedger(problem,budget)
    xs=[];fs=[];batch=[]
    def consume(batch):
        X=np.asarray(batch,float);F=ledger.evaluate(X)
        xs.extend(X);fs.extend(F)
    for x in encoded_designs:
        batch.append(np.asarray(x,float))
        if len(batch)==chunk_size:consume(batch);batch=[]
    if batch:consume(batch)
    if ledger.spent!=cardinality:raise AssertionError('Generator cardinality mismatch')
    X=np.asarray(xs);F=np.asarray(fs)
    unique,index=np.unique(F,axis=0,return_index=True)
    nd=core.nondominated_mask(unique);index=index[nd]
    return ExhaustiveResult(X[index],F[index],ledger.spent,
      {'scope':scope,'declared_cardinality':cardinality,'evaluations':ledger.spent,
       'domain_exhausted':True,'unique_objective_vectors':len(unique),
       'front_size':len(index),'model_correctness_certified':False,
       'larger_policy_space_certified':False})
