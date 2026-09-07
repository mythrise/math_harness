"""Independent finite-front scoring, callable only after an optimizer finishes."""
import numpy as np
from scipy.spatial.distance import cdist

def nd2(F):
    F=np.unique(np.atleast_2d(F),axis=0)
    ids=np.lexsort((F[:,1],F[:,0]));last=np.inf;out=[]
    for i in ids:
        if F[i,1]<last:out.append(i);last=F[i,1]
    return F[out]

def hv2(F,ref=(1.1,1.1)):
    F=np.atleast_2d(F);r=np.asarray(ref)
    F=F[np.all(F<r,axis=1)]
    last=r[1];v=0.
    for f in F[np.argsort(F[:,0],kind='stable')]:
        if f[1]<last:v+=(r[0]-f[0])*(last-f[1]);last=f[1]
    return float(v)

def metrics(F,R,rounding=True):
    low=np.min(R,axis=0);scale=np.maximum(np.ptp(R,axis=0),1e-12)
    y=(np.atleast_2d(F)-low)/scale;ref=(np.atleast_2d(R)-low)/scale
    if rounding:y=np.round(y,10);ref=np.round(ref,10)
    y=nd2(y);ref=nd2(ref);hvr=hv2(ref);hvy=hv2(y)
    igd=np.sqrt(np.sum(np.maximum(y[None,:,:]-ref[:,None,:],0.)**2,axis=-1)).min(axis=1).mean()
    covered=(cdist(ref,y,metric='chebyshev').min(axis=1)<=1e-9)
    return dict(hv_gap=float(max(0.,hvr-hvy)/max(hvr,1e-15)),igd_plus=float(igd),
                recall=float(covered.mean()),numeric_front_hit=bool(covered.all()),front_size=len(y),reference_size=len(ref))

def score_trace(F,outF,R,budget):
    cs=[v for v in [32,64,128,256,512,1024,2048] if v<=budget]
    if cs[-1]!=budget:cs.append(budget)
    trace=[dict(fe=c,**metrics(F[:c],R)) for c in cs]
    auc=float(np.trapezoid([x['hv_gap'] for x in trace],np.log2(cs))/(np.log2(cs[-1])-np.log2(cs[0])))
    end=metrics(outF,R);raw=metrics(outF,R,rounding=False)
    return dict(auc=auc,final_gap=end['hv_gap'],igd=end['igd_plus'],recall=end['recall'],
                hit=end['numeric_front_hit'],front_size=end['front_size'],reference_size=end['reference_size'],
                observed_gap=trace[-1]['hv_gap'],raw_final_gap=raw['hv_gap'],raw_igd=raw['igd_plus'],trace=trace)
