"""Independent file/trajectory audit. No optimization or extra objective calls."""
from pathlib import Path
import json,gzip,hashlib,sys
import numpy as np,pandas as pd
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R))
from harnesslab.problems import make_problem
from harnesslab.model import features
from sklearn.linear_model import Ridge

def main():
 out=R/'results/analysis';out.mkdir(exist_ok=True)
 sources=json.loads((R/'protocol/SELECTION_BEFORE_CONFIRM.json').read_text())['files'];hashchecks={p:hashlib.sha256((R/p).read_bytes()).hexdigest()==h for p,h in sources.items()};assert all(hashchecks.values())
 specs={s['id']:s for s in json.loads((R/'protocol/instances.json').read_text())}
 for g in [1,2,3]:specs.setdefault(f'rgv_g{g}',dict(id=f'rgv_g{g}',kind='rgv',group=g,partition='original'))
 counts={};rows=[];init={};checked=0;prediction_rows=0;fallbacks=0;gates=[];parity=[];modelreplay=[]
 for stage in ['dev','dev2','dev3','confirm','original','stress','serial','serial_contended']:
  source=R/f'results/{stage}/raw.csv'
  if not source.exists():continue
  d=pd.read_csv(source);assert len(json.loads((R/f'results/{stage}/ERRORS.json').read_text()))==0
  for row in d.to_dict('records'):
   stem=f"{row['task']}__{row['algorithm']}__{row['seed']}";p=R/f'results/{stage}/{stem}.npz';z=np.load(p);X,F=z['X'],z['F'];B=int(row['budget'])
   assert len(X)==len(F)==B==row['fe']==row['physical_calls'];assert np.isfinite(X).all()and np.isfinite(F).all();assert ((X>=0)&(X<=1)).all()
   for f in z['output_F']:assert np.any(np.all(F==f,axis=1))
   k=(stage,row['task'],row['seed']);h=hashlib.sha256(X[:32].tobytes()).hexdigest()
   if k in init:assert init[k]==h
   else:init[k]=h
   with gzip.open(R/f'results/{stage}/{stem}.log.json.gz','rt')as f:logs=json.load(f)
   fs=logs.get('forecasts',[])
   for rec in fs:
    pred=rec.get('prediction')
    if pred is not None:
     fe=int(rec['fe']);train=rec.get('train_fe')
     if train is None:
      versions={int(v['version']):int(v['fe'])for v in logs.get('model_fits',[])};train=versions[int(rec['model_version'])]
     assert train<fe<=B
     if 'actual'in rec:np.testing.assert_array_equal(rec['actual'],F[fe-1])
     prediction_rows+=1
   reason_counts={key:sum(q.get('reason')==key for q in fs)for key in ['audit_fallback','baseline_exploration','residual','base_wins','nonfinite_prediction']}
   fallback_count=reason_counts['audit_fallback'];fallbacks+=fallback_count
   gates.append(dict(stage=stage,task=row['task'],algorithm=row['algorithm'],seed=row['seed'],predicted_evaluations=len(fs),overrides=logs.get('overrides',0),model_fits=len(logs.get('model_fits',[])),extra_proposals=logs.get('extra_pure_proposals',logs.get('pure_proposals',0)),**reason_counts))
   checked+=1
   # Rebuild the stored model from ONLY the prefix it claims to use.
   if stage=='confirm'and row['algorithm']=='no_uncertainty_linear'and row['seed']==13501:
    codec=make_problem(specs[row['task']]).codec;low=F[:32].min(0);scale=np.maximum(np.ptp(F[:32],axis=0),1e-9)
    for rec in [fs[0],fs[len(fs)//2],fs[-1]]:
     t=int(rec['train_fe']);fe=int(rec['fe']);model=Ridge(alpha=.1).fit(features(X[:t],codec),(F[:t]-low)/scale);pred=model.predict(features(X[fe-1],codec))[0];err=float(np.max(np.abs(pred-rec['prediction'])));assert err<1e-10;modelreplay.append(dict(task=row['task'],seed=row['seed'],fe=fe,train_fe=t,max_error=err))
  counts[stage]=dict(runs=len(d),FE=int(d.fe.sum()))
 # Persisted off-switch and cache equivalence, not merely final metric equality.
 for task in [s['id']for s in specs.values()if s['partition']=='development']:
  for seed in [13101,13102,13103,13104]:
   for st1,a,st2,b in [('dev2','fast_v10','dev2','residual_off'),('dev2','residual_linear','dev3','guarded_linear')]:
    p1=R/f'results/{st1}/{task}__{a}__{seed}.npz';p2=R/f'results/{st2}/{task}__{b}__{seed}.npz'
    if not(p1.exists()and p2.exists()):continue
    z1,z2=np.load(p1),np.load(p2);ok=all(np.array_equal(z1[k],z2[k])for k in ['X','F','output_X','output_F']);assert ok;parity.append(dict(task=task,seed=seed,base=a,candidate=b,full_equal=ok))
 refs=json.loads((R/'results/references/ACCOUNTING.json').read_text())+json.loads((R/'results/references/ADDITIONAL_ORIGINAL_ACCOUNTING.json').read_text())
 warm=[json.loads(p.read_text())for p in (R/'results/warmups').glob('*.json')]
 report=dict(full_traces_checked=checked,counts=counts,registered_runs=sum(q['runs']for q in counts.values()),registered_search_FE=sum(q['FE']for q in counts.values()),source_freeze_matches=all(hashchecks.values()),source_hashes=hashchecks,initialization_groups_compared=len(init),forecast_records_checked=prediction_rows,prefix_model_replay_checks=len(modelreplay),max_replay_error=max([q['max_error']for q in modelreplay],default=0),full_parity_pairs=len(parity),all_full_parity=True,finite_reference_instances=len(refs),finite_reference_FE=sum(q['fe']for q in refs),warmup_process_records=len(warm),discarded_warmup_calls=sum(q['physical_calls']for entries in warm for q in entries),notes=['Formal matrix counts exclude debugging smoke runs, cProfile, unit tests, and prior-round data.','Search never uses reference files; this is source/flow isolation, not a hostile-code sandbox.','Forecast audit is temporal and numerical, not a calibrated coverage or no-regret theorem.'])
 pd.DataFrame(gates).to_csv(out/'prediction_audit_per_run.csv',index=False);pd.DataFrame(parity).to_csv(out/'full_trace_parity.csv',index=False);pd.DataFrame(modelreplay).to_csv(out/'independent_model_replay.csv',index=False)
 (out/'FULL_AUDIT.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items()if k!='source_hashes'},indent=2))
if __name__=='__main__':main()
