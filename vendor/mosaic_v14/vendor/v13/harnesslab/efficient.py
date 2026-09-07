"""Memoize deterministic codec operations, never objective evaluations.
Operator code and all RNG calls are delegated unchanged. Cached outputs are copies.
"""
import numpy as np
from .residual import ResidualHarness,ResidualConfig,ObjectiveModel

FAST_CONFIGS={
 'guarded_linear':ResidualConfig(model='linear'),
 'unguarded_linear':ResidualConfig(model='linear',guarded=False),
 'random_residual':ResidualConfig(model='random',guarded=False),
 'scalar_linear':ResidualConfig(model='linear',acquisition='scalar'),
 'raw_linear':ResidualConfig(model='linear',raw_features=True),
 'no_uncertainty_linear':ResidualConfig(model='linear',uncertainty=0.),
 'guarded_hybrid':ResidualConfig(),
 'off_fast':ResidualConfig(enabled=False),
}

class CachedCodec:
    def __init__(self,base):
        self.base=base;self.n_var=base.n_var;self.n=getattr(base,'n',self.n_var//2)
        self._dec={};self._enc={}
    def decode(self,x):
        k=np.asarray(x,dtype=float).tobytes()
        if k not in self._dec:self._dec[k]=self.base.decode(x)
        return self._dec[k].copy()
    def encode(self,p):
        k=tuple(map(int,p))
        if k not in self._enc:self._enc[k]=self.base.encode(p)
        return self._enc[k].copy()
    def mutate(self,parent,donor,expert,rng):
        return type(self.base).mutate(self,parent,donor,expert,rng)

class EfficientModel(ObjectiveModel):
    def predict(self,Z):
        r=Z@self.ridge.coef_.T+self.ridge.intercept_
        if self.tree is None:return r,np.tile(self.error,(len(Z),1))
        ps=np.asarray([t.predict(Z) for t in self.tree.estimators_])
        return np.where(self.choices,r,ps.mean(0)),np.where(self.choices,self.error,ps.std(0))

class EfficientHarness(ResidualHarness):
    def __init__(self,codec,seed,budget,cfg):
        super().__init__(CachedCodec(codec),seed,budget,cfg)
        self.model=EfficientModel(cfg,seed+13)
    def diagnostics(self):
        d=super().diagnostics();d['codec_cached']=True;d['codec_cache_sizes']=[len(self.codec._enc),len(self.codec._dec)];return d
