import numpy as np
import pytest
from cumcm_harness.algopt import solve_linear,primal_check,milp_neighborhood,pareto_audit
from cumcm_harness.algpredict import ResidualRegressor,fit_tabular,folds_for,conformal_interval,forecast_portfolio,forecast_candidate
from cumcm_harness.alggraph import shortest_path
from cumcm_harness.algdecision import fixed_topsis,rank_acceptability,ahp_weights
from cumcm_harness.algscience import integrate_unit,checked_ivp,project_linear_invariant,adjust_pvalues,paired_summary,cluster_diagnostics
from cumcm_harness.algorithm_library import FAMILIES,external_manifest,enrich_method,select_algorithms
from cumcm_harness.algpromotion import logical_hash,promotion_decision

@pytest.mark.parametrize('scale',[True,False])
def test_lp_solution(scale):
    r=solve_linear([-1,-2],[[1,1]],[0],[4],[(0,3),(0,3)],scale_rows=scale)
    assert r['feasible'] and r['status']=='SOLVER_OPTIMAL'
    assert r['objective']==pytest.approx(-7)
    assert r['absolute_gap']<1e-7

@pytest.mark.parametrize('kinds',[[0,0],[1,1]])
def test_equality_and_nonzero_lower(kinds):
    r=solve_linear([1,2],[[1,1]],[3],[3],[(-2,4),(-2,4)],integrality=kinds)
    assert r['objective']==pytest.approx(2)

@pytest.mark.parametrize('kind',[[0],[1]])
def test_infeasible_not_green(kind):
    r=solve_linear([1],[[1]],[3],[4],[(0,1)],integrality=kind)
    assert not r['feasible'] and r['status']=='INFEASIBLE'

def test_unbounded():
    assert solve_linear([-1],bounds=[(0,np.inf)])['status']=='UNBOUNDED'

@pytest.mark.parametrize('field,val',[('c',[np.nan]),('bounds',[(2,1)]),('integrality',[2]),('seconds',0)])
def test_bad_lp_inputs(field,val):
    kw={'c':[1]};kw[field]=val
    with pytest.raises(ValueError):solve_linear(**kw)

def test_milp_not_relaxation():
    r=solve_linear([-3,-2],[[2,2]],None,[3],[(0,1)]*2,integrality=[1,1])
    assert r['objective']==pytest.approx(-3)
    assert r['max_integrality_violation']<1e-7

def test_local_bound_not_global_certificate():
    r=milp_neighborhood([-3,-2],[[2,2]],None,[3],[(0,1)]*2,[1,1],[0,1],[0,1])
    assert r['objective']==pytest.approx(-3) and r['dual_bound'] is None

def test_bad_incumbent_refused():
    with pytest.raises(ValueError):milp_neighborhood([-1],[[1]],None,[0],[(0,1)],[1],[1],[0])

def test_front_audit():
    obj=lambda x:[x[0],1-x[0]]
    r=pareto_audit([[0],[.5],[1]],[[0,1],[.5,.5],[1,0]],obj)
    assert r['valid'] and r['verification_evaluations']==3
    assert not pareto_audit([[0]],[[999,1]],obj)['valid']
    assert not pareto_audit([[0],[1]],[[0,0],[1,1]],lambda x:[x[0],x[0]])['valid']

def test_inactive_residual_is_identical_and_no_global_rng_change():
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import Ridge
    rng=np.random.default_rng(0);X=rng.normal(size=(40,3));y=X[:,0]+rng.normal(size=40)*.1
    np.random.seed(8);state=np.random.get_state()
    m=ResidualRegressor(alpha=0).fit(X,y)
    ref=make_pipeline(StandardScaler(),Ridge(alpha=1.)).fit(X,y)
    assert np.array_equal(m.predict(X),ref.predict(X))
    after=np.random.get_state();assert state[0]==after[0] and np.array_equal(state[1],after[1]) and state[2:]==after[2:]

def test_tabular_inner_only():
    rng=np.random.default_rng(1);X=rng.normal(size=(48,3));y=X[:,0]+rng.normal(size=48)*.1
    m=fit_tabular(X,y,include_residual=False,max_candidates=2)
    assert m.report['fits']==7 and m.report['test_used'] is False
    assert m.predict(X[:2]).shape==(2,)

