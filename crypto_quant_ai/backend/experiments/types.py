"""Stage 6 — Local Experiment Runner: types and experiment hashing.

Pure local experiment layer. No network, no exchange, no real trading.
Reuses Stage 5 StrategyReplayer / ReplayConfig / StrategySpec and Stage 4
BacktestResult / BacktestMetrics / AuditLog.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Sequence

from crypto_quant_ai.backend.replay.types import (
    ReplayConfig,
    StrategySpec,
    RiskGateSpec,
    canonical_hash,
)


class RunStatus(str, Enum):
    """Outcome of a single strategy run inside an experiment."""
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ExperimentConfig:
    """Immutable description of a multi-strategy experiment."""

    experiment_id: str
    name: str
    description: str
    strategies: tuple[StrategySpec, ...]
    replay_config: ReplayConfig
    baseline_strategy_id: Optional[str] = None
    fail_fast: bool = False

    def __post_init__(self) -> None:
        if not self.experiment_id or not self.experiment_id.strip():
            raise ValueError("experiment_id must be non-empty")
        if not self.name or not self.name.strip():
            raise ValueError("name must be non-empty")
        if not self.strategies:
            raise ValueError("at least one strategy is required")
        ids = [s.id for s in self.strategies]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate strategy id: {dupes}")
        if self.baseline_strategy_id is not None:
            if self.baseline_strategy_id not in ids:
                raise ValueError("baseline_strategy_id must match a strategy id")
        if not self.replay_config.paper_trading:
            raise ValueError("replay_config.paper_trading must be true")
        # All numeric values (cash/fees/gate thresholds) are validated by the
        # nested ReplayConfig / RiskGateSpec classes, which already enforce
        # finite, positive, paper-only constraints.


@dataclass
class ExperimentRun:
    """Result of running one strategy inside an experiment."""

    strategy_id: str
    status: RunStatus
    input_hash: str = ""
    final_equity: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    win_rate_pct: float = 0.0
    total_trades: int = 0
    executed_orders: int = 0
    rejected_orders: int = 0
    error_message: str = ""


@dataclass
class ComparisonRow:
    """One ranked strategy row in the comparison report."""

    strategy_id: str
    rank: int
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate_pct: float
    total_trades: int
    rejected_orders: int
    vs_baseline_return_pct: float


@dataclass
class ExperimentReport:
    """Aggregated, serializable experiment report."""

    experiment_id: str
    generated_at: datetime
    experiment_hash: str
    config: dict
    strategy_ids: list
    completed: int
    failed: int
    skipped: int
    runs: list
    comparison: list
    baseline_strategy_id: Optional[str]
    baseline_comparison: dict
    input_hashes: dict
    error_messages: dict
    safety_summary: str

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "generated_at": self.generated_at.isoformat(),
            "experiment_hash": self.experiment_hash,
            "config": self.config,
            "strategy_ids": self.strategy_ids,
            "completed": self.completed,
            "failed": self.failed,
            "skipped": self.skipped,
            "runs": [dataclasses.asdict(r) for r in self.runs],
            "comparison": [dataclasses.asdict(r) for r in self.comparison],
            "baseline_strategy_id": self.baseline_strategy_id,
            "baseline_comparison": self.baseline_comparison,
            "input_hashes": self.input_hashes,
            "error_messages": self.error_messages,
            "safety_summary": self.safety_summary,
        }


def _candle_point(candle: Any) -> dict:
    ts = getattr(candle, "timestamp", None)
    if isinstance(ts, datetime):
        ts = ts.isoformat()
    elif ts is not None:
        ts = str(ts)
    return {
        "timestamp": ts,
        "open": float(getattr(candle, "open", 0.0)),
        "high": float(getattr(candle, "high", 0.0)),
        "low": float(getattr(candle, "low", 0.0)),
        "close": float(getattr(candle, "close", 0.0)),
        "volume": float(getattr(candle, "volume", 0.0)),
    }


def experiment_payload(config: ExperimentConfig, candles: Sequence[Any]) -> dict:
    """Build a canonical, hashable payload for the experiment hash.

    Includes ExperimentConfig, ReplayConfig, every StrategySpec (with its
    RiskGateSpec), baseline_strategy_id, fail_fast, and the raw candle series
    (timestamp/open/high/low/close/volume) in original order. generated_at is
    intentionally NOT included.
    """
    return {
        "experiment_id": config.experiment_id,
        "name": config.name,
        "description": config.description,
        "fail_fast": config.fail_fast,
        "baseline_strategy_id": config.baseline_strategy_id,
        "replay_config": dataclasses.asdict(config.replay_config),
        "strategies": [dataclasses.asdict(s) for s in config.strategies],
        "candles": [_candle_point(c) for c in candles],
    }


def compute_experiment_hash(config: ExperimentConfig, candles: Sequence[Any]) -> str:
    """Deterministic SHA-256 of the experiment payload (canonical JSON)."""
    return canonical_hash(experiment_payload(config, candles))
