"""Checked mathematical-programming adapters; learned hints never create certificates.
This is original adapter code around SciPy/HiGHS, not a reimplementation of EnCore.
All objectives use minimization. Numerical certificates are tolerance-based.
"""
from __future__ import annotations
import time
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp


def array(x, ndim=None, name='array'):
    a = np.asarray(x, dtype=float)
    if not np.all(np.isfinite(a)) or (ndim is not None and a.ndim != ndim):
        raise ValueError(f'{name}: finite {ndim}-dimensional values required')
    return a


def _linear_inputs(c, A, lo, hi, bounds, integrality):
    c = array(c, 1, 'c')
    if not len(c): raise ValueError('Empty objective')
    n = len(c)
    A = np.zeros((0, n)) if A is None else array(A, 2, 'A')
    lo = np.full(len(A), -np.inf) if lo is None else np.asarray(lo, float)
    hi = np.full(len(A), np.inf) if hi is None else np.asarray(hi, float)
    b = np.asarray([(0, np.inf)] * n if bounds is None else bounds, float)
    kinds = np.zeros(n, int) if integrality is None else np.asarray(integrality)
    if (A.shape[1] != n or lo.shape != (len(A),) or hi.shape != (len(A),)
        or b.shape != (n, 2) or kinds.shape != (n,)):
        raise ValueError('Incompatible linear-program shapes')
    if (np.isnan(lo).any() or np.isnan(hi).any() or np.isnan(b).any()
        or np.any(lo > hi) or np.any(b[:, 0] > b[:, 1])
        or np.isposinf(lo).any() or np.isneginf(hi).any()
        or np.isposinf(b[:, 0]).any() or np.isneginf(b[:, 1]).any()):
        raise ValueError('Invalid constraint/bound interval')
    # Semicontinuous and semiinteger variables require a different residual checker.
    if not np.isin(kinds, [0, 1]).all(): raise ValueError('Only continuous/general integer variables supported')
    return c, A, lo, hi, b, kinds.astype(int)


def primal_check(x, c, A, lo, hi, bounds, integrality, *, tolerance=1e-7):
    c, A, lo, hi, b, kinds = _linear_inputs(c, A, lo, hi, bounds, integrality)
    x = array(x, 1, 'x')
    if x.shape != c.shape or not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('Bad solution shape or tolerance')
    activity = A @ x
    v = max(0., np.max(lo - activity, initial=0.), np.max(activity - hi, initial=0.),
            np.max(b[:, 0] - x, initial=0.), np.max(x - b[:, 1], initial=0.))
    iv = float(np.max(np.abs(x[kinds == 1] - np.rint(x[kinds == 1])), initial=0.))
    objective = float(c @ x)
    if not np.isfinite(objective) or not np.isfinite(v): raise ValueError('Numerical overflow in verifier')
    return dict(feasible=bool(v <= tolerance and iv <= tolerance), objective=objective,
                max_primal_violation=float(v), max_integrality_violation=iv,
                tolerance=float(tolerance), certificate='NUMERICAL_PRIMAL_CHECK_NOT_FORMAL_PROOF')