def test_tabular_residual_fits_count():
    rng=np.random.default_rng(1);X=rng.normal(size=(40,2));y=X[:,0]**2
    m=fit_tabular(X,y,include_residual=True)
    assert m.report['fits'] in (28,32)

def test_classification_probability():
    rng=np.random.default_rng(1);X=rng.normal(size=(60,3));y=(X[:,0]>0).astype(int)
    m=fit_tabular(X,y,task='classification')
    assert np.allclose(m.predict_proba(X[:2]).sum(axis=1),1)

def test_fit_budget_counts_nested_models():
    with pytest.raises(ValueError,match='Fit budget'):fit_tabular(np.ones((48,2)),np.arange(48),max_fits=10,include_residual=True)

@pytest.mark.parametrize('kind',['group','time'])
def test_split_isolation(kind):
    X=np.arange(120).reshape(60,2);y=np.arange(60);groups=np.repeat(np.arange(12),5)
    ff=folds_for(X,y,kind=kind,groups=groups)
    for tr,va in ff:
        assert not set(tr)&set(va)
        if kind=='time':assert max(tr)<min(va)
        else:assert not set(groups[tr])&set(groups[va])

def test_unknown_dependence_blocks():
    with pytest.raises(ValueError):folds_for(np.ones((20,2)),np.arange(20),kind='unknown')

def test_conformal_small_calibration_infinite():
    r=conformal_interval([0],[1],[0],alpha=.1,exchangeable=True)
    assert np.isinf(r['quantile'])

def test_conformal_quantile_exact():
    r=conformal_interval([0],np.arange(1,10),np.zeros(9),alpha=.2,exchangeable=True)
    assert r['quantile']==8

def test_conformal_requires_assumptions():
    with pytest.raises(ValueError):conformal_interval([1],[2],[1])

def test_rolling_history_only():
    y=np.sin(np.arange(120)*2*np.pi/12)+np.arange(120)*.01
    r=forecast_portfolio(y,12,season=12)
    assert r['prediction'].shape==(12,) and r['fits']==16
    assert r['origin_starts']==[84,96,108] and not r['test_used']

def test_forecast_short_or_overbudget():
    for kw in [{'history':[1,2,3],'horizon':10},{'history':np.arange(120),'horizon':12,'max_fits':2}]:
        with pytest.raises(ValueError):forecast_portfolio(**kw)

@pytest.mark.parametrize('method',['naive','linear','seasonal','seasonal_residual','ridge_lags'])
def test_forecast_each(method):
    assert np.isfinite(forecast_candidate(np.arange(72),6,method,6)).all()

def test_fixed_anchor_insertion_invariant():
    X=[[2,4],[4,2]];weights=[.4,.6];a=[[0,10],[0,10]]
    first=fixed_topsis(X,weights,[1,1],a)
    after=fixed_topsis(X+[[0,0]],weights,[1,1],a)
    assert np.array_equal(first,after[:2])

def test_cost_criterion_monotone():
    s=fixed_topsis([[2],[4]],[1],[False],[[0,10]])
    assert s[0]>s[1]

@pytest.mark.parametrize('X,w,a',[([[20]],[1],[[0,10]]),([[2]],[-1],[[0,10]]),([[2]],[1],[[2,2]])])
def test_bad_mcda_contract(X,w,a):
    with pytest.raises(ValueError):fixed_topsis(X,w,[True],a)

def test_rank_ties_fair():
    r=rank_acceptability([[1],[1],[1]],[True],[[0,2]],draws=32)
    assert np.allclose(r['rank_probability'],1/3)

def test_acceptability_double_stochastic():
    r=rank_acceptability([[1,2],[2,1],[.5,.5]],[1,1],[[0,3],[0,3]],draws=64)
    assert np.allclose(r['rank_probability'].sum(axis=0),1)
    assert np.allclose(r['rank_probability'].sum(axis=1),1)

def test_ahp_consistent():
    w=np.array([.2,.3,.5]);r=ahp_weights(w[:,None]/w[None,:])
    assert r['consistent'] and np.allclose(r['weights'],w)

def test_ahp_inconsistent_and_nonreciprocal():
    assert not ahp_weights([[1,9,1/9],[1/9,1,9],[9,1/9,1]])['consistent']
    with pytest.raises(ValueError):ahp_weights([[1,2],[2,1]])

