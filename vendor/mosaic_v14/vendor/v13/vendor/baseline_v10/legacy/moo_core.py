from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple
import math
import numpy as np
from scipy.stats import qmc

Array = np.ndarray


@dataclass(frozen=True)
class Problem:
    name: str
    n_var: int
    n_obj: int
    xl: Array
    xu: Array
    evaluate: Callable[[Array], Array]
    pareto_front: Callable[[int], Array]


# ------------------------------
# Benchmark problems
# ------------------------------

def _as_2d(x: Array) -> Array:
    x = np.asarray(x, dtype=float)
    return x[None, :] if x.ndim == 1 else x


def make_zdt(name: str, n_var: int = 30) -> Problem:
    name = name.lower()
    if name == "zdt4":
        n_var = 10
        xl = np.r_[0.0, np.full(n_var - 1, -5.0)]
        xu = np.r_[1.0, np.full(n_var - 1, 5.0)]
    else:
        xl = np.zeros(n_var)
        xu = np.ones(n_var)

    def evaluate(x: Array) -> Array:
        X = _as_2d(x)
        if name == "zdt1":
            f1 = X[:, 0]
            g = 1.0 + 9.0 * X[:, 1:].mean(axis=1)
            f2 = g * (1.0 - np.sqrt(f1 / g))
        elif name == "zdt2":
            f1 = X[:, 0]
            g = 1.0 + 9.0 * X[:, 1:].mean(axis=1)
            f2 = g * (1.0 - (f1 / g) ** 2)
        elif name == "zdt3":
            f1 = X[:, 0]
            g = 1.0 + 9.0 * X[:, 1:].mean(axis=1)
            r = f1 / g
            f2 = g * (1.0 - np.sqrt(r) - r * np.sin(10.0 * np.pi * f1))
        elif name == "zdt4":
            f1 = X[:, 0]
            z = X[:, 1:]
            g = 1.0 + 10.0 * (n_var - 1) + np.sum(z * z - 10.0 * np.cos(4.0 * np.pi * z), axis=1)
            f2 = g * (1.0 - np.sqrt(f1 / g))
        elif name == "zdt6":
            x1 = X[:, 0]
            f1 = 1.0 - np.exp(-4.0 * x1) * np.sin(6.0 * np.pi * x1) ** 6
            g = 1.0 + 9.0 * (X[:, 1:].mean(axis=1) ** 0.25)
            f2 = g * (1.0 - (f1 / g) ** 2)
        else:
            raise KeyError(name)
        return np.column_stack([f1, f2])

    def pareto_front(n: int = 2000) -> Array:
        x = np.linspace(0.0, 1.0, max(n * 3, 4000))
        if name in ("zdt1", "zdt4"):
            f1 = x
            f2 = 1.0 - np.sqrt(x)
        elif name == "zdt2":
            f1 = x
            f2 = 1.0 - x**2
        elif name == "zdt3":
            intervals = np.array([
                [0.0, 0.0830015349],
                [0.1822287280, 0.2577623634],
                [0.4093136748, 0.4538821041],
                [0.6183967944, 0.6525117038],
                [0.8233317983, 0.8518328654],
            ])
            per = max(20, int(math.ceil(n / len(intervals))))
            f1 = np.concatenate([np.linspace(a, b, per) for a, b in intervals])[:n]
            f2 = 1.0 - np.sqrt(f1) - f1 * np.sin(10.0 * np.pi * f1)
            return np.column_stack([f1, f2])
        elif name == "zdt6":
            f1 = 1.0 - np.exp(-4.0 * x) * np.sin(6.0 * np.pi * x) ** 6
            f2 = 1.0 - f1**2
            F = np.column_stack([f1, f2])
            F = F[nondominated_mask(F)]
            F = F[np.argsort(F[:, 0])]
            # Uniformize by arc length rather than x1 because ZDT6 density is strongly biased.
            d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(F, axis=0), axis=1))]
            targets = np.linspace(0, d[-1], min(n, len(F)))
            idx = np.searchsorted(d, targets)
            return F[np.clip(idx, 0, len(F) - 1)]
        else:
            raise KeyError(name)
        return np.column_stack([f1, f2])

    return Problem(name.upper(), n_var, 2, xl, xu, evaluate, pareto_front)


def _dirichlet_reference_points(n: int, m: int, seed: int = 12345, pool_mult: int = 80) -> Array:
    """Deterministic maximin simplex design with exact extremes."""
    rng = np.random.default_rng(seed + 97 * m + n)
    if m == 2:
        t = np.linspace(0.0, 1.0, n)
        return np.column_stack([t, 1.0 - t])
    if n > 500:
        # Fast deterministic quasi-random Dirichlet design for dense metric fronts.
        power = int(math.ceil(math.log2(max(n - m, 1))))
        U = qmc.Sobol(d=m, scramble=True, seed=seed + 97 * m).random_base2(power)
        U = np.clip(U[: max(n - m, 1)], 1e-12, 1.0 - 1e-12)
        E = -np.log(U)
        W = E / E.sum(axis=1, keepdims=True)
        W = np.vstack([np.eye(m), W])[:n]
        return W
    pool_n = max(n * pool_mult, 5000)
    pool = rng.dirichlet(np.ones(m), size=pool_n)
    extremes = np.eye(m)
    chosen = [e for e in extremes]
    C = np.vstack(chosen)
    # Maximin farthest-point sampling in Euclidean simplex geometry.
    min_d2 = ((pool[:, None, :] - C[None, :, :]) ** 2).sum(axis=2).min(axis=1)
    while len(chosen) < n:
        j = int(np.argmax(min_d2))
        p = pool[j]
        chosen.append(p)
        d2 = ((pool - p) ** 2).sum(axis=1)
        min_d2 = np.minimum(min_d2, d2)
        min_d2[j] = -1.0
    W = np.vstack(chosen[:n])
    W = np.maximum(W, 1e-12)
    W /= W.sum(axis=1, keepdims=True)
    return W


def make_dtlz(name: str, n_obj: int = 3, n_var: Optional[int] = None) -> Problem:
    name = name.lower()
    if n_var is None:
        k = 5 if name == "dtlz1" else 10
        n_var = n_obj + k - 1
    xl = np.zeros(n_var)
    xu = np.ones(n_var)

    def evaluate(x: Array) -> Array:
        X = _as_2d(x)
        M = n_obj
        k = n_var - M + 1
        tail = X[:, M - 1 :]
        if name in ("dtlz1", "dtlz3"):
            g = 100.0 * (k + np.sum((tail - 0.5) ** 2 - np.cos(20.0 * np.pi * (tail - 0.5)), axis=1))
        elif name in ("dtlz2", "dtlz4", "dtlz5"):
            g = np.sum((tail - 0.5) ** 2, axis=1)
        elif name == "dtlz6":
            g = np.sum(tail ** 0.1, axis=1)
        elif name == "dtlz7":
            g = 1.0 + 9.0 / k * np.sum(tail, axis=1)
        else:
            raise KeyError(name)

        if name == "dtlz1":
            F = np.empty((len(X), M))
            for i in range(M):
                value = 0.5 * (1.0 + g)
                for j in range(M - i - 1):
                    value *= X[:, j]
                if i > 0:
                    value *= 1.0 - X[:, M - i - 1]
                F[:, i] = value
            return F

        if name in ("dtlz2", "dtlz3", "dtlz4"):
            alpha = 100.0 if name == "dtlz4" else 1.0
            A = X[:, : M - 1] ** alpha
            F = np.empty((len(X), M))
            for i in range(M):
                value = 1.0 + g
                for j in range(M - i - 1):
                    value *= np.cos(A[:, j] * np.pi / 2.0)
                if i > 0:
                    value *= np.sin(A[:, M - i - 1] * np.pi / 2.0)
                F[:, i] = value
            return F

        if name in ("dtlz5", "dtlz6"):
            theta = np.empty((len(X), M - 1))
            theta[:, 0] = X[:, 0] * np.pi / 2.0
            if M > 2:
                theta[:, 1:] = (np.pi / (4.0 * (1.0 + g)))[:, None] * (
                    1.0 + 2.0 * g[:, None] * X[:, 1 : M - 1]
                )
            F = np.empty((len(X), M))
            for i in range(M):
                value = 1.0 + g
                for j in range(M - i - 1):
                    value *= np.cos(theta[:, j])
                if i > 0:
                    value *= np.sin(theta[:, M - i - 1])
                F[:, i] = value
            return F

        # DTLZ7
        F = np.empty((len(X), M))
        F[:, : M - 1] = X[:, : M - 1]
        h = M - np.sum(
            (F[:, : M - 1] / (1.0 + g[:, None]))
            * (1.0 + np.sin(3.0 * np.pi * F[:, : M - 1])),
            axis=1,
        )
        F[:, M - 1] = (1.0 + g) * h
        return F

    def pareto_front(n: int = 3000) -> Array:
        M = n_obj
        if name == "dtlz1":
            return 0.5 * _dirichlet_reference_points(n, M, seed=211)
        if name in ("dtlz2", "dtlz3", "dtlz4"):
            W = _dirichlet_reference_points(n, M, seed=223)
            return W / np.linalg.norm(W, axis=1, keepdims=True)
        if name in ("dtlz5", "dtlz6"):
            # Degenerate one-dimensional Pareto front. Only the first angle varies;
            # the remaining angles are pi/4 at g=0.
            theta0 = np.linspace(0.0, np.pi / 2.0, n)
            theta = np.full((n, M - 1), np.pi / 4.0)
            theta[:, 0] = theta0
            F = np.empty((n, M))
            for i in range(M):
                value = np.ones(n)
                for j in range(M - i - 1):
                    value *= np.cos(theta[:, j])
                if i > 0:
                    value *= np.sin(theta[:, M - i - 1])
                F[:, i] = value
            return F
        if name == "dtlz7":
            # The DTLZ7 Pareto set is disconnected. For each free objective, the
            # efficient intervals are approximately [0,0.2514] and
            # [0.6316,0.8594]. Sampling their Cartesian union avoids an
            # O(pool^2) skyline filter and yields a stable reference front.
            rng = np.random.default_rng(239 + M + n)
            pool_n = max(30 * n, 12000)
            choose_hi = rng.random((pool_n, M - 1)) < 0.5
            U = rng.random((pool_n, M - 1))
            low = 0.251411836
            hi0, hi1 = 0.631626531, 0.859400856
            X = np.where(choose_hi, hi0 + (hi1 - hi0) * U, low * U)
            h = M - np.sum((X / 2.0) * (1.0 + np.sin(3.0 * np.pi * X)), axis=1)
            F = np.column_stack([X, 2.0 * h])
            return farthest_point_select(F, min(n, len(F)), normalize=True)
        raise KeyError(name)

    return Problem(name.upper(), n_var, n_obj, xl, xu, evaluate, pareto_front)


