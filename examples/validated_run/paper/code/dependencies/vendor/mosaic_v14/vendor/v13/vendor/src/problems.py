"""Known v10 RGV model + preregistered perturbations + synthetic transfer tasks."""
from __future__ import annotations
import numpy as np
from .bootstrap import core
from mosaic.rgv import RGVProblem, RGVCodec, all_policies, batch_simulate, nondominated_2d
from numba import njit

@njit(cache=True)
def tour_batch(orders,sizes,dist,values,service,discount):
    out=np.zeros((len(orders),2))
    for i in range(len(orders)):
        clock=0.;reward=0.;prev=8
        for q in range(sizes[i]):
            j=orders[i,q];clock+=dist[prev,j]+service[j]
            reward+=values[j]*np.exp(-clock/discount[j]);prev=j
        clock+=dist[prev,8]
        out[i,0]=-reward;out[i,1]=clock
    return out

class TourProblem:
    def __init__(self,spec):
        self.name=spec['id'];self.n_var=16;self.n_obj=2;self.xl=np.zeros(16);self.xu=np.ones(16)
        self.codec=RGVCodec();self.calls=0
        self.dist=np.array(spec['dist']);self.values=np.array(spec['values']);self.service=np.array(spec['service']);self.discount=np.array(spec['discount'])
    def evaluate(self,X):
        X=np.atleast_2d(X);orders=np.zeros((len(X),8),np.int64);sizes=np.zeros(len(X),np.int64)
        for i,x in enumerate(X):
            p=self.codec.decode(x);orders[i,:len(p)]=p;sizes[i]=len(p)
        self.calls+=len(X)
        return tour_batch(orders,sizes,self.dist,self.values,self.service,self.discount)
    def pareto_front(self,*a,**kw):raise RuntimeError('No oracle during search')

def make_problem(spec):
    if spec['kind']=='tour':return TourProblem(spec)
    p=RGVProblem(spec.get('group',1));p.name=spec['id']
    for name in ['process','wash','horizon']:
        if name in spec:setattr(p,name,float(spec[name]))
    for name in ['loads','travel']:
        if name in spec:setattr(p,name,np.array(spec[name],float))
    return p

def generate_specs():
    specs=[dict(id=f'rgv_g{g}',kind='rgv',group=g,partition='known_confirmation') for g in [1,2,3]]
    for i,seed in enumerate([5411,6781,7823,8317,9719]):
        rng=np.random.default_rng(seed);g=(i%3)+1;p=RGVProblem(g)
        specs.append(dict(id='rgv_dev' if i==0 else f'rgv_hold{i}',kind='rgv',group=g,
           partition='development' if i==0 else 'heldout_parameter',
           process=float(np.round(p.process*rng.uniform(.60,1.50))),
           wash=float(np.round(p.wash*rng.uniform(.6,1.7))),
           loads=np.round(p.loads*rng.uniform(.6,1.7,8)).tolist(),
           travel=(np.r_[0.,np.cumsum(rng.uniform(10.,40.,3))]).round().tolist(),
           horizon=float(rng.choice([7200,14400,21600,36000]))))
    for i,seed in enumerate([4133,5129,6163,7283,8297]):
        rng=np.random.default_rng(seed);xy=rng.uniform(0,100,(9,2));xy[8]=[50,50]
        d=np.sqrt(np.sum((xy[:,None]-xy[None,:])**2,axis=2))
        specs.append(dict(id='tour_dev' if i==0 else f'tour_hold{i}',kind='tour',
            partition='development' if i==0 else 'heldout_synthetic_transfer',
            dist=d.tolist(),values=rng.uniform(15,100,8).tolist(),service=rng.uniform(1,10,8).tolist(),
            discount=rng.uniform(80,350,8).tolist()))
    return specs

def enumerate_oracle(spec):
    p=make_problem(spec);o,n=all_policies()
    if spec['kind']=='tour':F=tour_batch(o,n,p.dist,p.values,p.service,p.discount)
    else:F=batch_simulate(o,n,p.travel,p.process,p.loads,p.wash,p.horizon)
    p.calls+=len(o) # Certification calls are counted separately from search FE.
    ids=nondominated_2d(F)
    return F[ids],o[ids],n[ids],len(o)
