from pathlib import Path
import sys,json,hashlib,math
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mosaic.api import EvaluationLedger,ProblemContract,optimize,core
from mosaic.final import solve,enumerate_finite
from mosaic.rgv import RGVProblem,RGVCodec,simulate_fast,all_policies
from mosaic.metrics import hv2,score

@pytest.mark.parametrize('group',[1,2,3])
def test_fast_simulator_matches_event_log(group):
    p=RGVProblem(group);rng=np.random.default_rng(337)
    for _ in range(40):
        o=p.codec.decode(rng.random(16));log=p.simulate_log(o)
        n,m=simulate_fast(o,p.travel,p.process,p.loads,p.wash,p.horizon)
        assert n==sum(x['was_loaded'] for x in log)
        assert m==sum(x['travel'] for x in log)
        assert all(x['end']<=p.horizon for x in log)
        for x in log:
            assert x['service_start']>=x['arrival']
            if x['was_loaded']:assert x['service_start']>=x['processing_ready_before']

@pytest.mark.parametrize('group',[1,2,3])
def test_single_machine_analytic(group):
    p=RGVProblem(group);L=p.loads[0]
    first=2*L+p.process+p.wash
    expected=1+math.floor((p.horizon-first)/(L+p.process))
    n,m=simulate_fast(np.array([0]),p.travel,p.process,p.loads,p.wash,p.horizon)
    assert n==expected and m==0

def test_codec_roundtrip_and_valid_variation():
    c=RGVCodec();rng=np.random.default_rng(501)
    for _ in range(200):
        p=rng.random(16);q=rng.random(16);o=c.decode(p)
        assert np.array_equal(c.decode(c.encode(o)),o)
        for e in range(4):
            z=c.mutate(p,q,e,rng);order=c.decode(z)
            assert 1<=len(order)<=8 and len(np.unique(order))==len(order)
            assert np.all((z>=0)&(z<=1))

def test_ledger_boundary_failure_and_no_free_attempts():
    p=RGVProblem();ledger=EvaluationLedger(p,2)
    ledger.evaluate(np.zeros(16));assert ledger.spent==p.calls==1
    with pytest.raises(RuntimeError):ledger.evaluate(np.zeros((2,16)))
    assert ledger.spent==p.calls==1
    with pytest.raises(RuntimeError):ledger.pareto_front()

@pytest.mark.parametrize('algorithm',['v10','v9','typed_nsga2_unique'])
def test_strict_external_count(algorithm):
    p=RGVProblem();c=ProblemContract('ordered_subset',p.codec,'feasible_decoder')
    if algorithm=='v10':r=solve(p,3,256,32,c)
    else:r=optimize(p,3,256,32,c,algorithm='mosaic_v9' if algorithm=='v9' else algorithm)
    assert p.calls==r.ledger.spent==r.result.evaluations==256

def test_determinism():
    def run():
        p=RGVProblem();return solve(p,998,256,32,ProblemContract('ordered_subset',p.codec,'feasible_decoder')).result
    a,b=run(),run();assert np.array_equal(a.X,b.X) and np.array_equal(a.F,b.F)

def test_exact_continuous_fallback():
    p=core.make_dtlz('dtlz2',5,12)
    a=optimize(p,77,256,32,algorithm='mosaic_v9')
    b=solve(p,77,256,32)
    assert np.array_equal(a.result.X,b.result.X) and np.array_equal(a.result.F,b.result.F)
    assert a.ledger.spent==b.ledger.spent==256

def test_frozen_sources_unchanged():
    f=json.loads((ROOT/'docs/R1_FROZEN_PROTOCOL.json').read_text())
    for file,sha in f['sources'].items():assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==sha

def test_metrics_known_rectangles():
    assert abs(hv2(np.array([[0.,1.],[1.,0.]]),np.array([2.,2.]))-3)<1e-12
    R=np.array([[0.,1.],[1.,0.]])
    s=score(R,R);assert s['igd_plus']==s['hv_gap']==0 and s['exact_front_hit']

def test_enumeration_cardinality():
    orders,sizes=all_policies();expected=sum(math.factorial(8)//math.factorial(8-k) for k in range(1,9))
    assert len(orders)==expected==109600
    assert len(set(tuple(o[:k]) for o,k in zip(orders,sizes)))==expected

def test_certifier_requires_budget_and_counts_it():
    p=RGVProblem();c=p.codec;designs=[c.encode([0]),c.encode([1]),c.encode([0,1])]
    with pytest.raises(ValueError):enumerate_finite(p,designs,3,2,'tiny')
    r=enumerate_finite(p,designs,3,3,'three predefined policies')
    assert r.evaluations==p.calls==3 and r.certificate['domain_exhausted']
    assert not r.certificate['larger_policy_space_certified']

def test_unsupported_contract_rejected():
    p=RGVProblem()
    with pytest.raises(NotImplementedError):solve(p,contract=ProblemContract(deterministic=False))
    with pytest.raises(NotImplementedError):solve(p,contract=ProblemContract(constraints='nonlinear'))
    with pytest.raises(NotImplementedError):solve(p,contract=ProblemContract(representation='permutation'))
