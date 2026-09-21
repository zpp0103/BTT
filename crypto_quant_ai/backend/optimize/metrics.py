"""Stage 8 - robustness / out-of-sample stability metrics."""
from __future__ import annotations

import math
from typing import Sequence

from .types import WindowResult, RobustnessReport


def _mean(xs: Sequence[float]) -> float:
    xs = [x for x in xs if math.isfinite(x)]
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float]) -> float:
    xs = [x for x in xs if math.isfinite(x)]
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / n)


def compute_robustness(windows: Sequence[WindowResult],
                      metric: str = "sharpe_ratio") -> RobustnessReport:
    is_vals = [float(w.in_sample.get(metric, 0.0)) for w in windows]
    oos_vals = [float(w.out_of_sample.get(metric, 0.0)) for w in windows]
    is_mean = _mean(is_vals)
    oos_mean = _mean(oos_vals)
    decay = is_mean - oos_mean
    decay_std = _std([i - o for i, o in zip(is_vals, oos_vals)])
    denom = abs(is_mean) + 1e-9
    stability = 1.0 - min(1.0, decay_std / denom)
    return RobustnessReport(
        metric=metric,
        is_mean=is_mean,
        oos_mean=oos_mean,
        decay=decay,
        stability_score=stability,
        windows=len(windows),
    )
