"""Deployment wrapper. Search code/configuration is separately frozen.

No objective caching, cross-run training data, hidden enumeration, or automatic
activation of unsupported variable/constraint types.
"""
from mosaic14.bootstrap import EvaluationLedger,AuditedRun,ProblemContract
from mosaic14.engine import run_fast_h0
from mosaic14.fast import PolicyCodec
from mosaic14.bootstrap import run_fast_v10
from mosaic14.variants import CONFIGS,SearchHarness
from harnesslab.api import solve as previous_solve
from harnesslab.problems import OrderedSubsetCodec
from mosaic.rgv import RGVCodec

VERSION='MOSAIC-v14-Efficiency-Lab'

def solve(problem, *, seed:int=1, budget:int=1024, population:int=32,
          contract:ProblemContract=ProblemContract(), strategy:str='incumbent')->AuditedRun:
    """Use fast_h0 for execution-equivalent accelerated v13 H0.

    incumbent: unchanged Fast-v10 dispatch, including its continuous fallback.
    fast_h0: exact-trace engineering candidate (tested numerical environment).
    local24/refit32: explicitly experimental policy changes, not auto-selected.
    """
    if strategy=='incumbent':
        return previous_solve(problem,seed,budget,population,contract,strategy='incumbent')
    if strategy not in ('incumbent_cached','fast_h0','local24','refit32'):
        raise ValueError('Choose incumbent, incumbent_cached, fast_h0, local24, or refit32')
    if budget<population or population<8:raise ValueError('Require budget >= population >= 8')
    if not contract.deterministic or contract.constraints not in ('box','feasible_decoder'):
        raise NotImplementedError('Noise and general constraints need separately validated adapters')
    if contract.representation!='ordered_subset' or contract.codec is None or problem.n_obj!=2:
        raise NotImplementedError('This extension supports deterministic bi-objective ordered subsets only')
    if type(contract.codec) not in (RGVCodec,OrderedSubsetCodec):
        raise NotImplementedError('The exact codec rewrite is certified only for the two included codecs')
    ledger=EvaluationLedger(problem,budget)
    if strategy=='incumbent_cached':
        result=run_fast_v10(ledger,PolicyCodec(contract.codec),seed,population,budget)
    else:
        result=run_fast_h0(ledger,contract.codec,seed,population,budget,CONFIGS[strategy],harness_type=SearchHarness)
    if result.evaluations!=ledger.spent or ledger.spent!=budget:raise AssertionError('Budget mismatch')
    result.algorithm=VERSION+'-'+strategy
    result.diagnostics.update(strategy=strategy,engineering_equivalent_to=('v13-H0' if strategy=='fast_h0' else 'Fast-v10' if strategy=='incumbent_cached' else None),
                              no_universal_sota_claim=True,empirical_scope_only=True)
    return AuditedRun(result,ledger)
