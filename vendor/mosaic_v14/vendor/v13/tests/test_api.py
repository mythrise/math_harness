from pathlib import Path
import sys
import pytest,numpy as np
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from harnesslab.api import solve,ProblemContract
from mosaic.rgv import RGVProblem
from src.fast_api import solve_fast

def test_default_is_incumbent():
 p=RGVProblem();q=RGVProblem();a=solve(p,17,128,32,ProblemContract('ordered_subset',p.codec,'feasible_decoder'));b=solve_fast(q,17,128,32,ProblemContract('ordered_subset',q.codec,'feasible_decoder'))
 np.testing.assert_array_equal(a.ledger.X,b.ledger.X)

def test_unsupported_contracts_do_not_silently_run():
 p=RGVProblem()
 for c in [ProblemContract(deterministic=False),ProblemContract(constraints='nonlinear'),ProblemContract(representation='continuous_box')]:
  with pytest.raises(NotImplementedError):solve(p,contract=c,strategy='audited_infill')
 assert p.calls==0

def test_api_records_true_fee():
 p=RGVProblem();r=solve(p,17,128,32,ProblemContract('ordered_subset',p.codec,'feasible_decoder'),strategy='audited_infill')
 assert r.result.evaluations==r.ledger.spent==p.calls==128
