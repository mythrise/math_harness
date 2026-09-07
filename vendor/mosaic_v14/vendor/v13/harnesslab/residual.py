"""Second development family: auditable residual preselection, not an LLM.
Preserves the incumbent's proposed point and its RNG when no intervention occurs.
Per-objective model choice is checked against already-paid chronological holdout.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from collections import deque
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.ensemble import ExtraTreesRegressor
from scipy.stats import spearmanr
from .model import features,hypervolume_improvement

@dataclass(frozen=True)
class ResidualConfig:
    model:str='hybrid'
    guarded:bool=True
    enabled:bool=True
    pool:int=8
    warmup:int=64
    refit:int=64
    exploration:float=.20
    uncertainty:float=.15
    rank_threshold:float=.35
    error_threshold:float=.25
    acquisition:str='hvi'
    raw_features:bool=False

RESIDUAL_CONFIGS={
 'residual':ResidualConfig(),
 'residual_no_gate':ResidualConfig(guarded=False),
 'residual_linear':ResidualConfig(model='linear'),
 'residual_trees':ResidualConfig(model='trees'),
 'residual_random':ResidualConfig(model='random',guarded=False),
 'residual_scalar':ResidualConfig(acquisition='scalar'),
 'residual_strict':ResidualConfig(rank_threshold=.60,error_threshold=.15),
 'residual_off':ResidualConfig(enabled=False),
}

class ObjectiveModel:
    def __init__(self,cfg,seed):self.cfg=cfg;self.seed=seed;self.version=0;self.model_fits=[]
    def newtree(self):return ExtraTreesRegressor(n_estimators=12,min_samples_leaf=2,max_depth=14,n_jobs=1,random_state=self.seed)
    def fit(self,Z,Y):
        n=len(Z);h=min(32,max(12,n//4));train,test=Z[:-h],Z[-h:];yt,yv=Y[:-h],Y[-h:]
        r=Ridge(alpha=.10).fit(train,yt);rp=r.predict(test)
        if self.cfg.model!='linear':
            tree=self.newtree().fit(train,yt);tp=tree.predict(test)
        else:tp=rp
        re=np.mean(np.abs(rp-yv),axis=0);te=np.mean(np.abs(tp-yv),axis=0)
        choices=re<=te
        if self.cfg.model=='linear':choices[:]=True
        if self.cfg.model=='trees':choices[:]=False
        pred=np.where(choices,rp,tp);ranks=[]
        for j in range(Y.shape[1]):
            if np.std(yv[:,j])<1e-12 or np.std(pred[:,j])<1e-12:ranks.append(0.)
            else:ranks.append(float(spearmanr(yv[:,j],pred[:,j]).statistic))
        self.rank=float(min(ranks));self.mae=float(np.mean(np.abs(pred-yv)));self.error=np.sqrt(np.mean((pred-yv)**2,axis=0))
        self.choices=choices;self.ridge=Ridge(alpha=.1).fit(Z,Y)
        self.tree=self.newtree().fit(Z,Y) if not choices.all() else None
        self.version+=1;self.fitted_fe=n
        rec=dict(version=self.version,fe=n,rank=self.rank,mae=self.mae,per_objective=['linear'if c else 'trees' for c in choices],linear_holdout_mae=re.tolist(),trees_holdout_mae=te.tolist())
        self.model_fits.append(rec)
    def predict(self,Z):
        r=self.ridge.predict(Z)
        if self.tree is None:return r,np.tile(self.error,(len(Z),1))
        ps=np.asarray([t.predict(Z) for t in self.tree.estimators_]);mu=np.where(self.choices,r,ps.mean(0));sigma=np.where(self.choices,self.error,ps.std(0))
        return mu,sigma

class ResidualHarness:
    def __init__(self,codec,seed,budget,cfg):
        self.codec=codec;self.cfg=cfg;self.budget=budget;self.rng=np.random.default_rng(np.random.SeedSequence([seed,139831]))
        self.dataX=[];self.dataF=[];self.Z=[];self.forecasts=[];self.events=[];self.errors=deque(maxlen=16);self.calls=0;self.trials=0;self.override=0;self.pending=None
        self.model=ObjectiveModel(cfg,seed+13);self.fit_at=-1;self.key=lambda x:tuple(map(int,codec.decode(x)))
    def initialize(self,X,F):
        self.dataX=list(X.copy());self.dataF=list(F.copy());self.low=F.min(0);self.scale=np.maximum(np.ptp(F,axis=0),1e-9);self.ref=(F.max(0)-self.low)/self.scale+.2
    def intervene(self,child,expert,parent,donor,seen,AF,fe):
        self.pending=None;c=self.cfg
        if not c.enabled or fe<c.warmup:return child,expert
        if c.model!='random':
            if self.fit_at<0 or fe-self.fit_at>=c.refit:
                self.model.fit(features(np.asarray(self.dataX),self.codec,c.raw_features),(np.asarray(self.dataF)-self.low)/self.scale);self.fit_at=fe
            allowed=not c.guarded or (self.model.rank>=c.rank_threshold and self.model.mae<=c.error_threshold and (len(self.errors)<8 or np.mean(self.errors)<=.35))
            mu,std=self.model.predict(features(child,self.codec,c.raw_features));self.calls+=1
            # Predictions are never promoted into verified observations.
            if not np.isfinite(mu).all() or not np.isfinite(std).all():
                self.events.append(dict(fe=fe+1,version=self.model.version,reason='nonfinite_prediction_fallback'))
                return child,expert
            self.pending=dict(fe=fe+1,version=self.model.version,train_fe=self.fit_at,prediction=mu[0].tolist(),std=std[0].tolist(),override=False,reason='base')
        else:allowed=True
        if not allowed:
            if self.pending:self.pending['reason']='audit_fallback'
            return child,expert
        if self.rng.random()<c.exploration:
            if self.pending:self.pending['reason']='baseline_exploration'
            return child,expert
        candidates=[child.copy()];experts=[expert];local={self.key(child)}
        # No objective function is available to this object. The default baseline
        # proposal is always in the pool; the four operator definitions do not change.
        for _ in range(c.pool-1):
            for tries in range(12):
                ee=int(self.rng.integers(4));cc=self.codec.mutate(parent,donor,ee,self.rng);self.trials+=1;k=self.key(cc)
                if k not in local and k not in seen:candidates.append(cc);experts.append(ee);local.add(k);break
        X=np.asarray(candidates)
        if c.model=='random':pick=int(self.rng.integers(len(X)))
        else:
            mu,std=self.model.predict(features(X,self.codec,c.raw_features));self.calls+=len(X)
            if not np.isfinite(mu).all() or not np.isfinite(std).all():
                self.pending['reason']='nonfinite_prediction';return child,expert
            scoreY=mu-c.uncertainty*std
            if c.acquisition=='scalar':
                w=self.rng.dirichlet(np.ones(2));scores=-np.max(scoreY*w,axis=1)
            else:
                scores=hypervolume_improvement(scoreY,(AF-self.low)/self.scale,self.ref)
                if scores.max()<=1e-14:
                    # No predicted improvement: preserve the baseline proposal.
                    pick=0
                else:pick=int(np.argmax(scores))
            if c.acquisition=='scalar':pick=int(np.argmax(scores))
            self.pending=dict(fe=fe+1,version=self.model.version,train_fe=self.fit_at,prediction=mu[pick].tolist(),std=std[pick].tolist(),override=bool(pick),reason='residual' if pick else 'base_wins',candidate_count=len(X),baseline_prediction=mu[0].tolist())
        self.override+=bool(pick)
        return X[pick].copy(),int(experts[pick])
    def observe(self,child,cf,fe):
        self.dataX.append(child.copy());self.dataF.append(cf.copy())
        if self.pending is not None:
            pred=np.asarray(self.pending['prediction']);err=float(np.mean(np.abs(pred-(cf-self.low)/self.scale)))
            if np.isfinite(err):self.errors.append(err)
            self.pending['actual']=cf.tolist();self.pending['error']=err;self.forecasts.append(self.pending);self.pending=None
    def diagnostics(self):return dict(config=asdict(self.cfg),model_fits=self.model.model_fits,forecasts=self.forecasts,overrides=self.override,surrogate_predictions=self.calls,extra_pure_proposals=self.trials,events=self.events)
