"""Pure proposal extensions: no evaluator, oracle front, or objective callback.

The quantile correction is an online routing heuristic inspired by expert-load
calibration. It is not Kimi's neural router, a pretrained policy, or a guarantee
that equal expert utilization is optimal for black-box optimization.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import deque
from typing import Protocol
import numpy as np
from scipy.special import logsumexp, softmax

class Codec(Protocol):
    def mutate(self, parent, donor, expert:int, rng:np.random.Generator)->np.ndarray: ...
    def features(self, parent, donor)->np.ndarray: ...

@dataclass(frozen=True)
class ExtensionConfig:
    mode:str='quantile'  # quantile, contextual, uniform, disabled
    fraction:float=.50
    warmup:float=.10
    forgetting:float=.995
    uncertainty:float=.18
    quantile_cap:float=.08

@dataclass
class Ticket:
    expert:int
    phi:np.ndarray
    parent_f:np.ndarray
    ideal:np.ndarray
    scale:np.ndarray
    weight:np.ndarray
    mu:float
    selected_at:int

class TypedRouter:
    def __init__(self,codec:Codec,seed:int,budget:int,config:ExtensionConfig=ExtensionConfig()):
        self.codec=codec;self.config=config;self.budget=budget
        self.rng=np.random.default_rng(np.random.SeedSequence([int(seed),991081]))
        self.n_experts=4;self.dim=7
        self.A=np.repeat(np.eye(self.dim)[None,:,:],4,axis=0)
        self.b=np.zeros((4,self.dim));self.bias=np.zeros(4)
        self.count=np.zeros(4,int);self.reward_sum=np.zeros(4);self.ema=np.full(4,.5)
        self.contexts=deque(maxlen=48);self.executed=0;self.null_routes=0;self.log=[]

    @staticmethod
    def scalar(f,w,ideal,scale,mu):
        y=np.maximum((f-ideal)/scale,0.)
        return float(mu*logsumexp(np.maximum(w,1e-4)*y/mu))

    def _quantile_bias(self, means):
        # S[i,e]: predicted utility for several recent compatible contexts.
        # Nonuniform target load tracks empirical utility, with a small floor.
        S=np.asarray(self.contexts)@means.T
        q=.30/4+.70*softmax((self.ema-self.ema.max())/.15)
        bias=self.bias.copy()
        for _ in range(3):
            proposal=[]
            for e in range(4):
                others=np.delete(S+bias[None,:],e,axis=1)
                margin=np.max(others,axis=1)-S[:,e]
                proposal.append(np.quantile(margin,1-q[e]))
            proposal=np.asarray(proposal);proposal-=proposal.mean()
            bias=.7*bias+.3*proposal
        self.bias=np.clip(bias,-self.config.quantile_cap,self.config.quantile_cap)

    def propose(self, shared, parent, parent_f, X, F, W, cell, ideal, nadir,
                progress, evals, base_op, stagnation):
        if (self.config.mode=='disabled' or base_op>=5 or progress<self.config.warmup
                or self.executed>=int(self.config.fraction*self.budget)
                or self.rng.random()>=self.config.fraction):
            self.null_routes+=1
            return shared,None
        # Donor selection uses only observed population values, not new calls.
        dist=np.sum((F-parent_f)**2/(np.ptp(F,axis=0)**2+1e-12),axis=1)
        near=np.argsort(dist,kind='stable')[:max(4,len(X)//3)]
        donor=X[int(self.rng.choice(near))]
        feats=np.clip(np.asarray(self.codec.features(parent,donor),float),0,1)
        phi=np.r_[1.,progress, min(float(stagnation)/8,1.),feats, progress*feats[0]]
        if phi.shape!=(7,):raise ValueError('Codec must return exactly three context features')
        if self.config.mode=='uniform': e=int(self.rng.integers(4))
        else:
            inv=np.linalg.inv(self.A)
            means=np.einsum('eij,ej->ei',inv,self.b)
            if self.config.mode=='quantile' and len(self.contexts)>=16 and self.executed%12==0:
                self._quantile_bias(means)
            std=np.sqrt(np.maximum(np.einsum('i,eij,j->e',phi,inv,phi),1e-12))
            score=means@phi+self.config.uncertainty*std*self.rng.standard_normal(4)
            if self.config.mode=='quantile':score+=self.bias
            # Deterministic finite warm-up ensures each compatible expert gets data.
            e=int(self.executed%4) if self.executed<8 else int(np.argmax(score))
        child=self.codec.mutate(parent,donor,e,self.rng)
        self.contexts.append(phi.copy());self.executed+=1
        ticket=Ticket(e,phi,parent_f.copy(),ideal.copy(),np.maximum(nadir-ideal,1e-9),
                      W[cell].copy(),.008+.10*(1-progress)**2,int(evals))
        return child,ticket

    def observe(self,ticket,child_f,entered,replaced):
        if ticket is None:return
        old=self.scalar(ticket.parent_f,ticket.weight,ticket.ideal,ticket.scale,ticket.mu)
        new=self.scalar(child_f,ticket.weight,ticket.ideal,ticket.scale,ticket.mu)
        relative=np.clip((old-new)/(abs(old)+.05),-1.,1.)
        # Evaluated parent vs evaluated child: NOT an unobserved counterfactual.
        reward=float(.8*(.5+.5*relative)+.2*bool(entered))
        e=ticket.expert;p=ticket.phi;g=self.config.forgetting
        self.A[e]=np.eye(7)+g*(self.A[e]-np.eye(7))+np.outer(p,p)
        self.b[e]=g*self.b[e]+p*reward
        self.count[e]+=1;self.reward_sum[e]+=reward
        self.ema[e]=.9*self.ema[e]+.1*reward
        self.log.append({'fe':ticket.selected_at+1,'expert':int(e),'reward':reward,
                         'entered':bool(entered),'replaced':int(replaced),
                         'bias':self.bias.tolist()})

    def diagnostics(self):
        return {'mode':self.config.mode,'executed':self.executed,'null_routes':self.null_routes,
                'counts':self.count.tolist(),'reward_sum':self.reward_sum.tolist(),
                'final_bias':self.bias.tolist(),'route_log':self.log}
