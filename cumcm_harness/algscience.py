"""Numerical diagnostics, Monte Carlo error accounting, and statistical safeguards."""
from __future__ import annotations
import numpy as np
from scipy import stats
from scipy.integrate import solve_ivp
from scipy.stats import qmc
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from .algopt import array


def integrate_unit(fn,dim,*,points_per_rep=128,replicates=8,method='sobol',seed=0,
                   control=None,control_mean=None,pilot=0,budget=None):
    """Integrate on [0,1]^dim. fn must be vectorized: (N,d)->(N,).
    Errors are from independent replicate *means*, never treating Sobol points IID.
    Optional control variate coefficients are fitted on an independent IID pilot.
    Student-t interval is an approximation, not a universal finite-sample guarantee.
    """
    if (not isinstance(dim,int) or not 1<=dim<=1000 or not isinstance(points_per_rep,int)
        or points_per_rep<2 or not isinstance(replicates,int) or not 2<=replicates<=1000):
        raise ValueError('Integration dimensions/sample counts')
    if method not in ('mc','sobol'):raise ValueError('Unknown sampler')
    if method=='sobol' and points_per_rep&(points_per_rep-1):raise ValueError('Sobol requires power-of-two per replicate')
    if not isinstance(pilot,int) or pilot<0:raise ValueError('Invalid pilot size')
    total=points_per_rep*replicates+pilot
    if total>10_000_000 or (budget is not None and total>budget):raise ValueError('Evaluation budget exceeded')
    streams=np.random.SeedSequence(seed).spawn(replicates+1);coef=None;count=0;control_count=0
    def values(x):
        nonlocal count
        y=array(fn(x.copy()),1,'integrand');count+=len(x)
        if y.shape!=(len(x),):raise ValueError('Integrand shape')
        return y
    if control is not None:
        if pilot<8 or control_mean is None:raise ValueError('Independent pilot and known control mean required')
        u=np.random.default_rng(streams[0]).random((pilot,dim));y=values(u)
        h=array(control(u.copy()),2,'control');control_count+=len(u)
        mean=array(control_mean,1,'control mean')
        if h.shape[0]!=pilot or h.shape[1]!=len(mean):raise ValueError('Control shape mismatch')
        hc=h-h.mean(axis=0)
        coef=np.linalg.lstsq(hc,y-y.mean(),rcond=None)[0]
    elif pilot:raise ValueError('Pilot without a control function')
    means=[]
    for ss in streams[1:]:
        rng=np.random.default_rng(ss)
        x=rng.random((points_per_rep,dim)) if method=='mc' else qmc.Sobol(dim,scramble=True,rng=rng).random_base2(int(np.log2(points_per_rep)))
        y=values(x)
        if coef is not None:
            h=array(control(x.copy()),2,'control');control_count+=len(x)
            if h.shape!=(len(x),len(mean)):raise ValueError('Control shape mismatch')
            y=y-(h-mean)@coef
        means.append(float(y.mean()))
    est=float(np.mean(means));se=float(np.std(means,ddof=1)/np.sqrt(replicates));half=float(stats.t.ppf(.975,replicates-1)*se)
    return dict(estimate=est,standard_error=se,interval95=[est-half,est+half],replicate_means=means,
                evaluations=count,control_evaluations=control_count,pilot_evaluations=pilot,method=method,
                error_unit='INDEPENDENT_REPLICATE_MEAN',interval_scope='APPROXIMATE_STUDENT_T_NOT_RIGOROUS',
                warning='Zero sampled rare events does not prove zero risk or a reliable Gaussian interval')


def checked_ivp(rhs,y0,times,*,stiff=False,rtol=1e-5,atol=1e-8,max_rhs=100000,
                invariant_matrix=None,invariant_value=None,invariant_tolerance=1e-6,nonnegative=False):
    y0,times=array(y0,1,'y0'),array(times,1,'times')
    if len(y0)<1 or len(times)<2 or np.any(np.diff(times)<=0):raise ValueError('Initial state/times')
    if not 0<rtol<.1 or not 0<atol<.1 or not isinstance(max_rhs,int) or max_rhs<1:raise ValueError('ODE tolerances/budget')
    count=0
    def f(t,y):
        nonlocal count
        if count>=max_rhs:raise ValueError('RHS budget exhausted')
        count+=1;out=array(rhs(t,y.copy()),1,'rhs')
        if out.shape!=y0.shape:raise ValueError('RHS shape mismatch')
        return out
    method='Radau' if stiff else 'DOP853';solutions=[]
    for factor in (1.,.1):
        s=solve_ivp(f,(float(times[0]),float(times[-1])),y0,t_eval=times,method=method,
                    rtol=rtol*factor,atol=atol*factor)
        if not s.success or s.y.shape!=(len(y0),len(times)) or not np.isfinite(s.y).all():raise ValueError('ODE solver failed')
        solutions.append(s.y)
    relative=float(np.max(np.abs(solutions[0]-solutions[1])/(atol+rtol*np.maximum(np.abs(solutions[0]),np.abs(solutions[1])))))
    inv_error=None;checks={'tolerance_refinement':relative<=10.}
    if invariant_matrix is not None:
        A,b=array(invariant_matrix,2),array(invariant_value,1)
        if A.shape!=(len(b),len(y0)):raise ValueError('Invariant shape mismatch')
        if not np.isfinite(invariant_tolerance) or invariant_tolerance<=0:raise ValueError('Invariant tolerance')
        inv_error=float(np.max(np.abs(A@solutions[1]-b[:,None])))
        checks['linear_invariant']=inv_error<=invariant_tolerance
    if nonnegative:checks['nonnegative']=bool(np.min(solutions[1])>=-atol)
    return dict(solution=solutions[1],times=times,method=method,rhs_evaluations=count,
                refinement_scaled_difference=relative,invariant_error=inv_error,checks=checks,
                valid=all(checks.values()),scope='REFINEMENT_DIAGNOSTIC_NOT_A_RIGOROUS_ERROR_BOUND')


