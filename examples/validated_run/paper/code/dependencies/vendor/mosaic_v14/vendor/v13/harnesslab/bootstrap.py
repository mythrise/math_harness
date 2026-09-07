from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/'vendor'
if str(VENDOR) not in sys.path:sys.path.insert(0,str(VENDOR))
from src.bootstrap import core,EvaluationLedger,ProblemContract,AuditedRun
from src.fast_v10 import run_fast_v10
from src.problems import make_problem as old_make_problem
from mosaic.typed_baseline import run_typed_nsga2_unique
