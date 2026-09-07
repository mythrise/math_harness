"""Post-run summaries; never imported by optimizers and no reference leakage."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import json,gzip
import numpy as np,pandas as pd
from scipy.stats import wilcoxon
from mosaic14.bootstrap import score_trace
from harnesslab.metrics import nd2
def holm(p):
 p=np.asarray(p,float);order=np.argsort(p);adj=np.empty(len(p));v=0.
 for i,j in enumerate(order):v=max(v,(len(p)-i)*p[j]);adj[j]=min(1.,v)
 return adj
R=Path(__file__).resolve().parent;out=R/'results/analysis'

def stress():
 d=pd.read_csv(R/'results/stress/raw.csv');refs=R/'results/stress/pooled_references';refs.mkdir(exist_ok=True)
 rows=[]
 for task,g in d.groupby('task'):
  arrays=[np.load(R/f"results/stress/{task}__{z['algorithm']}__{z['seed']}.npz")for z in g.to_dict('records')]
  # Duplicate engineering trajectories have no effect on the Pareto union.
  front=nd2(np.vstack([a['F']for a in arrays]));np.savez_compressed(refs/f'{task}.npz',F=front)
  for z,a in zip(g.to_dict('records'),arrays):
   s=score_trace(a['F'],a['output_F'],front,int(z['budget']));s.pop('trace');rows.append(z|s)
 df=pd.DataFrame(rows);df.to_csv(out/'stress_scored.csv',index=False)
 per=df.groupby(['task','algorithm'],as_index=False)[['auc','final_gap','igd','recall']].mean();per.to_csv(out/'stress_per_task.csv',index=False)
 per.groupby('algorithm')[['auc','final_gap','igd','recall']].mean().to_csv(out/'stress_summary.csv')
 (refs/'REFERENCE_SCOPE.json').write_text(json.dumps(dict(scope='Pooled observed reference from all completed methods, not exact; scoring after all searches finished',algorithms=sorted(d.algorithm.unique()),tasks=sorted(d.task.unique()),reference_calls_during_search=0),indent=2))
 print('STRESS\n',per.groupby('algorithm')[['auc','final_gap','igd','recall']].mean())

def cap():
 extra=pd.read_csv(R/'results/cap_ablation/raw.csv');conf=pd.read_csv(R/'results/confirm/raw.csv');seeds=extra.seed.unique()
 d=pd.concat([extra,conf[conf.seed.isin(seeds)&conf.algorithm.isin(['fast_h0','local24'])]],ignore_index=True)
 per=d.groupby(['task','algorithm'],as_index=False)[['auc','final_gap','igd','recall','neighbor_builds','neighbor_filter_checks','predictions']].mean();per.to_csv(out/'cap_per_task.csv',index=False)
 per.groupby('algorithm').mean(numeric_only=True).to_csv(out/'cap_summary.csv')
 w=per.pivot(index='task',columns='algorithm',values='auc');rows=[]
 for a,b in [('local24','local7'),('local7','fast_h0'),('local24','fast_h0')]:
  x,y=w[a].values,w[b].values;dif=x-y
  rows.append(dict(candidate=a,baseline=b,instances=len(x),seeds_per_instance=len(seeds),improvement_pct=100*(1-x.mean()/y.mean()),wins=int((dif< -1e-12).sum()),ties=int((abs(dif)<=1e-12).sum()),losses=int((dif>1e-12).sum()),p=float(wilcoxon(dif,alternative='less').pvalue)))
 rows=pd.DataFrame(rows);rows['holm_p']=holm(rows.p);rows.to_csv(out/'cap_tests.csv',index=False)
 print('CAP\n',per.groupby('algorithm').mean(numeric_only=True));print(rows.to_string(index=False))

def original():
 d=pd.read_csv(R/'results/original/raw.csv');p=d.groupby(['task','algorithm'],as_index=False)[['auc','final_gap','igd']].mean();p.to_csv(out/'original_per_task.csv',index=False)
 s=p.groupby('algorithm').mean(numeric_only=True);s['front_hits']=d.groupby('algorithm').hit.sum();s['runs']=d.groupby('algorithm').size();s.to_csv(out/'original_summary.csv')
 print('ORIGINAL\n',s)
 # Prespecified first original-case seed; all candidates' actual returned policies.
 from mosaic14.bootstrap import make_problem
 rows=[]
 for task,g in d[d.seed==74801].groupby('task'):
  group=int(task[-1]);pr=make_problem(dict(id=task,kind='rgv',group=group))
  for z in g.to_dict('records'):
   a=np.load(R/f"results/original/{task}__{z['algorithm']}__{z['seed']}.npz")
   for x,f in zip(a['output_X'],a['output_F']):rows.append(dict(task=task,algorithm=z['algorithm'],seed=z['seed'],cycle='-'.join(str(int(v)+1)for v in pr.codec.decode(x)),products=-f[0],travel_seconds=f[1]))
 pd.DataFrame(rows).to_csv(out/'original_policy_examples.csv',index=False)

def parity():
 rows=[]
 for stage in ['confirm','original','stress','serial']:
  p=R/f'results/{stage}/raw.csv'
  if not p.exists():continue
  d=pd.read_csv(p)
  comparisons=[('fast_h0','h0')]+([('fast_v10_codec','fast_v10'),('local24_no_cache','local24')]if stage=='serial'else[])
  for (task,seed),g in d.groupby(['task','seed']):
   for a,b in comparisons:
    if not {a,b}<=set(g.algorithm):continue
    u=np.load(R/f'results/{stage}/{task}__{a}__{seed}.npz');v=np.load(R/f'results/{stage}/{task}__{b}__{seed}.npz')
    row=dict(stage=stage,task=task,seed=seed,candidate=a,baseline=b,**{k:bool(np.array_equal(u[k],v[k]))for k in ['X','F','output_X','output_F']});rows.append(row)
 # Post-timing engineering control: same codec optimization also applied to
 # Fast-v10. Match against original confirmation traces, not new problem data.
 control=R/'results/baseline_codec_audit/raw.csv'
 if control.exists():
  for z in pd.read_csv(control).to_dict('records'):
   task,seed=z['task'],z['seed']
   u=np.load(R/f'results/baseline_codec_audit/{task}__fast_v10_codec__{seed}.npz')
   v=np.load(R/f'results/confirm/{task}__fast_v10__{seed}.npz')
   rows.append(dict(stage='baseline_codec_audit',task=task,seed=seed,candidate='fast_v10_codec',baseline='fast_v10',**{k:bool(np.array_equal(u[k],v[k]))for k in ['X','F','output_X','output_F']}))
 df=pd.DataFrame(rows);df.to_csv(out/'all_trace_parity.csv',index=False)
 assert df[['X','F','output_X','output_F']].all().all()
 print('ALL PARITY\n',df.groupby(['candidate','baseline']).size())

def diagnostics():
 d=pd.read_csv(R/'results/confirm/raw.csv');rows=[]
 for z in d.to_dict('records'):
  if z['algorithm']not in ['h0','fast_h0','local24','refit32']:continue
  with gzip.open(R/f"results/confirm/{z['task']}__{z['algorithm']}__{z['seed']}.log.json.gz",'rt')as f:h=json.load(f).get('harness',{})
  row={k:z[k]for k in ['task','algorithm','seed']}
  for k in ['feature_cache_hits','feature_cache_misses','hv_cache_rebuilds','hv_cache_hits','neighbor_builds','neighbor_cache_hits','neighbor_filter_checks']:row[k]=h.get(k,0)
  pool=h.get('pool_counts',[]);row['mean_pool_size']=float(np.mean(pool))if pool else np.nan;row['max_pool_size']=max(pool)if pool else np.nan
  rows.append(row)
 pd.DataFrame(rows).to_csv(out/'cache_diagnostics_raw.csv',index=False)
 pd.DataFrame(rows).groupby('algorithm').mean(numeric_only=True).to_csv(out/'cache_diagnostics_summary.csv')
if __name__=='__main__':
 import sys
 cmd=sys.argv[1]if len(sys.argv)>1 else'all'
 if cmd in ['stress','all']:stress()
 if cmd in ['cap','all']:cap()
 if cmd in ['original','all']:original()
 if cmd in ['parity','all']:parity()
 if cmd in ['diagnostics','all']:diagnostics()
