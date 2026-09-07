"""Execute exact before/after evaluator regressions inside the Docker executor."""
import argparse
import json
import shutil
from pathlib import Path
from cumcm_harness.controller import DEFAULT_CONFIG
from cumcm_harness.store import Store
from cumcm_harness.sandbox import Executor
from cumcm_harness.verifier_preflight import run_preflight
from cumcm_harness.common import write_json

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('version',choices=['before','after']);a=p.parse_args()
source=root/'repairs/heliostat-evaluator-fable-v1'
files=[{'path':p.name,'content':p.read_text()} for p in sorted(source.glob('*.py'))]
if a.version=='before':
    original=root/'reports/heliostat-intake/verifier-r1-probe-code/evaluate.py'
    for f in files:
        if f['path']=='evaluate.py':f['content']=original.read_text()
bundle={'files':files,'notes':['Repair regression only; not a complete scientific acceptance'], 'algorithm_usage':[]}
base=root/'reports/heliostat-evaluator-repair'/a.version
if base.exists():raise SystemExit('Evidence directory exists; do not rerun or overwrite: '+str(base))
shutil.copytree(root/'inputs/heliostat-2023/data',base/'evaluation_inputs/development/public')
report=run_preflight(base,Store(base),Executor(),{**DEFAULT_CONFIG,'trial_timeout':120},bundle)
write_json(base/'result.json',report)
print(json.dumps(report,ensure_ascii=False,indent=2))
