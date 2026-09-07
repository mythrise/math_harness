"""2018 CUMCM B, deterministic one-process cyclic-policy benchmark.

The input parameters are transcribed from the published problem. The policy
restriction, event ordering and added movement objective are documented in data.
Only the small finite policy class is exhaustively certifiable, NOT the whole
original dynamic scheduling problem.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from itertools import permutations
import json
import numpy as np
try:
    from numba import njit
except ImportError:
    def njit(*args, **kwargs):
        return lambda f: f

DATA = json.loads((Path(__file__).resolve().parents[1]/'data/rgv2018_parameters.json').read_text())

@njit(cache=True)
def simulate_fast(order, travel, process, loads, wash, horizon):
    ready = np.zeros(8, dtype=np.float64)
    loaded = np.zeros(8, dtype=np.bool_)
    t=0.; position=0; completed=0; movement=0.; p=0
    # Every operation advances time by >=27; bounded even for singleton cycles.
    while True:
        j = order[p % len(order)]
        pos=j//2
        move=travel[abs(pos-position)]
        arrival=t+move
        start=max(arrival,ready[j]) if loaded[j] else arrival
        service_end=start+loads[j]
        end=service_end+(wash if loaded[j] else 0.)
        if end>horizon+1e-10:
            break
        completed+=int(loaded[j]); movement+=move
        ready[j]=service_end+process; loaded[j]=True
        position=pos; t=end; p+=1
    return completed,movement

@njit(cache=True)
def batch_simulate(orders, sizes, travel, process, loads, wash, horizon):
    F=np.empty((len(orders),2))
    for k in range(len(orders)):
        n,m=simulate_fast(orders[k,:sizes[k]],travel,process,loads,wash,horizon)
        F[k,0]=-n; F[k,1]=m
    return F

class RGVCodec:
    """Real random keys -> nonempty ordered subset; surjective over our class."""
    n_var=16
    def decode(self, x):
        x=np.asarray(x)
        active=x[:8]>=.5
        if not np.any(active):
            active[int(np.argmax(x[:8]))]=True
        ordered=np.argsort(x[8:],kind='stable')
        return ordered[active[ordered]].astype(np.int64)
    def encode(self, order):
        order=np.asarray(order,dtype=np.int64)
        if len(order)==0 or len(np.unique(order))!=len(order) or np.any(order<0) or np.any(order>=8):
            raise ValueError('Not a nonempty ordered CNC subset')
        x=np.zeros(16); x[order]=.75; x[8:]=.99
        for k,j in enumerate(order): x[8+j]=(k+.5)/8
        return x
    def mutate(self, parent, donor, expert, rng):
        p=list(map(int,self.decode(parent))); q=list(map(int,self.decode(donor)))
        absent=[j for j in range(8) if j not in p]
        if expert==0: # swap: change visit order, preserve active set
            if len(p)>1:
                a,b=rng.choice(len(p),2,replace=False);p[a],p[b]=p[b],p[a]
            elif absent:p.append(int(rng.choice(absent)))
        elif expert==1: # relocate / orientation: structural local search
            if len(p)>1:
                a,b=map(int,rng.choice(len(p),2,replace=False));j=p.pop(a);p.insert(b,j)
            elif absent:p.insert(0,int(rng.choice(absent)))
        elif expert==2: # activate / deactivate: cross subset cardinalities
            if absent and (len(p)==1 or rng.random()<.5):
                p.insert(int(rng.integers(len(p)+1)),int(rng.choice(absent)))
            elif len(p)>1:p.pop(int(rng.integers(len(p))))
        elif expert==3: # order-preserving donor segment, no numeric averaging
            if len(q)>1:
                a,b=sorted(map(int,rng.choice(len(q)+1,2,replace=False)))
                piece=q[a:b]
            else:piece=q[:]
            p=[j for j in p if j not in piece]
            at=int(rng.integers(len(p)+1));p[at:at]=piece
        else:raise ValueError('Unknown expert')
        return self.encode(p)
    def features(self,parent,donor):
        p=self.decode(parent);q=self.decode(donor)
        return np.array([len(p)/8, np.mean(np.abs(np.diff(p//2)))/3 if len(p)>1 else 0.,len(set(p)&set(q))/8])

@dataclass
class RGVProblem:
    group:int=1
    horizon:float=28800.
    def __post_init__(self):
        g=DATA['groups'][self.group-1]
        self.travel=np.array(g['travel'],dtype=np.float64)
        self.process=float(g['process']);self.wash=float(g['wash'])
        self.loads=np.array([g['odd_load'] if j%2==0 else g['even_load'] for j in range(8)],float)
        self.name=f'CUMCM2018B-G{self.group}-cyclic'
        self.n_var=16;self.n_obj=2;self.xl=np.zeros(16);self.xu=np.ones(16)
        self.codec=RGVCodec();self.calls=0
    def evaluate(self,X):
        X=np.atleast_2d(X)
        if X.shape[1]!=16 or not np.isfinite(X).all():raise ValueError('Invalid input')
        orders=np.zeros((len(X),8),dtype=np.int64); sizes=np.zeros(len(X),dtype=np.int64)
        for i,x in enumerate(X):
            o=self.codec.decode(x);orders[i,:len(o)]=o;sizes[i]=len(o)
        self.calls+=len(X)
        return batch_simulate(orders,sizes,self.travel,self.process,self.loads,self.wash,self.horizon)
    def pareto_front(self,n=1000):
        raise RuntimeError('Oracle front deliberately unavailable to optimizer')
    def simulate_log(self,order):
        ready=np.zeros(8);loaded=np.zeros(8,bool);t=0.;pos=0;rows=[];p=0
        while True:
            j=int(order[p%len(order)]);move=float(self.travel[abs(j//2-pos)])
            arrival=t+move;start=max(arrival,ready[j]) if loaded[j] else arrival
            endservice=start+self.loads[j];end=endservice+(self.wash if loaded[j] else 0.)
            if end>self.horizon+1e-10:break
            rows.append(dict(visit=p,cnc=j+1,depart=t,arrival=arrival,service_start=start,
                service_end=endservice,end=end,was_loaded=bool(loaded[j]),travel=move,
                processing_ready_before=float(ready[j]),next_ready=float(endservice+self.process)))
            ready[j]=endservice+self.process;loaded[j]=True;t=end;pos=j//2;p+=1
        return rows

def all_policies():
    orders=[];sizes=[]
    for k in range(1,9):
        for p in permutations(range(8),k):
            orders.append(list(p)+[-1]*(8-k));sizes.append(k)
    return np.asarray(orders,dtype=np.int64),np.asarray(sizes,dtype=np.int64)

def nondominated_2d(F):
    # Unique nondominated objective vectors for minimization, exact integer values.
    ids=np.lexsort((F[:,1],F[:,0]));best=np.inf;out=[]
    for i in ids:
        if F[i,1]<best:
            out.append(int(i));best=F[i,1]
    return np.array(out,dtype=int)

def exhaustive(group):
    problem=RGVProblem(group); orders,sizes=all_policies()
    F=batch_simulate(orders,sizes,problem.travel,problem.process,problem.loads,problem.wash,problem.horizon)
    idx=nondominated_2d(F)
    return {'F':F[idx], 'orders':orders[idx], 'sizes':sizes[idx], 'all_F':F, 'num_policies':len(F)}
