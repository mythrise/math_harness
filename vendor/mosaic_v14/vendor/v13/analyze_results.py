from pathlib import Path
import json,sys
import numpy as np,pandas as pd
from scipy.stats import wilcoxon
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R))
from harnesslab.metrics import nd2,score_trace
OUT=R/'results/analysis';OUT.mkdir(exist_ok=True)
PRIMARY='no_uncertainty_linear'

def holm(rows):
 if not rows:return rows
 order=np.argsort([r['p']for r in rows]);last=0.;m=len(rows)
 for j,i in enumerate(order):
  last=max(last,min(1.,rows[i]['p']*(m-j)));rows[i]['holm_p']=last
 return rows

def pair(df,cand,base,metric='auc',boot=True):
 pt=df.groupby(['task','algorithm'])[metric].mean().unstack();a=pt[cand].values;b=pt[base].values;delta=a-b
 p=float(wilcoxon(a,b,alternative='less').pvalue)if np.any(np.abs(delta)>1e-14)else 1.
 d=dict(candidate=cand,baseline=base,metric=metric,instances=len(a),wins=int((delta<-1e-12).sum()),ties=int((abs(delta)<=1e-12).sum()),losses=int((delta>1e-12).sum()),improvement_pct=float(100*(1-a.mean()/b.mean())),worst_ratio=float(np.max(a/np.maximum(b,1e-15))),p=p)
 if boot:
  rng=np.random.default_rng(130908);ix=rng.integers(len(a),size=(20000,len(a)));gain=100*(1-a[ix].mean(1)/b[ix].mean(1));d.update(zip(['bootstrap95_low','bootstrap95_high'],map(float,np.quantile(gain,[.025,.975]))))
 return d

def main():
 frames=[]
 for stage in ['dev','dev2','dev3','confirm','original','stress','serial','serial_contended']:
  f=R/f'results/{stage}/raw.csv'
  if f.exists():
   d=pd.read_csv(f);d['stage']=stage;frames.append(d)
 allrows=pd.concat(frames,ignore_index=True);allrows.to_csv(OUT/'all_registered_runs.csv',index=False)
 d=pd.read_csv(R/'results/confirm/raw.csv');mean=d.groupby('algorithm').agg(runs=('seed','size'),auc=('auc','mean'),final_gap=('final_gap','mean'),igd=('igd','mean'),recall=('recall','mean'),hits=('hit','sum'),mean_parallel_seconds=('seconds','mean'),mean_overrides=('overrides','mean'));mean.to_csv(OUT/'confirm_summary.csv')
 per=d.groupby(['task','kind','algorithm']).mean(numeric_only=True).reset_index();per.to_csv(OUT/'per_task.csv',index=False)
 tests=holm([pair(d,PRIMARY,b)for b in ['fast_v10','nsga2_typed']]);pd.DataFrame(tests).to_csv(OUT/'primary_tests.csv',index=False)
 pairs=[('no_uncertainty_linear','guarded_linear'),('guarded_linear','unguarded_linear'),('guarded_linear','random_residual'),('guarded_linear','raw_linear'),('guarded_linear','scalar_linear'),('nsga2_guarded','nsga2_typed'),('guarded_linear','nsga2_guarded')]
 secondary=holm([pair(d,a,b)for a,b in pairs]);pd.DataFrame(secondary).to_csv(OUT/'ablation_tests.csv',index=False)
 changes=per.pivot(index='task',columns='algorithm',values='auc');ch=100*(1-changes.div(changes.fast_v10,axis=0));ch.to_csv(OUT/'per_instance_improvement_pct.csv')
 gate=dict(selected=PRIMARY,mean_auc_gate=all(t['improvement_pct']>=5 for t in tests),worst_instance_gate=all(t['worst_ratio']<=1.2 for t in tests),significance_gate=all(t['holm_p']<=.05 for t in tests),final_gap_delta=float(mean.loc[PRIMARY,'final_gap']-mean.loc['fast_v10','final_gap']),default_mainline='fast_v10')
 gate['final_gap_gate']=gate['final_gap_delta']<=.001
 gate['confirmation_quality_gate']=all(gate[x]for x in ['mean_auc_gate','worst_instance_gate','significance_gate','final_gap_gate'])
 if (R/'results/serial/raw.csv').exists():
  serial=pd.read_csv(R/'results/serial/raw.csv');serial.groupby('algorithm').seconds.agg(['count','mean','median']).to_csv(OUT/'serial_summary.csv');ps=serial.pivot(index=['task','seed'],columns='algorithm',values='seconds');r=[]
  for alg in ps:
   x=ps[alg]/ps.fast_v10;r.append(dict(algorithm=alg,pairs=len(x),median_ratio=float(x.median()),mean_ratio=float(x.mean()),min_ratio=float(x.min()),max_ratio=float(x.max())))
  pd.DataFrame(r).to_csv(OUT/'serial_ratios.csv',index=False)
  gate['median_serial_ratio']=float((ps[PRIMARY]/ps.fast_v10).median());gate['serial_gate']=gate['median_serial_ratio']<=1.8
  gate['full_gate']=gate['confirmation_quality_gate']and gate['serial_gate']
  # Same-budget latency crossover: actual measured optimizer overhead, hypothetical extra objective latency, no fake sleeps.
  slow=ps[PRIMARY]-ps.fast_v10
  gate['extra_objective_seconds_per_call_to_meet_1_8x_median_pair_threshold']=float(np.median(np.maximum((ps[PRIMARY]-1.8*ps.fast_v10)/(.8*1024),0.)))
 if (R/'results/original/raw.csv').exists():
  o=pd.read_csv(R/'results/original/raw.csv');o.groupby('algorithm').agg(runs=('seed','size'),auc=('auc','mean'),final_gap=('final_gap','mean'),hits=('hit','sum')).to_csv(OUT/'original_summary.csv');o.groupby(['task','algorithm']).mean(numeric_only=True).to_csv(OUT/'original_per_task.csv')
 if (R/'results/stress/raw.csv').exists():
  sd=pd.read_csv(R/'results/stress/raw.csv');rows=[];dest=R/'results/stress_reference';dest.mkdir(exist_ok=True)
  for task in sd.task.unique():
   rr=sd[sd.task==task];parts=[]
   for q in rr.to_dict('records'):
    z=np.load(R/f"results/stress/{task}__{q['algorithm']}__{q['seed']}.npz");parts.append(z['F'])
   ref=nd2(np.concatenate(parts));np.savez_compressed(dest/(task+'.npz'),F=ref)
   for q in rr.to_dict('records'):
    z=np.load(R/f"results/stress/{task}__{q['algorithm']}__{q['seed']}.npz");m=score_trace(z['F'],z['output_F'],ref,int(q['budget']));m.pop('trace');rows.append({**q,**m,'reference_kind':'pooled_observations_NOT_exact'})
  sr=pd.DataFrame(rows);sr.to_csv(OUT/'stress_scored.csv',index=False);sr.groupby('algorithm').agg(runs=('seed','size'),auc=('auc','mean'),final_gap=('final_gap','mean'),igd=('igd','mean')).to_csv(OUT/'stress_summary.csv');sr.groupby(['task','algorithm']).mean(numeric_only=True).to_csv(OUT/'stress_per_task.csv')
 (OUT/'GATES.json').write_text(json.dumps(gate,indent=2));print(mean.to_string());print(json.dumps(gate,indent=2));print(pd.DataFrame(tests).to_string(index=False));print('TOTAL',len(allrows),allrows.fe.sum())
if __name__=='__main__':main()
