from pathlib import Path
import json,datetime,hashlib,sys
import numpy as np
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R))
from harnesslab.bootstrap import old_make_problem
old=json.loads((R/'vendor/protocol/instances.json').read_text())
dev=[dict(s,partition='development') for s in old if s['id'] in ['rgv_g1','rgv_dev','tour_dev']]

def tour(n,seed,id,part):
 r=np.random.default_rng(seed);xy=r.uniform(0,100,(n+1,2));xy[n]=[50,50];d=np.sqrt(((xy[:,None]-xy[None,:])**2).sum(2))
 return dict(id=id,kind='tour',partition=part,n=n,generator_seed=seed,dist=d.tolist(),values=r.uniform(15,100,n).tolist(),service=r.uniform(1,10,n).tolist(),discount=r.uniform(80,350,n).tolist())
def jobs(n,seed,id,part):
 r=np.random.default_rng(seed);setup=r.uniform(0,30,(n+1,n+1));np.fill_diagonal(setup,0)
 return dict(id=id,kind='job',partition=part,n=n,generator_seed=seed,setup=setup.tolist(),values=r.uniform(20,100,n).tolist(),process=r.uniform(5,25,n).tolist(),dues=r.uniform(20,160,n).tolist(),penalty=r.uniform(.1,1.1,n).tolist())
dev.append(jobs(8,813091,'job_dev','development'))
hold=[]
for i,s in enumerate([911033,911057,911071,911089]):
 r=np.random.default_rng(s);g=i%3+1;p=old_make_problem(dict(id='tmp',kind='rgv',group=g))
 hold.append(dict(id=f'rgv_h{i+1}',kind='rgv',partition='holdout',group=g,generator_seed=s,
 process=float(round(p.process*r.uniform(.6,1.5))),wash=float(round(p.wash*r.uniform(.6,1.7))),loads=np.round(p.loads*r.uniform(.6,1.7,8)).tolist(),travel=np.r_[0,np.cumsum(r.uniform(10,40,3))].round().tolist(),horizon=float(r.choice([7200,14400,21600,36000]))))
for i,s in enumerate([921011,921029,921053,921073]):hold.append(tour(8,s,f'tour_h{i+1}','holdout'))
for i,s in enumerate([931003,931051,931067,931079]):hold.append(jobs(8,s,f'job_h{i+1}','holdout'))
stress=[]
for n in [12,16]:
 for kind,fn in [('tour',tour),('job',jobs)]:stress.append(fn(n,941000+n+(0 if kind=='tour' else 100),f'{kind}_n{n}','stress'))
(R/'protocol/instances.json').write_text(json.dumps(dev+hold+stress,indent=2))
plan=dict(round='MOSAIC-v13-Harness-Lab',date='2026-09-05',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 research='Beyond routing: bounded missions, surrogate preselection, verified model-authority gate',
 dev=dict(tasks=[s['id'] for s in dev],seeds=list(range(13101,13105)),budget=512,population=32),
 confirm=dict(tasks=[s['id'] for s in hold],seeds=list(range(13501,13513)),budget=1024,population=32),
 primary='Equal-instance mean of normalized hypervolume-gap AUC over log2 FE checkpoints',
 checkpoints=[32,64,128,256,512,1024],
 thresholds=dict(mean_auc_improvement_vs_each_baseline_pct=5,worst_task_auc_ratio=1.20,final_mean_gap_increase=.001,serial_median_time_ratio_vs_fast=1.8,holm_p=.05),
 selection='One candidate with lowest development equal-task mean AUC among those meeting mean final-gap guard. Both baselines and mandatory same-pool random, no-gate, no-uncertainty, scalar acquisition, raw-feature and same-harness NSGA controls remain diagnostic regardless. Do not retune on confirmation.',
 baselines=['fast_v10','nsga2_typed'],claim_boundary='No neural LLM inside loop. Frozen v10 mainline retained unless full gate passes. No official or universal SOTA.',
 references='Complete n=8 finite fronts for scoring only, not imported by optimizer. Models train only on this run paid evaluations. No prior-run training.',
 real_problem='2018 CUMCM B one-process no-fault cyclic nonempty ordered subsets; inherited assumptions unchanged. Added travel-time objective.',
 runtime='True FE and model training/prediction/proposal CPU reported separately; parallel elapsed not serial speed.',
 stress='n=12/16 synthetic instances only; independent pooled reference approximation, NOT exact front. Separate from primary significance.',
 warmup='At most one discarded physical model call per domain per process, logged and unavailable to search.')
(R/'protocol/PLAN.json').write_text(json.dumps(plan,indent=2))
print('prepared',len(dev),len(hold),len(stress))
