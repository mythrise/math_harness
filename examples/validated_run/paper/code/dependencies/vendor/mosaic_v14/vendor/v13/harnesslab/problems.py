"""Inherited RGV; variable-sized tours and a NEW synthetic due-date job model.
All dimensions, tasks and objective semantics are explicitly declared. The job
model is not a claim to solve another official competition problem.
"""
from __future__ import annotations
import numpy as np
from itertools import permutations
from numba import njit
from .bootstrap import old_make_problem

class OrderedSubsetCodec:
    def __init__(self,n):self.n=int(n);self.n_var=2*self.n
    def decode(self,x):
        x=np.asarray(x);active=x[:self.n]>=.5
        if not np.any(active):active[int(np.argmax(x[:self.n]))]=True
        p=np.argsort(x[self.n:],kind='stable');return p[active[p]].astype(np.int64)
    def encode(self,p):
        p=np.asarray(p,dtype=int)
        if len(p)==0 or len(np.unique(p))!=len(p) or p.min()<0 or p.max()>=self.n:raise ValueError('Invalid policy')
        x=np.zeros(2*self.n);x[p]=.75;x[self.n:]=.99
        for k,j in enumerate(p):x[self.n+j]=(k+.5)/self.n
        return x
    def mutate(self,parent,donor,expert,rng):
        p=list(map(int,self.decode(parent)));q=list(map(int,self.decode(donor)))
        absent=[j for j in range(self.n) if j not in p]
        if expert==0:
            if len(p)>1:
                a,b=rng.choice(len(p),2,replace=False);p[a],p[b]=p[b],p[a]
            elif absent:p.append(int(rng.choice(absent)))
        elif expert==1:
            if len(p)>1:
                a,b=map(int,rng.choice(len(p),2,replace=False));j=p.pop(a);p.insert(b,j)
            elif absent:p.insert(0,int(rng.choice(absent)))
        elif expert==2:
            if absent and (len(p)==1 or rng.random()<.5):p.insert(int(rng.integers(len(p)+1)),int(rng.choice(absent)))
            elif len(p)>1:p.pop(int(rng.integers(len(p))))
        elif expert==3:
            if len(q)>1:
                a,b=sorted(map(int,rng.choice(len(q)+1,2,replace=False)));piece=q[a:b]
            else:piece=q[:]
            p=[j for j in p if j not in piece];at=int(rng.integers(len(p)+1));p[at:at]=piece
        else:raise ValueError('Unknown operator')
        return self.encode(p)

@njit(cache=True)
def tour_batch(orders,sizes,dist,values,service,discount):
    n=len(values);out=np.zeros((len(orders),2))
    for i in range(len(orders)):
        t=0.;reward=0.;prev=n
        for k in range(sizes[i]):
            j=orders[i,k];t+=dist[prev,j]+service[j]
            reward+=values[j]*np.exp(-t/discount[j]);prev=j
        out[i,0]=-reward;out[i,1]=t+dist[prev,n]
    return out

@njit(cache=True)
def job_batch(orders,sizes,setup,values,process,dues,penalty):
    n=len(values);out=np.zeros((len(orders),2))
    for i in range(len(orders)):
        t=0.;reward=0.;prev=n
        for k in range(sizes[i]):
            j=orders[i,k];t+=setup[prev,j]+process[j]
            reward+=max(0.,values[j]-penalty[j]*max(t-dues[j],0.));prev=j
        out[i,0]=-reward;out[i,1]=t
    return out

class SequenceProblem:
    def __init__(self,spec):
        self.spec=spec;self.name=spec['id'];self.n=len(spec['values']);self.codec=OrderedSubsetCodec(self.n)
        self.n_var=2*self.n;self.n_obj=2;self.xl=np.zeros(self.n_var);self.xu=np.ones(self.n_var);self.calls=0
    def evaluate(self,X):
        X=np.atleast_2d(np.asarray(X,float));orders=np.zeros((len(X),self.n),np.int64);sizes=np.zeros(len(X),np.int64)
        for i,x in enumerate(X):
            p=self.codec.decode(x);orders[i,:len(p)]=p;sizes[i]=len(p)
        self.calls+=len(X);return self.evaluate_orders(orders,sizes)
    def evaluate_orders(self,o,s):
        d=self.spec
        if d['kind']=='tour':return tour_batch(o,s,np.array(d['dist']),np.array(d['values']),np.array(d['service']),np.array(d['discount']))
        return job_batch(o,s,np.array(d['setup']),np.array(d['values']),np.array(d['process']),np.array(d['dues']),np.array(d['penalty']))
    def pareto_front(self,*a,**kw):raise RuntimeError('Reference front forbidden during search')

def make_problem(spec):
    return old_make_problem(spec) if spec['kind']=='rgv' else SequenceProblem(spec)

def enumerate_reference(spec):
    p=make_problem(spec);n=p.n_var//2
    if n>8:raise ValueError('Exhaustive certificate deliberately limited to n<=8')
    orders=[];sizes=[]
    for k in range(1,n+1):
        for perm in permutations(range(n),k):orders.append(perm+(-1,)*(n-k));sizes.append(k)
    orders=np.asarray(orders,np.int64);sizes=np.asarray(sizes,np.int64)
    if spec['kind']=='rgv':
        from mosaic.rgv import batch_simulate
        F=batch_simulate(orders,sizes,p.travel,p.process,p.loads,p.wash,p.horizon)
    else:F=p.evaluate_orders(orders,sizes)
    ids=np.lexsort((F[:,1],F[:,0]));best=np.inf;keep=[]
    for j in ids:
        if F[j,1]<best:best=F[j,1];keep.append(j)
    return F[keep],orders[keep],sizes[keep],len(F)
