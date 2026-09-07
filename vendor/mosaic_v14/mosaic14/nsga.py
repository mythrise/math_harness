"""Matched control: SAME frozen typed NSGA-II, with residual preselection hook.
Generational selection and 32-point evaluation batches stay unchanged. Predictions
are made from the already completed generations; pending predictions are logged
before the batch's true evaluation.
"""
import numpy as np
from .bootstrap import core
from .fast import PolicyCodec
from .variants import SearchHarness

def run_nsga_local(problem,codec,seed,pop_size,max_evals,config):
    codec=PolicyCodec(codec)
    rng,X,F=core.initialize(problem,pop_size,seed)
    h=SearchHarness(codec,seed,max_evals,config);h.initialize(X,F)
    to_key=codec.key;seen=set(to_key(x)for x in X)
    A=core.Archive(max_size=5*pop_size);A.update(X,F)
    fronts,ranks=core.fast_nondominated_sort(F);crowd=np.zeros(pop_size)
    for front in fronts:crowd[front]=core.crowding_distance(F[front])
    count=pop_size;duplicates=0
    while count<max_evals:
        n=min(pop_size,max_evals-count);offs=[];predictions=[]
        _,AF=A.output(5*pop_size)
        for offset in range(n):
            a=core.tournament(ranks,crowd,rng);b=core.tournament(ranks,crowd,rng);child=None;chosen=4
            for e in rng.permutation(4):
                for _ in range(12):
                    cand=codec.mutate(X[a],X[b],int(e),rng)
                    if to_key(cand)not in seen:child=cand;chosen=int(e);break
                    duplicates+=1
                if child is not None:break
            if child is None:child=problem.xl+rng.random(problem.n_var)*(problem.xu-problem.xl)
            child,chosen=h.intervene(child,chosen,X[a],X[b],seen,AF,count)
            if h.pending is not None:h.pending['fe']=count+offset+1
            predictions.append(h.pending);h.pending=None
            seen.add(to_key(child));offs.append(child)
        Q=np.asarray(offs);G=problem.evaluate(Q)
        for i,(x,f)in enumerate(zip(Q,G)):
            h.pending=predictions[i];h.observe(x,f,count+i+1)
        count+=n;A.update(Q,G)
        X,F,ranks,crowd=core.nsga2_environmental_selection(np.vstack([X,Q]),np.vstack([F,G]),pop_size)
    xx,ff=A.output(pop_size)
    return core.RunResult('nsga_residual',problem.name,seed,xx,ff,count,[],{'duplicate_proposals_rejected':duplicates,'unique_evaluated':len(seen),'harness':h.diagnostics()})
