"""Pure prediction: cannot evaluate objective or write verified archives."""
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor
from scipy.stats import spearmanr

def features(X,codec,raw=False):
    X=np.atleast_2d(X)
    if raw:return X.copy()
    n=X.shape[1]//2;p=2*n+(n+1)**2+n
    out=np.zeros((len(X),p))
    for i,x in enumerate(X):
        order=codec.decode(x);out[i,order]=1
        out[i,n+order]=(np.arange(len(order))+1)/n
        nodes=np.r_[n,order,n];a=nodes[:-1];b=nodes[1:]
        out[i,2*n+a*(n+1)+b]=1
        out[i,2*n+(n+1)**2+len(order)-1]=1
    return out

class PredictionModel:
    def __init__(self,seed):self.seed=seed;self.version=0;self.validation_score=0.;self.validation_error=float('inf')
    def _new(self):return ExtraTreesRegressor(n_estimators=16,max_depth=14,min_samples_leaf=2,max_features=1.,n_jobs=1,random_state=self.seed)
    def fit(self,Z,Y):
        # Time-ordered validation: the most recent evaluated points were not in
        # the fit used to score validity. All these labels have already cost FE.
        hold=min(32,max(12,len(Z)//4));m=self._new();m.fit(Z[:-hold],Y[:-hold]);pred=m.predict(Z[-hold:])
        cor=[]
        for j in range(Y.shape[1]):
            if np.std(Y[-hold:,j])<1e-12 or np.std(pred[:,j])<1e-12:cor.append(0.)
            else:cor.append(float(spearmanr(Y[-hold:,j],pred[:,j]).statistic))
        self.validation_score=float(min(cor));self.validation_error=float(np.mean(np.abs(pred-Y[-hold:])))
        self.model=self._new();self.model.fit(Z,Y);self.version+=1;self.fitted_until=len(Z)
        return dict(version=self.version,fe=len(Z),validation_rank=self.validation_score,validation_mae=self.validation_error)
    def predict(self,Z):
        ps=np.asarray([m.predict(Z) for m in self.model.estimators_])
        return ps.mean(0),ps.std(0)

def nd_indices(F):
    F=np.asarray(F);ids=np.lexsort((F[:,1],F[:,0]));best=np.inf;keep=[]
    for i in ids:
        if F[i,1]<best:keep.append(i);best=F[i,1]
    return np.asarray(keep,int)

def hypervolume_improvement(points,front,ref):
    """Exact 2D HVI for predicted points, independently versus the observed front."""
    points=np.atleast_2d(points);front=np.asarray(front);ref=np.asarray(ref)
    front=front[np.all(front<ref,axis=1)]
    if len(front):front=front[nd_indices(front)]
    left=np.r_[-np.inf,front[:,0] if len(front) else []]
    right=np.r_[front[:,0] if len(front) else [],ref[0]]
    height=np.r_[ref[1],front[:,1] if len(front) else []]
    widths=np.maximum(right[None,:]-np.maximum(left[None,:],points[:,0,None]),0.)
    heights=np.maximum(height[None,:]-points[:,1,None],0.)
    return (widths*heights).sum(1)
