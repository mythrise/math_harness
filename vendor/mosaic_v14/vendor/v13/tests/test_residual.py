from pathlib import Path
import sys,json
import numpy as np
import pytest
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from harnesslab.bootstrap import EvaluationLedger,run_fast_v10
from harnesslab.problems import make_problem
from harnesslab.residual import ResidualConfig,ResidualHarness,ObjectiveModel,RESIDUAL_CONFIGS
from harnesslab.residual_engine import run_residual
S=json.loads((R/'protocol/instances.json').read_text())

def compare(kind,seed,cfg):
 s=next(s for s in S if s['kind']==kind and s['partition']=='development')
 p=make_problem(s);L=EvaluationLedger(p,160)
 r=run_residual(L,p.codec,seed,32,160,cfg)
 p2=make_problem(s);L2=EvaluationLedger(p2,160);r2=run_fast_v10(L2,p2.codec,seed,32,160)
 return L,r,L2,r2

@pytest.mark.parametrize('kind',['rgv','tour','job'])
@pytest.mark.parametrize('seed',[701,709])
def test_off_exact_parity(kind,seed):
 L,r,L2,r2=compare(kind,seed,ResidualConfig(enabled=False))
 for a,b in [(L.X,L2.X),(L.F,L2.F),(r.X,r2.X),(r.F,r2.F)]:np.testing.assert_array_equal(a,b)

@pytest.mark.parametrize('variant',['residual','residual_no_gate','residual_linear','residual_trees','residual_random'])
def test_all_truth_temporal_and_budget(variant):
 L,r,_,_=compare('tour',711,RESIDUAL_CONFIGS[variant])
 assert L.spent==r.evaluations==160
 F=np.asarray(L.F)
 for f in r.F:assert np.any(np.all(F==f,axis=1))
 for log in r.diagnostics['harness']['forecasts']:
  assert log['train_fe']<log['fe']<=160
  np.testing.assert_array_equal(log['actual'],F[log['fe']-1])
 assert np.isfinite(F).all()

def test_forced_rejection_keeps_baseline_stream():
 L,r,L2,r2=compare('rgv',743,ResidualConfig(rank_threshold=2.))
 np.testing.assert_array_equal(L.X,L2.X);np.testing.assert_array_equal(L.F,L2.F)
 assert r.diagnostics['harness']['overrides']==0
 assert len(r.diagnostics['harness']['forecasts'])>0

def test_nonfinite_prediction_keeps_truth_and_log_json(monkeypatch):
 def bad(self,Z):return np.full((len(Z),2),np.nan),np.zeros((len(Z),2))
 monkeypatch.setattr(ObjectiveModel,'predict',bad)
 L,r,L2,r2=compare('rgv',743,ResidualConfig())
 np.testing.assert_array_equal(L.X,L2.X)
 assert len(r.diagnostics['harness']['events'])>0
 json.dumps(r.diagnostics['harness'],allow_nan=False)

def test_poison_prediction_is_not_promoted(monkeypatch):
 def bad(self,Z):return np.full((len(Z),2),-1e9),np.zeros((len(Z),2))
 monkeypatch.setattr(ObjectiveModel,'predict',bad)
 L,r,_,_=compare('job',751,ResidualConfig())
 assert np.min(np.asarray(L.F))>-1e9
 assert any(q['reason']=='audit_fallback' for q in r.diagnostics['harness']['forecasts'])
 assert all(any(np.array_equal(f,g)for g in L.F)for f in r.F)

def test_contract_has_no_oracle_reference():
 c=make_problem(S[0]).codec;h=ResidualHarness(c,1,128,ResidualConfig())
 assert not hasattr(h,'problem') and not hasattr(h,'evaluate')
