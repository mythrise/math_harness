"""Manage--Propose--Evaluate--Audit harness for deterministic ordered subsets.
The manager sees only paid observations, never a reference front or task name.
No LLM inference takes place inside the optimization loop.
"""
from dataclasses import dataclass,asdict
from collections import deque
import numpy as np
from .bootstrap import core
from .model import features,PredictionModel,nd_indices,hypervolume_improvement

@dataclass(frozen=True)
class Config:
    planner:str='hvi'          # random, scalar, hvi, mission
    guarded:bool=True
    uncertainty:float=.35
    pool:int=24
    batch:int=4
    refit:int=64
    exploration:float=.20
    raw_features:bool=False
    mission_horizon:int=8
    backend:str='archive'    # archive or nsga2; matched harness control

CONFIGS={
 'pool_random':Config(planner='random',guarded=False),
 'surrogate_scalar':Config(planner='scalar',guarded=False),
 'surrogate_hvi':Config(planner='hvi',guarded=False),
 'harness':Config(),
 'harness_no_uncertainty':Config(uncertainty=0.),
 'harness_raw':Config(raw_features=True),
 'mission':Config(planner='mission',guarded=False),
 'mission_one_step':Config(planner='mission',guarded=False,mission_horizon=1),
 'nsga2_harness':Config(backend='nsga2'),
}

