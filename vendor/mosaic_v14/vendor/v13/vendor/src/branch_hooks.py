"""Pure candidate-generation hooks; no objective evaluator or reference front.

Every new mechanism is independently disabled by default. The all-off branch
preserves the random draw order and outputs of frozen v10-R1.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from collections import deque
import numpy as np

@dataclass(frozen=True)
class BranchConfig:
    name: str = 'identity'
    queue: bool = False
    bridge: bool = False
    compound: bool = False
    memory_route: bool = False
    bridge_rate: float = 0.25
    target_size: bool = False
    random_target: bool = False
    parent_fresh: bool = False
    global_route: bool = False

CONFIGS = {
 'identity':BranchConfig(),
 'queue':BranchConfig('queue',queue=True),
 'bridge':BranchConfig('bridge',bridge=True),
 'compound':BranchConfig('compound',compound=True),
 'memory':BranchConfig('memory',memory_route=True),
 # Declared interaction candidates. Which one advances is chosen on development only.
 'queue_bridge':BranchConfig('queue_bridge',queue=True,bridge=True),
 'queue_memory':BranchConfig('queue_memory',queue=True,memory_route=True),
 'queue_compound':BranchConfig('queue_compound',queue=True,compound=True),
 'all':BranchConfig('all',queue=True,bridge=True,compound=True,memory_route=True),
 'target':BranchConfig('target',target_size=True),
 'target_random':BranchConfig('target_random',target_size=True,random_target=True),
 'target_memory':BranchConfig('target_memory',target_size=True,memory_route=True),
 'target_queue':BranchConfig('target_queue',target_size=True,queue=True),
 'fresh':BranchConfig('fresh',parent_fresh=True),
 'fresh_memory':BranchConfig('fresh_memory',parent_fresh=True,memory_route=True),
 'global_memory':BranchConfig('global_memory',memory_route=True,global_route=True),
}

def structural_neighbors(p: tuple[int,...], expert: int, n: int=8) -> list[tuple[int,...]]:
    """Enumerate proposals, NOT evaluations. Keep exactly the v10 move types 0-2.

    Returned order is sorted for process-independent reproducibility. Rotation
    and reversal are NOT identified: initial location/horizon break that symmetry.
    """
    k=len(p);out=set();absent=[j for j in range(n) if j not in p]
    if expert==0:
        if k>1:
            for a in range(k):
                for b in range(a+1,k):
                    v=list(p);v[a],v[b]=v[b],v[a];out.add(tuple(v))
        else:
            for j in absent:out.add(p+(j,))
    elif expert==1:
        if k>1:
            for a in range(k):
                for b in range(k):
                    if a!=b:
                        v=list(p);j=v.pop(a);v.insert(b,j);out.add(tuple(v))
        else:
            for j in absent:out.add((j,)+p)
    elif expert==2:
        for j in absent:
            for at in range(k+1):out.add(p[:at]+(j,)+p[at:])
        if k>1:
            for at in range(k):out.add(p[:at]+p[at+1:])
    else:raise ValueError('Only finite local operators 0,1,2 have a queue')
    out.discard(p)
    return sorted(out)

class BranchHooks:
    def __init__(self,codec,seed,config,X,F,budget):
        self.codec=codec;self.config=config;self.budget=budget
        self.rng=np.random.default_rng(np.random.SeedSequence([int(seed),881107]))
        self.queue={};self.queue_idx={};self.bridge={};self.memory=deque(maxlen=128)
        self.low=F.min(axis=0);self.scale=np.maximum(np.ptp(F,axis=0),1.)
        self.context=None;self.since_gain=0
        self.size_counts=np.bincount([len(codec.decode(x)) for x in X],minlength=9)
        self.stats_target_proposals=0
        self.stats={'queue_built':0,'queue_pops':0,'queue_skipped_seen':0,
                    'bridge_parents':0,'compound_steps':0,'memory_routes':0,
                    'pure_proposals':0,'bridge_updates':0}
        if config.bridge:
            for x,f in zip(X,F):self._bridge_add(x,f)

    def _bridge_add(self,x,f):
        # Conditional Pareto archive at each cardinality, <=2 extremes per cell.
        k=len(self.codec.decode(x));items=self.bridge.get(k,[])+[(x.copy(),f.copy())]
        F=np.array([v[1] for v in items]);keep=[]
        for i in range(len(F)):
            if not np.any(np.all(F<=F[i],axis=1)&np.any(F<F[i],axis=1)):keep.append(i)
        if len(keep)>2:
            # First objective minimum + second objective minimum; no oracle range.
            ids=np.array(keep);a=int(ids[np.argmin(F[ids,0])]);b=int(ids[np.argmin(F[ids,1])]);keep=list(dict.fromkeys([a,b]))
        self.bridge[k]=[items[i] for i in keep];self.stats['bridge_updates']+=1

    def parent(self,x,f,rng):
        if not self.config.bridge:return x,f
        if self.rng.random()>=self.config.bridge_rate:return x,f
        keys=sorted(self.bridge)
        if not keys:return x,f
        items=self.bridge[keys[int(self.rng.integers(len(keys)))]]
        self.stats['bridge_parents']+=1
        return items[int(self.rng.integers(len(items)))]

    def set_context(self,parent,pf,fe):
        self.context=np.r_[fe/self.budget,len(self.codec.decode(parent))/8.,
                           min(self.since_gain/64.,1.),
                           np.clip((pf-self.low)/self.scale,0.,1.)]

    def route(self,raw):
        if not self.config.memory_route or len(self.memory)<16:return raw
        # Empirical local conditional reward, NOT a counterfactual estimate.
        feats=np.array([v[0] for v in self.memory]);ops=np.array([v[1] for v in self.memory]);rr=np.array([v[2] for v in self.memory])
        dist=np.sum((feats-self.context)**2,axis=1)
        if self.config.global_route:dist=np.arange(len(self.memory),0,-1)*1e-14
        ids=np.argsort(dist,kind='stable')[:24];weights=np.exp(-dist[ids]/.25)
        if self.rng.random()<.20:return raw  # Explicit exploration floor.
        scores=[]
        for e in range(4):
            mask=ops[ids]==e;mass=weights[mask].sum()
            quality=(.5+np.dot(weights[mask],rr[ids][mask]))/(1+mass)
            bonus=.15/np.sqrt(1+mass)
            scores.append(quality+bonus+1e-9*raw[e])
        self.stats['memory_routes']+=1
        return np.array(scores)

    def propose(self,parent,donor,e,rng,seen,fe):
        self.stats['pure_proposals']+=1;candidate=None
        if self.config.target_size and (fe<64 or (self.since_gain>=16 and fe%8==0)):
            # Aim at the least-evaluated phenotype cardinality, not an oracle region.
            ks=np.flatnonzero(self.size_counts[1:]==self.size_counts[1:].min())+1
            target=int(self.rng.choice(ks));p=list(map(int,self.codec.decode(parent)))
            if self.config.random_target:
                p=list(map(int,self.rng.permutation(8)[:target]))
            else:
                while len(p)>target:p.pop(int(self.rng.integers(len(p))))
                while len(p)<target:
                    absent=[j for j in range(8) if j not in p]
                    p.insert(int(self.rng.integers(len(p)+1)),int(self.rng.choice(absent)))
                if tuple(p) in seen and len(p)>1:
                    a,b=self.rng.choice(len(p),2,replace=False);p[a],p[b]=p[b],p[a]
            self.stats_target_proposals+=1
            return self.codec.encode(p)

        if self.config.queue and e<3:
            p=tuple(map(int,self.codec.decode(parent)));key=(p,e)
            if key not in self.queue:
                neighbors=structural_neighbors(p,e)
                self.rng.shuffle(neighbors);self.queue[key]=neighbors;self.queue_idx[key]=0
                self.stats['queue_built']+=1
            q=self.queue[key];at=self.queue_idx[key]
            while at<len(q):
                child=q[at];at+=1;self.stats['queue_pops']+=1
                if child not in seen:
                    candidate=self.codec.encode(child);break
                self.stats['queue_skipped_seen']+=1
            self.queue_idx[key]=at
        if candidate is None:candidate=self.codec.mutate(parent,donor,e,rng)
        if self.config.compound:
            p=.40*(1-fe/self.budget)+.20*(self.since_gain>=32)
            extra=int(self.rng.binomial(2,p))
            for _ in range(extra):candidate=self.codec.mutate(candidate,donor,int(self.rng.integers(4)),rng)
            self.stats['compound_steps']+=extra
        return candidate

    def observe(self,x,f,expert,reward,new_objective):
        self.since_gain=0 if new_objective else self.since_gain+1
        self.size_counts[len(self.codec.decode(x))]+=1
        if self.config.bridge:self._bridge_add(x,f)
        if self.config.memory_route and expert<4:
            self.memory.append((self.context.copy(),int(expert),float(reward)))

    def diagnostics(self):
        return {'config':asdict(self.config),**self.stats,
                'bridge_size':sum(map(len,self.bridge.values())),
                'queue_slots':sum(map(len,self.queue.values())),
                'target_proposals':self.stats_target_proposals,
                'size_counts':self.size_counts.tolist()}