def solve_linear(c, A=None, lower=None, upper=None, bounds=None, *, integrality=None,
                 seconds=10., scale_rows=True, tolerance=1e-7):
    """LP/MILP with row scaling, independent original-space residuals, honest statuses.
    HiGHS time limit is advisory to the native solver, not a hard process deadline.
    Wrap in the harness Docker timeout for an adversarial/production workload.
    """
    c, A, lo, hi, b, kinds = _linear_inputs(c, A, lower, upper, bounds, integrality)
    if not np.isfinite(seconds) or seconds <= 0: raise ValueError('Positive finite seconds required')
    scale = np.maximum(np.max(np.abs(A), axis=1, initial=0), 1.) if scale_rows else np.ones(len(A))
    As, ls, hs = A / scale[:, None], lo / scale, hi / scale
    start = time.perf_counter()
    if np.any(kinds):
        r = milp(c, integrality=kinds, bounds=Bounds(b[:, 0], b[:, 1]),
                 constraints=LinearConstraint(As, ls, hs),
                 options={'time_limit':float(seconds), 'mip_rel_gap':0.})
        dual = getattr(r, 'mip_dual_bound', None)
    else:
        eq = np.isfinite(ls) & np.isfinite(hs) & (ls == hs)
        upl, low = np.isfinite(hs) & ~eq, np.isfinite(ls) & ~eq
        Au = np.vstack([As[upl], -As[low]])
        bu = np.r_[hs[upl], -ls[low]]
        r = linprog(c, A_ub=Au if len(Au) else None, b_ub=bu if len(bu) else None,
                    A_eq=As[eq] if np.any(eq) else None, b_eq=ls[eq] if np.any(eq) else None,
                    bounds=b, method='highs', options={'time_limit':float(seconds)})
        dual = float(r.fun) if r.status == 0 else None
    status = {0:'SOLVER_OPTIMAL',1:'LIMIT',2:'INFEASIBLE',3:'UNBOUNDED',4:'SOLVER_ERROR'}.get(r.status,'UNKNOWN')
    out = dict(status=status, solver_status=int(r.status), message=str(r.message), x=None,
               feasible=False, objective=None, seconds=time.perf_counter()-start,
               time_limit=float(seconds), row_scaling=bool(scale_rows),
               dual_bound=float(dual) if dual is not None and np.isfinite(dual) else None,
               optimality_scope='ORIGINAL_PROBLEM_NUMERICAL_SOLVER_STATUS')
    if r.x is not None:
        out.update(primal_check(r.x, c, A, lo, hi, b, kinds, tolerance=tolerance))
        out['x'] = np.asarray(r.x).tolist()
        if not out['feasible']: out['status'] = 'REJECTED_PRIMAL'
    out['absolute_gap'] = (max(0., out['objective']-out['dual_bound'])
        if out['feasible'] and out['dual_bound'] is not None else None)
    return out


def milp_neighborhood(c, A, lower, upper, bounds, integrality, incumbent, free_indices, *, seconds=5.):
    """Exact subproblem around a verified incumbent. Never claim global optimality.
    free_indices may be proposed by an LLM or learned model; all others are fixed
    to the *existing feasible incumbent*, not an unverified predicted assignment.
    Continuous variables remain free. No incumbent-dependent cut reaches the global solver.
    """
    c, A, lo, hi, b, kinds = _linear_inputs(c, A, lower, upper, bounds, integrality)
    x = array(incumbent, 1, 'incumbent')
    before = primal_check(x,c,A,lo,hi,b,kinds)
    if not before['feasible']: raise ValueError('Incumbent is infeasible')
    free = set(free_indices)
    if any(isinstance(i,bool) or not isinstance(i,(int,np.integer)) or not 0 <= i < len(c) for i in free):
        raise ValueError('Invalid free variable index')
    local = b.copy()
    for i in range(len(c)):
        if kinds[i] and i not in free: local[i] = x[i]
    result = solve_linear(c,A,lo,hi,local,integrality=kinds,seconds=seconds)
    accepted = bool(result['feasible'] and result['objective'] <= before['objective'])
    # The neighborhood's dual bound is not valid for the original feasible set.
    return dict(x=result['x'] if accepted else x.tolist(),
                objective=result['objective'] if accepted else before['objective'],
                feasible=True, accepted=accepted, subproblem=result,
                dual_bound=None, optimality_scope='LOCAL_NEIGHBORHOOD_ONLY')


def pareto_audit(X, F, objective, *, tolerance=1e-8):
    """Independent minimization-front audit. Verification calls are counted separately.
    Does not retrain a surrogate, change MOSAIC, or count verifier calls as free search.
    """
    X, F = array(X,2,'X'), array(F,2,'F')
    if len(X) != len(F) or len(F) == 0 or F.shape[1] < 2: raise ValueError('Bad Pareto shapes')
    if not np.isfinite(tolerance) or tolerance <= 0: raise ValueError('Positive tolerance required')
    recomputed = array([objective(x.copy()) for x in X],2,'objectives')
    if recomputed.shape != F.shape: raise ValueError('Objective shape mismatch')
    faithful = bool(np.allclose(F,recomputed,rtol=0,atol=tolerance))
    dominated = [i for i in range(len(F)) if np.any(np.all(recomputed <= recomputed[i],axis=1)
                         & np.any(recomputed < recomputed[i],axis=1))]
    return dict(valid=faithful and not dominated, exact_objectives_match=faithful,
                dominated_indices=dominated, verification_evaluations=len(X),
                directions=['min']*F.shape[1], scope='OBJECTIVES_AND_NONDOMINANCE_WITHIN_RETURNED_SET_ONLY')
