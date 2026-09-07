"""Explicit experimental policies. No prior-run labels or oracle access."""
from dataclasses import dataclass,asdict
import numpy as np
from .fast import FastHarness,PolicyCodec
from harnesslab.residual import ResidualConfig

@dataclass(frozen=True)
class SearchConfig(ResidualConfig):
    proposal_mode:str='legacy'    # legacy, bounded, local
    trial_cap:int=24
    local_cap:int=24

CONFIGS={
 'fast_h0':SearchConfig(model='linear',uncertainty=0.),
 'bounded24':SearchConfig(model='linear',uncertainty=0.,proposal_mode='bounded',trial_cap=24),
 'pool4':SearchConfig(model='linear',uncertainty=0.,pool=4),
 'local24':SearchConfig(model='linear',uncertainty=0.,proposal_mode='local',local_cap=24),
 'local48':SearchConfig(model='linear',uncertainty=0.,proposal_mode='local',local_cap=48),
 'local_all':SearchConfig(model='linear',uncertainty=0.,proposal_mode='local',local_cap=10000),
 'refit32':SearchConfig(model='linear',uncertainty=0.,refit=32),
 'local24_refit32':SearchConfig(model='linear',uncertainty=0.,proposal_mode='local',local_cap=24,refit=32),
 'local24_random':SearchConfig(model='random',guarded=False,uncertainty=0.,proposal_mode='local',local_cap=24),
 'local24_no_cache':SearchConfig(model='linear',uncertainty=0.,proposal_mode='local_no_cache',local_cap=24),
}

class SearchHarness(FastHarness):
    def __init__(self,codec,seed,budget,cfg):
        super().__init__(codec,seed,budget,cfg)
        self.neighborhood_cache={};self.neighbor_builds=0;self.neighbor_cache_hits=0
        self.neighbor_filter_checks=0;self.pool_counts=[]
    def neighbors(self,parent):
        k=self.codec.key(parent)
        if self.cfg.proposal_mode!='local_no_cache' and k in self.neighborhood_cache:
            self.neighbor_cache_hits+=1;return self.neighborhood_cache[k]
        p=list(k);n=self.codec.n;out={}
        def add(q,e):
            z=tuple(q)
            if z!=k:out.setdefault(z,e)
        for a in range(len(p)):
            for b in range(a+1,len(p)):
                q=p.copy();q[a],q[b]=q[b],q[a];add(q,0)
        for a in range(len(p)):
            for b in range(len(p)):
                if a==b:continue
                q=p.copy();x=q.pop(a);q.insert(b,x);add(q,1)
        for j in range(n):
            if j in k:continue
            for a in range(len(p)+1):
                q=p.copy();q.insert(a,j);add(q,2)
        if len(p)>1:
            for a in range(len(p)):
                q=p.copy();q.pop(a);add(q,2)
        # Some moves have several representations. Preserve deterministic first
        # producer; records report it as a local-pool generator, not causal credit.
        ans=list(out.items());self.neighbor_builds+=1
        if self.cfg.proposal_mode!='local_no_cache':self.neighborhood_cache[k]=ans
        return ans
    def make_candidates(self,child,expert,parent,donor,seen):
        c=self.cfg;candidates=[child.copy()];experts=[expert];local={self.key(child)}
        if c.proposal_mode.startswith('local'):
            nb=self.neighbors(parent);self.neighbor_filter_checks+=len(nb)
            available=[(k,e) for k,e in nb if k not in seen and k not in local]
            take=min(c.local_cap,len(available))
            # Same random sampling rule for cached and uncached ablation.
            ids=self.rng.choice(len(available),take,replace=False) if take else []
            for i in ids:
                k,e=available[int(i)];candidates.append(self.codec.encode(k));experts.append(e);local.add(k)
            # The incumbent x0 still includes the donor-segment operator. Do not
            # silently generate new donor-search operators in this experiment.
        elif c.proposal_mode=='bounded':
            for _ in range(c.trial_cap):
                if len(candidates)>=c.pool:break
                ee=int(self.rng.integers(4));cc=self.codec.mutate(parent,donor,ee,self.rng);self.trials+=1;k=self.key(cc)
                if k not in local and k not in seen:candidates.append(cc);experts.append(ee);local.add(k)
        else:
            for _ in range(c.pool-1):
                for tries in range(12):
                    ee=int(self.rng.integers(4));cc=self.codec.mutate(parent,donor,ee,self.rng);self.trials+=1;k=self.key(cc)
                    if k not in local and k not in seen:candidates.append(cc);experts.append(ee);local.add(k);break
        self.pool_counts.append(len(candidates));return np.asarray(candidates),experts
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
        X,experts=self.make_candidates(child,expert,parent,donor,seen)
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
    def diagnostics(self):
        d=super().diagnostics();d.update(neighbor_builds=self.neighbor_builds,neighbor_cache_hits=self.neighbor_cache_hits,neighbor_filter_checks=self.neighbor_filter_checks,pool_counts=self.pool_counts);return d
