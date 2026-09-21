"""Stage 8 - Local Parameter Optimization & Walk-Forward Validation: types.

Pure local / paper-only research layer. No network, no external venue connection,
no real orders, no API credentials. Reuses Stage 4 BacktestSimulator,
Stage 5 ReplayConfig, and Stage 6 ExperimentRun / ComparisonEngine.

LIVE_TRADING must remain false; guarded at import time.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any, Sequence

if os.environ.get("LIVE_TRADING", "false").lower() in ("true", "1"):
    raise RuntimeError("Stage 8 optimization requires LIVE_TRADING=false (paper only).")


def _require_finite(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class ParamSpec:
    """A single tunable parameter with its search domain."""
    name: str
    low: float
    high: float
    step: float = 1.0
    integer: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("param name must be non-empty")
        _require_finite(self.low, "low")
        _require_finite(self.high, "high")
        _require_finite(self.step, "step")
        if self.step <= 0:
            raise ValueError("step must be positive")
        if self.low > self.high:
            raise ValueError("low must be <= high")


@dataclass(frozen=True)
class ParamSpace:
    """A collection of tunable parameters (the search space)."""
    params: tuple[ParamSpec, ...]

    def __post_init__(self) -> None:
        if not self.params:
            raise ValueError("ParamSpace must contain at least one parameter")
        names = [p.name for p in self.params]
        if len(names) != len(set(names)):
            dupes = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"duplicate parameter name: {dupes}")

    def grid_points(self, max_points: int = 2000) -> list[dict[str, float]]:
        """Enumerate the cartesian grid (capped to avoid combinatorial blow-up)."""
        import itertools
        per_param: list[list[float]] = []
        for p in self.params:
            n = max(1, int(round((p.high - p.low) / p.step)) + 1) if p.step > 0 else 1
            vals = [round(p.low + i * p.step, 6) for i in range(n)]
            if p.integer:
                vals = [float(int(round(v))) for v in vals]
            per_param.append(vals)
        combos = list(itertools.product(*per_param))
        if len(combos) > max_points:
            raise ValueError(
                f"grid has {len(combos)} points > max_points={max_points}; narrow the space"
            )
        return [dict(zip((p.name for p in self.params), c)) for c in combos]

    def sample(self, n: int, rng: Any | None = None) -> list[dict[str, float]]:
        """Sample n random points (deterministic when rng is seeded)."""
        import random
        r = rng if isinstance(rng, random.Random) else random.Random(rng)
        out: list[dict[str, float]] = []
        for _ in range(n):
            pt: dict[str, float] = {}
            for p in self.params:
                v = r.uniform(p.low, p.high)
                if p.integer:
                    v = float(int(round(v)))
                if p.step and p.step > 0:
                    v = p.low + round((v - p.low) / p.step) * p.step
                pt[p.name] = float(v)
            out.append(pt)
        return out


@dataclass(frozen=True)
class SearchConfig:
    method: str = "grid"
    max_points: int = 2000
    random_samples: int = 200
    metric: str = "sharpe_ratio"
    random_seed: int | None = 42

    def __post_init__(self) -> None:
        if self.method not in ("grid", "random"):
            raise ValueError("method must be 'grid' or 'random'")
        if self.max_points <= 0:
            raise ValueError("max_points must be positive")
        if self.random_samples <= 0:
            raise ValueError("random_samples must be positive")
        if not self.metric or not self.metric.strip():
            raise ValueError("metric must be non-empty")


@dataclass(frozen=True)
class WalkForwardConfig:
    train_size: int = 60
    test_size: int = 30
    step: int = 30

    def __post_init__(self) -> None:
        if self.train_size <= 0:
            raise ValueError("train_size must be positive")
        if self.test_size <= 0:
            raise ValueError("test_size must be positive")
        if self.step <= 0:
            raise ValueError("step must be positive")


@dataclass
class CandidateResult:
    params: dict[str, float]
    metrics: dict[str, float]
    is_completed: bool = True
    error: str = ""

    @property
    def objective(self) -> float:
        return float(self.metrics.get("sharpe_ratio", 0.0))


@dataclass
class WindowResult:
    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    best_params: dict[str, float]
    in_sample: dict[str, float]
    out_of_sample: dict[str, float]


@dataclass
class RobustnessReport:
    metric: str
    is_mean: float
    oos_mean: float
    decay: float
    stability_score: float
    windows: int

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "is_mean": self.is_mean,
            "oos_mean": self.oos_mean,
            "decay": self.decay,
            "stability_score": self.stability_score,
            "windows": self.windows,
        }


@dataclass
class OptimizationResult:
    space: dict
    search: dict
    walk_forward: dict
    candidates: list
    best_params: dict[str, float]
    best_metrics: dict[str, float]
    windows: list
    robustness: dict
    objective: str

    def to_dict(self) -> dict:
        return {
            "space": self.space,
            "search": self.search,
            "walk_forward": self.walk_forward,
            "candidates": [
                {"params": c.params, "metrics": c.metrics, "is_completed": c.is_completed}
                for c in self.candidates
            ],
            "best_params": self.best_params,
            "best_metrics": self.best_metrics,
            "windows": [vars(w) for w in self.windows],
            "robustness": self.robustness,
            "objective": self.objective,
        }
