"""Current-turn orchestration; no service or future/background delivery."""
import subprocess,time,json,os
from pathlib import Path
R=Path(__file__).resolve().parent
p=R/'results/confirm/RUN_METADATA.json'
while not p.exists():time.sleep(2)
d=json.loads(p.read_text())
if d['errors'] or d['complete']!=d['planned']:raise RuntimeError('Primary confirmation incomplete')
commands=[
 ['original','--workers','4','--algs','fast_v10,nsga2_typed,no_uncertainty_linear,guarded_linear,nsga2_guarded'],
 ['stress','--workers','4','--algs','fast_v10,nsga2_typed,no_uncertainty_linear,nsga2_guarded'],
 ['serial','--workers','1','--algs','fast_v10,nsga2_typed,no_uncertainty_linear,guarded_linear,nsga2_guarded'],
]
for cmd in commands:
 with open(R/f'results/{cmd[0]}.log','w')as f:
  subprocess.run(['python',str(R/'run_experiments.py')]+cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT,check=True,env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
(R/'results/FOLLOWUPS_COMPLETE.json').write_text(json.dumps({'complete':True}))
