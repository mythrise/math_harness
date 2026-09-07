import pytest,numpy as np
from mosaic_solve import solve,ProblemContract
from mosaic14.bootstrap import ROOT,make_problem
import json
S=json.loads((ROOT/'protocol/instances.json').read_text())[0]

def test_api_budget():
 p=make_problem(S)
 with pytest.raises(ValueError):solve(p,budget=4,strategy='fast_h0')

def test_api_refuses_noise():
 p=make_problem(S)
 with pytest.raises(NotImplementedError):solve(p,strategy='fast_h0',contract=ProblemContract(deterministic=False))

def test_api_refuses_unknown_strategy():
 with pytest.raises(ValueError):solve(make_problem(S),strategy='universal')

def test_api_valid():
 p=make_problem(S);r=solve(p,seed=24,budget=128,strategy='fast_h0',contract=ProblemContract(representation='ordered_subset',codec=p.codec,constraints='feasible_decoder'))
 assert r.ledger.spent==p.calls==128
 assert r.result.diagnostics['engineering_equivalent_to']=='v13-H0'

def test_cached_incumbent_full_trace():
 import numpy as np
 from mosaic14.bootstrap import make_problem,ROOT
 from mosaic_solve import solve,ProblemContract
 import json
 spec=next(s for s in json.loads((ROOT/'protocol/instances.json').read_text())if s['kind']=='job')
 runs=[]
 for strategy in ['incumbent','incumbent_cached']:
  p=make_problem(spec);r=solve(p,seed=308,budget=128,strategy=strategy,contract=ProblemContract(representation='ordered_subset',codec=p.codec,constraints='feasible_decoder'))
  runs.append([np.array(r.ledger.X),np.array(r.ledger.F),r.result.X,r.result.F])
 assert all(np.array_equal(a,b)for a,b in zip(*runs))