# ------------------------------
# WFG benchmark suite (WFG1-WFG9)
# ------------------------------

def _wfg_correct01(x: Array, eps: float = 1e-10) -> Array:
    y = np.asarray(x, dtype=float).copy()
    y[(y < 0.0) & (y >= -eps)] = 0.0
    y[(y > 1.0) & (y <= 1.0 + eps)] = 1.0
    return np.clip(y, 0.0, 1.0)


def _wfg_shift_linear(y: Array, a: float = 0.35) -> Array:
    return _wfg_correct01(np.abs(y - a) / np.abs(np.floor(a - y) + a))


def _wfg_shift_deceptive(y: Array, a: float = 0.35, b: float = 0.001, c: float = 0.05) -> Array:
    t1 = np.floor(y - a + b) * (1.0 - c + (a - b) / b) / (a - b)
    t2 = np.floor(a + b - y) * (1.0 - c + (1.0 - a - b) / b) / (1.0 - a - b)
    return _wfg_correct01(1.0 + (np.abs(y - a) - b) * (t1 + t2 + 1.0 / b))


def _wfg_shift_multimodal(y: Array, a: float, b: float, c: float) -> Array:
    t1 = np.abs(y - c) / (2.0 * (np.floor(c - y) + c))
    t2 = (4.0 * a + 2.0) * np.pi * (0.5 - t1)
    return _wfg_correct01((1.0 + np.cos(t2) + 4.0 * b * t1**2) / (b + 2.0))


def _wfg_param_dependent(y: Array, u: Array, a: float = 0.98 / 49.98,
                         b: float = 0.02, c: float = 50.0) -> Array:
    aux = a - (1.0 - 2.0 * u) * np.abs(np.floor(0.5 - u) + a)
    return _wfg_correct01(y ** (b + (c - b) * aux))


def _wfg_bias_flat(y: Array, a: float, b: float, c: float) -> Array:
    ret = (
        a
        + np.minimum(0.0, np.floor(y - b)) * (a * (b - y) / b)
        - np.minimum(0.0, np.floor(c - y)) * ((1.0 - a) * (y - c) / (1.0 - c))
    )
    return _wfg_correct01(ret)


def _wfg_bias_poly(y: Array, alpha: float) -> Array:
    return _wfg_correct01(y ** alpha)


def _wfg_reduce_weighted(y: Array, w: Array) -> Array:
    return _wfg_correct01(np.dot(y, w) / np.sum(w))


def _wfg_reduce_uniform(y: Array) -> Array:
    return _wfg_correct01(np.mean(y, axis=1))


def _wfg_reduce_nonsep(y: Array, a: int) -> Array:
    n, m = y.shape
    val = np.ceil(a / 2.0)
    num = np.zeros(n)
    for j in range(m):
        num += y[:, j]
        for k in range(a - 1):
            num += np.abs(y[:, j] - y[:, (1 + j + k) % m])
    den = m * val * (1.0 + 2.0 * a - 2.0 * val) / a
    return _wfg_correct01(num / den)


def _wfg_shape_concave(x: Array, m: int) -> Array:
    M = x.shape[1]
    if m == 1:
        out = np.prod(np.sin(0.5 * x[:, :M] * np.pi), axis=1)
    elif 1 < m <= M:
        out = np.prod(np.sin(0.5 * x[:, : M - m + 1] * np.pi), axis=1)
        out *= np.cos(0.5 * x[:, M - m + 1] * np.pi)
    else:
        out = np.cos(0.5 * x[:, 0] * np.pi)
    return _wfg_correct01(out)


def _wfg_shape_convex(x: Array, m: int) -> Array:
    M = x.shape[1]
    if m == 1:
        out = np.prod(1.0 - np.cos(0.5 * x[:, :M] * np.pi), axis=1)
    elif 1 < m <= M:
        out = np.prod(1.0 - np.cos(0.5 * x[:, : M - m + 1] * np.pi), axis=1)
        out *= 1.0 - np.sin(0.5 * x[:, M - m + 1] * np.pi)
    else:
        out = 1.0 - np.sin(0.5 * x[:, 0] * np.pi)
    return _wfg_correct01(out)


def _wfg_shape_linear(x: Array, m: int) -> Array:
    M = x.shape[1]
    if m == 1:
        out = np.prod(x, axis=1)
    elif 1 < m <= M:
        out = np.prod(x[:, : M - m + 1], axis=1)
        out *= 1.0 - x[:, M - m + 1]
    else:
        out = 1.0 - x[:, 0]
    return _wfg_correct01(out)


def _wfg_shape_mixed(x: Array, a: float = 5.0, alpha: float = 1.0) -> Array:
    aux = 2.0 * a * np.pi
    return _wfg_correct01((1.0 - x - np.cos(aux * x + 0.5 * np.pi) / aux) ** alpha)


def _wfg_shape_disconnected(x: Array, alpha: float = 1.0, beta: float = 1.0,
                            a: float = 5.0) -> Array:
    return _wfg_correct01(1.0 - x**alpha * np.cos(a * np.pi * x**beta) ** 2)


def _wfg_post(t: Array, a: Array) -> Array:
    cols = [np.maximum(t[:, -1], a[i]) * (t[:, i] - 0.5) + 0.5
            for i in range(t.shape[1] - 1)]
    cols.append(t[:, -1])
    return np.column_stack(cols)


