from __future__ import annotations

"""MOSAIC-ST research branch.

This module keeps the frozen MOSAIC-MOEA v4 evaluator, scalarization and exact
replacement semantics, and adds three isolated mechanisms:

1. Exact Coverage Memory (ECM): a bounded bank of *actually evaluated* designs,
   indexed by reference direction.  It is separate from the Pareto archive so
   potentially useful stepping stones are not erased merely because they are
   temporarily dominated.
2. Archive-Reuse Transport Expert (ART, operator 5): a failure-mode specialist
   activated only when reference-cell coverage is distressed.
3. Secant-Repulsive Transport (SRT, optional upgrade of operator 2): a local
   ridge secant model maps a Smooth-Tchebycheff descent/repulsion direction in
   objective space back to a trust-region decision-space residual.  The residual
   is bypassed when its cross-validated local fit is unreliable.
4. Role-Gated Coordinate Basin Tunneling (RCBT, operator 6): when reference
   coverage is healthy but scalar progress stalls, low-discrepancy one-coordinate
   probes are applied only to variables inferred to control convergence rather
   than Pareto direction. Successful coordinate values are composed into later
   probes, but every candidate still requires exact evaluation and STCH acceptance.

The default callable exposes ablations so every mechanism can be evaluated under
identical seeds and function-evaluation budgets.  No surrogate prediction is
allowed to update the population or archive without exact objective evaluation.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple
import math
import numpy as np

import moo_core as core

Array = np.ndarray


def _associate_fixed(F: Array, W: Array, ideal: Array, nadir: Array) -> Tuple[Array, Array]:
    """Reference association in one shared longitudinal normalization frame."""
    F = np.asarray(F, dtype=float)
    Y = np.maximum((F - ideal) / (nadir - ideal + 1e-12), 0.0)
    Yn = Y / (np.linalg.norm(Y, axis=1, keepdims=True) + 1e-12)
    Wn = W / (np.linalg.norm(W, axis=1, keepdims=True) + 1e-12)
    cos = np.clip(Yn @ Wn.T, -1.0, 1.0)
    assoc = np.argmax(cos, axis=1)
    angle = np.arccos(cos[np.arange(len(F)), assoc])
    return assoc.astype(int), angle


def _occupancy_entropy(assoc: Array, n_cells: int) -> Tuple[float, float, Array]:
    counts = np.bincount(np.asarray(assoc, dtype=int), minlength=n_cells)
    occupancy = float(np.count_nonzero(counts) / max(n_cells, 1))
    p = counts[counts > 0].astype(float)
    p /= max(p.sum(), 1.0)
    if n_cells <= 1 or len(p) == 0:
        entropy = 0.0
    else:
        entropy = float(-np.sum(p * np.log(p + 1e-15)) / np.log(n_cells))
    return occupancy, entropy, counts


@dataclass
class MemoryCandidate:
    x: Array
    f: Array
    born: int


class ExactCoverageMemory:
    """Bounded exact-evaluation memory with reference-cell-aware compaction.

    Pareto archives are intentionally selective in objective space.  This memory
    has a different role: preserve historically evaluated stepping stones that
    may be needed to reconstruct a missing reference region.  It never invents
    objective values and never bypasses the exact verifier for newly generated
    offspring.
    """

    def __init__(self, capacity: int, per_cell: int = 3):
        self.capacity = int(max(capacity, 8))
        self.per_cell = int(max(per_cell, 1))
        self.X = np.empty((0, 0), dtype=float)
        self.F = np.empty((0, 0), dtype=float)
        self.born = np.empty(0, dtype=int)

    def add(self, X: Array, F: Array, generation: int, W: Array, ideal: Array, nadir: Array) -> None:
        X = np.asarray(X, dtype=float)
        F = np.asarray(F, dtype=float)
        if X.ndim == 1:
            X = X[None, :]
        if F.ndim == 1:
            F = F[None, :]
        if self.X.size == 0:
            self.X = X.copy()
            self.F = F.copy()
            self.born = np.full(len(X), generation, dtype=int)
        else:
            self.X = np.vstack([self.X, X])
            self.F = np.vstack([self.F, F])
            self.born = np.r_[self.born, np.full(len(X), generation, dtype=int)]
        if len(self.F) > int(1.20 * self.capacity):
            self.compact(W, ideal, nadir)

    def compact(self, W: Array, ideal: Array, nadir: Array) -> None:
        if len(self.F) <= self.capacity:
            return
        assoc, _ = _associate_fixed(self.F, W, ideal, nadir)
        selected: List[int] = []
        mu = 0.02
        span_x = np.ptp(self.X, axis=0) + 1e-12
        for c in range(len(W)):
            idx = np.flatnonzero(assoc == c)
            if len(idx) == 0:
                continue
            Wi = np.repeat(W[c][None, :], len(idx), axis=0)
            scores = core._mosaic_scalar(self.F[idx], Wi, ideal, nadir, mu, theta=0.22, blend=0.0)
            order = idx[np.argsort(scores, kind="mergesort")]
            keep: List[int] = [int(order[0])]
            # Preserve a recent candidate and then decision-diverse candidates.
            recent = int(idx[np.argmax(self.born[idx])])
            if recent not in keep and len(keep) < self.per_cell:
                keep.append(recent)
            while len(keep) < min(self.per_cell, len(idx)):
                remaining = [int(j) for j in idx if int(j) not in keep]
                if not remaining:
                    break
                D = (self.X[remaining] - self.X[keep][:, None, :]).transpose(1, 0, 2)
                # min normalized decision distance to an already kept point
                d = np.linalg.norm(D / span_x[None, None, :], axis=2).min(axis=1)
                keep.append(remaining[int(np.argmax(d))])
            selected.extend(keep)
        # If per-cell retention is still too large, use objective-space maximin.
        selected = list(dict.fromkeys(selected))
        if len(selected) > self.capacity:
            local = core.select_indices_farthest(self.F[selected], self.capacity)
            selected = [selected[int(j)] for j in local]
        # If cells are sparse and capacity remains, retain recent evaluated points.
        if len(selected) < self.capacity:
            rest = [i for i in np.argsort(-self.born, kind="mergesort") if int(i) not in set(selected)]
            selected.extend([int(i) for i in rest[: self.capacity - len(selected)]])
        idx = np.asarray(selected[: self.capacity], dtype=int)
        self.X, self.F, self.born = self.X[idx], self.F[idx], self.born[idx]

    def candidates_for_cell(
        self, cell: int, W: Array, ideal: Array, nadir: Array, max_candidates: int = 6
    ) -> Array:
        if len(self.F) == 0:
            return np.empty(0, dtype=int)
        assoc, angle = _associate_fixed(self.F, W, ideal, nadir)
        exact = np.flatnonzero(assoc == int(cell))
        if len(exact) == 0:
            # Fallback to closest objective direction; this is still exact memory.
            return np.argsort(angle, kind="mergesort")[:max_candidates]
        Wi = np.repeat(W[int(cell)][None, :], len(exact), axis=0)
        score = core._mosaic_scalar(self.F[exact], Wi, ideal, nadir, 0.018, theta=0.25, blend=0.0)
        return exact[np.argsort(score, kind="mergesort")[:max_candidates]]

    def best_anchor_advantage(
        self, cell: int, current_F: Array, W: Array, ideal: Array, nadir: Array
    ) -> float:
        """Exact scalar advantage of the best memory anchor for one cell."""
        idx = self.candidates_for_cell(cell, W, ideal, nadir, max_candidates=3)
        if len(idx) == 0:
            return 0.0
        wc = W[int(cell)][None, :]
        mem = core._mosaic_scalar(
            self.F[idx], np.repeat(wc, len(idx), axis=0), ideal, nadir, 0.018,
            theta=0.25, blend=0.0
        ).min()
        cur = core._mosaic_scalar(
            current_F, np.repeat(wc, len(current_F), axis=0), ideal, nadir, 0.018,
            theta=0.25, blend=0.0
        ).min()
        return float((cur - mem) / (abs(cur) + 1e-12))

    def choose_anchor(
        self, cell: int, W: Array, ideal: Array, nadir: Array, rng: np.random.Generator
    ) -> Optional[Tuple[Array, Array]]:
        idx = self.candidates_for_cell(cell, W, ideal, nadir)
        if len(idx) == 0:
            return None
        # Mostly choose the best scalar candidate but retain slight diversity.
        j = int(idx[0] if len(idx) == 1 or rng.random() < 0.75 else rng.choice(idx[: min(3, len(idx))]))
        return self.X[j].copy(), self.F[j].copy()

    def reconstruct(
        self,
        X: Array,
        F: Array,
        W: Array,
        ideal: Array,
        nadir: Array,
        fraction: float,
        rng: np.random.Generator,
    ) -> Tuple[Array, Array, int, List[int]]:
        """Inject exact historical candidates into missing cells without new FEs."""
        if len(self.F) == 0:
            return X, F, 0, []
        assoc, _ = _associate_fixed(F, W, ideal, nadir)
        _, _, counts = _occupancy_entropy(assoc, len(W))
        missing = np.flatnonzero(counts == 0)
        if len(missing) == 0:
            return X, F, 0, []
        n_inject = min(max(1, int(math.ceil(fraction * len(X)))), len(missing))
        # Largest angular holes first: directions farthest from occupied directions.
        occupied = np.flatnonzero(counts > 0)
        Wn = W / (np.linalg.norm(W, axis=1, keepdims=True) + 1e-12)
        if len(occupied):
            proximity = np.max(Wn[missing] @ Wn[occupied].T, axis=1)
            targets = missing[np.argsort(proximity, kind="mergesort")[:n_inject]]
        else:
            targets = missing[:n_inject]

        # Victims: poor members of over-populated cells.  Do not force a target
        # into the same array index; the frozen MOEA/D update will reassociate it.
        redundancy = counts[assoc]
        ownW = W[assoc]
        scalar = core._mosaic_scalar(F, ownW, ideal, nadir, 0.012, theta=0.25, blend=0.0)
        s_norm = (scalar - scalar.min()) / (np.ptp(scalar) + 1e-12)
        victim_score = redundancy.astype(float) + s_norm
        victim_order = np.argsort(-victim_score, kind="mergesort")

        Xn, Fn = X.copy(), F.copy()
        used_mem: set[int] = set()
        used_victims: set[int] = set()
        restored_cells: List[int] = []
        for cell in targets:
            cand = self.candidates_for_cell(int(cell), W, ideal, nadir)
            cand = np.asarray([j for j in cand if int(j) not in used_mem], dtype=int)
            if len(cand) == 0:
                continue
            mem_j = int(cand[0])
            victim = next((int(j) for j in victim_order if int(j) not in used_victims), None)
            if victim is None:
                break
            # Skip exact duplicate designs.
            if np.any(np.all(np.isclose(Xn, self.X[mem_j], atol=1e-12, rtol=1e-10), axis=1)):
                used_mem.add(mem_j)
                continue
            Xn[victim], Fn[victim] = self.X[mem_j].copy(), self.F[mem_j].copy()
            used_mem.add(mem_j)
            used_victims.add(victim)
            restored_cells.append(int(cell))
        return Xn, Fn, len(restored_cells), restored_cells


class DiscountedPortfolio(core.ContextualThompsonPortfolio):
    """Optional non-stationary extension; kept as an ablation, not assumed useful."""

    def decay(self, gamma: float) -> None:
        g = float(np.clip(gamma, 0.90, 1.0))
        self.a = 1.0 + g * (self.a - 1.0)
        self.b = 1.0 + g * (self.b - 1.0)
        self.ga = 1.0 + g * (self.ga - 1.0)
        self.gb = 1.0 + g * (self.gb - 1.0)
        self.reward_sum *= g


def _secant_repulsive_delta(
    i: int,
    X: Array,
    F: Array,
    archive: core.Archive,
    W: Array,
    ideal: Array,
    nadir: Array,
    progress: float,
    problem: core.Problem,
    rng: np.random.Generator,
    use_repulsion: bool = True,
) -> Tuple[Array, float, float]:
    """Map an objective-space descent/repulsion vector through a local secant model.

    Returns (decision residual, reliability, normalized local fit error).  The
    caller must ignore the residual when reliability is low.
    """
    d, m = problem.n_var, problem.n_obj
    if len(archive.F) < max(8, m + 4):
        return np.zeros(d), 0.0, 1.0
    span_x = problem.xu - problem.xl + 1e-12
    span_f = nadir - ideal + 1e-12
    AF = np.maximum((archive.F - ideal) / span_f, 0.0)
    yi = np.maximum((F[i] - ideal) / span_f, 0.0)
    dist = np.linalg.norm(AF - yi, axis=1)
    k = min(max(10, 2 * m + 4), len(AF))
    idx = np.argsort(dist, kind="mergesort")[:k]
    DX = (archive.X[idx] - X[i]) / span_x
    DY = AF[idx] - yi
    # Remove nearly identical rows, which make local secants unidentifiable.
    keep = np.linalg.norm(DX, axis=1) > 1e-8
    DX, DY = DX[keep], DY[keep]
    if len(DX) < m + 3:
        return np.zeros(d), 0.0, 1.0
    ridge = 2e-3 + 2e-2 * (1.0 - progress)
    try:
        # Dual ridge fit: J^T = DX^T (DX DX^T + λI)^-1 DY.
        gram = DX @ DX.T + ridge * np.eye(len(DX))
        Jt = DX.T @ np.linalg.solve(gram, DY)
        J = Jt.T
    except np.linalg.LinAlgError:
        return np.zeros(d), 0.0, 1.0
    pred = DX @ Jt
    sse = float(np.sum((DY - pred) ** 2))
    sst = float(np.sum((DY - DY.mean(axis=0, keepdims=True)) ** 2)) + 1e-12
    fit_error = float(np.clip(sse / sst, 0.0, 2.0))
    # Condition reliability in objective row-space.
    try:
        cond = float(np.linalg.cond(J @ J.T + 1e-4 * np.eye(m)))
    except np.linalg.LinAlgError:
        cond = 1e12
    reliability = float(np.clip((1.0 - min(fit_error, 1.0)) * np.exp(-max(np.log10(cond) - 3.0, 0.0)), 0.0, 1.0))
    if reliability < 0.28:
        return np.zeros(d), reliability, fit_error

    # Smooth-Tchebycheff gradient in normalized objective coordinates.
    w = np.maximum(W[i], 1e-4)
    mu = 0.012 + 0.07 * (1.0 - progress) ** 2
    logits = w * yi / mu
    logits -= logits.max()
    soft = np.exp(logits)
    soft /= soft.sum() + 1e-12
    grad = soft * w
    dy = -grad / (np.linalg.norm(grad) + 1e-12)

    if use_repulsion:
        D = yi[None, :] - AF[idx]
        r = np.linalg.norm(D, axis=1)
        positive = r[r > 1e-8]
        h = float(np.median(positive)) if len(positive) else 0.15
        h = max(h, 0.05)
        weight = np.exp(-(r * r) / (2.0 * h * h))
        rep = np.sum(weight[:, None] * D, axis=0) / (weight.sum() + 1e-12)
        if np.linalg.norm(rep) > 1e-10:
            rep /= np.linalg.norm(rep)
            # Repulsion matters mainly in crowded regions and later in the run.
            beta = 0.12 + 0.22 * progress
            dy = dy + beta * rep
            dy /= np.linalg.norm(dy) + 1e-12

    try:
        dx = J.T @ np.linalg.solve(J @ J.T + (4e-3 + 1e-2 * (1.0 - progress)) * np.eye(m), dy)
    except np.linalg.LinAlgError:
        return np.zeros(d), 0.0, fit_error
    nrm = np.linalg.norm(dx)
    if not np.isfinite(nrm) or nrm < 1e-12:
        return np.zeros(d), 0.0, fit_error
    dx /= nrm
    trust = 0.10 * (1.0 - progress) + 0.018
    # Small random tangent jitter prevents deterministic secant lock-in.
    jitter = rng.normal(size=d)
    jitter -= dx * float(np.dot(jitter, dx))
    jitter /= np.linalg.norm(jitter) + 1e-12
    residual = span_x * trust * (0.90 * dx + 0.10 * jitter)
    return residual, reliability, fit_error



def _infer_variable_roles(
    memory: ExactCoverageMemory,
    problem: core.Problem,
    ideal: Array,
    nadir: Array,
    W: Optional[Array] = None,
) -> Tuple[Optional[Array], float, Dict[str, float]]:
    """Infer position-vs-distance roles by recent reference-cell separation.

    Let c(n) be the reference cell associated with evaluated design n.  For each
    decision variable j, we compute the one-way ANOVA effect size

        eta_j^2 = between-cell variance / total variance.

    A high eta^2 means the variable changes systematically with Pareto direction
    (a position/diversity variable).  A low eta^2 means it is better supplied by
    a currently converged donor.  Only the recent half of exact memory is used;
    early random correlations otherwise make unrelated variables look like
    position variables after the population has already contracted.
    """
    if W is None:
        W = core._dirichlet_reference_points(max(32, problem.n_obj * 16), problem.n_obj, seed=601)
    if len(memory.F) < max(40, 2 * problem.n_var):
        return None, 0.0, {"occupied_cells": 0.0, "eta_gap": 0.0}
    cutoff = float(np.quantile(memory.born, 0.50))
    idx = np.flatnonzero(memory.born >= cutoff)
    if len(idx) < max(40, 2 * problem.n_var):
        idx = np.argsort(memory.born, kind="mergesort")[-min(len(memory.F), max(80, 4 * problem.n_var)):]
    X, F = memory.X[idx], memory.F[idx]
    Xn = (X - problem.xl) / (problem.xu - problem.xl + 1e-12)
    assoc, _ = _associate_fixed(F, W, ideal, nadir)
    occupied = np.unique(assoc)
    mean = Xn.mean(axis=0)
    total = np.sum((Xn - mean) ** 2, axis=0) + 1e-12
    between = np.zeros(problem.n_var)
    for cell in occupied:
        j = np.flatnonzero(assoc == cell)
        if len(j):
            between += len(j) * (Xn[j].mean(axis=0) - mean) ** 2
    eta = np.clip(between / total, 0.0, 1.0)

    # Deterministic 1-D two-cluster split of variable effect sizes.
    c0, c1 = float(eta.min()), float(eta.max())
    for _ in range(20):
        d0, d1 = np.abs(eta - c0), np.abs(eta - c1)
        hi = d1 < d0
        if not np.any(hi) or np.all(hi):
            break
        n0, n1 = float(eta[~hi].mean()), float(eta[hi].mean())
        if abs(n0 - c0) + abs(n1 - c1) < 1e-10:
            c0, c1 = n0, n1
            break
        c0, c1 = n0, n1
    low, high = sorted((c0, c1))
    gap = high - low
    midpoint = 0.5 * (high + low)
    temperature = max(0.035, 0.18 * gap)
    role_prob = 1.0 / (1.0 + np.exp(-(eta - midpoint) / temperature))
    # Require at least one clear position variable; cap uncertain probabilities.
    role_prob = np.clip(role_prob, 0.02, 0.98)
    if gap < 0.06:
        reliability = 0.0
    else:
        cell_factor = min(1.0, len(occupied) / max(problem.n_obj + 2, 4))
        reliability = float(np.clip((gap / (np.std(eta) + 1e-12)) / 4.0, 0.0, 1.0) * cell_factor)
    return role_prob, reliability, {
        "occupied_cells": float(len(occupied)),
        "eta_gap": float(gap),
        "eta_max": float(eta.max()),
        "eta_second": float(np.partition(eta, -2)[-2]) if len(eta) > 1 else float(eta.max()),
        "mean_position_probability": float(role_prob.mean()),
    }


def _archive_transport_child(
    i: int,
    target_cell: int,
    X: Array,
    F: Array,
    W: Array,
    B: Array,
    memory: ExactCoverageMemory,
    ideal: Array,
    nadir: Array,
    progress: float,
    rng: np.random.Generator,
    problem: core.Problem,
    role_probability: Optional[Array] = None,
    role_reliability: float = 0.0,
) -> Optional[Array]:
    anchor = memory.choose_anchor(target_cell, W, ideal, nadir, rng)
    if anchor is None:
        return None
    xa, _ = anchor
    n, d = X.shape
    pool = B[i] if len(B[i]) >= 3 else np.arange(n)
    r1, r2 = rng.choice(pool, size=2, replace=False)

    if role_probability is not None and role_reliability >= 0.18:
        # Donor minimizes the target scalarization among the current population:
        # it supplies variables that have already learned convergence, while the
        # memory anchor supplies variables that control objective direction.
        wt = np.repeat(W[int(target_cell)][None, :], n, axis=0)
        score = core._mosaic_scalar(F, wt, ideal, nadir, 0.015, theta=0.22, blend=0.0)
        elite = np.argsort(score, kind="mergesort")[: max(2, int(math.ceil(0.12 * n)))]
        donor = X[int(rng.choice(elite))]
        ppos = np.clip(role_probability, 0.05, 0.95)
        position_mask = rng.random(d) < ppos
        if not np.any(position_mask):
            position_mask[int(np.argmax(ppos))] = True
        if np.all(position_mask):
            position_mask[int(np.argmin(ppos))] = False
        child = donor.copy()
        child[position_mask] = 0.92 * xa[position_mask] + 0.08 * donor[position_mask]
        # Refine distance variables only; perturbing inferred position variables
        # would immediately destroy the rescued reference direction.
        conv_mask = ~position_mask
        scale = float(np.clip(rng.normal(0.18 - 0.08 * progress, 0.05), 0.04, 0.28))
        child[conv_mask] += scale * (X[r1, conv_mask] - X[r2, conv_mask])
    else:
        # Reliability fallback: ordinary archive transport, still exact-verified.
        Fscale = float(np.clip(rng.normal(0.30 - 0.12 * progress, 0.08), 0.08, 0.45))
        mutant = xa + Fscale * (X[r1] - X[r2])
        cr = float(np.clip(rng.normal(0.82, 0.10), 0.35, 1.0))
        child = core.de_binomial(xa, mutant, cr, rng)

    child = np.clip(child, problem.xl, problem.xu)
    child = core.polynomial_mutation(child, problem.xl, problem.xu, rng, eta=30.0, prob=0.35 / d)
    return child



def _van_der_corput(index: int, base: int = 2) -> float:
    """Deterministic low-discrepancy scalar in (0,1)."""
    n = max(int(index), 1)
    denom = 1.0
    out = 0.0
    while n:
        n, rem = divmod(n, base)
        denom *= base
        out += rem / denom
    return float(out)



def _coordinate_expert_scores(
    candidates: Array,
    role_probability: Array,
    memory: ExactCoverageMemory,
    problem: core.Problem,
    ideal: Array,
    nadir: Array,
    probe_trials: Array,
    probe_success: Array,
) -> Array:
    """Score coordinate experts from exact memory, role confidence and UCB.

    No objective call is made here. The sensitivity term measures how strongly
    elite exact-memory points concentrate a variable relative to the whole exact
    memory, while the role prior suppresses variables that encode PF position.
    """
    cand = np.asarray(candidates, dtype=int)
    if len(cand) == 0:
        return np.empty(0)
    role = 1.0 - np.clip(role_probability[cand], 0.0, 1.0)
    sensitivity = np.zeros(len(cand), dtype=float)
    if len(memory.F) >= max(30, 2 * len(cand)):
        recent_cut = float(np.quantile(memory.born, 0.45))
        idx = np.flatnonzero(memory.born >= recent_cut)
        if len(idx) < 30:
            idx = np.arange(len(memory.F))
        MX = (memory.X[idx] - problem.xl) / (problem.xu - problem.xl + 1e-12)
        MF = memory.F[idx]
        Y = np.maximum((MF - ideal) / (nadir - ideal + 1e-12), 0.0)
        quality = np.sum(Y, axis=1)
        elite_n = max(8, int(math.ceil(0.20 * len(quality))))
        elite_idx = np.argsort(quality, kind="mergesort")[:elite_n]
        for k, j in enumerate(cand):
            all_std = float(np.std(MX[:, j])) + 1e-9
            elite_std = float(np.std(MX[elite_idx, j]))
            center_shift = abs(float(np.mean(MX[elite_idx, j]) - np.mean(MX[:, j]))) / all_std
            concentration = float(np.clip(1.0 - elite_std / all_std, 0.0, 1.0))
            sensitivity[k] = float(np.clip(0.55 * concentration + 0.45 * np.tanh(center_shift / 2.0), 0.0, 1.0))
    post_mean = (probe_success[cand] + 1.0) / (probe_trials[cand] + 2.0)
    uncertainty = 1.0 / np.sqrt(1.0 + probe_trials[cand])
    return 0.42 * role + 0.28 * sensitivity + 0.20 * post_mean + 0.10 * uncertainty


def _dynamic_coordinate_batch(
    candidates: Array,
    scores: Array,
    probe_trials: Array,
    max_batch: int = 4,
) -> Tuple[Array, int, float]:
    """Entropy-calibrated dynamic-k with a score-quantile cutoff."""
    cand = np.asarray(candidates, dtype=int)
    scores = np.asarray(scores, dtype=float)
    if len(cand) == 0:
        return np.empty(0, dtype=int), 0, 0.0
    z = scores - np.max(scores)
    p = np.exp(z / 0.12)
    p /= max(float(p.sum()), 1e-12)
    entropy = float(-np.sum(p * np.log(p + 1e-15)) / max(np.log(len(p)), 1e-12)) if len(p) > 1 else 0.0
    # High uncertainty/entropy buys more coordinate experts; confident routing
    # spends only one. The overall FE budget remains unchanged.
    k = int(np.clip(1 + math.ceil((max_batch - 1) * entropy), 1, min(max_batch, len(cand))))
    # Prefer untested experts, then apply the score quantile within that set.
    untested = probe_trials[cand] == 0
    pool_idx = np.flatnonzero(untested) if np.any(untested) else np.arange(len(cand))
    pool_scores = scores[pool_idx]
    take = min(k, len(pool_idx))
    cutoff = float(np.quantile(pool_scores, max(0.0, 1.0 - take / max(len(pool_scores), 1))))
    eligible = pool_idx[pool_scores >= cutoff - 1e-12]
    order = eligible[np.argsort(-scores[eligible], kind="mergesort")]
    chosen = cand[order[:take]]
    return chosen.astype(int), k, entropy


def _coordinate_tunnel_child(
    target_cell: int,
    variable: int,
    X: Array,
    F: Array,
    W: Array,
    ideal: Array,
    nadir: Array,
    problem: core.Problem,
    probe_index: Array,
    learned_values: Array,
    role_probability: Array,
) -> Tuple[Array, float]:
    """Generate one exact coordinate intervention without moving PF position vars."""
    n, d = X.shape
    wt = np.repeat(W[int(target_cell)][None, :], n, axis=0)
    score = core._mosaic_scalar(F, wt, ideal, nadir, 0.015, theta=0.22, blend=0.0)
    donor = X[int(np.argmin(score))]
    child = donor.copy()
    # Compose previously verified convergence alleles. This is an exact-memory
    # analogue of optimal mixing: only values with prior positive verifier credit
    # are broadcast, and inferred position variables remain untouched.
    known = np.isfinite(learned_values) & (role_probability < 0.35)
    child[known] = learned_values[known]
    j = int(variable)
    span = float(problem.xu[j] - problem.xl[j])
    # Advance the base-2 low-discrepancy line-search sequence until the probe is
    # not numerically identical to the donor/known value.
    value = child[j]
    for _ in range(8):
        probe_index[j] += 1
        u = _van_der_corput(int(probe_index[j]), 2)
        value = float(problem.xl[j] + u * span)
        if abs(value - child[j]) > 0.015 * max(span, 1e-12):
            break
    child[j] = value
    return np.clip(child, problem.xl, problem.xu), value


# ---------------------------------------------------------------------------
# MOSAIC-LQMoE v8: Shared backbone + latent quantile-routed micro-experts
# ---------------------------------------------------------------------------

from scipy.optimize import linear_sum_assignment


def _safe_unit_rows(A: Array) -> Array:
    A = np.asarray(A, dtype=float)
    return A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-12)


def _build_latent_basis(
    X: Array,
    successful_steps: Sequence[Sequence[Array]],
    span: Array,
    n_obj: int,
    max_rank: int = 10,
) -> Array:
    """Build a stable low-rank routed subspace from population and verified steps.

    The always-on shared proposal remains full dimensional. Only routed residuals
    are compressed into this basis, mirroring the shared-full-width / routed-latent
    separation of modern LatentMoE designs.
    """
    blocks: List[Array] = []
    span = np.maximum(np.asarray(span, dtype=float), 1e-12)
    Xn = (np.asarray(X, dtype=float) - np.mean(X, axis=0, keepdims=True)) / span
    if len(Xn):
        blocks.append(Xn)
    verified: List[Array] = []
    for seq in successful_steps:
        if seq:
            verified.extend(np.asarray(s, dtype=float) / span for s in seq[-24:])
    if verified:
        blocks.append(np.vstack(verified))
    Z = np.vstack(blocks) if blocks else np.eye(len(span))
    # Remove numerically empty rows and apply light shrinkage toward coordinate axes.
    nz = np.linalg.norm(Z, axis=1) > 1e-10
    Z = Z[nz]
    if len(Z) == 0:
        return np.eye(len(span))[:1]
    try:
        _, s, vt = np.linalg.svd(Z, full_matrices=False)
    except np.linalg.LinAlgError:
        return np.eye(len(span))[: min(len(span), max(1, n_obj))]
    numerical_rank = int(np.count_nonzero(s > max(s[0], 1e-12) * 1e-7))
    rank = max(1, min(max_rank, len(span), max(n_obj + 1, numerical_rank)))
    return vt[:rank].copy()


def _project_routed_residual(delta: Array, basis: Array, span: Array, retain: float = 0.18) -> Array:
    """Project a residual into the latent search subspace with an escape floor."""
    span = np.maximum(np.asarray(span, dtype=float), 1e-12)
    z = np.asarray(delta, dtype=float) / span
    if basis.size == 0:
        return np.asarray(delta, dtype=float)
    projected = (z @ basis.T) @ basis
    # A small full-space component prevents a stale basis from making dimensions
    # permanently unreachable.
    return span * ((1.0 - retain) * projected + retain * z)


def _proposal_energy_clip(delta: Array, span: Array, cap: float) -> Tuple[Array, float]:
    """RMS-cap the routed proposal energy; return clipped delta and scale factor."""
    span = np.maximum(np.asarray(span, dtype=float), 1e-12)
    energy = float(np.sqrt(np.mean((np.asarray(delta, dtype=float) / span) ** 2)))
    if not np.isfinite(energy) or energy <= 1e-15:
        return np.zeros_like(delta, dtype=float), 1.0
    scale = min(1.0, float(cap) / energy)
    return np.asarray(delta, dtype=float) * scale, scale


class LatentQuantileRouter:
    """Continuous Bayesian router with memory and loss-free quantile balancing.

    Balance biases affect assignment only. They never enter the exact reward or
    posterior target, preserving a clean separation between task utility and load
    control, analogous to auxiliary-loss-free routing.
    """

    def __init__(self, n_experts: int, n_features: int, ridge: float = 2.0):
        self.n_experts = int(n_experts)
        self.n_features = int(n_features)
        self.ridge = float(ridge)
        eye = np.eye(self.n_features, dtype=float)
        self.A = np.repeat((self.ridge * eye)[None, :, :], self.n_experts, axis=0)
        self.b = np.zeros((self.n_experts, self.n_features), dtype=float)
        self.calls = np.zeros(self.n_experts, dtype=int)
        self.reward_ema = np.full(self.n_experts, 0.30, dtype=float)
        self.advantage_ema = np.zeros(self.n_experts, dtype=float)
        self.load_ema = np.full(self.n_experts, 1.0 / self.n_experts, dtype=float)
        self.default_reward = np.full(self.n_experts, 0.30, dtype=float)
        self.prototypes = np.zeros((self.n_experts, self.n_features), dtype=float)
        self.prototype_mass = np.zeros(self.n_experts, dtype=float)
        self.last_target = np.full(self.n_experts, 1.0 / self.n_experts, dtype=float)
        self.last_bias = np.zeros(self.n_experts, dtype=float)
        self.last_load = np.zeros(self.n_experts, dtype=float)
        self.score_clip_events = 0

    def _posterior_scores(self, Phi: Array, rng: np.random.Generator, uncertainty: float) -> Array:
        Phi = np.asarray(Phi, dtype=float)
        scores = np.empty((len(Phi), self.n_experts), dtype=float)
        for e in range(self.n_experts):
            try:
                inv = np.linalg.inv(self.A[e])
            except np.linalg.LinAlgError:
                inv = np.linalg.pinv(self.A[e])
            mean = inv @ self.b[e]
            cov = 0.10 ** 2 * inv
            try:
                theta = rng.multivariate_normal(mean, cov, check_valid="ignore")
            except (ValueError, np.linalg.LinAlgError):
                theta = mean
            pred = Phi @ theta
            unc = np.sqrt(np.maximum(np.einsum("nd,dd,nd->n", Phi, inv, Phi), 0.0))
            scores[:, e] = pred + float(uncertainty) * unc
        return scores

    def _memory_affinity(self, Phi: Array) -> Array:
        P = _safe_unit_rows(np.asarray(Phi, dtype=float))
        Q = _safe_unit_rows(self.prototypes + 1e-12)
        sim = P @ Q.T
        active = self.prototype_mass >= 2.0
        sim[:, ~active] = 0.0
        return sim

    def _target_distribution(self, n: int, progress: float) -> Array:
        # The null residual (expert 0) is an always-available shared-only route.
        q0 = float(np.clip(0.42 + 0.18 * progress, 0.42, 0.60))
        quality = np.clip(self.advantage_ema[1:] / 0.10, -4.0, 4.0)
        quality -= np.max(quality) if len(quality) else 0.0
        expq = np.exp(quality / 1.35)
        soft = expq / max(float(expq.sum()), 1e-12)
        # Early in training every fine-grained expert receives a small probe quota;
        # later, proven specialists get the capacity while weak experts can go idle.
        if np.min(self.calls[1:]) < 2:
            floor = min(1.0 / max(n, 1), (1.0 - q0) / max(self.n_experts - 1, 1))
        else:
            floor = 0.0
        routed = (1.0 - q0) * (0.18 / max(self.n_experts - 1, 1) + 0.82 * soft)
        if floor > 0:
            routed = np.maximum(routed, floor)
            routed *= (1.0 - q0) / max(float(routed.sum()), 1e-12)
        q = np.r_[q0, routed]
        q /= q.sum()
        return q

    @staticmethod
    def _integer_quotas(q: Array, n: int) -> Array:
        raw = np.asarray(q, dtype=float) * int(n)
        quota = np.floor(raw).astype(int)
        remainder = int(n - quota.sum())
        if remainder > 0:
            order = np.argsort(-(raw - quota), kind="mergesort")
            quota[order[:remainder]] += 1
        elif remainder < 0:
            order = np.argsort(raw - quota, kind="mergesort")
            for e in order:
                take = min(quota[e], -remainder)
                quota[e] -= take
                remainder += take
                if remainder == 0:
                    break
        return quota

    def _quantile_bias(self, raw: Array, q: Array, sweeps: int = 4) -> Array:
        """Top-1 specialization of Kimi K3-style score-quantile balancing."""
        n, E = raw.shape
        bias = self.last_bias.copy()
        for _ in range(max(int(sweeps), 1)):
            adjusted = raw + bias[None, :]
            for e in range(E):
                other = adjusted.copy()
                other[:, e] = -np.inf
                cutoff = np.max(other, axis=1)
                margins = cutoff - raw[:, e]
                target = float(np.clip(q[e], 0.0, 1.0))
                if target <= 0.0:
                    bias[e] = float(np.min(margins) - 2.0)
                elif target >= 1.0:
                    bias[e] = float(np.max(margins) + 2.0)
                else:
                    bias[e] = float(np.quantile(margins, target))
            bias -= float(np.median(bias))
            bias = np.clip(bias, -2.5, 2.5)
        return bias

    def assign(
        self,
        Phi: Array,
        rng: np.random.Generator,
        progress: float,
        use_quantile: bool = True,
        use_memory: bool = True,
        use_specialization: bool = False,
    ) -> Tuple[Array, Array, Array, Array]:
        Phi = np.asarray(Phi, dtype=float)
        raw = self._posterior_scores(Phi, rng, uncertainty=0.08 if progress < 0.55 else 0.045)
        if use_memory:
            raw += 0.11 * self._memory_affinity(Phi)
        if use_specialization and np.count_nonzero(self.prototype_mass >= 2.0) >= 2:
            U = _safe_unit_rows(self.prototypes + 1e-12)
            overlap = np.maximum(U @ U.T - np.eye(self.n_experts), 0.0)
            redundancy = overlap.max(axis=1)
            raw -= 0.06 * redundancy[None, :]
        # Shared/null route receives a small reliability prior, but routed experts
        # can readily overtake it when their conditional evidence is stronger.
        raw[:, 0] += 0.11 + 0.08 * progress

        # MuonClip-inspired robust score clipping: only extreme router logits are
        # capped; ordinary ranking geometry is unchanged.
        med = np.median(raw, axis=1, keepdims=True)
        mad = np.median(np.abs(raw - med), axis=1, keepdims=True) + 1e-9
        lo, hi = med - 5.0 * mad, med + 5.0 * mad
        clipped = np.clip(raw, lo, hi)
        self.score_clip_events += int(np.count_nonzero(np.abs(clipped - raw) > 1e-12))
        raw = clipped

        q = self._target_distribution(len(Phi), progress)
        quota = self._integer_quotas(q, len(Phi))
        if use_quantile:
            bias = self._quantile_bias(raw, q)
            adjusted = raw + bias[None, :]
            # Exact capacity assignment after quantile correction. This prevents a
            # few near-tied contexts from violating the global FE allocation plan.
            slots = np.repeat(np.arange(self.n_experts), quota)
            if len(slots) != len(Phi):
                raise RuntimeError("quantile quota does not match population size")
            rows, cols = linear_sum_assignment(-adjusted[:, slots])
            assignment = np.empty(len(Phi), dtype=int)
            assignment[rows] = slots[cols]
        else:
            bias = np.zeros(self.n_experts, dtype=float)
            adjusted = raw
            assignment = np.argmax(adjusted, axis=1).astype(int)

        # Confidence controls routed residual amplitude, not FE count.
        sorted_scores = np.sort(adjusted, axis=1)
        margin = sorted_scores[:, -1] - sorted_scores[:, -2] if self.n_experts > 1 else np.ones(len(Phi))
        gate = 1.0 / (1.0 + np.exp(-np.clip(margin, -8.0, 8.0)))
        gate = np.clip(0.18 + 0.42 * gate, 0.18, 0.60)
        gate[assignment == 0] = 0.0

        load = np.bincount(assignment, minlength=self.n_experts).astype(float) / max(len(Phi), 1)
        self.load_ema = 0.92 * self.load_ema + 0.08 * load
        self.last_target = q
        self.last_bias = bias
        self.last_load = load
        return assignment, gate, raw, bias

    def update(
        self,
        phi: Array,
        expert: int,
        reward: float,
        baseline: float,
        dense_default: bool = False,
    ) -> float:
        phi = np.asarray(phi, dtype=float)
        e = int(expert)
        r = float(np.clip(reward, 0.0, 1.0))
        advantage = float(np.clip(r - baseline, -1.0, 1.0))
        target = float(np.clip(0.5 + advantage / 0.24, 0.0, 1.0))
        decay = 0.994
        eye = np.eye(self.n_features)
        self.A[e] = decay * self.A[e] + np.outer(phi, phi) + (1.0 - decay) * self.ridge * eye
        self.b[e] = decay * self.b[e] + phi * target
        self.calls[e] += 1
        self.reward_ema[e] = 0.94 * self.reward_ema[e] + 0.06 * r
        self.advantage_ema[e] = 0.94 * self.advantage_ema[e] + 0.06 * advantage
        self.default_reward[e] = 0.97 * self.default_reward[e] + 0.03 * r
        if r >= 0.42 or advantage >= 0.08:
            if self.prototype_mass[e] == 0:
                self.prototypes[e] = phi
            else:
                self.prototypes[e] = 0.92 * self.prototypes[e] + 0.08 * phi
            self.prototype_mass[e] += 1.0

        # Default-MoE-inspired weak dense feedback: unselected experts receive
        # only their EMA default target. The small weight regularizes the router
        # without pretending these are exact counterfactual evaluations.
        if dense_default:
            w = 0.018
            for j in range(self.n_experts):
                if j == e:
                    continue
                pseudo = float(np.clip(self.default_reward[j], 0.0, 1.0))
                self.A[j] = decay * self.A[j] + w * np.outer(phi, phi) + (1.0 - decay) * self.ridge * eye
                self.b[j] = decay * self.b[j] + w * phi * pseudo
        return advantage


def _lq_context_matrix(
    progress: float,
    stagnation: Array,
    densities: Array,
    med_density: float,
    distress: float,
    entropy: float,
    assigned_scalar: Array,
    F: Array,
    W: Array,
    ideal: Array,
    nadir: Array,
    role_reliability: float,
    archive_fill: float,
) -> Array:
    n = len(F)
    stag = np.clip(np.log1p(np.asarray(stagnation, dtype=float)) / np.log(12.0), 0.0, 1.0)
    density = np.asarray(densities, dtype=float)
    density_ratio = np.clip(density / (med_density + 1e-9), 0.0, 4.0) / 4.0 if med_density > 0 else np.zeros(n)
    scalar_rel = np.clip(np.asarray(assigned_scalar, dtype=float) / (np.median(assigned_scalar) + 1e-12), 0.0, 4.0) / 4.0
    Y = np.maximum((np.asarray(F) - ideal) / (nadir - ideal + 1e-12), 0.0)
    Yn = _safe_unit_rows(Y + 1e-12)
    Wn = _safe_unit_rows(W + 1e-12)
    alignment = np.clip(np.sum(Yn * Wn, axis=1), 0.0, 1.0)
    Phi = np.column_stack([
        np.ones(n),
        np.full(n, progress),
        np.full(n, progress * progress),
        stag,
        density_ratio,
        np.full(n, distress),
        np.full(n, entropy),
        scalar_rel,
        alignment,
        np.full(n, float(np.clip(role_reliability, 0.0, 1.0))),
        np.full(n, float(np.clip(archive_fill, 0.0, 1.0))),
        stag * scalar_rel,
    ])
    return Phi.astype(float)


def _choose_distinct(rng: np.random.Generator, pool: Array, exclude: Sequence[int], n: int) -> Array:
    pool = np.asarray(pool, dtype=int)
    mask = ~np.isin(pool, np.asarray(list(exclude), dtype=int))
    cand = pool[mask]
    if len(cand) < n:
        cand = pool
    return np.asarray(rng.choice(cand, size=n, replace=len(cand) < n), dtype=int)


def _micro_residual(
    micro: int,
    i: int,
    X: Array,
    F: Array,
    W: Array,
    B: Array,
    archive: core.Archive,
    residual_steps: Sequence[Sequence[Array]],
    sparse_target_x: Optional[Array],
    progress: float,
    rng: np.random.Generator,
    problem: core.Problem,
    ideal: Array,
    nadir: Array,
) -> Array:
    """Fine-grained residual bank; expert 0 is the exact shared-only route."""
    micro = int(micro)
    d = problem.n_var
    span = problem.xu - problem.xl
    if micro == 0:
        return np.zeros(d, dtype=float)

    neigh = np.asarray(B[int(i)], dtype=int)
    local = neigh if len(neigh) >= 3 else np.arange(len(X))
    mu = 0.015 + 0.08 * (1.0 - progress) ** 2
    scores = core._mosaic_scalar(
        F[local], np.repeat(W[int(i)][None, :], len(local), axis=0),
        ideal, nadir, mu, theta=0.18, blend=0.0,
    )
    elite = local[np.argsort(scores, kind="mergesort")[: max(2, int(math.ceil(0.18 * len(local))))]]
    pbest = int(rng.choice(elite))

    if micro == 1:  # pbest micro
        return (0.030 + 0.020 * (1.0 - progress)) * (X[pbest] - X[i])
    if micro == 2:  # pbest macro
        return (0.080 + 0.040 * (1.0 - progress)) * (X[pbest] - X[i])
    if micro == 3:  # local differential micro
        r1, r2 = _choose_distinct(rng, local, [i], 2)
        return 0.050 * (X[r1] - X[r2])
    if micro == 4:  # global differential
        r1, r2 = _choose_distinct(rng, np.arange(len(X)), [i], 2)
        return (0.070 + 0.035 * (1.0 - progress)) * (X[r1] - X[r2])
    if micro == 5:  # local archive tangent
        if len(archive.F) >= max(5, problem.n_obj + 1):
            AF = (archive.F - ideal) / (nadir - ideal + 1e-12)
            fi = (F[i] - ideal) / (nadir - ideal + 1e-12)
            idx = np.argsort(np.linalg.norm(AF - fi, axis=1), kind="mergesort")[: min(14, len(AF))]
            Z = (archive.X[idx] - np.mean(archive.X[idx], axis=0)) / (span + 1e-12)
            try:
                _, s, vt = np.linalg.svd(Z, full_matrices=False)
                k = max(1, min(problem.n_obj - 1, len(s)))
                return span * ((rng.normal(size=k) * (s[:k] + 0.01)) @ vt[:k]) * 0.050
            except np.linalg.LinAlgError:
                pass
        return np.zeros(d)
    if micro == 6:  # reference-gap transport
        if sparse_target_x is not None:
            return (0.055 + 0.030 * (1.0 - progress)) * (sparse_target_x - X[i])
        return np.zeros(d)
    if micro == 7:  # sparse Gaussian
        mask = rng.random(d) < min(0.20, 3.0 / max(d, 1))
        if not mask.any():
            mask[int(rng.integers(d))] = True
        out = np.zeros(d)
        out[mask] = rng.normal(size=int(mask.sum())) * span[mask] * (0.012 + 0.018 * (1.0 - progress))
        return out
    if micro == 8:  # sparse Cauchy
        mask = rng.random(d) < min(0.16, 2.5 / max(d, 1))
        if not mask.any():
            mask[int(rng.integers(d))] = True
        out = np.zeros(d)
        out[mask] = np.clip(rng.standard_cauchy(int(mask.sum())), -4.0, 4.0) * span[mask] * (0.010 + 0.022 * (1.0 - progress))
        return out
    if micro == 9:  # exact-verified residual replay
        bank = [s for seq in residual_steps for s in seq[-16:]]
        if bank:
            return 0.35 * np.asarray(bank[int(rng.integers(len(bank)))], dtype=float)
        return np.zeros(d)
    if micro == 10:  # SBX residual relative to parent
        mate = int(rng.choice(local))
        sbx = core.sbx_one(X[i], X[mate], problem.xl, problem.xu, rng, eta=25.0)
        return 0.12 * (sbx - X[i])
    if micro == 11:  # low-variance / orthogonal escape
        Z = (X - np.mean(X, axis=0)) / (span + 1e-12)
        try:
            _, _, vt = np.linalg.svd(Z, full_matrices=False)
            q = vt[-min(2, len(vt)):]
            direction = rng.normal(size=len(q)) @ q
            return span * direction * (0.010 + 0.018 * (1.0 - progress))
        except np.linalg.LinAlgError:
            return np.zeros(d)
    raise ValueError(f"unknown micro expert {micro}")


def run_mosaic_lqmoe(
    problem: core.Problem,
    seed: int,
    pop_size: int = 100,
    max_evals: int = 10100,
    T: int = 20,
    nr: int = 3,
    trace_every: int = 5,
    ablation: Optional[str] = None,
    recovery_fraction: float = 0.22,
    recovery_cooldown: int = 10,
    max_recoveries: int = 3,
    collapse_ratio: float = 0.35,
    collapse_start: float = 0.70,
    collapse_patience: int = 4,
    extension=None,
) -> core.RunResult:
    """MOSAIC-LQMoE with a frozen R3 shared backbone and routed micro-experts.

    Flags (join with '+'):
      no_memory       disable Exact Coverage Memory entirely
      no_recovery     keep memory/ART but disable collapse intervention
      no_o5           disable Archive-Reuse Transport expert entirely
      no_routine_o5   disable routine ART; allow it only through soft recovery
      no_role_factorization  use ordinary archive-DE instead of role-separated crossover
      soft_recovery   convert collapse intervention into an exact-verified ART queue
      hard_recovery   directly inject exact memory points (diagnostic comparator)
      secant          enable reliable Secant-Repulsive Transport in operator 2
      no_repulsion    with secant, remove objective-space RBF repulsion
      discount_router decay posterior evidence toward its prior each generation
      fixed_router    uniformly sample standard experts 0..4
      force_coverage  frozen v4 periodic NSGA-III archive repair comparator
      coordinate_tunnel enable role-gated coordinate basin tunneling (operator 6)
      moe_residual    enable shared-backbone + fine-grained residual MoE
      no_qb           disable loss-free quantile balancing in residual router
      no_memory_route disable successful-context expert memory
      no_latent       disable low-rank latent routed residuals
      no_energy_clip  disable routed proposal-energy clipping
      dense_default   weak EMA default feedback to non-selected micro-experts
      specialization  penalize overlapping expert context prototypes
      coordinate_qb  quantile-balanced dynamic-k routing over O6 variable experts
      coordinate_dynamic_k preserve R3 pilots, then evidence-scale O6 expert batch size
      coordinate_shared_qb preserve R3 shared pilots, then quantile-route residual coordinate experts
      coordinate_evidence_qb preserve R3 except under low-occupancy evidence, then quantile-route residual experts
      coordinate_geometry_qb additionally requires non-planar PF evidence before quantile residual routing
      coordinate_consensus_qb requires two consistent exact pilots before geometry-aware quantile routing
    """
    flags = set() if ablation is None else {s for s in str(ablation).split("+") if s}
    rng, X, F = core.initialize(problem, pop_size, seed)
    # Independent MoE stream: adding a router must not perturb the frozen R3
    # random trajectory when the shared/null route is selected.
    moe_rng = np.random.default_rng(int(seed) + 104729)
    W = core._dirichlet_reference_points(pop_size, problem.n_obj, seed=601)
    dW = ((W[:, None, :] - W[None, :, :]) ** 2).sum(axis=2)
    B = np.argsort(dW, axis=1)[:, : min(T, pop_size)]
    init_assoc, _ = core.associate_to_reference(F, W)
    init_occ = float(np.count_nonzero(np.bincount(init_assoc, minlength=pop_size)) / pop_size)
    alignment_latch = bool(problem.n_obj > 2 and init_occ < 0.25)

    ideal = F.min(axis=0)
    nadir = np.maximum(F.max(axis=0), ideal + 1e-9)
    archive = core.Archive(max_size=5 * pop_size)
    archive.update(X, F)
    memory = ExactCoverageMemory(capacity=8 * pop_size, per_cell=3)
    if "no_memory" not in flags:
        memory.add(X, F, 0, W, ideal, nadir)

    # Preserve the frozen five-expert router exactly.  ART (O5) is a
    # conservative challenger with its own posterior; adding an expert must not
    # perturb the core router merely by changing the dimension of a Beta draw.
    bandit = DiscountedPortfolio(n_states=12, n_ops=5)
    o5_a = np.ones(12, dtype=float)
    o5_b = np.full(12, 3.0, dtype=float)
    o6_a = np.ones(12, dtype=float)
    o6_b = np.full(12, 2.5, dtype=float)
    stagnation = np.zeros(pop_size, dtype=int)
    successful_steps: List[List[Array]] = [[] for _ in range(7)]
    evals, gen = pop_size, 0
    trace: List[Dict[str, float]] = []
    op_counts = np.zeros(7, dtype=int)
    op_rewards = np.zeros(7, dtype=float)
    secant_calls = secant_used = 0
    secant_rel_sum = 0.0
    role_probability: Optional[Array] = None
    role_reliability = 0.0
    role_diagnostics: Dict[str, float] = {}
    recovery_events: List[Dict[str, object]] = []
    rescue_queue: List[int] = []
    last_recovery = -10**9
    collapse_streak = 0
    max_occupancy = max(init_occ, 1.0 / pop_size)
    occupancy_history: List[float] = []
    archive_history: List[int] = []
    scalar_history: List[float] = []
    probe_index = np.zeros(problem.n_var, dtype=int)
    probe_trials = np.zeros(problem.n_var, dtype=int)
    probe_success = np.zeros(problem.n_var, dtype=int)
    learned_values = np.full(problem.n_var, np.nan, dtype=float)
    coordinate_events: List[Dict[str, object]] = []
    coordinate_candidates: Optional[Array] = None
    coordinate_pilot_rewards: List[float] = []
    coordinate_expand_threshold = 0.35
    coordinate_pilot_budget_current = 2
    coordinate_batch_history: List[Dict[str, object]] = []

    # DeepSeek/Kimi-inspired second routing layer. The legacy R3 proposal is the
    # always-on shared path; one of 11 fine-grained residual experts, or the exact
    # null residual, is selected without additional objective evaluations.
    n_micro = 12
    micro_router = LatentQuantileRouter(n_experts=n_micro, n_features=12)
    micro_counts = np.zeros(n_micro, dtype=int)
    micro_rewards = np.zeros(n_micro, dtype=float)
    micro_advantages = np.zeros(n_micro, dtype=float)
    micro_clip_scales: List[float] = []
    residual_successful_steps: List[List[Array]] = [[] for _ in range(n_micro)]
    shared_reward_ema = np.full(12, 0.30, dtype=float)
    micro_assignment_history: List[List[int]] = []
    micro_target_history: List[List[float]] = []
    micro_load_history: List[List[float]] = []
    radial_dispersion_history: List[float] = []
    geometry_score_history: List[float] = []
    radial_failure_streak = 0

    while evals < max_evals:
        progress = evals / max_evals
        densities = np.zeros(pop_size)
        for j in range(pop_size):
            densities[j] = core._local_density(archive.F, F[j])[0] if len(archive.F) else 0.0
        med_density = float(np.median(densities))

        # Frozen v4 search association is preserved for standard experts and
        # reward credit.  A separate shared longitudinal frame is used only by
        # the collapse detector and exact-memory reconstruction.
        assoc_search, _ = core.associate_to_reference(F, W)
        search_counts = np.bincount(assoc_search, minlength=pop_size)
        sparse_cells = np.flatnonzero(search_counts == search_counts.min())
        assoc_detect, _ = _associate_fixed(F, W, ideal, nadir)
        occupancy, entropy, detect_counts = _occupancy_entropy(assoc_detect, pop_size)
        max_occupancy = max(max_occupancy, occupancy)
        threshold = max(0.08, collapse_ratio * max_occupancy)
        distress = float(np.clip((threshold - occupancy) / (threshold + 1e-12), 0.0, 1.0))

        # Predict ART's exact anchor contribution once per generation.  This is
        # the optimization analogue of contribution regression in D2DMoE: the
        # router asks whether its specialist has a measurable job to do before
        # spending samples on it.
        o5_target_cell: Optional[int] = None
        o5_advantage_gen = 0.0
        if (
            "no_o5" not in flags
            and "no_routine_o5" not in flags
            and "no_memory" not in flags
            and len(memory.F) > pop_size
            and progress > 0.22
            and len(sparse_cells) > 0
        ):
            advantages = np.asarray([
                memory.best_anchor_advantage(int(c), F, W, ideal, nadir)
                for c in sparse_cells
            ])
            bp = int(np.argmax(advantages))
            o5_target_cell = int(sparse_cells[bp])
            o5_advantage_gen = float(advantages[bp])

        if (
            "no_o5" not in flags
            and "no_role_factorization" not in flags
            and "no_memory" not in flags
            and len(memory.F) >= max(40, 2 * problem.n_var)
            # RCBT needs role information earlier than coverage recovery.
            # Without the coordinate_tunnel ablation, preserve R2 timing.
            and progress >= (0.28 if "coordinate_tunnel" in flags else min(0.60, max(collapse_start - 0.10, 0.0)))
            and (gen % 4 == 0 or role_probability is None)
        ):
            role_probability, role_reliability, role_diagnostics = _infer_variable_roles(
                memory, problem, ideal, nadir, W
            )

        # Direction-conditioned convergence diagnostic. Unlike occupancy
        # distress, this detects a healthy spread whose assigned STCH values have
        # stopped improving. It controls a separate specialist and never changes
        # the frozen five-expert posterior.
        mu_diag = 0.008 + 0.10 * (1.0 - progress) ** 2
        theta_diag = 0.10 + 0.22 * progress
        assigned_scalar = core._mosaic_scalar(F, W, ideal, nadir, mu_diag, theta=theta_diag, blend=0.0)
        scalar_level = float(np.median(assigned_scalar))
        scalar_history.append(scalar_level)
        if len(scalar_history) >= 7:
            old_level = float(np.median(scalar_history[-7:-4]))
            new_level = float(np.median(scalar_history[-3:]))
            scalar_progress = (old_level - new_level) / (abs(old_level) + 1e-12)
        else:
            scalar_progress = 1.0
        # Scale-free local PF geometry diagnostic. A positive value means an
        # L2/spherical shell explains the current front better than an L1/simplex
        # shell; a negative value favors a flat simplex-like front. This is only
        # computed from already evaluated points.
        Y_geom = np.maximum((F - ideal) / (nadir - ideal + 1e-12), 0.0)
        l1_geom = np.sum(Y_geom, axis=1)
        l2_geom = np.linalg.norm(Y_geom, axis=1)
        cv1_geom = float(np.std(l1_geom) / (np.mean(l1_geom) + 1e-12))
        cv2_geom = float(np.std(l2_geom) / (np.mean(l2_geom) + 1e-12))
        geometry_score = float(cv1_geom - cv2_geom)
        geometry_score_history.append(geometry_score)
        coordinate_plans: List[Tuple[int, int]] = []
        if (
            "coordinate_tunnel" in flags
            and role_probability is not None
            and role_reliability >= 0.28
            and progress >= 0.40
            and gen % 2 == 0
            and not rescue_queue
        ):
            # Freeze one role-derived candidate set. Recomputing the role mask
            # could otherwise restart pilots and silently spend more than promised.
            if coordinate_candidates is None:
                conv_all = np.flatnonzero(role_probability <= 0.50)
                if len(conv_all) >= max(2, problem.n_var // 4):
                    order_conv = conv_all[np.argsort(role_probability[conv_all], kind="mergesort")]
                    coordinate_candidates = order_conv[: min(12, len(order_conv))].copy()

            conv = np.empty(0, dtype=int) if coordinate_candidates is None else coordinate_candidates
            if len(conv):
                target_score = assigned_scalar / (np.median(assigned_scalar) + 1e-12)
                target_order = np.argsort(-(stagnation + 3.0 * target_score), kind="mergesort")
                if "coordinate_evidence_qb" in flags or "coordinate_geometry_qb" in flags or "coordinate_consensus_qb" in flags:
                    # Evidence-triggered expert expansion. The two exact R3
                    # shared pilots always keep their original order. When the
                    # exact-memory reference occupancy is healthy, execution
                    # falls back bit-for-bit to the frozen R3 coordinate route.
                    # Only a low-occupancy + strong-pilot state unlocks the
                    # quantile-balanced residual experts.
                    untested = conv[probe_trials[conv] == 0]
                    total_trials = int(probe_trials[conv].sum())
                    pilot_budget = min(2, len(conv))
                    coordinate_pilot_budget_current = pilot_budget
                    pilot_due = total_trials < pilot_budget
                    pilot_ready = (
                        total_trials >= pilot_budget
                        and len(coordinate_pilot_rewards) >= pilot_budget
                    )
                    strong_rewards = (
                        np.asarray(coordinate_pilot_rewards[:pilot_budget], dtype=float)
                        if pilot_ready else np.empty(0, dtype=float)
                    )
                    occ_ratio = float(role_diagnostics.get("occupied_cells", pop_size)) / max(pop_size, 1)
                    structural_evidence = occ_ratio < 0.80
                    if "coordinate_geometry_qb" in flags or "coordinate_consensus_qb" in flags:
                        # Kimi-style expert expansion is reserved for a curved or
                        # irregular shell. On a clearly planar/simplex front, the
                        # frozen role order is more reliable than memory re-ranking.
                        structural_evidence = structural_evidence and geometry_score > -0.02
                    # The frozen shared path uses its original max-pilot gate.
                    # Routed residual experts may use a stricter consensus gate,
                    # but a failed residual gate must never disable the shared
                    # expert's own continuation (DeepSeek Keep-Routing analogue).
                    r3_expand_evidence = bool(
                        pilot_ready
                        and len(untested) > 0
                        and np.max(strong_rewards) >= coordinate_expand_threshold
                    )
                    if "coordinate_consensus_qb" in flags:
                        reward_evidence = bool(
                            pilot_ready
                            and len(untested) > 0
                            and np.min(strong_rewards) >= coordinate_expand_threshold
                        )
                    else:
                        reward_evidence = r3_expand_evidence
                    strong_evidence = reward_evidence
                    if pilot_due and len(untested):
                        coordinate_plans.append((int(target_order[0]), int(untested[0])))
                        k_now = 1
                        coord_entropy = 0.0
                        mode_now = "shared_pilot"
                    elif structural_evidence and strong_evidence:
                        rs = _coordinate_expert_scores(
                            untested, role_probability, memory, problem, ideal, nadir,
                            probe_trials, probe_success,
                        )
                        rs = rs + 1e-8 * moe_rng.normal(size=len(rs))
                        ranked, k_entropy, coord_entropy = _dynamic_coordinate_batch(
                            untested, rs, probe_trials, max_batch=min(3, len(untested))
                        )
                        n_strong = int(np.count_nonzero(strong_rewards >= coordinate_expand_threshold))
                        evidence_cap = 1 + int(n_strong >= 2 or np.max(strong_rewards) >= 0.60)
                        k_now = int(min(len(ranked), k_entropy, evidence_cap, 2))
                        for qidx, jvar in enumerate(ranked[:k_now]):
                            target = int(target_order[qidx % len(target_order)])
                            coordinate_plans.append((target, int(jvar)))
                        mode_now = "quantile_residual"
                    elif r3_expand_evidence:
                        # Residual gate closed: preserve the original R3 route and
                        # spend exactly one coordinate FE on the first untested
                        # role-ordered variable.
                        coordinate_plans.append((int(target_order[0]), int(untested[0])))
                        k_now = 1
                        coord_entropy = 0.0
                        mode_now = "frozen_r3_fallback"
                    else:
                        k_now = 0
                        coord_entropy = 0.0
                        mode_now = "null_route"
                    coordinate_batch_history.append({
                        "gen": int(gen), "evals": int(evals),
                        "dynamic_k": int(k_now), "entropy": float(coord_entropy),
                        "scheduled": [int(j) for _, j in coordinate_plans],
                        "pilot_budget": int(coordinate_pilot_budget_current),
                        "mode": mode_now, "keep_route": True,
                        "occupancy_ratio": float(occ_ratio),
                        "structural_evidence": bool(structural_evidence),
                        "geometry_score": float(geometry_score),
                        "consensus_gate": bool("coordinate_consensus_qb" in flags),
                    })
                elif "coordinate_shared_qb" in flags:
                    # DeepSeek shared-expert isolation + Kimi quantile balancing:
                    # the frozen R3 two-pilot path is always executed first, in
                    # exactly the same variable order. Routed coordinate experts
                    # are allowed only as a residual after exact pilot evidence.
                    untested = conv[probe_trials[conv] == 0]
                    total_trials = int(probe_trials[conv].sum())
                    pilot_budget = min(2, len(conv))
                    coordinate_pilot_budget_current = pilot_budget
                    pilot_due = total_trials < pilot_budget
                    pilot_ready = (
                        total_trials >= pilot_budget
                        and len(coordinate_pilot_rewards) >= pilot_budget
                    )
                    strong_rewards = (
                        np.asarray(coordinate_pilot_rewards[:pilot_budget], dtype=float)
                        if pilot_ready else np.empty(0, dtype=float)
                    )
                    residual_gate = bool(
                        pilot_ready
                        and len(untested) > 0
                        and np.max(strong_rewards) >= coordinate_expand_threshold
                    )
                    if pilot_due and len(untested):
                        # One exact shared pilot at a time; this preserves the
                        # R3 route and its random/evaluation trajectory.
                        coordinate_plans.append((int(target_order[0]), int(untested[0])))
                        k_now = 1
                        coord_entropy = 0.0
                    elif residual_gate:
                        rs = _coordinate_expert_scores(
                            untested, role_probability, memory, problem, ideal, nadir,
                            probe_trials, probe_success,
                        )
                        rs = rs + 1e-8 * moe_rng.normal(size=len(rs))
                        ranked, k_entropy, coord_entropy = _dynamic_coordinate_batch(
                            untested, rs, probe_trials, max_batch=min(3, len(untested))
                        )
                        # Evidence-triggered capacity. One strong pilot buys one
                        # routed expert; two strong pilots can buy a second. A
                        # very high single reward may also buy the second. This
                        # is a strict FE budget, not free parallel computation.
                        n_strong = int(np.count_nonzero(strong_rewards >= coordinate_expand_threshold))
                        evidence_cap = 1 + int(n_strong >= 2 or np.max(strong_rewards) >= 0.60)
                        k_now = int(min(len(ranked), k_entropy, evidence_cap, 2))
                        for qidx, jvar in enumerate(ranked[:k_now]):
                            target = int(target_order[qidx % len(target_order)])
                            coordinate_plans.append((target, int(jvar)))
                    else:
                        k_now = 0
                        coord_entropy = 0.0
                    coordinate_batch_history.append({
                        "gen": int(gen), "evals": int(evals),
                        "dynamic_k": int(k_now), "entropy": float(coord_entropy),
                        "scheduled": [int(j) for _, j in coordinate_plans],
                        "pilot_budget": int(coordinate_pilot_budget_current),
                        "mode": "shared_pilot_then_quantile_residual",
                        "keep_route": True,
                    })
                elif "coordinate_dynamic_k" in flags:
                    # Preserve the exact frozen R3 first-two pilot order. Only
                    # after those exact rewards prove usefulness do we expand the
                    # per-generation coordinate-expert budget. This mirrors
                    # Kimi-style dynamic-k while protecting the shared path.
                    untested = conv[probe_trials[conv] == 0]
                    total_trials = int(probe_trials[conv].sum())
                    pilot_budget = min(2, len(conv))
                    coordinate_pilot_budget_current = pilot_budget
                    pilot_due = total_trials < pilot_budget
                    expand_due = (
                        total_trials >= pilot_budget
                        and len(coordinate_pilot_rewards) >= pilot_budget
                        and max(coordinate_pilot_rewards[:pilot_budget]) >= coordinate_expand_threshold
                        and len(untested) > 0
                    )
                    if pilot_due and len(untested):
                        coordinate_plans.append((int(target_order[0]), int(untested[0])))
                        k_now = 1
                    elif expand_due:
                        strong = int(np.count_nonzero(
                            np.asarray(coordinate_pilot_rewards[:pilot_budget]) >= coordinate_expand_threshold
                        ))
                        k_now = min(len(untested), 1 + strong)
                        # Role ordering is the frozen R3 ordering; quantile-based
                        # capacity changes how many, not which, experts are trusted.
                        for qidx, jvar in enumerate(untested[:k_now]):
                            target = int(target_order[qidx % len(target_order)])
                            coordinate_plans.append((target, int(jvar)))
                    else:
                        k_now = 0
                    coordinate_batch_history.append({
                        "gen": int(gen), "evals": int(evals),
                        "dynamic_k": int(k_now), "entropy": None,
                        "scheduled": [int(j) for _, j in coordinate_plans],
                        "pilot_budget": int(coordinate_pilot_budget_current),
                        "mode": "shared_pilot_then_dynamic_k",
                    })
                elif "coordinate_qb" in flags:
                    cs = _coordinate_expert_scores(
                        conv, role_probability, memory, problem, ideal, nadir,
                        probe_trials, probe_success,
                    )
                    # Independent, tiny jitter only resolves exact score ties.
                    cs = cs + 1e-8 * moe_rng.normal(size=len(cs))
                    chosen_vars, dynamic_k, coord_entropy = _dynamic_coordinate_batch(
                        conv, cs, probe_trials, max_batch=min(4, len(conv))
                    )
                    coordinate_pilot_budget_current = max(2, dynamic_k)
                    total_trials = int(probe_trials[conv].sum())
                    pilot_due = total_trials < coordinate_pilot_budget_current
                    expand_due = (
                        total_trials >= coordinate_pilot_budget_current
                        and len(coordinate_pilot_rewards) >= coordinate_pilot_budget_current
                        and max(coordinate_pilot_rewards[:coordinate_pilot_budget_current]) >= coordinate_expand_threshold
                    )
                    if pilot_due or expand_due:
                        if not pilot_due:
                            # After a successful pilot phase, continue one expert
                            # at a time, ranked by exact posterior contribution.
                            remaining = conv[probe_trials[conv] == 0]
                            if len(remaining):
                                rs = _coordinate_expert_scores(
                                    remaining, role_probability, memory, problem,
                                    ideal, nadir, probe_trials, probe_success,
                                )
                                chosen_vars = remaining[np.argsort(-rs, kind="mergesort")[:1]]
                            else:
                                chosen_vars = np.empty(0, dtype=int)
                        else:
                            need = max(0, coordinate_pilot_budget_current - total_trials)
                            chosen_vars = chosen_vars[:need]
                        for qidx, jvar in enumerate(chosen_vars):
                            target = int(target_order[qidx % len(target_order)])
                            coordinate_plans.append((target, int(jvar)))
                    coordinate_batch_history.append({
                        "gen": int(gen), "evals": int(evals),
                        "dynamic_k": int(dynamic_k), "entropy": float(coord_entropy),
                        "scheduled": [int(j) for _, j in coordinate_plans],
                        "pilot_budget": int(coordinate_pilot_budget_current),
                    })
                else:
                    untested = conv[probe_trials[conv] == 0]
                    total_trials = int(probe_trials[conv].sum())
                    pilot_budget = min(2, len(conv))
                    coordinate_pilot_budget_current = pilot_budget
                    pilot_due = total_trials < pilot_budget
                    expand_due = (
                        total_trials >= pilot_budget
                        and len(coordinate_pilot_rewards) >= pilot_budget
                        and max(coordinate_pilot_rewards[:pilot_budget]) >= coordinate_expand_threshold
                        and len(untested) > 0
                    )
                    if (pilot_due or expand_due) and len(untested):
                        coordinate_plans.append((int(target_order[0]), int(untested[0])))

        if problem.n_obj <= 2:
            scalar_blend = 0.0
        elif alignment_latch:
            scalar_blend = 1.0
        else:
            scalar_blend = 0.0

        # Scale-free radial-dispersion diagnostic. A large ratio means a few
        # directions have reached a much better radial basin while most of the
        # population remains trapped far away -- the exact failure RCBT and the
        # routed residual bank are intended to solve.
        # Use a shift- and scale-equivariant radial mass ratio rather than the
        # current min-max normalized radius. The latter can hide severe multimodal
        # distance-variable traps by normalizing the trapped front to [0,1].
        span_obj = np.maximum(nadir - ideal, 1e-12)
        radial = np.sum(np.maximum(F - ideal, 0.0) + 0.01 * span_obj, axis=1)
        radial_dispersion = float(np.median(radial) / (np.quantile(radial, 0.10) + 1e-12))
        radial_dispersion_history.append(radial_dispersion)
        radial_failure_streak = radial_failure_streak + 1 if radial_dispersion >= 3.0 else 0

        micro_assign = np.zeros(pop_size, dtype=int)
        micro_gate = np.zeros(pop_size, dtype=float)
        micro_context = np.zeros((pop_size, 12), dtype=float)
        latent_basis = np.empty((0, problem.n_var), dtype=float)
        if "moe_residual" in flags:
            micro_context = _lq_context_matrix(
                progress, stagnation, densities, med_density, distress, entropy,
                assigned_scalar, F, W, ideal, nadir, role_reliability,
                len(archive.F) / max(archive.max_size, 1),
            )
            # A routed residual is a challenger, never a compulsory replacement
            # for the reliable shared path. Quantile balancing is performed only
            # across contexts for which a diagnosed radial failure exists; this
            # prevents capacity targets from spending residual routes on easy rows.
            eligible = (progress >= 0.25) & (
                (radial_failure_streak >= 3) & (stagnation >= 3)
            )
            idx_eligible = np.flatnonzero(eligible)
            if len(idx_eligible):
                ae, ge, _, _ = micro_router.assign(
                    micro_context[idx_eligible], moe_rng, progress,
                    use_quantile="no_qb" not in flags,
                    use_memory="no_memory_route" not in flags,
                    use_specialization="specialization" in flags,
                )
                micro_assign[idx_eligible] = ae
                micro_gate[idx_eligible] = ge
            if "no_latent" not in flags:
                latent_basis = _build_latent_basis(
                    X, list(successful_steps[:5]) + list(residual_successful_steps),
                    problem.xu - problem.xl, problem.n_obj, max_rank=10,
                )
            micro_assignment_history.append(np.bincount(micro_assign, minlength=n_micro).astype(int).tolist())
            micro_target_history.append(micro_router.last_target.tolist())
            micro_load_history.append(micro_router.last_load.tolist())

        for i in rng.permutation(pop_size):
            if evals >= max_evals:
                break
            state = core._mosaic_state(progress, int(stagnation[i]), float(densities[i]), med_density)
            forced_rescue = bool("soft_recovery" in flags and rescue_queue and "no_o5" not in flags)
            forced_target = int(rescue_queue.pop(0)) if forced_rescue else None
            forced_coordinate = bool(coordinate_plans and not forced_rescue)
            coordinate_variable: Optional[int] = None
            coordinate_value: Optional[float] = None
            if forced_rescue:
                op = 5
            elif forced_coordinate:
                op = 6
                forced_target, coordinate_variable = coordinate_plans.pop(0)
            elif "fixed_router" in flags:
                op = int(rng.integers(5))
            else:
                op = bandit.choose(state, rng, epsilon=0.10 if progress < 0.5 else 0.06)

            # D2DMoE-inspired contribution routing: ART is not selected merely
            # because its load is low.  Its best exact memory anchor must have a
            # measurable scalar advantage for a currently sparse cell, and its
            # conservative posterior must beat the selected core expert.
            target_cell = int(forced_target) if forced_target is not None else int(i)
            if (
                not forced_rescue
                and o5_target_cell is not None
                and (distress > 0.08 or stagnation[i] >= 8)
                and o5_advantage_gen > 0.025
            ):
                target_cell = int(o5_target_cell)
                q5 = float(rng.beta(o5_a[state], o5_b[state]))
                core_mean = float(bandit.a[state, op] / (bandit.a[state, op] + bandit.b[state, op]))
                predicted = float(np.clip(o5_advantage_gen / 0.12, 0.0, 1.0))
                o5_score = 0.55 * q5 + 0.45 * predicted
                if o5_score > core_mean + 0.06:
                    op = 5

            # A specialist routed to reference cell c must also be verified in
            # c's neighborhood.  Earlier prototypes generated for c but compared
            # only against the arbitrary loop index i, which silently discarded
            # otherwise useful rescue children.
            search_i = int(target_cell) if op in (5, 6) else int(i)
            parent = X[search_i].copy()
            parentF = F[search_i].copy()
            if op == 2 and len(archive.F) >= 3 and len(sparse_cells):
                # Preserve v4's stochastic sparse target for the original O2.
                target_cell = int(rng.choice(sparse_cells))
            sparse_target_x: Optional[Array] = None
            if op == 2 and len(archive.F) >= 3 and len(sparse_cells):
                az, an = archive.F.min(axis=0), archive.F.max(axis=0)
                AY = np.maximum((archive.F - az) / (an - az + 1e-12), 0.0)
                AYn = AY / (np.linalg.norm(AY, axis=1, keepdims=True) + 1e-12)
                wt = W[target_cell] / (np.linalg.norm(W[target_cell]) + 1e-12)
                sparse_target_x = archive.X[int(np.argmax(AYn @ wt))]

            micro_op = 0
            micro_phi = micro_context[int(i)].copy() if "moe_residual" in flags else np.zeros(12)
            shared_child: Optional[Array] = None
            routed_delta = np.zeros(problem.n_var, dtype=float)
            clip_scale = 1.0

            if op == 5:
                child = _archive_transport_child(
                    search_i, target_cell, X, F, W, B, memory, ideal, nadir, progress, rng, problem,
                    role_probability=role_probability, role_reliability=role_reliability
                )
                if child is None:
                    op = 0
                    search_i = int(i)
                    parent = X[search_i].copy()
            elif op == 6 and role_probability is not None and coordinate_variable is not None:
                child, coordinate_value = _coordinate_tunnel_child(
                    target_cell, coordinate_variable, X, F, W, ideal, nadir, problem,
                    probe_index, learned_values, role_probability
                )
            else:
                child = None

            if child is None:
                child = core._mosaic_operator(
                    int(op), search_i, X, F, W, B, archive, successful_steps, progress,
                    rng, problem, sparse_target_x=sparse_target_x, scalar_blend=scalar_blend
                )
                if op == 2 and "secant" in flags:
                    secant_calls += 1
                    residual, reliability, _ = _secant_repulsive_delta(
                        search_i, X, F, archive, W, ideal, nadir, progress, problem, rng,
                        use_repulsion="no_repulsion" not in flags,
                    )
                    secant_rel_sum += reliability
                    if reliability >= 0.28:
                        ramp = float(np.clip((progress - 0.12) / 0.35, 0.0, 1.0))
                        child = np.clip(child + ramp * reliability * residual, problem.xl, problem.xu)
                        secant_used += 1

            shared_child = child.copy()
            # Fine-grained residual MoE is applied only to the frozen core experts.
            # O5/O6 already are evidence-gated failure specialists with separate FE
            # semantics and are deliberately left untouched.
            if "moe_residual" in flags and op < 5:
                micro_op = int(micro_assign[int(i)])
                routed_delta = _micro_residual(
                    micro_op, search_i, X, F, W, B, archive, residual_successful_steps,
                    sparse_target_x, progress, moe_rng, problem, ideal, nadir,
                )
                if micro_op != 0 and "no_latent" not in flags:
                    routed_delta = _project_routed_residual(
                        routed_delta, latent_basis, problem.xu - problem.xl, retain=0.18
                    )
                if micro_op != 0 and "no_energy_clip" not in flags:
                    cap = 0.010 + 0.025 * (1.0 - progress) + 0.012 * float(stagnation[search_i] >= 6)
                    routed_delta, clip_scale = _proposal_energy_clip(
                        routed_delta, problem.xu - problem.xl, cap
                    )
                child = np.clip(
                    shared_child + float(micro_gate[int(i)]) * routed_delta,
                    problem.xl, problem.xu,
                )
                micro_clip_scales.append(float(clip_scale))

            extension_ticket = None
            if extension is not None:
                child, extension_ticket = extension.propose(
                    child, parent, parentF, X, F, W, search_i,
                    ideal, nadir, progress, evals, op, stagnation[search_i]
                )
                child = np.clip(child, problem.xl, problem.xu)
            childF = problem.evaluate(child)[0]
            evals += 1
            ideal = np.minimum(ideal, childF)
            pooled = np.vstack([F, archive.F, childF[None, :]]) if len(archive.F) else np.vstack([F, childF])
            nadir = np.maximum(np.quantile(pooled, 0.95, axis=0), ideal + 1e-9)
            entered, novelty = archive.update(child, childF)
            if "no_memory" not in flags:
                memory.add(child, childF, gen, W, ideal, nadir)

            neigh = B[search_i]
            replaced, max_rel_improve = 0, 0.0
            for j in rng.permutation(neigh):
                mu = 0.008 + 0.10 * (1.0 - progress) ** 2
                theta = 0.10 + 0.22 * progress
                oldg = core._mosaic_scalar(
                    F[j][None, :], W[j][None, :], ideal, nadir, mu, theta=theta, blend=scalar_blend
                )[0]
                newg = core._mosaic_scalar(
                    childF[None, :], W[j][None, :], ideal, nadir, mu, theta=theta, blend=scalar_blend
                )[0]
                rel = float((oldg - newg) / (abs(oldg) + 1e-12))
                verify = bool(newg <= oldg or (entered and novelty > 0.45 and newg <= oldg * 1.015))
                if verify:
                    X[j], F[j] = child.copy(), childF.copy()
                    stagnation[j] = 0
                    replaced += 1
                    max_rel_improve = max(max_rel_improve, max(rel, 0.0))
                    if replaced >= nr:
                        break
            if replaced == 0:
                stagnation[search_i] += 1
            elif extension_ticket is None:
                core_step = (shared_child if shared_child is not None else child) - parent
                successful_steps[op].append(core_step)
                if len(successful_steps[op]) > 64:
                    successful_steps[op] = successful_steps[op][-64:]
                if "moe_residual" in flags and op < 5 and micro_op != 0:
                    residual_successful_steps[micro_op].append(child - shared_child)
                    if len(residual_successful_steps[micro_op]) > 48:
                        residual_successful_steps[micro_op] = residual_successful_steps[micro_op][-48:]

            r_conv = float(np.clip(max_rel_improve / 0.08, 0.0, 1.0))
            r_rep = float(np.clip(replaced / max(nr, 1), 0.0, 1.0))
            r_arc = 0.25 + 0.75 * novelty if entered else 0.0
            # Preserve frozen v4 coverage credit so the no-O5/no-recovery
            # ablation is behavior-identical before a reconstruction event.
            cz = np.minimum(F.min(axis=0), childF)
            cn = np.maximum(F.max(axis=0), childF)
            cy = np.maximum((childF - cz) / (cn - cz + 1e-12), 0.0)
            cyn = cy / (np.linalg.norm(cy) + 1e-12)
            c = int(np.argmax((W / (np.linalg.norm(W, axis=1, keepdims=True) + 1e-12)) @ cyn))
            r_cover = 1.0 if entered and search_counts[c] == 0 else 0.0
            reward = float(np.clip(0.42*r_conv + 0.20*r_rep + 0.23*r_arc + 0.15*r_cover, 0.0, 1.0))
            if extension_ticket is not None:
                extension.observe(extension_ticket, childF, entered, replaced)
            if "fixed_router" not in flags and extension_ticket is None:
                if op == 5:
                    o5_a[state] += reward
                    o5_b[state] += 1.0 - reward
                elif op == 6:
                    o6_a[state] += reward
                    o6_b[state] += 1.0 - reward
                else:
                    bandit.update(state, op, reward)

            if "moe_residual" in flags and op < 5:
                baseline = float(shared_reward_ema[state])
                advantage = micro_router.update(
                    micro_phi, micro_op, reward, baseline,
                    dense_default="dense_default" in flags,
                )
                # Only actual null/shared-only routes update the counterfactual
                # baseline; routed outcomes cannot rewrite the control estimate.
                if micro_op == 0:
                    shared_reward_ema[state] = 0.94 * shared_reward_ema[state] + 0.06 * reward
                micro_counts[micro_op] += 1
                micro_rewards[micro_op] += reward
                micro_advantages[micro_op] += advantage

            if op == 6 and coordinate_variable is not None and coordinate_value is not None:
                jv = int(coordinate_variable)
                probe_trials[jv] += 1
                accepted_probe = bool(replaced > 0 and reward >= 0.08)
                if accepted_probe:
                    probe_success[jv] += 1
                    learned_values[jv] = float(coordinate_value)
                if len(coordinate_pilot_rewards) < max(coordinate_pilot_budget_current, 1):
                    coordinate_pilot_rewards.append(float(reward))
                coordinate_events.append({
                    "gen": gen, "evals": evals, "cell": int(search_i), "variable": jv,
                    "value": float(coordinate_value), "accepted": accepted_probe,
                    "reward": reward, "replaced": int(replaced),
                })
            if extension_ticket is None:
                op_counts[op] += 1
                op_rewards[op] += reward

        gen += 1
        if "discount_router" in flags:
            bandit.decay(0.992)
            o5_a = 1.0 + 0.992 * (o5_a - 1.0)
            o5_b = 1.0 + 0.992 * (o5_b - 1.0)
            o6_a = 1.0 + 0.992 * (o6_a - 1.0)
            o6_b = 1.0 + 0.992 * (o6_b - 1.0)

        # Compare against v4's periodic repair as an explicit ablation.
        if "force_coverage" in flags and gen % 4 == 0 and len(archive.F) >= pop_size // 2:
            ax, af = archive.output(min(2 * pop_size, len(archive.F)))
            X, F = core.nsga3_environmental_selection(
                np.vstack([X, ax]), np.vstack([F, af]), pop_size, W, rng
            )
            stagnation = np.minimum(stagnation, 3)

        # Evidence-triggered reconstruction.  It does not run for an initially
        # collapsed many-objective mapping, where low occupancy is structural.
        if (
            "no_memory" not in flags
            and "no_recovery" not in flags
            and "force_coverage" not in flags
            and not alignment_latch
            and progress >= collapse_start
        ):
            recent = np.asarray(occupancy_history[-6:], dtype=float)
            if len(recent) >= 4:
                xh = np.arange(len(recent), dtype=float)
                slope = float(np.polyfit(xh, recent, 1)[0])
            else:
                slope = 0.0
            # A temporary collapse is common and may self-recover.  Intervene
            # only when the low-entropy state persists late in the run and the
            # longitudinal occupancy is flat or declining.
            severe = occupancy < threshold and entropy < 0.62 and slope <= 0.003
            collapse_streak = collapse_streak + 1 if severe else 0
            if (
                collapse_streak >= max(int(collapse_patience), 1)
                and gen - last_recovery >= recovery_cooldown
                and len(recovery_events) < max_recoveries
            ):
                if "soft_recovery" in flags:
                    assoc_now, _ = _associate_fixed(F, W, ideal, nadir)
                    _, _, cnt_now = _occupancy_entropy(assoc_now, pop_size)
                    missing = np.flatnonzero(cnt_now == 0)
                    quota = min(max(1, int(math.ceil(recovery_fraction * pop_size))), len(missing))
                    occupied = np.flatnonzero(cnt_now > 0)
                    Wn = W / (np.linalg.norm(W, axis=1, keepdims=True) + 1e-12)
                    if len(missing) and len(occupied):
                        proximity = np.max(Wn[missing] @ Wn[occupied].T, axis=1)
                        cells = missing[np.argsort(proximity, kind="mergesort")[:quota]].astype(int).tolist()
                    else:
                        cells = missing[:quota].astype(int).tolist()
                    # Only cells backed by an exact memory anchor enter the queue.
                    cells = [c for c in cells if len(memory.candidates_for_cell(c, W, ideal, nadir)) > 0]
                    rescue_queue.extend(cells)
                    restored = len(cells)
                    mode = "soft_ART_queue"
                else:
                    X, F, restored, cells = memory.reconstruct(
                        X, F, W, ideal, nadir, recovery_fraction, rng
                    )
                    mode = "hard_exact_injection"
                if restored > 0:
                    recovery_events.append({
                        "gen": gen,
                        "evals": evals,
                        "occupancy_before": occupancy,
                        "entropy_before": entropy,
                        "restored": restored,
                        "cells": cells,
                        "mode": mode,
                    })
                    last_recovery = gen
                    collapse_streak = 0
                    if mode == "hard_exact_injection":
                        stagnation = np.minimum(stagnation, 3)
                        ideal = np.minimum(ideal, F.min(axis=0))
                        nadir = np.maximum(np.quantile(np.vstack([F, memory.F]), 0.95, axis=0), ideal + 1e-9)

        if gen % trace_every == 0:
            trace.append({
                "gen": gen,
                "evals": evals,
                "archive_size": len(archive.F),
                "memory_size": len(memory.F),
                "mean_stagnation": float(stagnation.mean()),
                "mean_reward": float(op_rewards.sum() / max(op_counts.sum(), 1)),
                "occupancy_ratio": occupancy,
                "occupancy_entropy": entropy,
                "coverage_distress": distress,
                "recoveries": len(recovery_events),
            })

    outX, outF = archive.output(pop_size)
    label = "MOSAIC-LQMoE" if "moe_residual" in flags else "MOSAIC-R3"
    if flags:
        label += "[" + "+".join(sorted(flags)) + "]"
    diagnostics: Dict[str, object] = {
        "version": "MOSAIC-LQMoE-v8-research",
        "flags": sorted(flags),
        "operator_counts": op_counts.tolist(),
        "operator_mean_rewards": (op_rewards / np.maximum(op_counts, 1)).tolist(),
        "bandit_counts": bandit.counts.tolist(),
        "micro_expert_names": [
            "shared_null", "pbest_micro", "pbest_macro", "local_diff",
            "global_diff", "archive_tangent", "gap_transport",
            "sparse_gaussian", "sparse_cauchy", "verified_replay",
            "sbx_residual", "orthogonal_escape",
        ],
        "micro_counts": micro_counts.tolist(),
        "micro_mean_rewards": (micro_rewards / np.maximum(micro_counts, 1)).tolist(),
        "micro_mean_advantages": (micro_advantages / np.maximum(micro_counts, 1)).tolist(),
        "micro_router_calls": micro_router.calls.tolist(),
        "micro_router_reward_ema": micro_router.reward_ema.tolist(),
        "micro_router_advantage_ema": micro_router.advantage_ema.tolist(),
        "micro_router_load_ema": micro_router.load_ema.tolist(),
        "micro_router_last_target": micro_router.last_target.tolist(),
        "micro_router_last_load": micro_router.last_load.tolist(),
        "micro_router_last_bias": micro_router.last_bias.tolist(),
        "micro_router_prototype_mass": micro_router.prototype_mass.tolist(),
        "micro_router_score_clip_events": int(micro_router.score_clip_events),
        "micro_assignment_history": micro_assignment_history,
        "micro_target_history": micro_target_history,
        "micro_load_history": micro_load_history,
        "micro_mean_clip_scale": float(np.mean(micro_clip_scales)) if micro_clip_scales else 1.0,
        "radial_dispersion_history": radial_dispersion_history,
        "geometry_score_history": geometry_score_history,
        "radial_failure_streak_final": int(radial_failure_streak),
        "o5_posterior_mean": (o5_a / (o5_a + o5_b)).tolist(),
        "o6_posterior_mean": (o6_a / (o6_a + o6_b)).tolist(),
        "coordinate_events": coordinate_events,
        "coordinate_probe_trials": probe_trials.tolist(),
        "coordinate_probe_success": probe_success.tolist(),
        "coordinate_learned_values": learned_values.tolist(),
        "coordinate_candidates": None if coordinate_candidates is None else coordinate_candidates.tolist(),
        "coordinate_pilot_rewards": coordinate_pilot_rewards,
        "coordinate_expand_threshold": coordinate_expand_threshold,
        "coordinate_pilot_budget": int(coordinate_pilot_budget_current),
        "coordinate_batch_history": coordinate_batch_history,
        "recoveries": recovery_events,
        "unspent_rescue_queue": rescue_queue,
        "secant_calls": secant_calls,
        "secant_used": secant_used,
        "mean_secant_reliability": float(secant_rel_sum / max(secant_calls, 1)),
        "role_reliability": role_reliability,
        "role_diagnostics": role_diagnostics,
        "role_probability": None if role_probability is None else role_probability.tolist(),
        "initial_occupancy": init_occ,
        "max_occupancy": max_occupancy,
        "scalar_history": scalar_history,
        "occupancy_history": occupancy_history,
        "recovery_config": {
            "fraction": recovery_fraction,
            "cooldown": recovery_cooldown,
            "max_recoveries": max_recoveries,
            "collapse_ratio": collapse_ratio,
            "collapse_start": collapse_start,
            "collapse_patience": collapse_patience,
        },
    }
    return core.RunResult(label, problem.name, seed, outX, outF, evals, trace, diagnostics)


__all__ = [
    "ExactCoverageMemory",
    "DiscountedPortfolio",
    "run_mosaic_lqmoe",
    "_van_der_corput",
    "_coordinate_tunnel_child",
]
