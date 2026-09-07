import time,subprocess,json,shutil,os
from pathlib import Path
R=Path(__file__).resolve().parent
while not (R/'results/FOLLOWUPS_COMPLETE.json').exists():time.sleep(1)
# First serial batch overlapped the full test invocation for about 8 seconds.
# Preserve it, rerun ALL identical pairs without other experiment/test jobs.
if not (R/'results/serial_contended').exists():
 shutil.move(str(R/'results/serial'),str(R/'results/serial_contended'))
 shutil.copy2(R/'results/serial.log',R/'results/serial_contended.log')
with open(R/'results/serial_clean.log','w')as f:
 subprocess.run(['python',str(R/'run_experiments.py'),'serial','--workers','1','--algs','fast_v10,nsga2_typed,no_uncertainty_linear,guarded_linear,nsga2_guarded'],cwd=R,stdout=f,stderr=subprocess.STDOUT,check=True,env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
(R/'results/CLEAN_TIMING_COMPLETE.json').write_text(json.dumps({'complete':True,'excluded_from_primary_timing':'serial_contended preserved: test job overlapped first batch'}))