def test_zero_edge_and_heuristic():
    edges=[(0,1,0),(1,2,1),(0,2,5)]
    r=shortest_path(3,edges,0,2,heuristic=[1,1,0])
    assert r['path']==[0,1,2] and r['distance']==1 and r['heuristic_accepted']
    r=shortest_path(3,edges,0,2,heuristic=[8,1,0])
    assert r['distance']==1 and not r['heuristic_accepted']

def test_negative_edges_and_cycle():
    assert shortest_path(3,[(0,1,-1),(1,2,2),(0,2,5)],0,2)['distance']==1
    assert shortest_path(3,[(0,1,0),(1,2,-2),(2,1,1)],0,2)['status']=='REACHABLE_NEGATIVE_CYCLE'

def test_disconnected_start_goal_and_duplicates():
    assert shortest_path(2,[],0,1)['status']=='UNREACHABLE'
    assert shortest_path(1,[],0,0)['distance']==0
    assert shortest_path(2,[(0,1,2),(0,1,1)],0,1)['distance']==1

@pytest.mark.parametrize('edge',[(0,2,1),(0,1,np.nan),(.5,1,1)])
def test_invalid_edges(edge):
    with pytest.raises(ValueError):shortest_path(2,[edge],0,1)

@pytest.mark.parametrize('method',['mc','sobol'])
def test_integration_counts_and_constant(method):
    r=integrate_unit(lambda X:np.ones(len(X))*3,2,method=method,points_per_rep=16,replicates=4,budget=64)
    assert r['evaluations']==64 and r['estimate']==3 and r['standard_error']==0

def test_control_pilot_independent_and_counted():
    r=integrate_unit(lambda X:X[:,0]+2*X[:,1],2,points_per_rep=32,replicates=4,
                    control=lambda X:X,control_mean=[.5,.5],pilot=32,budget=160)
    assert r['estimate']==pytest.approx(1.5) and r['evaluations']==160 and r['pilot_evaluations']==32

def test_qmc_standard_error_replicate_based():
    r=integrate_unit(lambda X:np.exp(X.sum(axis=1)),2,points_per_rep=16,replicates=8)
    assert r['standard_error']==pytest.approx(np.std(r['replicate_means'],ddof=1)/np.sqrt(8))

@pytest.mark.parametrize('kw',[{'points_per_rep':12},{'budget':3},{'control':lambda x:x,'pilot':0,'control_mean':[.5]},{'replicates':1}])
def test_invalid_integration(kw):
    with pytest.raises(ValueError):integrate_unit(lambda x:x[:,0],1,**kw)

@pytest.mark.parametrize('stiff',[False,True])
def test_checked_ode(stiff):
    times=np.linspace(0,1,20);rate=20 if stiff else 1
    r=checked_ivp(lambda t,y:-rate*y,[1],times,stiff=stiff)
    assert r['valid'] and np.max(abs(r['solution'][0]-np.exp(-rate*times)))<1e-5

def test_ode_budget():
    with pytest.raises(ValueError,match='budget'):checked_ivp(lambda t,y:-y,[1],[0,1],max_rhs=2)

def test_invariant_checker_and_projection():
    r=checked_ivp(lambda t,y:np.array([-y[0],y[0]]),[1,0],np.linspace(0,1,10),invariant_matrix=[[1,1]],invariant_value=[1],nonnegative=True)
    assert r['valid']
    r=checked_ivp(lambda t,y:-y,[1],np.linspace(0,1,10),invariant_matrix=[[1]],invariant_value=[1])
    assert not r['valid']
    assert np.sum(project_linear_invariant([.6,.3],[[1,1]],[1]))==pytest.approx(1)

@pytest.mark.parametrize('method,expected',[('holm',[.03,.06,.06]),('bh',[.03,.04,.04]),('by',[.055,.073333333,.073333333])])
def test_multiplicity(method,expected):
    assert np.allclose(adjust_pvalues([.01,.04,.03],method),expected)

def test_group_unit_not_window_count():
    r=paired_summary([3,3,5,5],[2,2,4,4],unit_ids=['a','a','b','b'],resamples=100)
    assert r['n_units']==2 and r['mean_gain']==1
    with pytest.raises(ValueError):paired_summary([3,3],[2,2],unit_ids=['a','a'],resamples=100)

