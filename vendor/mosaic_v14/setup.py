import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import json,datetime,hashlib,numpy as np
from mosaic14.bootstrap import ROOT,V13
from harnesslab.problems import make_problem
old=json.loads((V13/'protocol/instances.json').read_text());dev=[s for s in old if s['partition']=='development']
# Do not import v13/setup_protocol: importing it would overwrite frozen files.
def tour(n,seed,id,part):
 r=np.random.default_rng(seed);xy=r.uniform(0,100,(n+1,2));xy[n]=[50,50];d=np.sqrt(((xy[:,None]-xy[None,:])**2).sum(2))
 return dict(id=id,kind='tour',partition=part,n=n,generator_seed=seed,dist=d.tolist(),values=r.uniform(15,100,n).tolist(),service=r.uniform(1,10,n).tolist(),discount=r.uniform(80,350,n).tolist())
def jobs(n,seed,id,part):
 r=np.random.default_rng(seed);s=r.uniform(0,30,(n+1,n+1));np.fill_diagonal(s,0)
 return dict(id=id,kind='job',partition=part,n=n,generator_seed=seed,setup=s.tolist(),values=r.uniform(20,100,n).tolist(),process=r.uniform(5,25,n).tolist(),dues=r.uniform(20,160,n).tolist(),penalty=r.uniform(.1,1.1,n).tolist())
hold=[]
for i,seed in enumerate([1411033,1411057,1411071,1411089]):
 r=np.random.default_rng(seed);g=i%3+1;p=make_problem(dict(id='tmp',kind='rgv',group=g))
 hold.append(dict(id=f'rgv_new{i+1}',kind='rgv',partition='holdout',group=g,generator_seed=seed,process=float(round(p.process*r.uniform(.6,1.5))),wash=float(round(p.wash*r.uniform(.6,1.7))),loads=np.round(p.loads*r.uniform(.6,1.7,8)).tolist(),travel=np.r_[0,np.cumsum(r.uniform(10,40,3))].round().tolist(),horizon=float(r.choice([7200,14400,21600,36000]))))
for i,seed in enumerate([1421011,1421029,1421053,1421073]):hold.append(tour(8,seed,f'tour_new{i+1}','holdout'))
for i,seed in enumerate([1431003,1431051,1431067,1431079]):hold.append(jobs(8,seed,f'job_new{i+1}','holdout'))
stress=[fn(n,1441000+n+(100 if kind=='job' else 0),f'{kind}_stress{n}','stress') for n in [12,16] for kind,fn in [('tour',tour),('job',jobs)]]
(ROOT/'protocol/instances.json').write_text(json.dumps(dev+hold+stress,indent=2))
plan=dict(round='MOSAIC-v14-Efficiency-Lab',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
engineering='Same RNG, policies, objectives, model fit and HVI. Cache codec, semantic features and front decomposition. Preserve entire evaluated X/F sequences.',
development=dict(tasks=[s['id'] for s in dev],seeds=list(range(74101,74105)),budget=512,population=32,variants=['fast_v10','nsga2_typed','fast_h0','bounded24','pool4','local24','local48','local_all','refit32','local24_refit32']),
confirmation=dict(tasks=[s['id'] for s in hold],seeds=list(range(74501,74513)),budget=1024,population=32),
selection='Freeze single minimum equal-instance mean AUC candidate among variants with development mean final_gap <= fast_h0+.001; require >=3% improvement over fast_h0 to promote quality candidate. Otherwise only diagnostic confirmation. Engineering fast_h0 retained independently on trace parity.',
quality_gate=dict(auc_improvement_vs_h0=.03,auc_improvement_vs_fast_v10=.05,worst_instance_ratio_vs_h0=1.20,mean_final_gap_increase_vs_h0=.001,instance_holm_p=.05),
cost_gate=dict(engineering_median_ratio_vs_h0=.80,median_ratio_vs_fast_v10=1.8),
reference='n=8 full finite deterministic strategy fronts scored after search only; numerical tolerance inherited. New parameters in same 3 known model families, not new domains.',
serial='3 domains x4 seeds; randomized order; all imports/JIT warmup outside timer and disclosed. No concurrency during timing.',
claim='No official/universal SOTA. Original v13 immutable. No evaluator modifications or precomputed objectives injected. Error runs not scored.')
(ROOT/'protocol/PLAN.json').write_text(json.dumps(plan,indent=2))
h={str(p.relative_to(ROOT/'vendor/v13')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'vendor/v13').rglob('*.py')}
(ROOT/'protocol/INPUT_HASHES.json').write_text(json.dumps(h,indent=2))
print('plan written',len(dev),len(hold),len(stress))
