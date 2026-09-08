"""Preference-aware decision tools. Robustness is not an objective ground-truth rank."""
from __future__ import annotations
import numpy as np
from scipy.stats import rankdata
from .algopt import array


def fixed_topsis(X,weights,benefit,anchors):
    X,w,a=array(X,2,'X'),array(weights,1,'weights'),array(anchors,2,'anchors')
    benefit=np.asarray(benefit)
    if (len(X)<1 or a.shape!=(X.shape[1],2) or w.shape!=(X.shape[1],)
        or benefit.shape!=w.shape or not np.isin(benefit,[True,False]).all()):raise ValueError('TOPSIS shape/direction')
    if np.any(w<0) or w.sum()<=0 or np.any(a[:,1]<=a[:,0]):raise ValueError('Invalid weights/anchors')
    if np.any(X<a[:,0]) or np.any(X>a[:,1]):raise ValueError('Outside predeclared anchors; do not silently clip')
    w=w/w.sum();z=(X-a[:,0])/(a[:,1]-a[:,0]);z=np.where(benefit.astype(bool),z,1-z)
    v=z*w;dp=np.linalg.norm(v-w,axis=1);dn=np.linalg.norm(v,axis=1)
    return dn/(dp+dn)


def rank_acceptability(X,benefit,anchors,*,alpha=None,draws=2048,seed=0):
    X=array(X,2)
    if not isinstance(draws,int) or not 2<=draws<=100000:raise ValueError('Bounded number of draws required')
    alpha=np.ones(X.shape[1]) if alpha is None else array(alpha,1)
    if alpha.shape!=(X.shape[1],) or np.any(alpha<=0):raise ValueError('Positive Dirichlet parameters required')
    rng=np.random.default_rng(seed);weights=rng.dirichlet(alpha,size=draws)
    ranks=np.zeros((len(X),len(X)))
    # Ties share their occupied rank positions; never favor smaller input row IDs.
    for w in weights:
        scores=fixed_topsis(X,w,benefit,anchors)
        order=np.argsort(-scores,kind='stable');p=0
        while p<len(order):
            q=p+1
            while q<len(order) and scores[order[q]]==scores[order[p]]:q+=1
            ranks[np.ix_(order[p:q],np.arange(p,q))]+=1/(q-p)
            p=q
    ranks/=draws
    return dict(rank_probability=ranks,first_probability=ranks[:,0],
                expected_rank=ranks@np.arange(1,len(X)+1),draws=draws,
                weight_model='DIRICHLET_ASSUMPTION_NOT_DISCOVERED_PREFERENCE',alpha=alpha.tolist())


def ahp_weights(pairwise,*,consistency_limit=.1):
    """Saaty eigenvector weights, RI table n<=10. Inconsistent input is reported,
    not silently replaced by an LLM's preferred weights."""
    P=array(pairwise,2,'pairwise')
    if P.shape[0]!=P.shape[1] or not 1<=len(P)<=10 or np.any(P<=0):raise ValueError('AHP positive square matrix n<=10')
    if not np.allclose(P*P.T,1,atol=1e-8,rtol=0) or not np.allclose(np.diag(P),1):raise ValueError('AHP reciprocity/diagonal')
    if not np.isfinite(consistency_limit) or not 0<=consistency_limit<1:raise ValueError('Consistency limit')
    vals,vec=np.linalg.eig(P);idx=np.argmax(vals.real);lm=vals[idx].real;w=np.abs(vec[:,idx].real);w/=w.sum()
    ri=[0,0,0,.58,.90,1.12,1.24,1.32,1.41,1.45,1.49][len(P)]
    cr=0. if len(P)<=2 else max(0.,float((lm-len(P))/(len(P)-1)/ri))
    return dict(weights=w,consistency_ratio=cr,consistent=cr<=consistency_limit,
                note='CONSISTENCY_IS_NOT_VALIDITY_OF_HUMAN_PREFERENCES')
