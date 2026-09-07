"""Run fixed standalone analytic diagnostics through the Docker executor."""
from pathlib import Path
from cumcm_harness.common import write_json
from cumcm_harness.sandbox import Executor, Limits

root = Path(__file__).resolve().parents[1]
base = root / 'reports/heliostat-intake'
receipt = Executor().execute(base/'physics-check-code', 'check_math.py',
    root/'inputs/heliostat-2023/data', base/'math-diagnostics/out', [],
    Limits(seconds=120, cpu_threads=1, memory_mb=1024), logdir=base/'math-diagnostics/logs')
write_json(base/'math-diagnostics/executor-receipt.json', receipt)
print((base/'math-diagnostics/out/math_diagnostics.json').read_text())
