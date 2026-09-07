# MOSAIC v14: execution cache and bounded semantic-neighborhood experiments

## Scope
Frozen v13 H0 is a deterministic bi-objective ordered-subset optimizer. This round
changes execution cost first, then studies proposal quality. Continuous v9/v10,
general constraints, noise, and many-objective paths are not upgraded.

## Engineering invariant
For fixed problem, initial RNG seed, budget, and numeric environment, compare the
entire paid evaluation stream X[0:B], F[0:B] AND returned X/F. Equality of a scalar
metric is insufficient. Pure caches do not hold objective values. Evaluator and
Ridge fits are untouched; mathematical HVI operations retain their order.

1. PolicyCodec stores raw-encoding -> policy tuples, and policy -> canonical
   encoding. Mutations perform the inherited sequence of RNG calls on Python
   lists. Encoding outputs are copies, immutable storage cannot be mutated by a
   caller. Candidate and main search share this cache.
2. Semantic features psi(policy) are cached independently of model versions.
   Retraining still sees exactly the same feature rows and true labels.
3. HVI strips are cached by the complete normalized observed front and reference
   point. A changed archive invalidates the cache. Predictions are NOT cached
   across a model update.

## Prediction and acquisition
F is minimized, normalized using the first 32 paid samples. Ridge solves
||ZW+1c^T-Y||_F^2 + 0.1||W||_F^2. Warmup is 64 FE; refit baseline 64 FE.
Chronological validation and forecast audit retain all v13 thresholds.
Each actual model-chosen proposal still costs one true FE and is committed only
with its observed F. No predicted point enters the Pareto archive.

For sorted nondominated points (a_j,b_j), use strips with left l_j, right u_j,
height h_j. The pointwise predicted HVI is
sum_j max(u_j-max(l_j,mu_1),0) max(h_j-mu_2,0).
The same strips can be reused until the true front/reference changes. This is
mean HVI, NOT EHVI and NOT a calibrated confidence bound.

## Bounded-neighborhood branch
Current parent policy p has legal swap, relocate, add/remove neighborhoods.
Build a deterministic list of unique (policy,first-producer-id), excluding p;
cache it by p. At every use, filter against current paid-visited set V and x0.
Sample at most K=24 policies without replacement, keeping x0 first. Score them
with the same fitted predictor and HVI. If no positive score exists, use x0.
A local candidate has the same parent as the inherited proposal. Descriptor
coverage is not an extra objective. This is a surrogate-assisted local candidate
pool, NOT a newly invented swap/PLS operator.

Local7 (supplementary ablation) holds the maximum pool size equal to H0's 8 total
candidates; Local24 vs Local7 isolates the candidate-cap change. Local24 without
neighborhood cache is a deterministic execution ablation, not a quality change.

## Rejected / diagnostic branches
Bounded24: at most 24 random pure attempts rather than seven slots * 12 attempts.
Pool4: fewer random candidates.
Local48/all: wider surrogate search, possibly exposing model optimism.
Refit32: identical H0 proposal policy but shorter retraining interval.
Dual-parent: union of two actual observed parent neighborhoods; selected child
records the true source parent before reward/visits. No fake lineage attribution.
The dual/refit development candidate improved early AUC but violated the final
gap guard, and was not promoted. The selected quality candidate Ref it32 missed
its 3% development threshold; confirmation remains diagnostic.

## Experimental boundaries
Development reuses four known instances. Confirmation has four new parameter
instances for each of RGV, discounted tours, and due-date jobs, 12 seeds each,
1024 FE. These are 12 parameter instances in three known model families, not
12 new real contest problems. Only RGV derives from an actual contest; it is the
restricted no-fault cyclic single-process model, not the complete official task.

Independent finite numerical references are computed separately, never accessed
by an optimizer. Their simulator-vector count is reported separately, including
when bypassing the search ledger for vectorized certification. Search always
uses the unchanged EvaluationLedger with physical vector counts.

RNGs are separated for the search and surrogate candidate pool. Rejection after
an earlier intervention cannot restore the counterfactual no-intervention run.

## Sources and what was not implemented
- Uploaded v13 METHODS_CN.md, REPORT_CN.md, H0 source: inherited model, objective,
  operator and accounting semantics.
- BoTorch official multiobjective tutorial: efficient acquisition using cached
  box decompositions. Our simple deterministic 2D cache is not qNEHVI.
  https://botorch.org/docs/v0.17.2/tutorials/multi_objective_bo
- Scikit-learn computational-performance documentation: profile feature extraction,
  representation and per-call overhead; batching is not automatically a semantic
  no-op because numerical accumulation can differ.
  https://scikit-learn.org/stable/computing/computational_performance.html
- Yang et al., Efficient Computation of Expected Hypervolume Improvement Using
  Box Decomposition Algorithms (2019): related efficient geometric decomposition,
  not a claim that we implemented their entire EHVI method.
  https://arxiv.org/abs/1904.12672

Exa returned 5 discovery items this round, followed by primary-source checks.
We did not train an LLM, reproduce a new neural agent paper, or run CEC 2025.
