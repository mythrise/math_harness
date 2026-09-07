from pathlib import Path
import json,gzip,hashlib
import numpy as np,pandas as pd
from scipy.stats import wilcoxon
R=Path(__file__).resolve().parent;out=R/'results/analysis';out.mkdir(parents=True,exist_ok=True)
def holm(p):
 p=np.array(p,float);order=np.argsort(p);adj=np.empty(len(p));v=0
 for i,j in enumerate(order):v=max(v,(len(p)-i)*p[j]);adj[j]=min(1.,v)
 return adj

def analyze_confirm():
 d=pd.read_csv(R/'results/confirm/raw.csv')
 cols=['auc','final_gap','igd','recall','seconds','extra_pure_proposals','neighbor_builds','neighbor_filter_checks','predictions','overrides']
 per=d.groupby(['task','kind','algorithm'],as_index=False)[cols].mean();per.to_csv(out/'per_task.csv',index=False)
 sm=per.groupby('algorithm')[cols].mean();sm['runs']=d.groupby('algorithm').size();sm['front_hits']=d.groupby('algorithm').hit.sum();sm.to_csv(out/'confirm_summary.csv')
 wide=per.pivot(index='task',columns='algorithm',values='auc');rng=np.random.default_rng(1405);pairs=[]
 comparisons=[('fast_h0','fast_v10'),('fast_h0','nsga2_typed')]+[(a,b) for a in ['refit32','local24'] for b in ['fast_h0','fast_v10','nsga2_typed']]
 for a,b in comparisons:
  x=wide[a].values;y=wide[b].values;diff=x-y
  p=1. if np.max(np.abs(diff))<1e-12 else float(wilcoxon(diff,alternative='less').pvalue)
  idx=rng.integers(0,len(x),(10000,len(x)));boot=100*(1-x[idx].mean(1)/y[idx].mean(1))
  pairs.append(dict(candidate=a,baseline=b,instances=len(x),wins=int((diff< -1e-12).sum()),ties=int((np.abs(diff)<=1e-12).sum()),losses=int((diff>1e-12).sum()),improvement_pct=100*(1-x.mean()/y.mean()),worst_ratio=float((x/y).max()),p=p,bootstrap_low=float(np.quantile(boot,.025)),bootstrap_high=float(np.quantile(boot,.975))))
 pdx=pd.DataFrame(pairs);pdx['holm_p']=holm(pdx.p);pdx.to_csv(out/'primary_tests.csv',index=False)
 sec=[]
 for a,b in [('local24','local24_random'),('local24','nsga_local24'),('nsga_local24','nsga2_typed'),('refit32','fast_h0')]:
  x=wide[a].values;y=wide[b].values;dif=x-y
  sec.append(dict(candidate=a,baseline=b,improvement_pct=100*(1-x.mean()/y.mean()),wins=int((dif< -1e-12).sum()),ties=int((abs(dif)<=1e-12).sum()),losses=int((dif>1e-12).sum()),p=1. if np.max(abs(dif))<1e-12 else float(wilcoxon(dif,alternative='less').pvalue)))
 sec=pd.DataFrame(sec);sec['holm_p']=holm(sec.p);sec.to_csv(out/'ablation_tests.csv',index=False)
 per.groupby(['kind','algorithm'])[cols].mean().to_csv(out/'family_summary.csv')
 parity=[]
 for (task,seed),group in d.groupby(['task','seed']):
  x=np.load(R/f'results/confirm/{task}__h0__{seed}.npz');y=np.load(R/f'results/confirm/{task}__fast_h0__{seed}.npz')
  eq={k:bool(np.array_equal(x[k],y[k])) for k in ['X','F','output_X','output_F']}
  parity.append(dict(task=task,seed=seed,**eq))
 pd.DataFrame(parity).to_csv(out/'engineering_trace_parity.csv',index=False)
 print(sm.to_string());print(pdx.to_string(index=False));print('PARITY',len(parity),all(all(r[k] for k in ['X','F','output_X','output_F']) for r in parity))


