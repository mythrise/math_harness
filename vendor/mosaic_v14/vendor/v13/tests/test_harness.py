import sys,json
from pathlib import Path
import numpy as np
import pytest
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from harnesslab.bootstrap import EvaluationLedger,run_fast_v10,run_typed_nsga2_unique
from harnesslab.engine import Config,run_harness
from harnesslab.model import hypervolume_improvement,PredictionModel,features
from harnesslab.metrics import hv2
from harnesslab.problems import OrderedSubsetCodec,make_problem
from mosaic.rgv import RGVCodec

def spec():return json.loads((R/'protocol/instances.json').read_text())[0]
def run(cfg=Config(),budget=128):
 p=make_problem(spec());L=EvaluationLedger(p,budget);r=run_harness(L,p.codec,17,32,budget,cfg);return p,L,r

@pytest.mark.parametrize('n',[3,8,12,16])
def test_codec_validity(n):
 c=OrderedSubsetCodec(n);rng=np.random.default_rng(n)
 for _ in range(12):
  x=rng.random(2*n);p=c.decode(x);assert np.array_equal(p,c.decode(c.encode(p)))
  for e in range(4):
   y=c.mutate(x,rng.random(2*n),e,rng);q=c.decode(y)
   assert len(q)>=1 and len(q)==len(set(q)) and q.max()<n

def test_codec_legacy_parity():
 a=RGVCodec();b=OrderedSubsetCodec(8)
 for s in range(12):
  r=np.random.default_rng(s);x=r.random(16);y=r.random(16)
  assert np.array_equal(a.decode(x),b.decode(x))
  for e in range(4):assert np.array_equal(a.mutate(x,y,e,np.random.default_rng(s)),b.mutate(x,y,e,np.random.default_rng(s)))

def test_hvi_against_independent_integral():
 rng=np.random.default_rng(8);ref=np.array([1.1,1.1])
 for _ in range(30):
  A=rng.random((12,2));P=rng.random((8,2))*.9-.05
  est=hypervolume_improvement(P,A,ref)
  expected=np.array([hv2(np.vstack([A,p]),ref)-hv2(A,ref) for p in P])
  np.testing.assert_allclose(est,expected,atol=1e-12)

@pytest.mark.parametrize('cfg',[Config(),Config(planner='random'),Config(planner='mission'),Config(backend='nsga2')])
def test_budget_prediction_separation(cfg):
 p,L,r=run(cfg)
 assert r.evaluations==L.spent==p.calls==128
 allF=np.asarray(L.F)
 for f in r.F:assert np.any(np.all(f==allF,axis=1))
 for f in r.F:assert not np.any(np.all(r.F<=f,axis=1)&np.any(r.F<f,axis=1))
 fits={f['version']:f['fe'] for f in r.diagnostics['model_fits']}
 for rec in r.diagnostics['forecasts']:
  if rec['prediction'] is not None:assert fits[rec['model_version']]<rec['fe']


def test_no_reference():
 p=make_problem(spec());L=EvaluationLedger(p,128)
 with pytest.raises(RuntimeError):L.pareto_front()


def test_overflow():
 p=make_problem(spec());L=EvaluationLedger(p,1);x=p.codec.encode([0]);L.evaluate(x)
 with pytest.raises(RuntimeError):L.evaluate(x)
 assert p.calls==L.spent==1


def test_determinism():
 p,L,r=run();p2,L2,r2=run();np.testing.assert_array_equal(L.X,L2.X);np.testing.assert_array_equal(L.F,L2.F)


def test_same_initialization():
 p,L,r=run();p2=make_problem(spec());L2=EvaluationLedger(p2,128);run_fast_v10(L2,p2.codec,17,32,128)
 np.testing.assert_array_equal(np.asarray(L.X)[:32],np.asarray(L2.X)[:32])


def test_overoptimism_is_not_truth_and_triggers_fallback(monkeypatch):
 oldfit=PredictionModel.fit
 def fit(self,Z,Y):
  d=oldfit(self,Z,Y);self.validation_score=1.;self.validation_error=0.;return d
 def bad_predict(self,Z):return np.full((len(Z),2),-1e6),np.zeros((len(Z),2))
 monkeypatch.setattr(PredictionModel,'fit',fit);monkeypatch.setattr(PredictionModel,'predict',bad_predict)
 p,L,r=run(budget=160)
 assert any(c.get('reason')=='audit_fallback' for c in r.diagnostics['contracts'])
 assert np.min(np.asarray(L.F))>-1e6
 assert all(np.any(np.all(np.asarray(L.F)==f,axis=1)) for f in r.F)
