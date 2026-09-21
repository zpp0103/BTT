"""Stage 8 - optimization report generator."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Sequence

from .types import (
    ParamSpace,
    SearchConfig,
    WalkForwardConfig,
    CandidateResult,
    WindowResult,
    RobustnessReport,
    OptimizationResult,
)


def build_result(space: ParamSpace, search: SearchConfig, wf: WalkForwardConfig,
                 candidates: Sequence[CandidateResult],
                 best: CandidateResult | None,
                 windows: Sequence[WindowResult],
                 robustness: RobustnessReport | None, metric: str) -> OptimizationResult:
    return OptimizationResult(
        space={"params": [asdict(p) for p in space.params]},
        search={
            "method": search.method,
            "max_points": search.max_points,
            "random_samples": search.random_samples,
            "metric": search.metric,
            "random_seed": search.random_seed,
        },
        walk_forward={
            "train_size": wf.train_size,
            "test_size": wf.test_size,
            "step": wf.step,
        },
        candidates=list(candidates),
        best_params=best.params if best else {},
        best_metrics=best.metrics if best else {},
        windows=list(windows),
        robustness=robustness.to_dict() if robustness else {},
        objective=metric,
    )