def analyze_serial():
 d=pd.read_csv(R/'results/serial/raw.csv');sm=d.groupby('algorithm').seconds.agg(['count','mean','median']);sm.to_csv(out/'serial_summary.csv')
 w=d.pivot(index=['task','seed'],columns='algorithm',values='seconds');rows=[]
 for a,b in [('fast_h0','h0'),('fast_h0','fast_v10'),('fast_h0','fast_v10_codec'),('local24','h0'),('local24','fast_h0'),('local24','fast_v10'),('local24','fast_v10_codec'),('fast_v10_codec','fast_v10'),('local24','local24_no_cache'),('refit32','fast_h0'),('nsga2_typed','fast_v10'),('nsga_local24','nsga2_typed')]:
  q=w[a]/w[b];rows.append(dict(candidate=a,baseline=b,pairs=len(q),median_ratio=q.median(),mean_ratio=q.mean(),min_ratio=q.min(),max_ratio=q.max()))
 pd.DataFrame(rows).to_csv(out/'serial_ratios.csv',index=False);print(sm.to_string());print(pd.DataFrame(rows).to_string(index=False))


def audit():
 rows=[];forecast_count=0;init={};initchecks=0;outchecks=0;arrays=0;bad=[]
 for stage in ['dev','dev2','confirm','serial','original','stress','cap_ablation','baseline_codec_audit']:
  fp=R/f'results/{stage}/raw.csv'
  if not fp.exists():continue
  df=pd.read_csv(fp)
  for row in df.to_dict('records'):
   stem=f"{row['task']}__{row['algorithm']}__{row['seed']}";data=np.load(R/f'results/{stage}/{stem}.npz')
   X,F=data['X'],data['F'];B=int(row['budget']);arrays+=1
   assert len(X)==len(F)==int(row['fe'])==int(row['physical_calls'])==B
   assert np.isfinite(X).all() and np.isfinite(F).all() and np.all((X>=0)&(X<=1))
   key=(row['task'],row['seed'],B);sig=hashlib.sha256(X[:32].tobytes()).hexdigest()
   if key in init:assert init[key]==sig;initchecks+=1
   else:init[key]=sig
   true_pairs={x.tobytes():f for x,f in zip(X,F)}
   for x,f in zip(data['output_X'],data['output_F']):assert x.tobytes()in true_pairs and np.array_equal(true_pairs[x.tobytes()],f);outchecks+=1
   with gzip.open(R/f'results/{stage}/{stem}.log.json.gz','rt') as z:d=json.load(z)
   h=d.get('harness',d)
   for z in h.get('forecasts',[]):
    assert z['train_fe']<z['fe']<=B
    assert np.array_equal(np.array(z['actual']),F[z['fe']-1]);forecast_count+=1
   rows.append(dict(stage=stage,task=row['task'],algorithm=row['algorithm'],seed=row['seed'],fe=B))
 originals=json.loads((R/'protocol/INPUT_HASHES.json').read_text())
 baselineok=all(hashlib.sha256((R/'vendor/v13'/p).read_bytes()).hexdigest()==v for p,v in originals.items())
 assert baselineok
 frozen={}
 for p in (R/'protocol').glob('*_FREEZE.json'):
  d=json.loads(p.read_text());ok=True
  stage=p.stem.removesuffix('_FREEZE')
  for path,h in d['files'].items():
   f=R/path
   if stage in ['dev','dev2'] and path.startswith('mosaic14/'):
    f=R/f'protocol/{stage}_source_snapshot'/Path(path).name
   if stage in ['dev','dev2'] and path=='run_experiments.py':f=R/f'protocol/{stage}_source_snapshot/run_experiments.py'
   ok=ok and hashlib.sha256(f.read_bytes()).hexdigest()==h
  frozen[stage]=ok
 assert all(frozen.values())
 pd.DataFrame(rows).to_csv(out/'all_registered_runs.csv',index=False)
 warms=[]
 for p in (R/'results/warmup').glob('*.json'):warms.extend(json.loads(p.read_text()))
 cert=json.loads((R/'results/references/ACCOUNTING.json').read_text())
 result=dict(complete_runs=arrays,search_FE=sum(x['fe']for x in rows),initialization_matches=initchecks,output_truth_checks=outchecks,forecast_temporal_checks=forecast_count,baseline_source_unchanged=baselineok,stage_source_freezes=frozen,recorded_discarded_warmup_calls=sum(x['physical_evals']for x in warms),reference_vector_evaluations=sum(x['oracle_vectors']for x in cert),reference_instance_count=len(cert),all_audits_pass=True,scope='Only registered complete runs. Profiles, quick parity smoke and unit tests are excluded from benchmark counts.')
 (out/'FULL_AUDIT.json').write_text(json.dumps(result,indent=2));print(result)

if __name__=='__main__':
 import sys
 cmd=sys.argv[1] if len(sys.argv)>1 else 'all'
 if cmd in ['confirm','all']:analyze_confirm()
 if cmd in ['serial','all'] and (R/'results/serial/raw.csv').exists():analyze_serial()
 if cmd in ['audit','all']:audit()
