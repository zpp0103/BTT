"""Stage 9 - Layer 3: Research Intelligence.

Reuses Stage 8 optimize / walk-forward / robustness. Adds a sensitivity map
(derived from the candidate grid) and overfitting flags (derived from the
walk-forward windows and robustness report). No rewrite of Stage 8 logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from crypto_quant_ai.backend.optimize.search import run_optimization
from crypto_quant_ai.backend.optimize.types import (
    ParamSpace,
    SearchConfig,
    WalkForwardConfig,
    OptimizationResult,
)


@dataclass(frozen=True)
class ParamSensitivity:
    param: str
    values: list[float]
    metric_means: list[float]


@dataclass(frozen=True)
class ResearchReport:
    objective: str
    candidates_count: int
    completed_count: int
    best_params: dict[str, float]
    best_metrics: dict[str, float]
    robustness: dict[str, float]
    sensitivity: list[ParamSensitivity]
    overfit_flags: list[str]
    stability_score: float


def run_research(
    space: ParamSpace,
    candles: Sequence[Any],
    search: SearchConfig,
    wf: WalkForwardConfig,
    replay_config: Any,
) -> ResearchReport:
    result: OptimizationResult = run_optimization(space, candles, search, wf, replay_config)
    metric = search.metric

    candidates = [c for c in result.candidates if getattr(c, "is_completed", False)]
    sensitivity: list[ParamSensitivity] = []
    for p in space.params:
        name = p.name
        buckets: dict[float, list[float]] = {}
        for c in candidates:
            v = c.params.get(name)
            m = c.metrics.get(metric, 0.0)
            if v is None or not isinstance(m, (int, float)):
                continue
            buckets.setdefault(round(float(v), 6), []).append(float(m))
        values = sorted(buckets.keys())
        means = [sum(buckets[v]) / len(buckets[v]) for v in values]
        if values:
            sensitivity.append(ParamSensitivity(param=name, values=values, metric_means=means))

    overfit_flags: list[str] = []
    for w in result.windows:
        is_m = float(w.in_sample.get(metric, 0.0) or 0.0)
        oos_m = float(w.out_of_sample.get(metric, 0.0) or 0.0)
        if is_m > 0 and (is_m - oos_m) > 0.3 * abs(is_m) + 0.1:
            overfit_flags.append(
                f"window {w.index}: in-sample {is_m:.3f} >> out-of-sample {oos_m:.3f}"
            )
    rob = result.robustness or {}
    stability = float(rob.get("stability_score", 0.0) or 0.0)
    if rob and stability < 0.5:
        overfit_flags.append(f"low stability_score={stability:.3f}")

    rob_dict = dict(rob)

    return ResearchReport(
        objective=metric,
        candidates_count=len(result.candidates),
        completed_count=len(candidates),
        best_params=dict(result.best_params),
        best_metrics=dict(result.best_metrics),
        robustness=rob_dict,
        sensitivity=sensitivity,
        overfit_flags=overfit_flags,
        stability_score=stability,
    )