def make_wfg(name: str, n_obj: int = 3, n_var: Optional[int] = None, k: Optional[int] = None) -> Problem:
    name = name.lower()
    valid = {f"wfg{i}" for i in range(1, 10)}
    if name not in valid:
        raise KeyError(name)
    if k is None:
        k = 4 if n_obj == 2 else 2 * (n_obj - 1)
    if n_var is None:
        n_var = k + 20
    l = n_var - k
    if k % (n_obj - 1) != 0 or k < 4 or l <= 0:
        raise ValueError("invalid WFG dimensions")
    if name in {"wfg2", "wfg3"} and l % 2:
        raise ValueError("WFG2/WFG3 require an even number of distance variables")
    xl = np.zeros(n_var)
    xu = 2.0 * np.arange(1, n_var + 1, dtype=float)
    S = 2.0 * np.arange(1, n_obj + 1, dtype=float)
    A = np.ones(n_obj - 1)
    if name == "wfg3" and len(A) > 1:
        A[1:] = 0.0
    gap = k // (n_obj - 1)

    def reduce_uniform_blocks(y: Array, tail_end: Optional[int] = None) -> Array:
        cols = [_wfg_reduce_uniform(y[:, j * gap : (j + 1) * gap])
                for j in range(n_obj - 1)]
        stop = y.shape[1] if tail_end is None else tail_end
        cols.append(_wfg_reduce_uniform(y[:, k:stop]))
        return np.column_stack(cols)

    def reduce_nonsep_blocks(y: Array) -> Array:
        cols = [_wfg_reduce_nonsep(y[:, j * gap : (j + 1) * gap], gap)
                for j in range(n_obj - 1)]
        cols.append(_wfg_reduce_nonsep(y[:, k:], y.shape[1] - k))
        return np.column_stack(cols)

    def evaluate(x: Array) -> Array:
        y = _as_2d(x) / xu
        apply_post = True
        shape_kind = "concave"

        if name == "wfg1":
            z = y.copy()
            z[:, k:] = _wfg_shift_linear(z[:, k:], 0.35)
            z[:, k:] = _wfg_bias_flat(z[:, k:], 0.8, 0.75, 0.85)
            z = _wfg_bias_poly(z, 0.02)
            weights = 2.0 * np.arange(1, n_var + 1, dtype=float)
            cols = [_wfg_reduce_weighted(z[:, j * gap : (j + 1) * gap],
                                         weights[j * gap : (j + 1) * gap])
                    for j in range(n_obj - 1)]
            cols.append(_wfg_reduce_weighted(z[:, k:], weights[k:]))
            t = np.column_stack(cols)
            shape_kind = "wfg1"

        elif name in {"wfg2", "wfg3"}:
            z = y.copy()
            z[:, k:] = _wfg_shift_linear(z[:, k:], 0.35)
            pair_tail = np.column_stack([
                _wfg_reduce_nonsep(z[:, k + 2 * q : k + 2 * q + 2], 2)
                for q in range(l // 2)
            ])
            z = np.column_stack([z[:, :k], pair_tail])
            t = reduce_uniform_blocks(z, tail_end=k + l // 2)
            shape_kind = "linear" if name == "wfg3" else "wfg2"

        elif name == "wfg4":
            z = _wfg_shift_multimodal(y, 30.0, 10.0, 0.35)
            t = reduce_uniform_blocks(z)

        elif name == "wfg5":
            z = _wfg_shift_deceptive(y, 0.35, 0.001, 0.05)
            t = reduce_uniform_blocks(z)

        elif name == "wfg6":
            z = y.copy()
            z[:, k:] = _wfg_shift_linear(z[:, k:], 0.35)
            t = reduce_nonsep_blocks(z)

        elif name == "wfg7":
            z = y.copy()
            for i in range(k):
                u = _wfg_reduce_uniform(z[:, i + 1:])
                z[:, i] = _wfg_param_dependent(z[:, i], u)
            z[:, k:] = _wfg_shift_linear(z[:, k:], 0.35)
            t = reduce_uniform_blocks(z)

        elif name == "wfg8":
            z = y.copy()
            dependent_tail = []
            for i in range(k, n_var):
                u = _wfg_reduce_uniform(y[:, :i])
                dependent_tail.append(_wfg_param_dependent(y[:, i], u))
            z[:, k:] = np.column_stack(dependent_tail)
            z[:, k:] = _wfg_shift_linear(z[:, k:], 0.35)
            t = reduce_uniform_blocks(z)

        else:  # WFG9: parameter-dependent, deceptive, multimodal, non-separable
            z = y.copy()
            for i in range(n_var - 1):
                u = _wfg_reduce_uniform(z[:, i + 1:])
                z[:, i] = _wfg_param_dependent(z[:, i], u)
            a_cols = [_wfg_shift_deceptive(z[:, i], 0.35, 0.001, 0.05) for i in range(k)]
            b_cols = [_wfg_shift_multimodal(z[:, i], 30.0, 95.0, 0.35)
                      for i in range(k, n_var)]
            z = np.column_stack(a_cols + b_cols)
            t = reduce_nonsep_blocks(z)
            apply_post = False

        if apply_post:
            t = _wfg_post(t, A)
        if shape_kind == "wfg1":
            h = [_wfg_shape_convex(t[:, :-1], j + 1) for j in range(n_obj - 1)]
            h.append(_wfg_shape_mixed(t[:, 0], alpha=1.0, a=5.0))
        elif shape_kind == "wfg2":
            h = [_wfg_shape_convex(t[:, :-1], j + 1) for j in range(n_obj - 1)]
            h.append(_wfg_shape_disconnected(t[:, 0], alpha=1.0, beta=1.0, a=5.0))
        elif shape_kind == "linear":
            h = [_wfg_shape_linear(t[:, :-1], j + 1) for j in range(n_obj)]
        else:
            h = [_wfg_shape_concave(t[:, :-1], j + 1) for j in range(n_obj)]
        return t[:, -1][:, None] + S[None, :] * np.column_stack(h)

    def optimal_decisions(position: Array) -> Array:
        K = np.asarray(position, dtype=float).copy()
        if name == "wfg8":
            X = K.copy()
            for _ in range(l):
                u = X.mean(axis=1)
                tmp1 = np.abs(np.floor(0.5 - u) + 0.98 / 49.98)
                tmp2 = 0.02 + 49.98 * (0.98 / 49.98 - (1.0 - 2.0 * u) * tmp1)
                suffix = 0.35 ** (tmp2 ** -1.0)
                X = np.column_stack([X, suffix])
        elif name == "wfg9":
            X = np.column_stack([K, np.zeros((len(K), l))])
            X[:, -1] = 0.35
            for i in range(n_var - 2, k - 1, -1):
                u = X[:, i + 1:].mean(axis=1)
                X[:, i] = 0.35 ** ((0.02 + 1.96 * u) ** -1.0)
        else:
            X = np.column_stack([K, np.full((len(K), l), 0.35)])
        return X * xu

    def pareto_front(n: int = 3000) -> Array:
        if name in {"wfg4", "wfg5", "wfg6", "wfg7", "wfg8", "wfg9"}:
            W = _dirichlet_reference_points(n, n_obj, seed=307 + int(name[-1]))
            return (W / (np.linalg.norm(W, axis=1, keepdims=True) + 1e-12)) * S[None, :]
        # WFG1-WFG3 have mixed/disconnected/degenerate fronts. Generate an
        # official-form Pareto set in decision space, evaluate it, then retain
        # a deterministic maximin objective-space reference design.
        pool_n = max(4 * n, 4000)
        sobol_power = int(math.ceil(math.log2(pool_n)))
        U = qmc.Sobol(d=k, scramble=True, seed=331 + int(name[-1])).random_base2(sobol_power)[:pool_n]
        if name == "wfg1":
            U = U ** 50.0
        binary = np.array([[float((mask >> j) & 1) for j in range(k)]
                           for mask in range(2**k)], dtype=float)
        K = np.vstack([binary, U])
        PF = evaluate(optimal_decisions(K))
        target = min(n, len(PF))
        lo, hi = PF.min(axis=0), PF.max(axis=0)
        G = (PF - lo) / (hi - lo + 1e-12)
        if name == "wfg3":
            # The WFG3 front is degenerate. Order by its principal geodesic and
            # sample uniformly in cumulative arc length instead of forcing a
            # full-dimensional reference simplex onto a line.
            _, _, vt = np.linalg.svd(G - G.mean(axis=0), full_matrices=False)
            order = np.argsort((G - G.mean(axis=0)) @ vt[0])
            Q = PF[order]
            arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
            idx = np.searchsorted(arc, np.linspace(0.0, arc[-1], target))
            return Q[np.clip(idx, 0, len(Q) - 1)]
        # Match candidate Pareto points to deterministic simplex directions in
        # chunks. This mirrors the WFG toolkit's reference-direction sampling
        # while avoiding an O(pool*n) Python maximin loop.
        R = _dirichlet_reference_points(target, n_obj, seed=347 + int(name[-1]))
        R = R / (np.linalg.norm(R, axis=1, keepdims=True) + 1e-12)
        g2 = np.sum(G * G, axis=1)
        selected: List[int] = []
        seen = set()
        for start_ref in range(0, target, 128):
            Rc = R[start_ref : start_ref + 128]
            dot = G @ Rc.T
            d2 = np.maximum(g2[:, None] - dot * dot, 0.0)
            for idx in np.argmin(d2, axis=0):
                ii = int(idx)
                if ii not in seen:
                    seen.add(ii)
                    selected.append(ii)
        if len(selected) < target:
            # Disconnected WFG2 can map several directions to one component.
            # Fill only the missing slots by exact maximin selection.
            chosen = np.asarray(selected, dtype=int)
            if len(chosen) == 0:
                chosen = np.array([int(np.argmin(G[:, 0]))])
                selected = chosen.tolist(); seen = set(selected)
            min_d2 = ((G[:, None, :] - G[chosen][None, :, :]) ** 2).sum(axis=2).min(axis=1)
            min_d2[chosen] = -1.0
            while len(selected) < target:
                ii = int(np.argmax(min_d2))
                selected.append(ii); seen.add(ii)
                min_d2 = np.minimum(min_d2, np.sum((G - G[ii]) ** 2, axis=1))
                min_d2[np.asarray(selected, dtype=int)] = -1.0
        return PF[np.asarray(selected[:target], dtype=int)]

    return Problem(name.upper(), n_var, n_obj, xl, xu, evaluate, pareto_front)


def get_problem(name: str, n_obj: int = 3) -> Problem:
    lname = name.lower()
    if lname.startswith("zdt"):
        return make_zdt(lname)
    if lname.startswith("dtlz"):
        return make_dtlz(lname, n_obj=n_obj)
    if lname.startswith("wfg"):
        return make_wfg(lname, n_obj=n_obj)
    raise KeyError(name)


# ------------------------------
# Pareto utilities and indicators
# ------------------------------

def dominates(a: Array, b: Array) -> bool:
    return bool(np.all(a <= b) and np.any(a < b))


def nondominated_mask(F: Array) -> Array:
    F = np.asarray(F, dtype=float)
    n = len(F)
    if n == 0:
        return np.zeros(0, dtype=bool)
    if F.shape[1] == 2:
        # O(N log N) skyline for minimization, robust to ties.
        order = np.lexsort((F[:, 1], F[:, 0]))
        keep = np.zeros(n, dtype=bool)
        best_y = np.inf
        best_x = None
        i = 0
        while i < n:
            xval = F[order[i], 0]
            j = i
            group = []
            while j < n and abs(F[order[j], 0] - xval) <= 1e-14:
                group.append(order[j])
                j += 1
            min_y = min(F[g, 1] for g in group)
            if min_y < best_y - 1e-14:
                # For identical x, only the smallest y is nondominated; preserve one duplicate.
                candidates = [g for g in group if abs(F[g, 1] - min_y) <= 1e-14]
                keep[candidates[0]] = True
                best_y = min_y
            i = j
        return keep
    # Vectorized dominance matrix for the moderate population sizes used here.
    le = np.all(F[:, None, :] <= F[None, :, :], axis=2)
    lt = np.any(F[:, None, :] < F[None, :, :], axis=2)
    dom = le & lt
    return ~np.any(dom, axis=0)

def fast_nondominated_sort(F: Array) -> Tuple[List[Array], Array]:
    F = np.asarray(F, dtype=float)
    n = len(F)
    if n == 0:
        return [], np.zeros(0, dtype=int)
    le = np.all(F[:, None, :] <= F[None, :, :], axis=2)
    lt = np.any(F[:, None, :] < F[None, :, :], axis=2)
    dom = le & lt
    remaining = np.ones(n, dtype=bool)
    ranks = np.full(n, -1, dtype=int)
    fronts: List[Array] = []
    rank = 0
    while np.any(remaining):
        idx = np.flatnonzero(remaining)
        sub = dom[np.ix_(idx, idx)]
        front_local = ~np.any(sub, axis=0)
        front = idx[front_local]
        if len(front) == 0:  # numerical safety fallback
            front = idx[:1]
        ranks[front] = rank
        fronts.append(front)
        remaining[front] = False
        rank += 1
    return fronts, ranks

def crowding_distance(F: Array) -> Array:
    F = np.asarray(F, dtype=float)
    n, m = F.shape
    if n == 0:
        return np.zeros(0)
    if n <= 2:
        return np.full(n, np.inf)
    d = np.zeros(n)
    for j in range(m):
        order = np.argsort(F[:, j], kind="mergesort")
        d[order[0]] = d[order[-1]] = np.inf
        span = F[order[-1], j] - F[order[0], j]
        if span <= 1e-15:
            continue
        d[order[1:-1]] += (F[order[2:], j] - F[order[:-2], j]) / span
    return d


def farthest_point_select(F: Array, n: int, normalize: bool = True) -> Array:
    """Return selected points, preserving each objective extreme then maximin filling."""
    F = np.asarray(F, dtype=float)
    if len(F) <= n:
        return F.copy()
    if normalize:
        lo = F.min(axis=0)
        hi = F.max(axis=0)
        G = (F - lo) / (hi - lo + 1e-12)
    else:
        G = F
    selected: List[int] = []
    for j in range(G.shape[1]):
        idx = int(np.argmin(G[:, j]))
        if idx not in selected:
            selected.append(idx)
    if not selected:
        selected = [int(np.argmin(np.linalg.norm(G, axis=1)))]
    min_d2 = ((G[:, None, :] - G[np.asarray(selected)][None, :, :]) ** 2).sum(axis=2).min(axis=1)
    min_d2[np.asarray(selected)] = -1.0
    while len(selected) < n:
        j = int(np.argmax(min_d2))
        selected.append(j)
        d2 = ((G - G[j]) ** 2).sum(axis=1)
        min_d2 = np.minimum(min_d2, d2)
        min_d2[np.asarray(selected)] = -1.0
    return F[np.asarray(selected)]


def select_indices_farthest(F: Array, n: int) -> Array:
    if len(F) <= n:
        return np.arange(len(F), dtype=int)
    lo = F.min(axis=0)
    hi = F.max(axis=0)
    G = (F - lo) / (hi - lo + 1e-12)
    selected: List[int] = []
    for j in range(G.shape[1]):
        idx = int(np.argmin(G[:, j]))
        if idx not in selected:
            selected.append(idx)
    min_d2 = ((G[:, None, :] - G[np.asarray(selected)][None, :, :]) ** 2).sum(axis=2).min(axis=1)
    min_d2[np.asarray(selected)] = -1.0
    while len(selected) < n:
        idx = int(np.argmax(min_d2))
        selected.append(idx)
        min_d2 = np.minimum(min_d2, ((G - G[idx]) ** 2).sum(axis=1))
        min_d2[np.asarray(selected)] = -1.0
    return np.asarray(selected, dtype=int)


class Archive:
    def __init__(self, max_size: int = 500):
        self.max_size = int(max_size)
        self.X = np.empty((0, 0))
        self.F = np.empty((0, 0))

    def update(self, X: Array, F: Array) -> Tuple[bool, float]:
        X = _as_2d(X)
        F = _as_2d(F)
        any_entered = False
        max_novelty = 0.0
        for x, f in zip(X, F):
            if self.F.size == 0:
                self.X = x[None, :].copy()
                self.F = f[None, :].copy()
                any_entered = True
                max_novelty = 1.0
                continue
            # Exact incremental Pareto verifier.
            equal = np.all(np.isclose(self.F, f, atol=1e-11, rtol=1e-10), axis=1)
            if np.any(equal):
                continue
            old_dominates = np.all(self.F <= f, axis=1) & np.any(self.F < f, axis=1)
            if np.any(old_dominates):
                continue
            f_dominates = np.all(f <= self.F, axis=1) & np.any(f < self.F, axis=1)
            lo = np.minimum(self.F.min(axis=0), f)
            hi = np.maximum(self.F.max(axis=0), f)
            fn = (f - lo) / (hi - lo + 1e-12)
            oldn = (self.F - lo) / (hi - lo + 1e-12)
            nearest = float(np.linalg.norm(oldn - fn, axis=1).min())
            novelty = float(np.clip(nearest / 0.15, 0.0, 1.0))
            keep = ~f_dominates
            self.X = np.vstack([self.X[keep], x])
            self.F = np.vstack([self.F[keep], f])
            any_entered = True
            max_novelty = max(max_novelty, novelty)
            if len(self.F) > self.max_size + max(20, self.max_size // 10):
                # Cheap internal compression; final reporting still uses maximin selection.
                cd = crowding_distance(self.F)
                idx = np.argsort(-cd, kind="mergesort")[: self.max_size]
                self.X, self.F = self.X[idx], self.F[idx]
        return any_entered, max_novelty

    def output(self, n: int) -> Tuple[Array, Array]:
        if len(self.F) <= n:
            return self.X.copy(), self.F.copy()
        idx = select_indices_farthest(self.F, n)
        return self.X[idx].copy(), self.F[idx].copy()


def igd(reference: Array, approx: Array) -> float:
    R, A = np.asarray(reference), np.asarray(approx)
    d2 = ((R[:, None, :] - A[None, :, :]) ** 2).sum(axis=2)
    return float(np.sqrt(d2.min(axis=1)).mean())


def igd_plus(reference: Array, approx: Array) -> float:
    R, A = np.asarray(reference), np.asarray(approx)
    # d+(r,a) for minimization: only components where approximation is worse count.
    D = np.maximum(A[None, :, :] - R[:, None, :], 0.0)
    dist = np.sqrt((D * D).sum(axis=2))
    return float(dist.min(axis=1).mean())


def _hv_2d(F: Array, ref: Array) -> float:
    if len(F) == 0:
        return 0.0
    F = F[np.all(F < ref, axis=1)]
    if len(F) == 0:
        return 0.0
    F = F[nondominated_mask(F)]
    F = F[np.argsort(F[:, 0])]
    hv = 0.0
    prev_y = ref[1]
    for x, y in F:
        if y < prev_y:
            hv += max(ref[0] - x, 0.0) * (prev_y - y)
            prev_y = y
    return float(max(hv, 0.0))


def _hv_3d(F: Array, ref: Array) -> float:
    # Dimension sweep along first objective, integrating exact 2-D dominated area.
    if len(F) == 0:
        return 0.0
    F = F[np.all(F < ref, axis=1)]
    if len(F) == 0:
        return 0.0
    F = F[nondominated_mask(F)]
    xs = np.unique(np.r_[F[:, 0], ref[0]])
    xs.sort()
    hv = 0.0
    for i in range(len(xs) - 1):
        left, right = xs[i], xs[i + 1]
        active = F[F[:, 0] <= left + 1e-15][:, 1:]
        if len(active):
            hv += (right - left) * _hv_2d(active, ref[1:])
    return float(max(hv, 0.0))


def hypervolume(F: Array, ref: Array) -> float:
    F, ref = np.asarray(F, dtype=float), np.asarray(ref, dtype=float)
    if F.shape[1] == 2:
        return _hv_2d(F, ref)
    if F.shape[1] == 3:
        return _hv_3d(F, ref)
    # Deterministic quasi-Monte Carlo approximation for >3 objectives.
    # Used only as a secondary diagnostic, not for algorithm decisions.
    mask = np.all(F < ref, axis=1)
    F = F[mask]
    if len(F) == 0:
        return 0.0
    lo = np.minimum(F.min(axis=0), 0.0)
    rng = np.random.default_rng(99173 + F.shape[1] + len(F))
    samples = rng.random((50000, F.shape[1])) * (ref - lo) + lo
    dominated = np.any(np.all(F[:, None, :] <= samples[None, :, :], axis=2), axis=0)
    return float(dominated.mean() * np.prod(ref - lo))


def normalize_with_reference(F: Array, reference_pf: Array) -> Tuple[Array, Array, Array]:
    lo = reference_pf.min(axis=0)
    hi = reference_pf.max(axis=0)
    return (F - lo) / (hi - lo + 1e-12), lo, hi


def metric_bundle(F: Array, reference_pf: Array) -> Dict[str, float]:
    Fn, lo, hi = normalize_with_reference(F, reference_pf)
    Rn = (reference_pf - lo) / (hi - lo + 1e-12)
    ref = np.full(F.shape[1], 1.1)
    return {
        "igd": igd(Rn, Fn),
        "igd_plus": igd_plus(Rn, Fn),
        "hv": hypervolume(Fn, ref),
    }


# ------------------------------
# Sampling and variation
# ------------------------------

def latin_hypercube(n: int, d: int, rng: np.random.Generator) -> Array:
    U = rng.random((n, d))
    X = np.empty((n, d))
    for j in range(d):
        perm = rng.permutation(n)
        X[:, j] = (perm + U[:, j]) / n
    return X


def initialize(problem: Problem, n: int, seed: int) -> Tuple[np.random.Generator, Array, Array]:
    rng = np.random.default_rng(seed)
    U = latin_hypercube(n, problem.n_var, rng)
    X = problem.xl + U * (problem.xu - problem.xl)
    F = problem.evaluate(X)
    return rng, X, F


def repair_bounds(x: Array, xl: Array, xu: Array, parent: Optional[Array] = None) -> Array:
    y = np.asarray(x, dtype=float).copy()
    if parent is None:
        return np.clip(y, xl, xu)
    low = y < xl
    high = y > xu
    y[low] = 0.5 * (xl[low] + parent[low])
    y[high] = 0.5 * (xu[high] + parent[high])
    return np.clip(y, xl, xu)


def polynomial_mutation(x: Array, xl: Array, xu: Array, rng: np.random.Generator,
                        eta: float = 20.0, prob: Optional[float] = None) -> Array:
    y = np.asarray(x, dtype=float).copy()
    d = len(y)
    if prob is None:
        prob = 1.0 / d
    span = xu - xl
    for j in range(d):
        if rng.random() > prob or span[j] <= 0:
            continue
        delta1 = (y[j] - xl[j]) / span[j]
        delta2 = (xu[j] - y[j]) / span[j]
        r = rng.random()
        mut_pow = 1.0 / (eta + 1.0)
        if r <= 0.5:
            xy = 1.0 - delta1
            val = 2.0 * r + (1.0 - 2.0 * r) * (xy ** (eta + 1.0))
            deltaq = val ** mut_pow - 1.0
        else:
            xy = 1.0 - delta2
            val = 2.0 * (1.0 - r) + 2.0 * (r - 0.5) * (xy ** (eta + 1.0))
            deltaq = 1.0 - val ** mut_pow
        y[j] += deltaq * span[j]
    return np.clip(y, xl, xu)


def sbx_one(p1: Array, p2: Array, xl: Array, xu: Array, rng: np.random.Generator,
            eta: float = 20.0, prob_var: float = 0.5) -> Array:
    c = p1.copy()
    for j in range(len(p1)):
        if rng.random() > prob_var or abs(p1[j] - p2[j]) < 1e-14:
            continue
        x1, x2 = sorted((p1[j], p2[j]))
        rand = rng.random()
        beta = 1.0 + 2.0 * (x1 - xl[j]) / (x2 - x1)
        alpha = 2.0 - beta ** (-(eta + 1.0))
        if rand <= 1.0 / alpha:
            betaq = (rand * alpha) ** (1.0 / (eta + 1.0))
        else:
            betaq = (1.0 / (2.0 - rand * alpha)) ** (1.0 / (eta + 1.0))
        c1 = 0.5 * ((x1 + x2) - betaq * (x2 - x1))
        beta = 1.0 + 2.0 * (xu[j] - x2) / (x2 - x1)
        alpha = 2.0 - beta ** (-(eta + 1.0))
        if rand <= 1.0 / alpha:
            betaq = (rand * alpha) ** (1.0 / (eta + 1.0))
        else:
            betaq = (1.0 / (2.0 - rand * alpha)) ** (1.0 / (eta + 1.0))
        c2 = 0.5 * ((x1 + x2) + betaq * (x2 - x1))
        c[j] = c1 if rng.random() < 0.5 else c2
    return np.clip(c, xl, xu)


def de_binomial(target: Array, mutant: Array, cr: float, rng: np.random.Generator) -> Array:
    d = len(target)
    mask = rng.random(d) < cr
    mask[rng.integers(d)] = True
    return np.where(mask, mutant, target)


# ------------------------------
# Selection helpers
# ------------------------------

def nsga2_environmental_selection(X: Array, F: Array, n: int) -> Tuple[Array, Array, Array, Array]:
    fronts, ranks = fast_nondominated_sort(F)
    selected: List[int] = []
    crowd = np.zeros(len(F))
    for front in fronts:
        cd = crowding_distance(F[front])
        crowd[front] = cd
        if len(selected) + len(front) <= n:
            selected.extend(front.tolist())
        else:
            order = np.argsort(-cd, kind="mergesort")
            selected.extend(front[order[: n - len(selected)]].tolist())
            break
    idx = np.asarray(selected, dtype=int)
    new_fronts, new_ranks = fast_nondominated_sort(F[idx])
    new_crowd = np.zeros(len(idx))
    for front in new_fronts:
        new_crowd[front] = crowding_distance(F[idx][front])
    return X[idx], F[idx], new_ranks, new_crowd


def tournament(ranks: Array, crowd: Array, rng: np.random.Generator) -> int:
    a, b = rng.integers(0, len(ranks), size=2)
    if ranks[a] < ranks[b]:
        return int(a)
    if ranks[b] < ranks[a]:
        return int(b)
    if crowd[a] > crowd[b]:
        return int(a)
    if crowd[b] > crowd[a]:
        return int(b)
    return int(a if rng.random() < 0.5 else b)


def associate_to_reference(F: Array, W: Array) -> Tuple[Array, Array]:
    # Objective normalization then perpendicular-angle association.
    z = F.min(axis=0)
    nadir = F.max(axis=0)
    Y = (F - z) / (nadir - z + 1e-12)
    Yn = Y / (np.linalg.norm(Y, axis=1, keepdims=True) + 1e-12)
    Wn = W / (np.linalg.norm(W, axis=1, keepdims=True) + 1e-12)
    cos = np.clip(Yn @ Wn.T, -1.0, 1.0)
    assoc = np.argmax(cos, axis=1)
    angle = np.arccos(cos[np.arange(len(F)), assoc])
    return assoc, angle


def nsga3_environmental_selection(X: Array, F: Array, n: int, W: Array,
                                  rng: np.random.Generator) -> Tuple[Array, Array]:
    fronts, _ = fast_nondominated_sort(F)
    selected: List[int] = []
    last: Optional[Array] = None
    for front in fronts:
        if len(selected) + len(front) <= n:
            selected.extend(front.tolist())
        else:
            last = front
            break
    if len(selected) == n or last is None:
        idx = np.asarray(selected[:n], dtype=int)
        return X[idx], F[idx]

    all_idx = np.asarray(selected + last.tolist(), dtype=int)
    Fall = F[all_idx]
    assoc, angle = associate_to_reference(Fall, W)
    k_selected = len(selected)
    rho = np.bincount(assoc[:k_selected], minlength=len(W)).astype(int)
    candidates = {j: [] for j in range(len(W))}
    for local_idx in range(k_selected, len(all_idx)):
        candidates[int(assoc[local_idx])].append(local_idx)
    chosen_local = list(range(k_selected))
    while len(chosen_local) < n:
        available = [j for j, vals in candidates.items() if vals]
        if not available:
            remaining = [i for i in range(k_selected, len(all_idx)) if i not in chosen_local]
            rng.shuffle(remaining)
            chosen_local.extend(remaining[: n - len(chosen_local)])
            break
        min_rho = min(rho[j] for j in available)
        refs = [j for j in available if rho[j] == min_rho]
        j = int(rng.choice(refs))
        vals = candidates[j]
        if rho[j] == 0:
            pick = min(vals, key=lambda i: angle[i])
        else:
            pick = int(rng.choice(vals))
        chosen_local.append(pick)
        vals.remove(pick)
        rho[j] += 1
    idx = all_idx[np.asarray(chosen_local[:n], dtype=int)]
    return X[idx], F[idx]


# ------------------------------
# Baseline algorithms
# ------------------------------
@dataclass
class RunResult:
    algorithm: str
    problem: str
    seed: int
    X: Array
    F: Array
    evaluations: int
    trace: List[Dict[str, float]]
    diagnostics: Dict[str, object]


def run_nsga2(problem: Problem, seed: int, pop_size: int = 100, max_evals: int = 10100,
              trace_every: int = 10) -> RunResult:
    rng, X, F = initialize(problem, pop_size, seed)
    archive = Archive(max_size=5 * pop_size)
    archive.update(X, F)
    fronts, ranks = fast_nondominated_sort(F)
    crowd = np.zeros(pop_size)
    for front in fronts:
        crowd[front] = crowding_distance(F[front])
    evals = pop_size
    gen = 0
    trace: List[Dict[str, float]] = []
    while evals + pop_size <= max_evals:
        off = []
        for _ in range(pop_size):
            i = tournament(ranks, crowd, rng)
            j = tournament(ranks, crowd, rng)
            child = sbx_one(X[i], X[j], problem.xl, problem.xu, rng, eta=20.0)
            child = polynomial_mutation(child, problem.xl, problem.xu, rng, eta=20.0)
            off.append(child)
        Q = np.asarray(off)
        QF = problem.evaluate(Q)
        evals += pop_size
        archive.update(Q, QF)
        X, F, ranks, crowd = nsga2_environmental_selection(np.vstack([X, Q]), np.vstack([F, QF]), pop_size)
        gen += 1
        if gen % trace_every == 0:
            trace.append({"gen": gen, "evals": evals, "archive_size": len(archive.F)})
    outX, outF = archive.output(pop_size)
    return RunResult("NSGA-II", problem.name, seed, outX, outF, evals, trace, {})


def _tchebycheff(F: Array, W: Array, ideal: Array, nadir: Array) -> Array:
    del nadir
    Y = np.abs(F - ideal)
    ww = np.maximum(W, 1e-4)
    return np.max(ww * Y, axis=-1)


def run_moead(problem: Problem, seed: int, pop_size: int = 100, max_evals: int = 10100,
              T: int = 20, delta: float = 0.9, nr: int = 2, trace_every: int = 10) -> RunResult:
    rng, X, F = initialize(problem, pop_size, seed)
    W = _dirichlet_reference_points(pop_size, problem.n_obj, seed=541)
    d = ((W[:, None, :] - W[None, :, :]) ** 2).sum(axis=2)
    B = np.argsort(d, axis=1)[:, : min(T, pop_size)]
    ideal = F.min(axis=0)
    nadir = F.max(axis=0)
    archive = Archive(max_size=5 * pop_size)
    archive.update(X, F)
    evals = pop_size
    gen = 0
    trace: List[Dict[str, float]] = []
    while evals < max_evals:
        for i in rng.permutation(pop_size):
            if evals >= max_evals:
                break
            pool = B[i] if rng.random() < delta else np.arange(pop_size)
            replace = len(pool) < 3
            if rng.random() < 0.5:
                r1, r2 = rng.choice(pool, size=2, replace=len(pool) < 2)
                child = sbx_one(X[r1], X[r2], problem.xl, problem.xu, rng, eta=20.0)
            else:
                r1, r2 = rng.choice(pool, size=2, replace=len(pool) < 2)
                mutant = X[i] + 0.5 * (X[r1] - X[r2])
                child = de_binomial(X[i], mutant, cr=0.9, rng=rng)
                child = repair_bounds(child, problem.xl, problem.xu, parent=X[i])
            child = polynomial_mutation(child, problem.xl, problem.xu, rng, eta=20.0)
            childF = problem.evaluate(child)[0]
            evals += 1
            archive.update(child, childF)
            ideal = np.minimum(ideal, childF)
            nadir = np.maximum(nadir, childF)
            order = rng.permutation(B[i])
            replaced = 0
            for j in order:
                oldg = _tchebycheff(F[j][None, :], W[j][None, :], ideal, nadir)[0]
                newg = _tchebycheff(childF[None, :], W[j][None, :], ideal, nadir)[0]
                if newg <= oldg:
                    X[j], F[j] = child.copy(), childF.copy()
                    replaced += 1
                    if replaced >= nr:
                        break
        gen += 1
        if gen % trace_every == 0:
            trace.append({"gen": gen, "evals": evals, "archive_size": len(archive.F)})
    outX, outF = archive.output(pop_size)
    return RunResult("MOEA/D-DE", problem.name, seed, outX, outF, evals, trace, {})


def run_nsga3(problem: Problem, seed: int, pop_size: int = 100, max_evals: int = 10100,
              trace_every: int = 10) -> RunResult:
    rng, X, F = initialize(problem, pop_size, seed)
    W = _dirichlet_reference_points(pop_size, problem.n_obj, seed=557)
    archive = Archive(max_size=5 * pop_size)
    archive.update(X, F)
    evals = pop_size
    gen = 0
    trace: List[Dict[str, float]] = []
    # Reuse NSGA-II rank/crowding tournament for mating; NSGA-III differs in environmental selection.
    fronts, ranks = fast_nondominated_sort(F)
    crowd = np.zeros(pop_size)
    for front in fronts:
        crowd[front] = crowding_distance(F[front])
    while evals + pop_size <= max_evals:
        Q = []
        for _ in range(pop_size):
            i = tournament(ranks, crowd, rng)
            j = tournament(ranks, crowd, rng)
            child = sbx_one(X[i], X[j], problem.xl, problem.xu, rng, eta=30.0)
            child = polynomial_mutation(child, problem.xl, problem.xu, rng, eta=20.0)
            Q.append(child)
        Q = np.asarray(Q)
        QF = problem.evaluate(Q)
        evals += pop_size
        archive.update(Q, QF)
        X, F = nsga3_environmental_selection(np.vstack([X, Q]), np.vstack([F, QF]), pop_size, W, rng)
        fronts, ranks = fast_nondominated_sort(F)
        crowd = np.zeros(pop_size)
        for front in fronts:
            crowd[front] = crowding_distance(F[front])
        gen += 1
        if gen % trace_every == 0:
            trace.append({"gen": gen, "evals": evals, "archive_size": len(archive.F)})
    outX, outF = archive.output(pop_size)
    return RunResult("NSGA-III", problem.name, seed, outX, outF, evals, trace, {})

def _rdex_cal_fitness(F: Array, kappa: float = 0.05) -> Tuple[Array, Array, Array]:
    F = np.asarray(F, dtype=float)
    lo, hi = F.min(axis=0), F.max(axis=0)
    G = (F - lo) / (hi - lo + 1e-12)
    I = np.max(G[:, None, :] - G[None, :, :], axis=2)
    C = np.max(np.abs(I), axis=0)
    C = np.maximum(C, 1e-12)
    fitness = 1.0 - np.sum(np.exp(-I / C[None, :] / kappa), axis=0)
    return fitness, I, C


def _rdex_environmental(X: Array, F: Array, n: int, kappa: float = 0.05) -> Tuple[Array, Array]:
    if len(F) <= n:
        return X.copy(), F.copy()
    fitness, I, C = _rdex_cal_fitness(F, kappa)
    active = list(range(len(F)))
    while len(active) > n:
        values = fitness[np.asarray(active)]
        pos = int(np.argmin(values))
        worst = active[pos]
        # Faithful to the released MATLAB code: C is indexed by the removed solution.
        fitness += np.exp(-I[worst, :] / C[worst] / kappa)
        active.pop(pos)
    idx = np.asarray(active, dtype=int)
    return X[idx], F[idx]


def _rdex_selection(X: Array, F: Array, n: int, rng: np.random.Generator) -> Tuple[Array, Array, int]:
    nd = nondominated_mask(F)
    X, F = X[nd], F[nd]
    if len(F) == 0:
        return X, F, 0
    perm = rng.permutation(len(F))
    X, F = X[perm], F[perm]
    n_nd = len(F)
    if len(F) <= n:
        return X, F, n_nd
    lo, hi = F.min(axis=0), F.max(axis=0)
    G = (F - lo) / (hi - lo + 1e-12)
    d = np.linalg.norm(G[:, None, :] - G[None, :, :], axis=2)
    np.fill_diagonal(d, np.inf)
    sd = np.sort(d, axis=1)
    kth = min(2, sd.shape[1] - 1)
    radius = max(float(np.mean(sd[:, kth])), 1e-12)
    R = np.minimum(d / radius, 1.0)
    np.fill_diagonal(R, 1.0)
    active = np.arange(len(F))
    while len(active) > n:
        crowd_score = 1.0 - np.prod(R, axis=1)
        worst = int(np.argmax(crowd_score))
        active = np.delete(active, worst)
        R = np.delete(np.delete(R, worst, axis=0), worst, axis=1)
    return X[active], F[active], n_nd


def _rdex_tournament(fitness: Array, n: int, rng: np.random.Generator) -> Array:
    # Released code passes -CalFitness to a minimization tournament; equivalent to
    # choosing the larger CalFitness value from each random pair.
    cand = rng.integers(0, len(fitness), size=(n, 2))
    choose_left = fitness[cand[:, 0]] >= fitness[cand[:, 1]]
    return np.where(choose_left, cand[:, 0], cand[:, 1])


def _rdex_operator(P: Array, fitness: Array, problem: Problem, progress: float,
                   rng: np.random.Generator) -> Array:
    N, D = P.shape
    order = np.argsort(-fitness, kind="mergesort")
    Fm = np.array([0.6, 0.8, 1.0])
    CRm = np.array([0.1, 0.2, 1.0])
    scale = rng.choice(Fm, size=N)
    cr = rng.choice(CRm, size=N)
    p = max(int(np.floor(0.17 * N * (1.0 - 0.9 * progress) + 0.5)), 2)
    p = min(p, N)
    pbest = P[order[rng.integers(0, p, size=N)]]
    r1 = np.empty(N, dtype=int)
    r2 = np.empty(N, dtype=int)
    for i in range(N):
        pool1 = np.delete(np.arange(N), i)
        r1[i] = int(rng.choice(pool1))
        pool2 = np.delete(np.arange(N), np.sort([i, r1[i]]))
        r2[i] = int(rng.choice(pool2))
    V = P + scale[:, None] * (pbest - P + P[r1] - P[r2])
    mask = rng.random((N, D)) < cr[:, None]
    mask[np.arange(N), rng.integers(0, D, size=N)] = True
    Q = np.where(mask, V, P)
    perturb = rng.random((N, D)) < 0.2
    Q[perturb] += 0.2 * rng.standard_cauchy(np.count_nonzero(perturb))
    return np.clip(Q, problem.xl, problem.xu)


def _rdex_exploration(PCX: Array, PCF: Array, workX: Array, workF: Array,
                      n_nd: int, pop_size: int, problem: Problem,
                      rng: np.random.Generator) -> Array:
    if len(PCF) == 0:
        return np.empty((0, problem.n_var))
    lo, hi = PCF.min(axis=0), PCF.max(axis=0)
    A = (PCF - lo) / (hi - lo + 1e-12)
    B = (workF - lo) / (hi - lo + 1e-12)
    d_pc = np.linalg.norm(A[:, None, :] - A[None, :, :], axis=2)
    np.fill_diagonal(d_pc, np.inf)
    if len(A) == 1:
        r0 = 0.0
    else:
        sd = np.sort(d_pc, axis=1)
        r0 = float(np.mean(sd[:, min(2, sd.shape[1] - 1)]))
    radius = (n_nd / pop_size) * r0
    d = np.linalg.norm(A[:, None, :] - B[None, :, :], axis=2)
    sparse = np.flatnonzero(np.sum(d <= radius + 1e-15, axis=1) <= 1)
    if len(sparse) == 0:
        return np.empty((0, problem.n_var))
    base = PCX[sparse]
    guide = PCX[rng.integers(0, len(PCX), size=len(sparse))]
    n, D = base.shape
    scale = np.clip(0.7 + 0.2 * rng.standard_cauchy(n), 0.0, 1.0)
    cr = np.clip(rng.normal(0.5, 0.1, size=n), 0.0, 1.0)
    perm = rng.permutation(n)
    V = base + scale[:, None] * (base[perm] - guide)
    mask = rng.random((n, D)) < cr[:, None]
    mask[np.arange(n), rng.integers(0, D, size=n)] = True
    Q = np.where(mask, V, base)
    return np.clip(Q, problem.xl, problem.xu)


def run_rdex(problem: Problem, seed: int, pop_size: int = 100, max_evals: int = 10100,
             kappa: float = 0.05, trace_every: int = 10) -> RunResult:
    """Mechanism-faithful NumPy port of the released CEC-2025 RDEx-MOP code.

    This is a translation for controlled cross-problem comparison, not the official
    MATLAB/PlatEMO executable or an official competition score reproduction.
    """
    rng, workX, workF = initialize(problem, pop_size, seed)
    archive = Archive(max_size=5 * pop_size)
    archive.update(workX, workF)
    pcX, pcF, n_nd = _rdex_selection(workX, workF, pop_size, rng)
    auxX, auxF = pcX.copy(), pcF.copy()
    evals = pop_size
    gen = 0
    trace: List[Dict[str, float]] = []

    while evals < max_evals:
        exploreX = _rdex_exploration(pcX, pcF, workX, workF, n_nd, pop_size, problem, rng)
        remaining = max_evals - evals
        if len(exploreX) > remaining:
            exploreX = exploreX[:remaining]
        exploreF = problem.evaluate(exploreX) if len(exploreX) else np.empty((0, problem.n_obj))
        evals += len(exploreX)
        if len(exploreX):
            archive.update(exploreX, exploreF)
        if evals >= max_evals:
            pcX, pcF, n_nd = _rdex_selection(
                np.vstack([pcX, exploreX]), np.vstack([pcF, exploreF]), pop_size, rng
            )
            break

        use_aux = evals >= 0.5 * max_evals and rng.random() < 0.5
        if use_aux:
            if len(exploreX):
                auxX, auxF = _rdex_environmental(
                    np.vstack([auxX, exploreX]), np.vstack([auxF, exploreF]), pop_size, kappa
                )
            sourceX, sourceF = auxX, auxF
        else:
            if len(exploreX):
                workX, workF = _rdex_environmental(
                    np.vstack([workX, exploreX]), np.vstack([workF, exploreF]), pop_size, kappa
                )
            sourceX, sourceF = workX, workF

        fit, _, _ = _rdex_cal_fitness(sourceF, kappa)
        mating = _rdex_tournament(fit, pop_size, rng)
        parentsX = sourceX[mating]
        parent_fit, _, _ = _rdex_cal_fitness(sourceF[mating], kappa)
        newX = _rdex_operator(parentsX, parent_fit, problem, evals / max_evals, rng)
        remaining = max_evals - evals
        if len(newX) > remaining:
            newX = newX[:remaining]
        newF = problem.evaluate(newX)
        evals += len(newX)
        archive.update(newX, newF)

        if use_aux:
            auxX, auxF = _rdex_environmental(
                np.vstack([auxX, newX]), np.vstack([auxF, newF]), pop_size, kappa
            )
        else:
            workX, workF = _rdex_environmental(
                np.vstack([workX, newX]), np.vstack([workF, newF]), pop_size, kappa
            )

        pcX, pcF, n_nd = _rdex_selection(
            np.vstack([pcX, newX, exploreX, auxX]),
            np.vstack([pcF, newF, exploreF, auxF]),
            pop_size, rng,
        )
        auxX, auxF = pcX.copy(), pcF.copy()
        gen += 1
        if gen % trace_every == 0:
            trace.append({"gen": gen, "evals": evals, "archive_size": len(archive.F), "pc_size": len(pcF)})

    outX, outF = archive.output(pop_size)
    return RunResult("RDEx-MOP-port", problem.name, seed, outX, outF, evals, trace,
                     {"translation": "released MATLAB mechanisms, not official PlatEMO score"})


def _rvea_environmental_selection(X: Array, F: Array, n: int, W: Array,
                                  progress: float, alpha: float = 2.0) -> Tuple[Array, Array]:
    """Reference-vector guided selection using the angle-penalized distance (APD)."""
    ideal = F.min(axis=0)
    Y = np.maximum(F - ideal, 0.0)
    mag = np.linalg.norm(Y, axis=1)
    Yn = Y / (mag[:, None] + 1e-12)
    Wn = W / (np.linalg.norm(W, axis=1, keepdims=True) + 1e-12)
    cosine = np.clip(Yn @ Wn.T, -1.0, 1.0)
    assoc = np.argmax(cosine, axis=1)
    angles = np.arccos(cosine[np.arange(len(F)), assoc])

    ww_cos = np.clip(Wn @ Wn.T, -1.0, 1.0)
    np.fill_diagonal(ww_cos, -1.0)
    gamma = np.arccos(np.max(ww_cos, axis=1))
    gamma = np.maximum(gamma, 1e-12)
    penalty = F.shape[1] * (float(progress) ** alpha) * angles / gamma[assoc]
    apd = mag * (1.0 + penalty)

    selected: List[int] = []
    for j in range(len(W)):
        idx = np.flatnonzero(assoc == j)
        if len(idx):
            selected.append(int(idx[np.argmin(apd[idx])]))
    # The canonical RVEA population can temporarily shrink when reference cells are
    # empty. For a fair fixed-population comparison, deterministically fill from the
    # remaining lowest-APD candidates while avoiding duplicates.
    if len(selected) < n:
        selected_set = set(selected)
        for idx in np.argsort(apd, kind="mergesort"):
            ii = int(idx)
            if ii not in selected_set:
                selected.append(ii)
                selected_set.add(ii)
                if len(selected) == n:
                    break
    if len(selected) > n:
        selected = selected[:n]
    idx = np.asarray(selected, dtype=int)
    return X[idx], F[idx]


def run_rvea(problem: Problem, seed: int, pop_size: int = 100, max_evals: int = 10100,
             alpha: float = 2.0, adapt_fraction: float = 0.1, trace_every: int = 10) -> RunResult:
    rng, X, F = initialize(problem, pop_size, seed)
    W0 = _dirichlet_reference_points(pop_size, problem.n_obj, seed=563)
    W = W0 / (np.linalg.norm(W0, axis=1, keepdims=True) + 1e-12)
    archive = Archive(max_size=5 * pop_size)
    archive.update(X, F)
    evals = pop_size
    gen = 0
    max_gen = max(1, (max_evals - pop_size) // pop_size)
    adapt_every = max(1, int(round(adapt_fraction * max_gen)))
    trace: List[Dict[str, float]] = []
    fronts, ranks = fast_nondominated_sort(F)
    crowd = np.zeros(len(F))
    for front in fronts:
        crowd[front] = crowding_distance(F[front])

    while evals + pop_size <= max_evals:
        Q = []
        for _ in range(pop_size):
            i = tournament(ranks, crowd, rng)
            j = tournament(ranks, crowd, rng)
            child = sbx_one(X[i], X[j], problem.xl, problem.xu, rng, eta=30.0)
            child = polynomial_mutation(child, problem.xl, problem.xu, rng, eta=20.0)
            Q.append(child)
        Q = np.asarray(Q)
        QF = problem.evaluate(Q)
        evals += pop_size
        archive.update(Q, QF)
        gen += 1
        progress = min(gen / max_gen, 1.0)
        X, F = _rvea_environmental_selection(
            np.vstack([X, Q]), np.vstack([F, QF]), pop_size, W, progress, alpha=alpha
        )
        if gen % adapt_every == 0:
            span = np.maximum(F.max(axis=0) - F.min(axis=0), 1e-12)
            W = W0 * span[None, :]
            W /= np.linalg.norm(W, axis=1, keepdims=True) + 1e-12
        fronts, ranks = fast_nondominated_sort(F)
        crowd = np.zeros(len(F))
        for front in fronts:
            crowd[front] = crowding_distance(F[front])
        if gen % trace_every == 0:
            trace.append({"gen": gen, "evals": evals, "archive_size": len(archive.F)})
    outX, outF = archive.output(pop_size)
    return RunResult("RVEA", problem.name, seed, outX, outF, evals, trace, {})


# ------------------------------
# Proposed algorithm: MOSAIC-MOEA
# ------------------------------
class ContextualThompsonPortfolio:
    """Hierarchical fractional Beta-Bernoulli Thompson sampler.

    Local state learns context-specific success while a global posterior prevents sparse
    states from becoming brittle. Rewards are exact post-evaluation credits in [0,1].
    """

    def __init__(self, n_states: int, n_ops: int):
        self.a = np.ones((n_states, n_ops), dtype=float)
        self.b = np.ones((n_states, n_ops), dtype=float)
        self.ga = np.ones(n_ops, dtype=float)
        self.gb = np.ones(n_ops, dtype=float)
        self.counts = np.zeros((n_states, n_ops), dtype=int)
        self.reward_sum = np.zeros((n_states, n_ops), dtype=float)

    def choose(self, state: int, rng: np.random.Generator, epsilon: float = 0.08) -> int:
        n_ops = self.a.shape[1]
        if rng.random() < epsilon:
            # Prioritize least-tested arms inside the current state.
            c = self.counts[state]
            minc = c.min()
            return int(rng.choice(np.flatnonzero(c == minc)))
        local = rng.beta(self.a[state], self.b[state])
        global_ = rng.beta(self.ga, self.gb)
        # Small deterministic optimism for low-count operators.
        bonus = 0.08 / np.sqrt(1.0 + self.counts[state])
        score = 0.70 * local + 0.30 * global_ + bonus
        return int(np.argmax(score))

    def update(self, state: int, op: int, reward: float) -> None:
        r = float(np.clip(reward, 0.0, 1.0))
        self.a[state, op] += r
        self.b[state, op] += 1.0 - r
        self.ga[op] += 0.25 * r
        self.gb[op] += 0.25 * (1.0 - r)
        self.counts[state, op] += 1
        self.reward_sum[state, op] += r


def _smooth_tchebycheff(F: Array, W: Array, ideal: Array, nadir: Array, mu: float) -> Array:
    Y = np.maximum((F - ideal) / (nadir - ideal + 1e-12), 0.0)
    ww = np.maximum(W, 1e-4)
    A = (ww * Y) / mu
    amax = np.max(A, axis=-1, keepdims=True)
    return mu * (amax[..., 0] + np.log(np.sum(np.exp(A - amax), axis=-1)))


def _mosaic_scalar(F: Array, W: Array, ideal: Array, nadir: Array, mu: float,
                   theta: float = 0.18, blend: float = 0.0) -> Array:
    """Adaptive blend of preference-form STCH and reference-ray STCH-PBI.

    blend=0 uses the smooth multiplication-form Tchebycheff scalarization;
    blend=1 aligns the scalarization with the geometric objective ray W via
    reciprocal coefficients and a perpendicular-distance penalty.
    """
    legacy = _smooth_tchebycheff(F, W, ideal, nadir, mu)
    if blend <= 1e-12:
        return legacy
    Y = np.maximum((F - ideal) / (nadir - ideal + 1e-12), 0.0)
    coeff = 1.0 / np.maximum(W, 0.02)
    coeff = coeff / np.mean(coeff, axis=-1, keepdims=True)
    A = (coeff * Y) / mu
    amax = np.max(A, axis=-1, keepdims=True)
    aligned = mu * (amax[..., 0] + np.log(np.sum(np.exp(A - amax), axis=-1)))
    Wn = W / (np.linalg.norm(W, axis=-1, keepdims=True) + 1e-12)
    d1 = np.sum(Y * Wn, axis=-1, keepdims=True)
    d2 = np.linalg.norm(Y - d1 * Wn, axis=-1)
    aligned = aligned + theta * d2
    b = float(np.clip(blend, 0.0, 1.0))
    return (1.0 - b) * legacy + b * aligned

def _local_density(archive_F: Array, f: Array) -> Tuple[float, float]:
    if len(archive_F) < 3:
        return 0.0, 0.0
    lo = archive_F.min(axis=0)
    hi = archive_F.max(axis=0)
    G = (archive_F - lo) / (hi - lo + 1e-12)
    y = (f - lo) / (hi - lo + 1e-12)
    dist = np.linalg.norm(G - y, axis=1)
    dist.sort()
    nearest = float(dist[1] if dist[0] < 1e-10 and len(dist) > 1 else dist[0])
    k = min(4, len(dist) - 1)
    density = float(1.0 / (np.mean(dist[1 : k + 1]) + 1e-9)) if len(dist) > 1 else 0.0
    return density, nearest


def _mosaic_state(progress: float, stagnation: int, density: float, median_density: float) -> int:
    phase = 0 if progress < 0.33 else (1 if progress < 0.72 else 2)
    stuck = int(stagnation >= 5)
    crowded = int(density > median_density and median_density > 0)
    return phase * 4 + stuck * 2 + crowded


def _mosaic_operator(
    op: int,
    i: int,
    X: Array,
    F: Array,
    W: Array,
    B: Array,
    archive: Archive,
    successful_steps: List[List[Array]],
    progress: float,
    rng: np.random.Generator,
    problem: Problem,
    sparse_target_x: Optional[Array] = None,
    scalar_blend: float = 0.0,
) -> Array:
    n, d = X.shape
    neigh = B[i]
    pool = neigh if rng.random() < 0.85 else np.arange(n)
    if len(pool) < 3:
        pool = np.arange(n)
    # Base current-to-pbest/1 move, shared by exploit and residual variants.
    local_F = F[pool]
    ideal, nadir = F.min(axis=0), F.max(axis=0)
    mu = 0.02 + 0.13 * (1.0 - progress) ** 2
    scores = _mosaic_scalar(local_F, np.repeat(W[i][None, :], len(pool), axis=0), ideal, nadir, mu, blend=scalar_blend)
    top = pool[np.argsort(scores)[: max(2, int(math.ceil(0.2 * len(pool))))]]
    pbest = int(rng.choice(top))
    r1, r2 = rng.choice(pool, size=2, replace=False)
    Fscale = float(np.clip(0.55 + 0.20 * rng.standard_cauchy(), 0.15, 1.0))
    cr = float(np.clip(rng.normal(0.85, 0.10), 0.1, 1.0))
    base_mutant = X[i] + Fscale * (X[pbest] - X[i]) + Fscale * (X[r1] - X[r2])
    base = de_binomial(X[i], base_mutant, cr, rng)

    if op == 0:  # current-to-pbest exploitation
        child = base

    elif op == 1:  # global/niche DE exploration
        pool2 = np.arange(n)
        r = rng.choice(pool2, size=3, replace=False)
        F2 = float(np.clip(rng.normal(0.75, 0.18), 0.2, 1.2))
        mutant = X[r[0]] + F2 * (X[r[1]] - X[r[2]])
        child = de_binomial(X[i], mutant, float(np.clip(rng.normal(0.55, 0.2), 0.05, 1.0)), rng)

    elif op == 2:  # archive-manifold residual (PCA tangent + replay memory)
        ramp = np.clip((progress - 0.10) / 0.45, 0.0, 1.0)
        delta = np.zeros(d)
        if len(archive.F) >= min(6, d + 2):
            lo = archive.F.min(axis=0)
            hi = archive.F.max(axis=0)
            AF = (archive.F - lo) / (hi - lo + 1e-12)
            fi = (F[i] - lo) / (hi - lo + 1e-12)
            idx = np.argsort(np.linalg.norm(AF - fi, axis=1))[: min(10, len(AF))]
            AX = archive.X[idx]
            center = AX.mean(axis=0)
            Z = (AX - center) / (problem.xu - problem.xl + 1e-12)
            try:
                _, s, vt = np.linalg.svd(Z, full_matrices=False)
                k = max(1, min(problem.n_obj - 1, len(s)))
                coeff = rng.normal(size=k) * (s[:k] + 0.02)
                tangent = coeff @ vt[:k]
                delta += 0.20 * (problem.xu - problem.xl) * tangent
            except np.linalg.LinAlgError:
                pass
        if sparse_target_x is not None:
            # Coverage residual: transport a successful local proposal toward the
            # nearest currently under-occupied reference cell.
            delta += 0.30 * (sparse_target_x - X[i])
        if successful_steps[2] and rng.random() < 0.45:
            delta += 0.50 * successful_steps[2][rng.integers(len(successful_steps[2]))]
        child = base + ramp * delta

    elif op == 3:  # heavy-tail residual for valleys / stagnation
        ramp = np.clip((progress - 0.05) / 0.35, 0.0, 1.0)
        # Sparse component-wise Cauchy residual; scale shrinks over time but never vanishes.
        mask = rng.random(d) < min(0.25, 3.0 / d)
        if not mask.any():
            mask[rng.integers(d)] = True
        scale = (0.12 * (1.0 - progress) + 0.015) * (problem.xu - problem.xl)
        residual = np.zeros(d)
        residual[mask] = np.clip(rng.standard_cauchy(mask.sum()), -5.0, 5.0) * scale[mask]
        child = base + ramp * residual

    elif op == 4:  # SBX + polynomial mutation as a structurally different expert
        mate = int(rng.choice(pool))
        child = sbx_one(X[i], X[mate], problem.xl, problem.xu, rng, eta=15.0)
    else:
        raise ValueError(op)

    # Reachability-Consistent Projection (RCP): every expert is evaluated
    # under the same feasible proposal map, so contextual credit compares
    # operators rather than operator-by-repair confounding.
    child = np.clip(child, problem.xl, problem.xu)
    # All experts share a light mutation floor; this prevents frozen coordinates.
    child = polynomial_mutation(child, problem.xl, problem.xu, rng, eta=25.0, prob=0.5 / d)
    return child


def run_mosaic(problem: Problem, seed: int, pop_size: int = 100, max_evals: int = 10100,
               T: int = 20, nr: int = 3, trace_every: int = 10,
               ablation: Optional[str] = None) -> RunResult:
    """MOSAIC-MOEA v4: Multi-Operator Speculation with Archive/Indicator-Calibrated verification.

    All operator proposals use Reachability-Consistent Projection (RCP) before
    exact evaluation, eliminating repair-induced confounding in bandit credit.

    Ablations:
      - fixed: uniform random operator choice (no contextual Thompson portfolio)
      - no_stch: classical max Tchebycheff replacement
      - no_manifold: disables archive-manifold residual (maps op2 to exploit)
      - no_heavy: disables heavy-tail residual (maps op3 to exploit)
      - exploit_only: only current-to-pbest operator
      - force_coverage: enables periodic reference-cell population repair
      - legacy_scalar: multiplication-form STCH used by the v1 prototype
    """
    flags = set() if ablation is None else set(str(ablation).split("+"))
    rng, X, F = initialize(problem, pop_size, seed)
    W = _dirichlet_reference_points(pop_size, problem.n_obj, seed=601)
    dW = ((W[:, None, :] - W[None, :, :]) ** 2).sum(axis=2)
    B = np.argsort(dW, axis=1)[:, : min(T, pop_size)]
    init_assoc, _ = associate_to_reference(F, W)
    init_occupancy = float(np.count_nonzero(np.bincount(init_assoc, minlength=pop_size)) / pop_size)
    # Some decision-to-objective mappings (e.g. strong power-law bias) collapse
    # almost the entire initial population into a few reference cells. That is a
    # structural signal, so latch ray-aligned scalarization from the start.
    alignment_latch = bool(problem.n_obj > 2 and init_occupancy < 0.25)
    ideal = F.min(axis=0)
    nadir = F.max(axis=0)
    archive = Archive(max_size=5 * pop_size)
    archive.update(X, F)
    bandit = ContextualThompsonPortfolio(n_states=12, n_ops=5)
    stagnation = np.zeros(pop_size, dtype=int)
    successful_steps: List[List[Array]] = [[] for _ in range(5)]
    evals = pop_size
    gen = 0
    trace: List[Dict[str, float]] = []
    op_counts = np.zeros(5, dtype=int)
    op_rewards = np.zeros(5, dtype=float)

    while evals < max_evals:
        progress = evals / max_evals
        # Estimate current density distribution once per generation.
        densities = np.zeros(pop_size)
        for j in range(pop_size):
            densities[j] = _local_density(archive.F, F[j])[0] if len(archive.F) else 0.0
        med_density = float(np.median(densities))
        # Reference-cell occupancy is computed on the working population. It is a
        # deterministic state signal, not a learned surrogate.
        assoc_pop, _ = associate_to_reference(F, W)
        cell_counts = np.bincount(assoc_pop, minlength=pop_size)
        sparse_cells = np.flatnonzero(cell_counts == cell_counts.min())
        occupancy_ratio = float(np.count_nonzero(cell_counts) / pop_size)
        if problem.n_obj <= 2 or "legacy_scalar" in flags:
            scalar_blend = 0.0
        elif "aligned_scalar" in flags or alignment_latch:
            scalar_blend = 1.0
        else:
            # Conservative geometry gate: do not switch scalarization merely because
            # a healthy search temporarily occupies fewer cells. The initial
            # occupancy fingerprint is fixed before any optimization feedback, so it
            # cannot chase benchmark noise or create mid-run mode switching.
            scalar_blend = 0.0

        for i in rng.permutation(pop_size):
            if evals >= max_evals:
                break
            state = _mosaic_state(progress, int(stagnation[i]), float(densities[i]), med_density)
            if "exploit_only" in flags:
                op = 0
            elif "fixed" in flags:
                op = int(rng.integers(5))
            else:
                op = bandit.choose(state, rng, epsilon=0.10 if progress < 0.5 else 0.06)
            if "no_manifold" in flags and op == 2:
                op = 0
            if "no_heavy" in flags and op == 3:
                op = 0

            parent = X[i].copy()
            parentF = F[i].copy()
            sparse_target_x = None
            if op == 2 and len(archive.F) >= 3 and len(sparse_cells) > 0:
                target_cell = int(rng.choice(sparse_cells))
                # Select the archive design whose normalized objective direction is
                # closest to the under-filled reference vector.
                az = archive.F.min(axis=0)
                an = archive.F.max(axis=0)
                AY = np.maximum((archive.F - az) / (an - az + 1e-12), 0.0)
                AYn = AY / (np.linalg.norm(AY, axis=1, keepdims=True) + 1e-12)
                wt = W[target_cell] / (np.linalg.norm(W[target_cell]) + 1e-12)
                sparse_target_x = archive.X[int(np.argmax(AYn @ wt))]
            child = _mosaic_operator(
                op, i, X, F, W, B, archive, successful_steps, progress, rng, problem,
                sparse_target_x=sparse_target_x, scalar_blend=scalar_blend
            )
            childF = problem.evaluate(child)[0]
            evals += 1

            old_ideal, old_nadir = ideal.copy(), nadir.copy()
            ideal = np.minimum(ideal, childF)
            # Robust nadir tracks current + archive rather than monotonic historical worst.
            pooled_F = np.vstack([F, archive.F, childF[None, :]]) if len(archive.F) else np.vstack([F, childF])
            nadir = np.quantile(pooled_F, 0.95, axis=0)
            nadir = np.maximum(nadir, ideal + 1e-9)
            entered, novelty = archive.update(child, childF)

            neigh = B[i]
            order = rng.permutation(neigh)
            replaced = 0
            max_rel_improve = 0.0
            for j in order:
                if "no_stch" in flags:
                    oldg = _tchebycheff(F[j][None, :], W[j][None, :], ideal, nadir)[0]
                    newg = _tchebycheff(childF[None, :], W[j][None, :], ideal, nadir)[0]
                else:
                    mu = 0.008 + 0.10 * (1.0 - progress) ** 2
                    theta = 0.10 + 0.22 * progress
                    oldg = _mosaic_scalar(F[j][None, :], W[j][None, :], ideal, nadir, mu, theta=theta, blend=scalar_blend)[0]
                    newg = _mosaic_scalar(childF[None, :], W[j][None, :], ideal, nadir, mu, theta=theta, blend=scalar_blend)[0]
                rel = (oldg - newg) / (abs(oldg) + 1e-12)
                # Exact verifier: a speculative expert receives control only when the exact
                # scalarized objective improves. Near-ties may pass if the offspring is newly
                # nondominated and fills a sparse region.
                verify = newg <= oldg or (entered and novelty > 0.45 and newg <= oldg * 1.015)
                if verify:
                    X[j], F[j] = child.copy(), childF.copy()
                    stagnation[j] = 0
                    replaced += 1
                    max_rel_improve = max(max_rel_improve, float(max(rel, 0.0)))
                    if replaced >= nr:
                        break

            if replaced == 0:
                stagnation[i] += 1
            else:
                step = child - parent
                successful_steps[op].append(step)
                if len(successful_steps[op]) > 64:
                    successful_steps[op] = successful_steps[op][-64:]

            # Exact post-evaluation credit. No surrogate claim enters the posterior.
            r_conv = float(np.clip(max_rel_improve / 0.08, 0.0, 1.0))
            r_rep = float(np.clip(replaced / max(nr, 1), 0.0, 1.0))
            r_arc = 0.25 + 0.75 * novelty if entered else 0.0
            cz = np.minimum(F.min(axis=0), childF)
            cn = np.maximum(F.max(axis=0), childF)
            cy = np.maximum((childF - cz) / (cn - cz + 1e-12), 0.0)
            cyn = cy / (np.linalg.norm(cy) + 1e-12)
            child_cell = int(np.argmax((W / (np.linalg.norm(W, axis=1, keepdims=True) + 1e-12)) @ cyn))
            r_cover = 1.0 if entered and cell_counts[child_cell] == 0 else 0.0
            reward = float(np.clip(0.42 * r_conv + 0.20 * r_rep + 0.23 * r_arc + 0.15 * r_cover, 0.0, 1.0))
            if "fixed" not in flags and "exploit_only" not in flags:
                bandit.update(state, op, reward)
            op_counts[op] += 1
            op_rewards[op] += reward

        gen += 1
        if "force_coverage" in flags and gen % 4 == 0 and len(archive.F) >= pop_size // 2:
            # Exact coverage repair: combine the working population with a compact
            # nondominated archive sample, then apply NSGA-III reference niching.
            ax, af = archive.output(min(2 * pop_size, len(archive.F)))
            X, F = nsga3_environmental_selection(
                np.vstack([X, ax]), np.vstack([F, af]), pop_size, W, rng
            )
            stagnation = np.minimum(stagnation, 3)
            ideal = np.minimum(ideal, F.min(axis=0))
            nadir = np.maximum(np.quantile(np.vstack([F, af]), 0.95, axis=0), ideal + 1e-9)
        if gen % trace_every == 0:
            trace.append({
                "gen": gen,
                "evals": evals,
                "archive_size": len(archive.F),
                "mean_stagnation": float(stagnation.mean()),
                "mean_reward": float(op_rewards.sum() / max(op_counts.sum(), 1)),
                "occupancy_ratio": occupancy_ratio,
                "scalar_blend": scalar_blend,
            })

    outX, outF = archive.output(pop_size)
    name = "MOSAIC-MOEA" if ablation is None else f"MOSAIC[{ablation}]"
    diagnostics: Dict[str, object] = {
        "version": "MOSAIC-MOEA-v4-RCP",
        "repair": "reachability-consistent box projection",
        "operator_counts": op_counts.tolist(),
        "operator_mean_rewards": (op_rewards / np.maximum(op_counts, 1)).tolist(),
        "bandit_counts": bandit.counts.tolist(),
        "bandit_mean": (bandit.a / (bandit.a + bandit.b)).tolist(),
    }
    return RunResult(name, problem.name, seed, outX, outF, evals, trace, diagnostics)


ALGORITHMS = {
    "nsga2": run_nsga2,
    "moead": run_moead,
    "nsga3": run_nsga3,
    "rdex": run_rdex,
    "rvea": run_rvea,
    "mosaic": run_mosaic,
}
