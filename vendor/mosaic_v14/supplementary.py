"""Extra matched-cap/cache ablations, frozen before they run; no mainline reselection."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
import json,time
from pathlib import Path
from dataclasses import replace,asdict
import numpy as np,pandas as pd
from concurrent.futures import ProcessPoolExecutor,as_completed
from run_experiments import ROOT,run_one,warm,freeze
from mosaic14.variants import CONFIGS
CONFIGS['local7']=replace(CONFIGS['local24'],local_cap=7)
def initialize():
 CONFIGS['local7']=replace(CONFIGS['local24'],local_cap=7)
 warm()
def main():
 specs=json.loads((ROOT/'protocol/instances.json').read_text());tasks=[s for s in specs if s['partition']=='holdout']
 seeds=list(range(74501,74507));algs=['local7']
 freeze('cap_ablation',dict(algorithms=algs,seeds=seeds,budget=1024,tasks=[s['id']for s in tasks],configs={a:asdict(CONFIGS[a]) for a in algs},script_sha256=__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest(),designation='Supplementary matched-cap ablation; cannot change selected confirmation candidate. Compare to same-seed fast_h0 and local24 confirmation traces.'))
 jobs=[(s,a,seed,1024,'cap_ablation')for s in tasks for a in algs for seed in seeds];rows=[];t=time.perf_counter()
 with ProcessPoolExecutor(max_workers=1,initializer=initialize) as pool:
  for i,f in enumerate(as_completed([pool.submit(run_one,j) for j in jobs]),1):
   rows.append(f.result())
   if i%12==0:print(i,len(jobs),time.perf_counter()-t,flush=True)
 d=ROOT/'results/cap_ablation';errors=[r for r in rows if 'error'in r];(d/'ERRORS.json').write_text(json.dumps(errors));df=pd.DataFrame([{k:v for k,v in r.items()if k!='trace'}for r in rows if 'error'not in r]);df.to_csv(d/'raw.csv',index=False)
 (d/'RUN_METADATA.json').write_text(json.dumps(dict(complete=len(df),planned=len(jobs),fe=int(df.fe.sum()),errors=len(errors)),indent=2))
 print(df.groupby('algorithm')[['auc','final_gap','seconds']].mean().to_string())
if __name__=='__main__':main()