def run_harness(problem,codec,seed,pop_size,max_evals,config:Config):
    rng,X,F=core.initialize(problem,pop_size,seed)
    plan_rng=np.random.default_rng(np.random.SeedSequence([seed,130913]))
    key=lambda x:tuple(map(int,codec.decode(x)))
    seen=set(map(key,X));dataX=[x.copy() for x in X];dataF=[f.copy() for f in F]
    low=F.min(0);scale=np.maximum(np.ptp(F,axis=0),1e-9);ref=(F.max(0)-low)/scale+.2
    ids=nd_indices(F);AX=X[ids].copy();AF=F[ids].copy()
    popX=X.copy();popF=F.copy();model=PredictionModel(seed+1327)
    records=[];fits=[];decisions=[];residuals=deque(maxlen=16)
    held_pred=[];pending=[];fit_at=-1;proposals=0;dups=0;fallbacks=0;model_calls=0;mission=None
    t=len(dataF)

    def choose_parent():
        if config.backend=='nsga2':
            fronts,ranks=core.fast_nondominated_sort(popF);crowd=np.zeros(len(popF))
            for front in fronts:crowd[front]=core.crowding_distance(popF[front])
            a=core.tournament(ranks,crowd,rng);b=core.tournament(ranks,crowd,rng)
            return popX[a],popX[b]
        return AX[int(rng.integers(len(AX)))],AX[int(rng.integers(len(AX)))]

    def propose_one(local):
        nonlocal proposals,dups,fallbacks
        pa,don=choose_parent()
        for e in rng.permutation(4):
            for _ in range(12):
                c=codec.mutate(pa,don,int(e),rng);proposals+=1;k=key(c)
                if k not in seen and k not in local:return c,int(e)
                dups+=1
        for _ in range(64):
            c=problem.xl+rng.random(problem.n_var)*(problem.xu-problem.xl);proposals+=1
            if key(c) not in seen and key(c) not in local:return c,4
        fallbacks+=1
        return c,4

    while t<max_evals:
        if config.planner=='mission':
            if mission is None or mission['left']<=0 or mission['stuck']>=3:
                w=plan_rng.dirichlet(np.ones(2));Y=(AF-low)/scale
                i=int(np.argmin(np.max(Y*w,axis=1)))
                mission=dict(x=AX[i].copy(),f=AF[i].copy(),w=w,left=config.mission_horizon,stuck=0)
                decisions.append(dict(fe=t,state='PLAN',horizon=config.mission_horizon,weights=w.tolist()))
            pa=mission['x'];don=AX[int(rng.integers(len(AX)))];c=None
            for e in rng.permutation(4):
                for _ in range(12):
                    cc=codec.mutate(pa,don,int(e),rng);proposals+=1
                    if key(cc) not in seen:c=cc;break
                    dups+=1
                if c is not None:break
            if c is None:c,e=propose_one(set())
            mean=std=None;reason='bounded_mission';pred_ver=0
        else:
            if not pending:
                candidates=[];experts=[];local=set()
                for _ in range(config.pool):
                    cc,ee=propose_one(local);candidates.append(cc);experts.append(ee);local.add(key(cc))
                candidates=np.asarray(candidates);means=stds=None
                if config.planner!='random' and t>=64:
                    if fit_at<0 or t-fit_at>=config.refit:
                        Z=features(np.array(dataX),codec,config.raw_features);Y=(np.array(dataF)-low)/scale
                        fits.append(model.fit(Z,Y));fit_at=t
                    means,stds=model.predict(features(candidates,codec,config.raw_features));model_calls+=len(candidates)
                allowed=means is not None
                why='no_model'
                if allowed:
                    why='model'
                    if config.guarded:
                        ok=model.validation_score>=.35 and model.validation_error<=.35
                        if len(residuals)>=8 and np.mean(residuals)>.45:ok=False
                        if not ok:allowed=False;why='audit_fallback'
                Yfront=(AF-low)/scale;available=list(range(len(candidates)))
                # Fixed-size contracts. Selected siblings are not inserted as
                # verified facts; a temporary predicted set only diversifies picks.
                virtual=Yfront.copy()
                for q in range(min(config.batch,max_evals-t)):
                    use=allowed and plan_rng.random()>=config.exploration
                    if not use:pick=int(plan_rng.choice(available));reason=why if not allowed else 'exploration'
                    else:
                        pmean=means[available]-config.uncertainty*stds[available]
                        if config.planner=='scalar':
                            w=plan_rng.dirichlet(np.ones(2));scores=-np.max(pmean*w,axis=1)
                        else:
                            scores=hypervolume_improvement(pmean,virtual,ref)
                            if scores.max()<=1e-14:
                                w=plan_rng.dirichlet(np.ones(2));scores=-np.max(pmean*w,axis=1)
                        pick=available[int(np.argmax(scores))];reason='predicted_'+config.planner
                    pm=means[pick].copy() if means is not None else None
                    ps=stds[pick].copy() if stds is not None else None
                    pending.append((candidates[pick].copy(),experts[pick],pm,ps,reason,model.version))
                    if pm is not None:virtual=np.vstack([virtual,pm])
                    available.remove(pick)
                decisions.append(dict(fe=t,state='AUTHORIZE',allowed=bool(allowed),reason=why,pool=len(candidates),batch=len(pending),model_version=model.version))
            c,e,mean,std,reason,pred_ver=pending.pop(0)
        # Reserve/charge occurs in the only evaluator. Store forecasts before observing truth.
        rec=dict(fe=t+1,expert=int(e),reason=reason,model_version=pred_ver,prediction=None if mean is None else mean.tolist(),std=None if std is None else std.tolist())
        cf=problem.evaluate(c)[0];t+=1;seen.add(key(c));dataX.append(c.copy());dataF.append(cf.copy())
        if mean is not None:
            error=float(np.mean(np.abs((cf-low)/scale-mean)));residuals.append(error);rec['prequential_mae']=error
        if config.planner=='mission':
            old=np.max((mission['f']-low)/scale*mission['w']);new=np.max((cf-low)/scale*mission['w'])
            if new<old:mission['x']=c.copy();mission['f']=cf.copy();mission['stuck']=0
            else:mission['stuck']+=1
            mission['left']-=1
        joinedF=np.vstack([AF,cf]);joinedX=np.vstack([AX,c]);ids=nd_indices(joinedF);AX=joinedX[ids];AF=joinedF[ids]
        # Old pool cap retained for manageable archive use.
        if len(AF)>4*pop_size:
            ids=core.select_indices_farthest(AF,4*pop_size);AX=AX[ids];AF=AF[ids]
        if config.backend=='nsga2':
            popX,popF,_,_=core.nsga2_environmental_selection(np.vstack([popX,c]),np.vstack([popF,cf]),pop_size)
        rec['actual']=cf.tolist();records.append(rec)
    if len(AF)>pop_size:
        ids=core.select_indices_farthest(AF,pop_size);AX=AX[ids];AF=AF[ids]
    return core.RunResult('harness',problem.name,seed,AX,AF,t,[],dict(config=asdict(config),contracts=decisions,forecasts=records,model_fits=fits,proposal_attempts=proposals,duplicate_proposals=dups,unique_evaluated=len(seen),random_fallbacks=fallbacks,surrogate_predictions=model_calls))