def project_linear_invariant(state,A,b):
    """Least-Euclidean-change projection; not a positivity or dynamics certificate."""
    x,A,b=array(state,1),array(A,2),array(b,1)
    if A.shape!=(len(b),len(x)):raise ValueError('Projection shapes')
    delta=np.linalg.lstsq(A,b-A@x,rcond=None)[0];out=x+delta
    if not np.allclose(A@out,b,rtol=0,atol=1e-9):raise ValueError('Inconsistent linear invariants')
    return out


def adjust_pvalues(pvalues,method='holm'):
    p=array(pvalues,1,'pvalues');n=len(p)
    if n==0 or np.any((p<0)|(p>1)):raise ValueError('P values must lie in [0,1]')
    idx=np.argsort(p,kind='stable');v=p[idx]
    if method=='holm':adj=np.maximum.accumulate(v*np.arange(n,0,-1))
    elif method in ('bh','by'):
        multiplier=sum(1/np.arange(1,n+1)) if method=='by' else 1.
        adj=np.minimum.accumulate((v*n*multiplier/np.arange(1,n+1))[::-1])[::-1]
    else:raise ValueError('Unknown multiple-testing method')
    out=np.empty(n);out[idx]=np.minimum(adj,1);return out


def paired_summary(baseline,candidate,*,direction='min',unit_ids=None,seed=0,resamples=2000,alpha=.05):
    b,c=array(baseline,1),array(candidate,1)
    if b.shape!=c.shape or len(b)<2 or direction not in ('min','max') or not 100<=resamples<=100000 or not 0<alpha<1:raise ValueError('Paired inference contract')
    delta=(b-c) if direction=='min' else (c-b)
    if unit_ids is not None:
        if len(unit_ids)!=len(b):raise ValueError('Unit ID shape')
        unique=sorted(set(unit_ids),key=str)
        delta=np.array([delta[np.asarray(unit_ids)==u].mean() for u in unique])
    if len(delta)<2:raise ValueError('Need two independent units, not two windows of one subject')
    rng=np.random.default_rng(seed)
    samples=np.array([rng.choice(delta,len(delta),replace=True).mean() for _ in range(resamples)])
    wins=int(np.sum(delta>0));losses=int(np.sum(delta<0));ties=int(np.sum(delta==0))
    p=1. if wins+losses==0 else float(stats.binomtest(wins,wins+losses,.5,alternative='greater').pvalue)
    return dict(mean_gain=float(delta.mean()),ci=np.quantile(samples,[alpha/2,1-alpha/2]).tolist(),
                n_units=len(delta),wins=wins,losses=losses,ties=ties,one_sided_sign_pvalue=p,
                scope='IID_UNIT_BOOTSTRAP_APPROXIMATION; SIGN_TEST_TESTS_WIN_PROBABILITY_NOT_MEAN_GAIN')


def cluster_diagnostics(X,*,method='kmeans',n_clusters=3,seed=0,repeats=4,eps=.5):
    """Descriptive clustering+seed stability, not proof of real semantic clusters."""
    X=array(X,2)
    if len(X)<8 or X.shape[1]==0 or not 2<=repeats<=20:raise ValueError('Clustering shape/repeats')
    if method not in ('kmeans','dbscan') or not 2<=n_clusters<len(X) or eps<=0:raise ValueError('Clustering parameters')
    Z=StandardScaler().fit_transform(X);labels=[]
    for i in range(repeats):
        model=KMeans(n_clusters=n_clusters,n_init=10,random_state=seed+i) if method=='kmeans' else DBSCAN(eps=eps)
        labels.append(model.fit_predict(Z))
    stability=[float(adjusted_rand_score(labels[0],v)) for v in labels[1:]]
    k=len(set(labels[0]));sil=float(silhouette_score(Z,labels[0])) if 1<k<len(X) else None
    return dict(labels=labels[0],silhouette=sil,seed_stability=stability,noise_count=int(np.sum(labels[0]==-1)),
                scope='DESCRIPTIVE_ONLY; STABILITY_IS_NOT_SEMANTIC_TRUTH')
