import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import json
import numpy as np
import pytest
from mosaic14.bootstrap import ROOT,V13,make_problem,EvaluationLedger
from mosaic14.fast import PolicyCodec,CachedHV
from mosaic14.engine import run_fast_h0
from mosaic14.variants import SearchHarness,CONFIGS
from harnesslab.efficient_engine import run_efficient
from harnesslab.efficient import FAST_CONFIGS
from harnesslab.model import features,hypervolume_improvement

SPECS=json.loads((ROOT/'protocol/instances.json').read_text())
def spec(kind):return next(s for s in SPECS if s['kind']==kind)

@pytest.mark.parametrize('kind',['rgv','tour','job'])
def test_codec_rng_and_features(kind):
 p=make_problem(spec(kind));c=PolicyCodec(p.codec);r=np.random.default_rng(38)
 for i in range(120):
  x=r.random(p.n_var);y=r.random(p.n_var);a=np.random.default_rng(i);b=np.random.default_rng(i)
  for e in range(4):
   expected=p.codec.mutate(x,y,e,a);got=c.mutate(x,y,e,b)
   assert np.array_equal(expected,got)
   assert a.bit_generator.state==b.bit_generator.state
   assert np.array_equal(c.feature_matrix(got),features(got,p.codec))
   assert np.array_equal(c.decode(got),p.codec.decode(got))
  z=c.encode([0,1]);z[:]=10;assert np.all(c.encode([0,1])<=1)

@pytest.mark.parametrize('m',[0,1,8,32])
def test_hvi_exact(m):
 r=np.random.default_rng(444);F=r.uniform(-.5,1.5,(m,2));P=r.uniform(-1,2,(40,2));ref=np.array([1.2,1.2]);hv=CachedHV()
 assert np.array_equal(hv(P,F,ref),hypervolume_improvement(P,F,ref))
 assert np.array_equal(hv(P,F.copy(),ref),hypervolume_improvement(P,F,ref))
 assert hv.hits==1

@pytest.mark.parametrize('kind',['rgv','tour','job'])
def test_full_small_parity(kind):
 a=[]
 for fn in [run_efficient,run_fast_h0]:
  p=make_problem(spec(kind));l=EvaluationLedger(p,160)
  result=fn(l,p.codec,571,32,160,FAST_CONFIGS['no_uncertainty_linear'])
  assert l.spent==p.calls==result.evaluations==160
  a.append([np.asarray(l.X),np.asarray(l.F),result.X,result.F])
 assert all(np.array_equal(x,y) for x,y in zip(*a))

@pytest.mark.parametrize('name',['bounded24','pool4','local24','local48','local_all','refit32','local24_refit32','local24_random'])
def test_variants_ledger_and_archive_truth(name):
 p=make_problem(spec('job'));l=EvaluationLedger(p,128)
 r=run_fast_h0(l,p.codec,711,32,128,CONFIGS[name],harness_type=SearchHarness)
 assert l.spent==p.calls==r.evaluations==128
 for x,f in zip(r.X,r.F):assert any(np.array_equal(x,a) and np.array_equal(f,b) for a,b in zip(l.X,l.F))
 h=r.diagnostics['harness']
 assert all(d['train_fe']<d['fe'] for d in h['forecasts'])
 assert all(len(set(p.codec.decode(x)))==len(p.codec.decode(x)) for x in l.X)

@pytest.mark.parametrize('kind',['rgv','tour','job'])
def test_neighborhood_cache_parity(kind):
 runs=[]
 for name in ['local24','local24_no_cache']:
  p=make_problem(spec(kind));l=EvaluationLedger(p,160)
  r=run_fast_h0(l,p.codec,419,32,160,CONFIGS[name],harness_type=SearchHarness)
  runs.append([np.array(l.X),np.array(l.F),r.X,r.F])
 assert all(np.array_equal(x,y) for x,y in zip(*runs))

def test_budget_no_free_calls():
 p=make_problem(spec('job'));l=EvaluationLedger(p,1);l.evaluate(p.codec.encode([0]))
 with pytest.raises(RuntimeError):l.evaluate(p.codec.encode([1]))
 assert l.spent==p.calls==1

@pytest.mark.parametrize('n',[12,16])
def test_large_feature_and_rng_parity(n):
 s=next(s for s in SPECS if s['partition']=='stress' and s['kind']=='job' and s['n']==n)
 p=make_problem(s);c=PolicyCodec(p.codec);r=np.random.default_rng(198)
 for i in range(30):
  x,y=r.random(p.n_var),r.random(p.n_var)
  a,b=np.random.default_rng(i),np.random.default_rng(i)
  for e in range(4):
   aa=p.codec.mutate(x,y,e,a);bb=c.mutate(x,y,e,b)
   assert np.array_equal(aa,bb)
   assert a.bit_generator.state==b.bit_generator.state
   assert np.array_equal(c.feature_matrix(bb),features(bb,p.codec))


