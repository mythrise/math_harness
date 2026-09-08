---
name: algorithm-library-upgrade
description: Use the checked ten-family math modeling library, evidence-triggered residual candidates, and independently gated algorithm upgrades.
---

# Algorithm library v0.3

Read `docs/algorithm-upgrade/RESEARCH_AND_DESIGN_CN.md` and `API_CN.md` before implementation.
`cumcm_harness.algorithm_library.FAMILIES` is the exact supported family map.
`route_methods` is retrieval, NOT mathematical admission; use a structured problem contract
and check the assumptions before choosing an entrypoint.

Classical algorithms and new wrappers are not novel foundation models. External model names
in `external_candidates.json` are NOT_RUN research candidates. Never substitute an unrelated
small model or fixture under a frontier name. Do not fetch weights/install code or accept licenses
without the normal operator/resource permission flow. No model credentials enter trials.

Keep MOSAIC vendor code and inactive random trajectories unchanged. Its original representation,
determinism and constraint restrictions still apply. Verification FE is counted separately from
search FE, and cannot be hidden as free objective search.

Regression residual default is OFF because this upgrade's recorded tests found regressions.
Use crossfit residual only explicitly as a candidate. IID internal folds cannot be used on group/time
samples. Calibrate only on untouched data, after model selection; no distribution-shift coverage claim.
LP/MILP bounds from a fixed neighborhood are not global bounds. Exact shortest path and TSP are
different tasks. TOPSIS anchors and weights are predeclared. ODE tolerance refinement is diagnostic,
not a rigorous error enclosure. QMC uncertainty uses independent replicate means.

For a new mechanism: freeze protocol → baseline → one-variable candidate/ablation → negative tests →
independent held-out family trials → evidence-bound review → limited promotion. Use all original
budget dimensions; record training and inference cost, not just objective calls. Preserve failures.
`algpromotion` takes trusted controller-owned records; model-written booleans are not evidence.
Continue using the existing Exa adversary, GPT/Claude review board, sandbox, and contest human gates.
Do not waive a semantic FAIL merely because the new method sounds more advanced.
