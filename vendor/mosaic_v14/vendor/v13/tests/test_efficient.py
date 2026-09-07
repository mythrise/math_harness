from pathlib import Path
import sys,json
import numpy as np
import pytest
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from harnesslab.bootstrap import EvaluationLedger,run_typed_nsga2_unique
from harnesslab.problems import make_problem,OrderedSubsetCodec
from harnesslab.residual import ResidualConfig
from harnesslab.residual_engine import run_residual
from harnesslab.efficient import CachedCodec
from harnesslab.efficient_engine import run_efficient
from harnesslab.nsga_residual import run_nsga_residual
S=json.loads((R/'protocol/instances.json').read_text())

@pytest.mark.parametrize('n',[8,12,16])
def test_cached_codec_does_not_change_rng_or_output(n):
 a=OrderedSubsetCodec(n);b=CachedCodec(a);rr=np.random.default_rng(n)
 for s in range(16):
  x=rr.random(2*n);d=rr.random(2*n)
  for e in range(4):
   r1=np.random.default_rng(s);r2=np.random.default_rng(s)
   np.testing.assert_array_equal(a.mutate(x,d,e,r1),b.mutate(x,d,e,r2))
   assert r1.bit_generator.state==r2.bit_generator.state

@pytest.mark.parametrize('kind',['rgv','tour','job'])
def test_efficient_full_trace_parity(kind):
 s=next(x for x in S if x['kind']==kind and x['partition']=='development');out=[]
 for fn in [run_residual,run_efficient]:
  p=make_problem(s);L=EvaluationLedger(p,192);r=fn(L,p.codec,12313,32,192,ResidualConfig(model='linear'));out.append((L,r))
 for attr in ['X','F']:np.testing.assert_array_equal(getattr(out[0][0],attr),getattr(out[1][0],attr))
 for attr in ['X','F']:np.testing.assert_array_equal(getattr(out[0][1],attr),getattr(out[1][1],attr))

@pytest.mark.parametrize('kind',['rgv','tour','job'])
def test_nsga_alloff_exact_parity(kind):
 s=next(x for x in S if x['kind']==kind and x['partition']=='development');out=[]
 for off in [False,True]:
  p=make_problem(s);L=EvaluationLedger(p,128)
  r=run_nsga_residual(L,p.codec,1921,32,128,ResidualConfig(enabled=False))if off else run_typed_nsga2_unique(L,p.codec,1921,32,128)
  out.append((L,r))
 np.testing.assert_array_equal(out[0][0].X,out[1][0].X)
 np.testing.assert_array_equal(out[0][1].F,out[1][1].F)

def test_nsga_harness_batch_forecasts_before_truth():
 s=next(x for x in S if x['kind']=='tour'and x['partition']=='development');p=make_problem(s);L=EvaluationLedger(p,192)
 r=run_nsga_residual(L,p.codec,1921,32,192,ResidualConfig(model='linear'))
 assert p.calls==L.spent==192
 for row in r.diagnostics['harness']['forecasts']:
  assert row['train_fe']<row['fe'];np.testing.assert_array_equal(L.F[row['fe']-1],row['actual'])
