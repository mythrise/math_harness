"""Execute a bounded fixed-layout optical precheck in Docker."""
from pathlib import Path
from cumcm_harness.sandbox import Executor,Limits
from cumcm_harness.common import write_json
root=Path(__file__).resolve().parents[1]
base=root/'reports/heliostat-intake'
r=Executor().execute(base/'verifier-r1-probe-code','probe.py',root/'inputs/heliostat-2023/data',
    base/'verifier-r1-probe/out',[],Limits(seconds=300,cpu_threads=1,memory_mb=1024),logdir=base/'verifier-r1-probe/logs')
write_json(base/'verifier-r1-probe/executor-receipt.json',r)
print((base/'verifier-r1-probe/out/diagnosis.json').read_text())
