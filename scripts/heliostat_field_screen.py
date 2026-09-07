"""Execute a bounded fixed-layout optical precheck in Docker."""
from pathlib import Path
from cumcm_harness.sandbox import Executor,Limits
from cumcm_harness.common import write_json
root=Path(__file__).resolve().parents[1]
base=root/'reports/heliostat-intake'
r=Executor().execute(base/'field-screen-code','screen.py',root/'inputs/heliostat-2023/data',
    base/'field-screen/out',[],Limits(seconds=300,cpu_threads=1,memory_mb=1024),logdir=base/'field-screen/logs')
write_json(base/'field-screen/executor-receipt.json',r)
print((base/'field-screen/out/summary.json').read_text())
