import numpy as np
from scipy.spatial.distance import cdist

def nondominated(F):
    F=np.unique(np.asarray(F,float),axis=0)
    good=np.ones(len(F),bool)
    for i in range(len(F)):
        if good[i]:good[np.all(F>=F[i],axis=1)&np.any(F>F[i],axis=1)]=False
    return F[good]

def hv2(F,reference=np.array([1.1,1.1])):
    F=np.asarray(F,float);F=F[np.all(F<reference,axis=1)]
    if not len(F):return 0.
    ids=np.argsort(F[:,0],kind='stable');last=reference[1];v=0.
    for i in ids:
        if F[i,1]<last:
            v+=(reference[0]-F[i,0])*(last-F[i,1]);last=F[i,1]
    return float(v)

def score(F,R):
    F=nondominated(F);R=nondominated(R)
    lo=R.min(0);span=np.maximum(R.max(0)-lo,1e-12)
    fn=(F-lo)/span;rn=(R-lo)/span
    distances=np.sqrt(np.sum(np.maximum(fn[None,:,:]-rn[:,None,:],0)**2,axis=-1))
    hv=hv2(fn) if R.shape[1]==2 else float('nan');ohv=hv2(rn) if R.shape[1]==2 else float('nan')
    exact=float(np.mean(np.min(cdist(R,F,metric='chebyshev'),axis=1)<1e-9))
    return {'igd_plus':float(distances.min(1).mean()),'hv':hv,'oracle_hv':ohv,
            'hv_gap':max(0.,ohv-hv),'exact_front_fraction':exact,'exact_front_hit':bool(exact==1),
            'front_size':len(F)}
