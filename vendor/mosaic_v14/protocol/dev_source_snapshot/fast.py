"""Pure execution optimizations: policy-key/feature/front caches; same RNG calls.

No objective values cached. The objective evaluator remains untouched. Cached
encoding and feature arrays are immutable internally; public returns are copies.
"""
from __future__ import annotations
import numpy as np
from .bootstrap import core
from harnesslab.residual import ResidualHarness
from harnesslab.efficient import EfficientModel
from harnesslab.model import features as reference_features, nd_indices

class PolicyCodec:
    def __init__(self,base):
        self.base=base; self.n_var=base.n_var; self.n=getattr(base,'n',self.n_var//2)
        self._keys={};self._encoded={};self._features={};self.feature_hits=0;self.feature_misses=0
    def key(self,x):
        raw=np.asarray(x,dtype=float).tobytes()
        k=self._keys.get(raw)
        if k is None:
            k=tuple(map(int,self.base.decode(x)));self._keys[raw]=k
        return k
    def decode(self,x):return np.asarray(self.key(x),dtype=np.int64)
    def encode(self,order):
        k=tuple(map(int,order));old=self._encoded.get(k)
        if old is None:
            if not k or len(k)!=len(set(k)) or min(k)<0 or max(k)>=self.n:raise ValueError('Invalid policy')
            old=np.zeros(self.n_var);old[list(k)]=.75;old[self.n:]=.99
            for i,j in enumerate(k):old[self.n+j]=(i+.5)/self.n
            old.setflags(write=False);self._encoded[k]=old;self._keys[old.tobytes()]=k
        return old.copy()
    def mutate(self,parent,donor,expert,rng):
        # Matches every RNG call and policy update in inherited codecs.
        p=list(self.key(parent));q=list(self.key(donor));absent=[j for j in range(self.n) if j not in p]
        if expert==0:
            if len(p)>1:
                a,b=rng.choice(len(p),2,replace=False);p[a],p[b]=p[b],p[a]
            elif absent:p.append(int(rng.choice(absent)))
        elif expert==1:
            if len(p)>1:
                a,b=map(int,rng.choice(len(p),2,replace=False));j=p.pop(a);p.insert(b,j)
            elif absent:p.insert(0,int(rng.choice(absent)))
        elif expert==2:
            if absent and (len(p)==1 or rng.random()<.5):p.insert(int(rng.integers(len(p)+1)),int(rng.choice(absent)))
            elif len(p)>1:p.pop(int(rng.integers(len(p))))
        elif expert==3:
            if len(q)>1:
                a,b=sorted(map(int,rng.choice(len(q)+1,2,replace=False)));piece=q[a:b]
            else:piece=q[:]
            p=[j for j in p if j not in piece];at=int(rng.integers(len(p)+1));p[at:at]=piece
        else:raise ValueError('Unknown expert')
        return self.encode(p)
    def feature_matrix(self,X,raw=False):
        X=np.atleast_2d(X)
        if raw:return X.copy()
        p=3*self.n+(self.n+1)**2;out=np.empty((len(X),p))
        for i,x in enumerate(X):
            k=self.key(x);row=self._features.get(k)
            if row is None:
                row=reference_features(x,self)[0];row.setflags(write=False);self._features[k]=row;self.feature_misses+=1
            else:self.feature_hits+=1
            out[i]=row
        return out

class CachedHV:
    def __init__(self):self.signature=None;self.rebuilds=0;self.hits=0
    def __call__(self,points,front,ref):
        points=np.atleast_2d(points);front=np.asarray(front);ref=np.asarray(ref)
        signature=(front.shape,front.tobytes(),ref.tobytes())
        if signature!=self.signature:
            f=front[np.all(front<ref,axis=1)]
            if len(f):f=f[nd_indices(f)]
            self.left=np.r_[-np.inf,f[:,0] if len(f) else []]
            self.right=np.r_[f[:,0] if len(f) else [],ref[0]]
            self.height=np.r_[ref[1],f[:,1] if len(f) else []]
            self.signature=signature;self.rebuilds+=1
        else:self.hits+=1
        widths=np.maximum(self.right[None,:]-np.maximum(self.left[None,:],points[:,0,None]),0.)
        heights=np.maximum(self.height[None,:]-points[:,1,None],0.)
        return (widths*heights).sum(1)

from dataclasses import asdict
from collections import deque

class FastHarness(ResidualHarness):
    def __init__(self,codec,seed,budget,cfg):
        self.codec=codec;self.cfg=cfg;self.budget=budget;self.rng=np.random.default_rng(np.random.SeedSequence([seed,139831]))
        self.dataX=[];self.dataF=[];self.Z=[];self.forecasts=[];self.events=[];self.errors=deque(maxlen=16);self.calls=0;self.trials=0;self.override=0;self.pending=None
        self.model=EfficientModel(cfg,seed+13);self.fit_at=-1;self.key=codec.key;self.hvi=CachedHV()
    def initialize(self,X,F):
        self.dataX=list(X.copy());self.dataF=list(F.copy());self.low=F.min(0);self.scale=np.maximum(np.ptp(F,axis=0),1e-9);self.ref=(F.max(0)-self.low)/self.scale+.2
    def intervene(self,child,expert,parent,donor,seen,AF,fe):
        self.pending=None;c=self.cfg
        if not c.enabled or fe<c.warmup:return child,expert
        if c.model!='random':
            if self.fit_at<0 or fe-self.fit_at>=c.refit:
                self.model.fit(self.codec.feature_matrix(np.asarray(self.dataX),c.raw_features),(np.asarray(self.dataF)-self.low)/self.scale);self.fit_at=fe
            allowed=not c.guarded or (self.model.rank>=c.rank_threshold and self.model.mae<=c.error_threshold and (len(self.errors)<8 or np.mean(self.errors)<=.35))
            mu,std=self.model.predict(self.codec.feature_matrix(child,c.raw_features));self.calls+=1
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
            mu,std=self.model.predict(self.codec.feature_matrix(X,c.raw_features));self.calls+=len(X)
            if not np.isfinite(mu).all() or not np.isfinite(std).all():
                self.pending['reason']='nonfinite_prediction';return child,expert
            scoreY=mu-c.uncertainty*std
            if c.acquisition=='scalar':
                w=self.rng.dirichlet(np.ones(2));scores=-np.max(scoreY*w,axis=1)
            else:
                scores=self.hvi(scoreY,(AF-self.low)/self.scale,self.ref)
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
    def diagnostics(self):return dict(config=asdict(self.cfg),model_fits=self.model.model_fits,forecasts=self.forecasts,overrides=self.override,surrogate_predictions=self.calls,extra_pure_proposals=self.trials,events=self.events,feature_cache_hits=self.codec.feature_hits,feature_cache_misses=self.codec.feature_misses,hv_cache_hits=self.hvi.hits,hv_cache_rebuilds=self.hvi.rebuilds)
