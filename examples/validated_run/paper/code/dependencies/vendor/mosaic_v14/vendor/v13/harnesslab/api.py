"""Validated opt-in research API. No automatic claim of universal superiority."""
from .bootstrap import ProblemContract,AuditedRun,EvaluationLedger
from src.fast_api import solve_fast
from .efficient import FAST_CONFIGS
from .efficient_engine import run_efficient

VERSION='MOSAIC-v13-Audited-Infill'

def solve(problem,seed:int=1,budget:int=1024,population:int=32,
          contract:ProblemContract=ProblemContract(),strategy:str='incumbent')->AuditedRun:
    """Default stays Fast-v10. Set strategy='audited_infill' explicitly.

    New branch supports deterministic, feasible ordered subsets with exactly two
    minimization objectives. Its predictor learns ONLY the current run's paid
    evaluations. Reference fronts and model internals are never an input.
    """
    if strategy=='incumbent':return solve_fast(problem,seed,budget,population,contract)
    if strategy!='audited_infill':raise ValueError("strategy must be 'incumbent' or 'audited_infill'")
    if budget<population or population<8:raise ValueError('Require budget >= population >= 8')
    if not contract.deterministic or contract.constraints not in ('box','feasible_decoder'):
        raise NotImplementedError('Noise/general constraints need separately validated evaluators')
    if contract.representation!='ordered_subset' or contract.codec is None or problem.n_obj!=2:
        raise NotImplementedError('Audited infill currently requires deterministic bi-objective ordered-subset encoding')
    ledger=EvaluationLedger(problem,budget)
    result=run_efficient(ledger,contract.codec,seed,population,budget,FAST_CONFIGS['no_uncertainty_linear'])
    if result.evaluations!=ledger.spent or ledger.spent!=budget:raise AssertionError('Evaluation accounting mismatch')
    result.algorithm=VERSION
    result.diagnostics.update(research_opt_in=True,official_sota=False,guaranteed_nonregression=False)
    return AuditedRun(result,ledger)
