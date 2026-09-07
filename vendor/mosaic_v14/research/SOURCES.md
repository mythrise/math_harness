# Sources reviewed for the v14 iteration

Research date: 2026-09-05. This is a code-first performance iteration, not a claim
that a newly released neural architecture was reproduced.

## Authoritative project input
`vendor/v13` is extracted from the actually attached
MOSAIC_v13_SOURCE_AND_SUMMARY.zip (536,119 bytes), SHA256:
`4651eacda251a40981d77fd1fc66bbbd03e8ed40f3e9bc112ba0dc3937f7a360`.
The previous report defines H0, its measured quality gains and failed 1.8x CPU
threshold. All inherited source hashes are recorded independently.

## External sources
1. BoTorch official tutorial, Multi-objective optimization with qEHVI, qNEHVI,
   and qNParEGO, versioned 0.17.2 tutorial:
   https://botorch.org/docs/v0.17.2/tutorials/multi_objective_bo
   Relevant idea: caching geometric decomposition during acquisition. Not a
   reproduction of probabilistic qNEHVI: our model uses deterministic mean HVI.
2. Scikit-learn official computational performance documentation:
   https://scikit-learn.org/stable/computing/computational_performance.html
   Relevant dimensions: feature representation/extraction, batching and per-call
   validation overhead. We retain numerical checks and test actual trace parity;
   no unconditional assumption that refactoring preserves optimization decisions.
3. Yang, Emmerich, Deutz, Bäck, Efficient Computation of Expected Hypervolume
   Improvement Using Box Decomposition Algorithms, 2019:
   https://arxiv.org/abs/1904.12672
   Prior geometric decomposition work. We do not claim a new EHVI algorithm or
   transfer its complexity theorem to a different estimator.
4. Watanabe, Approximation of Box Decomposition Algorithm for Fast
   Hypervolume-Based Multi-Objective Optimization, submitted 2025-12-05:
   https://arxiv.org/abs/2512.05825
   A warning about higher-dimensional decomposition costs; not implemented here.

Exa discovery query: "category:research paper efficient batched hypervolume
improvement cached box decomposition candidate preselection surrogate multi
objective optimization computational cost", numResults=5. Discovery snippets
were checked against official documentation / author papers using web search.
No full PDF analysis was used; only HTML/abstract/documentation contents.

## Originality boundary
Swap, relocate, insertion/removal, Ridge, semantic feature caching and mean-HVI
preselection all have prior art. New work here is the specific tested execution
refactor and the controlled local-candidate experiments, not invention of these
components. No official CEC or universal SOTA claim.