def test_feature_equivalence_for_distinct_encodings():
 p=make_problem(spec('job'));c=PolicyCodec(p.codec)
 x=c.encode([3,0,2]);y=x.copy();y[:8][y[:8]>.5]=.9;y[8:][y[8:]<.9]*=.8
 assert not np.array_equal(x,y)
 assert c.key(x)==c.key(y)
 assert np.array_equal(c.feature_matrix(x),c.feature_matrix(y))


def test_hvi_front_invalidation():
 h=CachedHV();P=np.array([[.1,.6],[.2,.4]]);F=np.array([[.3,.3]])
 a=h(P,F,[1.2,1.2]);b=h(P,F,[1.2,1.2]);F[0]=[.05,.1];z=h(P,F,[1.2,1.2])
 assert h.rebuilds==2 and h.hits==1
 assert np.array_equal(a,b) and not np.array_equal(a,z)


def test_model_refit_version_and_forecast_order():
 p=make_problem(spec('job'));l=EvaluationLedger(p,256)
 r=run_fast_h0(l,p.codec,963,32,256,CONFIGS['refit32'],harness_type=SearchHarness)
 h=r.diagnostics['harness'];fits=h['model_fits'];versions=[z['version'] for z in fits]
 assert versions==list(range(1,len(fits)+1))
 assert [z['fe'] for z in fits]==[64,96,128,160,192,224]
 for z in h['forecasts']:
  assert z['train_fe']<z['fe'];assert np.array_equal(z['actual'],l.F[z['fe']-1])


def test_dual_parent_provenance():
 p=make_problem(spec('job'));l=EvaluationLedger(p,160)
 r=run_fast_h0(l,p.codec,322,32,160,CONFIGS['dual24'],harness_type=SearchHarness)
 h=r.diagnostics['harness']
 for z in h['forecasts']:
  if 'parent_is_donor'in z:assert isinstance(z['parent_is_donor'],bool)


def test_prediction_cannot_write_observations():
 from mosaic14.variants import SearchConfig
 from mosaic14.fast import FastHarness
 p=make_problem(spec('job'));c=PolicyCodec(p.codec);rng=np.random.default_rng(853)
 X=rng.random((64,p.n_var));F=p.evaluate(X)
 h=FastHarness(c,853,128,SearchConfig(model='linear',uncertainty=0.));h.initialize(X,F)
 h.model.fit(c.feature_matrix(X),(F-h.low)/h.scale);h.fit_at=64
 h.model.predict=lambda Z:(np.full((len(Z),2),np.nan),np.ones((len(Z),2)))
 calls=p.calls;before=np.array(h.dataF)
 child=c.encode([0,1,2]);ret,e=h.intervene(child,0,X[0],X[1],set(),F,64)
 assert np.array_equal(ret,child) and h.pending is None
 assert np.array_equal(before,h.dataF) and p.calls==calls
 assert h.events[-1]['reason']=='nonfinite_prediction_fallback'


def test_no_oracle_available_in_candidate_generation():
 from mosaic14.variants import SearchHarness
 p=make_problem(spec('tour'));c=PolicyCodec(p.codec)
 h=SearchHarness(c,199,1024,CONFIGS['local24'])
 x=c.encode([0,1,3,5]);y=c.encode([3,2,6]);calls=p.calls
 candidates,experts=h.make_candidates(x,0,x,y,set())
 assert p.calls==calls==0
 assert len(candidates)<=25 and np.array_equal(candidates[0],x)
 assert len({c.key(z) for z in candidates})==len(candidates)
 assert all(0<=e<4 for e in experts)

@pytest.mark.parametrize('k',[2,4,8])
def test_unique_neighborhood_size(k):
 p=make_problem(spec('job'));c=PolicyCodec(p.codec);h=SearchHarness(c,91,1024,CONFIGS['local24'])
 pi=tuple(range(k));nb=h.neighbors(c.encode(pi));keys=[x for x,e in nb]
 # Swap + relocate deduplicates adjacent-swap equivalences; add/drop cannot
 # overlap because they change cardinality. Derived for k >= 2.
 expected=k*(k-1)//2+(k-1)*(k-2)+k+(c.n-k)*(k+1)
 assert len(keys)==len(set(keys))==expected
 assert pi not in keys
