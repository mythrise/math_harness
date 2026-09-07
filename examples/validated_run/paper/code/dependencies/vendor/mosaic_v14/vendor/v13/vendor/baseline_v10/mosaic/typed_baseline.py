"""NSGA-II-style comparator using EXACTLY the same structural operator library.
Independent variation controller; environmental selection reused from legacy.
This is a documented implementation, NOT the authors' official executable.
"""
import numpy as np
import moo_core as core

def run_typed_nsga2(problem,codec,seed,pop_size,max_evals):
    rng,X,F=core.initialize(problem,pop_size,seed)
    A=core.Archive(max_size=5*pop_size);A.update(X,F)
    fronts,ranks=core.fast_nondominated_sort(F);crowd=np.zeros(pop_size)
    for front in fronts:crowd[front]=core.crowding_distance(F[front])
    count=pop_size
    while count<max_evals:
        n=min(pop_size,max_evals-count);offs=[]
        for _ in range(n):
            a=core.tournament(ranks,crowd,rng);b=core.tournament(ranks,crowd,rng)
            offs.append(codec.mutate(X[a],X[b],int(rng.integers(4)),rng))
        Q=np.asarray(offs);G=problem.evaluate(Q);count+=n;A.update(Q,G)
        X,F,ranks,crowd=core.nsga2_environmental_selection(np.vstack([X,Q]),np.vstack([F,G]),pop_size)
    xx,ff=A.output(pop_size)
    return core.RunResult('typed_nsga2',problem.name,seed,xx,ff,count,[],{})


def run_typed_nsga2_unique(problem,codec,seed,pop_size,max_evals):
    """Stronger control: same 4 operators AND same phenotype novelty filter.

    No evaluator call is made while testing key novelty. Pending batch keys count
    as seen immediately to prevent duplicate queries within the same batch.
    """
    rng,X,F=core.initialize(problem,pop_size,seed)
    to_key=lambda x:tuple(map(int,codec.decode(x)))
    seen=set(to_key(x) for x in X)
    A=core.Archive(max_size=5*pop_size);A.update(X,F)
    fronts,ranks=core.fast_nondominated_sort(F);crowd=np.zeros(pop_size)
    for front in fronts:crowd[front]=core.crowding_distance(F[front])
    count=pop_size;duplicates=0
    while count<max_evals:
        n=min(pop_size,max_evals-count);offs=[]
        for _ in range(n):
            a=core.tournament(ranks,crowd,rng);b=core.tournament(ranks,crowd,rng)
            child=None
            for e in rng.permutation(4):
                for _ in range(12):
                    cand=codec.mutate(X[a],X[b],int(e),rng)
                    if to_key(cand) not in seen:
                        child=cand;break
                    duplicates+=1
                if child is not None:break
            if child is None:
                child=problem.xl+rng.random(problem.n_var)*(problem.xu-problem.xl)
            seen.add(to_key(child));offs.append(child)
        Q=np.asarray(offs);G=problem.evaluate(Q);count+=n;A.update(Q,G)
        X,F,ranks,crowd=core.nsga2_environmental_selection(np.vstack([X,Q]),np.vstack([F,G]),pop_size)
    xx,ff=A.output(pop_size)
    return core.RunResult('typed_nsga2_unique',problem.name,seed,xx,ff,count,[],
        {'duplicate_proposals_rejected':duplicates,'unique_evaluated':len(seen)})