def test_cluster_diagnostics():
    rng=np.random.default_rng(0);X=np.r_[rng.normal(0,.1,(10,2)),rng.normal(4,.1,(10,2))]
    r=cluster_diagnostics(X,n_clusters=2)
    assert r['silhouette']>.8 and r['seed_stability']==[1,1,1]

def test_catalog_coverage_and_no_fake_models():
    assert len(FAMILIES)==10
    assert all(r['status']=='EXTERNAL_NOT_RUN' and r['runtime_entry'] is None for r in external_manifest())
    assert enrich_method({'id':'regression'})['algorithm_upgrade']['entry'].endswith('fit_tabular')

@pytest.mark.parametrize('contract',[{'family':'linear-programming','integer':True},{'family':'mixed-integer','nonlinear':True},
    {'family':'graph-path','task':'tsp'},{'family':'topsis'},{'family':'time-series','multivariate':True},{'family':'nothing'}])
def test_structural_router_blocks_misuse(contract):
    with pytest.raises(ValueError):select_algorithms(contract)


def protocol_fixture():
    units=[str(i) for i in range(20)]
    protocol=dict(candidate='new',baselines=['strong'],independent_units=units,unit_families={u:'heldout' for u in units},
        development_families=['train'],metric='loss',direction='min',budget={'fe':100},evaluator_hash='f'*64,
        candidate_hash='a'*64,code_hashes={n:'a'*64 for n in ['new','strong','no_residual']},min_effect=.01,alpha=.05,required_ablations=['no_residual'],multiplicity_total=1,min_units=10,max_regression_fraction=.1)
    rows=[]
    for name,score in [('new',1.),('strong',2.),('no_residual',1.8)]:
        for u in units:
            ev={'valid':True,'score':score}
            rows.append(dict(method=name,unit=u,phase='confirmation',metric='loss',budget={'fe':100},
                evaluator_hash='f'*64,code_hash='a'*64,evaluation=ev,evaluation_hash=logical_hash(ev)))
    return protocol,rows

def test_promotion_requires_real_scope_and_significance():
    p,rows=protocol_fixture();r=promotion_decision(rows,p)
    assert r['decision']=='PROMOTE_WITHIN_SCOPE' and 'NOT_GLOBAL_SOTA' in r['scope']

def test_promotion_missing_baseline_no_false_pass():
    p,rows=protocol_fixture();assert promotion_decision(rows[:-1],p)['decision']=='HOLD'

def test_tamper_is_not_model_fallback():
    p,rows=protocol_fixture();rows[0]['evaluation']['score']=0
    with pytest.raises(ValueError,match='digest'):promotion_decision(rows,p)

def test_family_leakage_blocks():
    p,rows=protocol_fixture();p['development_families']=['heldout']
    assert promotion_decision(rows,p)['decision']=='HOLD'

def test_budget_and_code_mismatch():
    for field in ['budget','code_hash']:
        p,rows=protocol_fixture();rows[0][field]='tampered'
        with pytest.raises(ValueError):promotion_decision(rows,p)


def test_legacy_router_enriched_without_changing_order():
    from cumcm_harness.algorithms import route_methods,METHODS
    query='多目标 multiobjective'
    cards=route_methods(query,10)
    expected=sorted(METHODS,key=lambda m:(-sum(k.casefold() in query.casefold() for k in m['keywords']),m['id']))
    assert [c['id'] for c in cards]==[c['id'] for c in expected]
    assert all('algorithm_upgrade' in c and c['implementation']==FAMILIES[c['id']]['entry'] for c in cards)

def test_residual_not_default_and_gated_variant():
    import inspect
    assert inspect.signature(fit_tabular).parameters['include_residual'].default is False
    rng=np.random.default_rng(5);X=rng.normal(size=(60,3));y=X[:,0]**2
    m=fit_tabular(X,y,include_residual=True)
    if m.report['selected']=='crossfit_residual':assert m.report['residual_gate_passed'] is True


def test_promotion_baseline_source_also_frozen():
    p,rows=protocol_fixture();rows[20]['code_hash']='different'
    with pytest.raises(ValueError):promotion_decision(rows,p)

def test_promotion_cannot_omit_ablation_contract():
    p,rows=protocol_fixture();p['required_ablations']=[]
    with pytest.raises(ValueError):promotion_decision(rows,p)
