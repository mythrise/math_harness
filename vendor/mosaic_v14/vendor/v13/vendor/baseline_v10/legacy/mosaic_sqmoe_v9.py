"""Frozen entry point for MOSAIC-SQMoE v9-CGR.

Shared-backbone Quantile-routed Mixture of Search Experts with
Consensus-Gated Residual routing.

The implementation deliberately wraps the research module with one immutable
configuration.  Every routed proposal is evaluated through the original
objective function and counts against ``max_evals``.
"""
from __future__ import annotations

from typing import Optional

import moo_core as core
from mosaic_lqmoe import run_mosaic_lqmoe

VERSION = "MOSAIC-SQMoE-v9-CGR"
ABBREVIATION = "SQMoE-CGR"
FROZEN_FLAGS = (
    "no_routine_o5+soft_recovery+coordinate_tunnel+coordinate_consensus_qb"
)


def run_mosaic_sqmoe(
    problem: core.Problem,
    seed: int,
    pop_size: int = 100,
    max_evals: int = 10100,
    T: int = 20,
    nr: int = 3,
    trace_every: int = 5,
) -> core.RunResult:
    """Run the frozen SQMoE-CGR configuration.

    Parameters follow the existing MOSAIC runner.  The returned diagnostics
    retain the full route, pilot, memory, geometry, and FE audit trail.
    """
    result = run_mosaic_lqmoe(
        problem=problem,
        seed=seed,
        pop_size=pop_size,
        max_evals=max_evals,
        T=T,
        nr=nr,
        trace_every=trace_every,
        ablation=FROZEN_FLAGS,
        recovery_cooldown=12,
        max_recoveries=2,
    )
    result.algorithm = VERSION
    result.diagnostics["release_version"] = VERSION
    result.diagnostics["frozen_flags"] = FROZEN_FLAGS
    result.diagnostics["strict_fe_pass"] = bool(result.evaluations == max_evals)
    return result


__all__ = ["VERSION", "ABBREVIATION", "FROZEN_FLAGS", "run_mosaic_sqmoe"]
