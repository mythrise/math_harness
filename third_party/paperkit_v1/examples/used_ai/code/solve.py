"""Self-contained synthetic least-squares example; no competition data."""
from __future__ import annotations
import json
import math
from pathlib import Path
from collections.abc import Sequence


def fit(x: Sequence[float], y: Sequence[float]) -> dict[str, float]:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("Need at least two paired observations")
    if any(not math.isfinite(v) for v in [*x, *y]):
        raise ValueError("Nonfinite input")
    mx, my = sum(x) / len(x), sum(y) / len(y)
    denominator = sum((v - mx) ** 2 for v in x)
    if denominator == 0:
        raise ValueError("Zero variance")
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y)) / denominator
    intercept = my - slope * mx
    sse = sum((b - slope * a - intercept) ** 2 for a, b in zip(x, y))
    return {"slope": slope, "intercept": intercept, "sse": sse}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = fit([0, 1, 2, 3], [1, 3, 5, 7])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
