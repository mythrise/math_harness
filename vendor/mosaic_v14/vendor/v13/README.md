# MOSAIC v13 Harness Lab

Research beyond MoE: bounded search missions, learned candidate preselection and an audited residual wrapper around frozen Fast-v10.

**Default remains Fast-v10.** The new `audited_infill` mode is opt-in. See `REPORT_CN.md`, `STATUS.json`, and `results/analysis/GATES.json` for the measured quality/cost decision. The package does not claim official or universal SOTA, and does not invoke or train an LLM.

## Install / demo

```bash
python -m pip install -r requirements.txt
python -m pytest -q tests vendor/baseline_v10/tests
python examples/demo.py --group 1 --budget 1024 --strategy incumbent
python examples/demo.py --group 1 --budget 1024 --strategy audited_infill
```

```python
from harnesslab.api import solve, ProblemContract
from mosaic.rgv import RGVProblem

p = RGVProblem(group=1)
run = solve(p, seed=13801, budget=1024, population=32,
            contract=ProblemContract('ordered_subset', p.codec, 'feasible_decoder'),
            strategy='audited_infill')
print(run.result.F)
print(run.ledger.spent)
```

The new mode requires deterministic **two-objective ordered subsets** with a caller-supplied feasible codec. General constraints, noise, continuous inputs, and >2 objectives are explicitly rejected for this mode. Default continuous fallback still delegates to the unmodified v10/v9 path, with no new continuous-performance claim.

## Files

- `vendor/`: selected, unmodified source files from uploaded v11/v10 packages.
- `harnesslab/engine.py`: first development family (bounded missions and batch model screening).
- `harnesslab/residual.py`, `residual_engine.py`: second family (original-candidate-preserving wrapper).
- `harnesslab/efficient.py`, `efficient_engine.py`: same-search codec caching and linear prediction path.
- `harnesslab/nsga_residual.py`: matched NSGA-II wrapper control.
- `harnesslab/api.py`: safe default and explicit opt-in entry point.
- `protocol/`: initial instance plan, each stage's freeze, pre-confirmation selection, deviations.
- `results/<stage>/`: per-run JSON, full real X/F NPZ, gzipped model/forecast logs.
- `results/analysis/`: all tables, instance-level tests, audit and promotion decisions.
- `research/SOURCES.md`: primary sources, venue status, what was and was not reproduced.

## Reproduce the frozen matrix

The runner uses persisted run IDs: existing complete run JSON files are reused. To recompute, use a separate copy of this package and remove the relevant `results/<stage>` directory there. Do not remove the original research evidence. Stage freeze files verify search code and matrix; they intentionally reject changes.

```bash
# Separate finite-reference evaluation, never fed to the optimizer:
python run_experiments.py reference

python run_experiments.py dev --workers 4
python run_experiments.py dev2 --workers 4
python run_experiments.py dev3 --workers 4 --algs fast_v10,nsga2_typed,guarded_linear,unguarded_linear,random_residual,scalar_linear,raw_linear,no_uncertainty_linear,nsga2_guarded

python run_experiments.py confirm --workers 4 --algs fast_v10,nsga2_typed,no_uncertainty_linear,guarded_linear,unguarded_linear,random_residual,scalar_linear,raw_linear,nsga2_guarded
python run_experiments.py original --workers 4 --algs fast_v10,nsga2_typed,no_uncertainty_linear,guarded_linear,nsga2_guarded
python run_experiments.py stress --workers 4 --algs fast_v10,nsga2_typed,no_uncertainty_linear,nsga2_guarded

# Run alone: no other experiment or test jobs in parallel.
python run_experiments.py serial --workers 1 --algs fast_v10,nsga2_typed,no_uncertainty_linear,guarded_linear,nsga2_guarded
python analyze_results.py
python audit_results.py
```

The bundled original-group reference files include groups 2/3, additionally certified outside search; their accounting is separate. Stress references are pooled observed fronts, **not exact fronts**. Frozen references and scoring use numerical tolerances, not claims of exact real-number arithmetic.

## Timing and budget

Real evaluated design vectors, including initialization, count against FE. Training, prediction, pure proposals, and encoding caches never call the true objective, but their CPU time is included in per-run search time. JIT warmup is recorded separately and discarded. The first serial batch overlapped a test invocation; it is preserved as `serial_contended`, and an entire clean repeated batch is used for primary timing. No fastest-run selection.

Code and artifacts are supplied for reproducibility and independent scrutiny. Basic SAEA, ridge regression, hypervolume acquisition, structural operators, archives and caching are established techniques; the engineering integration and tested restrictions are not by themselves a universal-optimality theorem.
