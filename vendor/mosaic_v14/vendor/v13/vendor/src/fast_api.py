"""Optional engineering upgrade, not an untested universal optimizer.

Only the deterministic ordered-subset branch is changed. Continuous problems
and all unsupported contracts are delegated to the unchanged v10 entry point.
"""
from .bootstrap import EvaluationLedger, AuditedRun, ProblemContract
from .fast_v10 import run_fast_v10
from mosaic.final import solve as solve_v10

VERSION='MOSAIC-v10-R1-Fast-branch'

def solve_fast(problem,seed:int=1,budget:int=2080,population:int=32,
               contract:ProblemContract=ProblemContract())->AuditedRun:
    if budget<population or population<8:
        raise ValueError('Require budget >= population >=8')
    if not contract.deterministic or contract.constraints not in ('box','feasible_decoder'):
        raise NotImplementedError('A validated noise/constraint adapter is required')
    if contract.representation=='ordered_subset' and contract.codec is not None:
        ledger=EvaluationLedger(problem,budget)
        result=run_fast_v10(ledger,contract.codec,seed,population,budget)
        assert result.evaluations==ledger.spent==budget
        result.algorithm=VERSION;result.diagnostics['search_distribution_changed']=False
        return AuditedRun(result,ledger)
    return solve_v10(problem,seed,budget,population,contract)
