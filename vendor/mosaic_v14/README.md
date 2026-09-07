# MOSAIC v14 Efficiency Lab

A real continuation of the attached MOSAIC v13 H0 source. The first branch caches
pure structural work without changing RNG calls, paid X/F trajectories, Ridge
training or acquisition semantics. Research branches change candidate generation
or refit intervals and are explicitly separated from that engineering claim.

## Run

```bash
python -m pip install -r requirements.txt
python examples/demo.py --strategy fast_h0 --group 1 --budget 1024
python examples/demo.py --strategy incumbent --group 1 --budget 1024
python -m pytest -q tests
```

`incumbent_cached` applies the same codec acceleration to the cheap incumbent.
`local24` and `refit32` are research options. No unsupported type is silently
rounded or penalized. The default Python dispatcher keeps the prior incumbent;
the report explains which explicitly chosen strategy passed which evidence gate.

```python
from mosaic_solve import solve, ProblemContract
from mosaic.rgv import RGVProblem
p = RGVProblem(group=2)
r = solve(p, seed=74501, budget=1024, strategy="fast_h0",
          contract=ProblemContract(representation="ordered_subset",
                                   codec=p.codec,
                                   constraints="feasible_decoder"))
print(r.result.F, r.ledger.spent)
```

## Evidence

- `vendor/v13`: unchanged actually uploaded source and summaries.
- `protocol/PLAN.json`: pre-development design and thresholds.
- `protocol/SELECTION_BEFORE_CONFIRM.json`: quality candidate and separately
  declared cost-first diagnostic candidate, chosen before new instance results.
- `protocol/*_source_snapshot`: exact development code snapshots, because the
  second development round introduces two-parent proposal experiments.
- `results/<stage>/*.npz`: full evaluated X/F and returned X/F.
- `results/<stage>/*.log.json.gz`: forecast, model and proposal diagnostics.
- `results/analysis`: aggregate results, task-level tests, hashes and FE audit.
- `results/serial`: randomized-order serial cost tests, separate from concurrent
  quality runs. Profiles are diagnostic, not speed measurements.

## Reproduce

The runners skip existing complete run IDs. Recompute in a copy by removing the
corresponding result stage. Do not remove source freeze manifests or change the
selected configuration based on confirmation scores.

```bash
python run_experiments.py confirm --workers 3 \
  --algs fast_v10,nsga2_typed,h0,fast_h0,local24,refit32,local24_random,nsga_local24
python supplementary.py
python analyze_results.py all
python analyze_supplementary.py all
```

Development stage source snapshots are archived; to reproduce those stages use
the matching snapshot files in a copy, not the later candidate files. Search
parameters, seeds and budgets are in the corresponding freeze JSON.

## Boundaries

Only deterministic bi-objective ordered subsets were upgraded. The RGV task is a
restricted policy model of 2018 CUMCM B, inherited unchanged. Tours and due-date
jobs are synthetic. n=8 references are complete finite numerical enumerations;
n=12/16 pressure references are pooled observations, NOT exact fronts. There is
no claim of universal/official SOTA, new neural MoE training, zero-regret
fallback, or cache equivalence on every future hardware/library environment.

Pure semantic caches never contain objective values. Compilation warmup,
reference evaluation and search vectors are separately counted. Profiling,
smoke tests and unit tests are not included in registered benchmark run counts.

Full reference files and per-stage ACCOUNTING are shipped. The low-level `reference` runner skips existing files; do not rerun it over an existing populated reference directory because it records only work newly performed by that invocation. Use a fresh results/references directory when rebuilding references, and preserve original accounting separately.
