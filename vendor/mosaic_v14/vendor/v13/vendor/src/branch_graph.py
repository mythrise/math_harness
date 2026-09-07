"""Behavior-diverse archive search with sparse, real-evaluation-only expert credit.

Preserves distinct decision policies even at exactly equal objective vectors.
The idea is a structured search extension, not a claim to reproduce a neural MoE.
"""
from __future__ import annotations
from collections import defaultdict,deque
import numpy as np
from scipy.special import softmax
from .bootstrap import core
from .branch_hooks import BranchConfig, BranchHooks

def key(codec,x): return tuple(map(int,codec.decode(x)))

def run_branch(problem,codec,seed,pop_size,max_evals,config=BranchConfig(),mode='no_memory',ties_per_objective=1):
    rng,X,F=core.initialize(problem,pop_size,seed)
    hooks=BranchHooks(codec,seed,config,X,F,max_evals)
    # Index by exact phenotype, NOT by floating-point random-key genotype.
    seen=set(key(codec,x) for x in X)
    visits=defaultdict(int)
    a=np.ones((3,4));b=np.ones((3,4));counts=np.zeros(4,int);rewards=np.zeros(4)
    bias=np.zeros(4);history=deque(maxlen=48);score_history=deque(maxlen=48)
    X=[x.copy() for x in X];F=[f.copy() for f in F]
    evals=pop_size;log=[];rejected_duplicates=0

    def trim_pool(X,F):
        arr=np.asarray(F);unique,inv=np.unique(arr,axis=0,return_inverse=True)
        valid=core.nondominated_mask(unique)
        kept=[]
        for u in np.flatnonzero(valid):
            ids=np.flatnonzero(inv==u)
            # Retain underexplored phenotypes; zero visits to newly admitted point.
            if mode=='no_memory':limit=1
            else:limit=ties_per_objective
            ids=sorted(ids,key=lambda i:(visits[key(codec,X[i])],rng.random()))
            distinct=[];local_seen=set()
            for i in ids:
                k=key(codec,X[i])
                if k not in local_seen:
                    distinct.append(i);local_seen.add(k)
                if len(distinct)>=limit:break
            kept.extend(distinct)
        if len(kept)>4*pop_size:
            loc=core.select_indices_farthest(arr[kept],4*pop_size)
            kept=[kept[i] for i in loc]
        return [X[i] for i in kept],[F[i] for i in kept]

    X,F=trim_pool(X,F)
    while evals<max_evals:
        arr=np.asarray(F);unique,inv=np.unique(arr,axis=0,return_inverse=True)
        # Regions (objective vectors) have equal parent probability, irrespective
        # of how many behavior variants happen to have accumulated there.
        group=int(rng.integers(len(unique)))
        if config.parent_fresh:
            # Inverse visitation of each live archive phenotype, with a uniform floor.
            freq=np.array([visits[key(codec,x)] for x in X],float)
            weights=1/(1+freq);weights=.15/len(X)+.85*weights/weights.sum()
            group=int(hooks.rng.choice(len(X),p=weights))
        ids=np.flatnonzero(inv==group)
        nvis=np.array([visits[key(codec,X[i])] for i in ids],float)
        parent_id=int(rng.choice(ids,p=(1/(1+nvis))/(1/(1+nvis)).sum()))
        donor_id=int(rng.integers(len(X)));parent=X[parent_id];pf=F[parent_id];donor=X[donor_id]
        parent,pf=hooks.parent(parent,pf,rng)
        hooks.set_context(parent,pf,evals)
        state=min(2,int(3*evals/max_evals))
        sample=rng.beta(a[state],b[state])
        if mode in ('uniform','no_memory','no_novelty'):sample=rng.random(4)
        if mode=='single_expert':sample=np.array([1.,0.,0.,0.])
        if mode=='quantile' and len(score_history)>=16 and evals%16==0:
            S=np.asarray(score_history)
            quality=(a.sum(0)/(a+b).sum(0))
            q=.20/4+.80*softmax((quality-quality.max())/.20)
            candidates=[]
            for e in range(4):
                margin=np.max(np.delete(S+bias,e,axis=1),axis=1)-S[:,e]
                candidates.append(np.quantile(margin,1-q[e]))
            correction=np.asarray(candidates);correction-=correction.mean()
            bias=np.clip(.75*bias+.25*correction,-.08,.08)
        score_history.append(sample.copy())
        if mode=='quantile':sample+=bias
        sample=hooks.route(sample)
        ranked=np.argsort(-sample,kind='stable')
        child=None;chosen=None
        # Pure generation can be retried without a function call. The same rule
        # is provided to the duplicate-aware NSGA-II control below.
        for e in ranked:
            attempts=1 if mode=='no_novelty' else 12
            for _ in range(attempts):
                cand=hooks.propose(parent,donor,int(e),rng,seen,evals)
                if mode=='no_novelty' or key(codec,cand) not in seen:
                    child=cand;chosen=int(e);break
                rejected_duplicates+=1
            if child is not None:break
        if child is None:
            child=problem.xl+rng.random(problem.n_var)*(problem.xu-problem.xl);chosen=4
        cf=problem.evaluate(child)[0];evals+=1
        visits[key(codec,parent)]+=1;seen.add(key(codec,child))
        nd=not np.any(np.all(arr<=cf,axis=1)&np.any(arr<cf,axis=1))
        dominates=bool(np.all(cf<=pf) and np.any(cf<pf))
        novelty=not np.any(np.all(arr==cf,axis=1))
        reward=float(.50*dominates+.35*(nd and novelty)+.15*nd)
        if chosen<4:
            # Only the actually evaluated expert receives evidence.
            a[state,chosen]=1+.995*(a[state,chosen]-1)+reward
            b[state,chosen]=1+.995*(b[state,chosen]-1)+1-reward
            counts[chosen]+=1;rewards[chosen]+=reward
        hooks.observe(child,cf,chosen,reward,nd and novelty)
        if nd:
            X.append(child.copy());F.append(cf.copy());X,F=trim_pool(X,F)
        log.append({'fe':evals,'expert':chosen,'reward':reward,'pool_size':len(X)})
    AX=np.asarray(X);AF=np.asarray(F)
    _,idx=np.unique(AF,axis=0,return_index=True);AX=AX[idx];AF=AF[idx]
    if len(AF)>pop_size:
        idx=core.select_indices_farthest(AF,pop_size);AX,AF=AX[idx],AF[idx]
    return core.RunResult('graph_'+mode,problem.name,seed,AX,AF,evals,[],
         {'counts':counts.tolist(),'reward_sum':rewards.tolist(),'route_log':log,
          'duplicate_proposals_rejected':rejected_duplicates,'unique_evaluated':len(seen),
          'behavior_memory':mode!='no_memory','novelty_filter':mode!='no_novelty',
          'branch':config.name,'hooks':hooks.diagnostics()})
