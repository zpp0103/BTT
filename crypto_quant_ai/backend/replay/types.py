from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Sequence

# LIVE_TRADING guard
import os

if os.environ.get("LIVE_TRADING", "false").lower() == "true":
    raise RuntimeError("LIVE_TRADING must be false for local replay")


def _require_finite(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")


def _require_bool(value: bool, name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be bool")


@dataclass(frozen=True)
class ReplayConfig:
    initial_cash: float = 100000.0
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    start_time: datetime | None = None
    end_time: datetime | None = None
    symbol: str = "BTC"
    report_formats: tuple[str, ...] = ("markdown", "json")
    paper_trading: bool = True

    def __post_init__(self):
        _require_finite(self.initial_cash, "initial_cash")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        _require_finite(self.fee_bps, "fee_bps")
        if self.fee_bps < 0:
            raise ValueError("fee_bps must be non-negative")
        _require_finite(self.slippage_bps, "slippage_bps")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps must be non-negative")
        _require_bool(self.paper_trading, "paper_trading")
        if not self.paper_trading:
            raise ValueError("paper_trading must be true")
        if self.start_time is not None and self.end_time is not None:
            if self.start_time >= self.end_time:
                raise ValueError("start_time must be before end_time")
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not isinstance(self.report_formats, tuple):
            raise ValueError("report_formats must be a tuple")

    def to_backtest_config(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig

        return BacktestConfig(
            initial_cash=self.initial_cash,
            fee_bps=self.fee_bps,
            slippage_bps=self.slippage_bps,
            start_time=self.start_time,
            end_time=self.end_time,
            paper_trading=True,
        )


@dataclass(frozen=True)
class RiskGateSpec:
    min_confidence: float = 0.0
    max_position_fraction: float = 1.0
    min_risk_reward: float = 0.0
    min_stop_loss_pct: float = 0.0

    def __post_init__(self):
        _require_finite(self.min_confidence, "min_confidence")
        _require_finite(self.max_position_fraction, "max_position_fraction")
        _require_finite(self.min_risk_reward, "min_risk_reward")
        _require_finite(self.min_stop_loss_pct, "min_stop_loss_pct")
        if not (0.0 <= self.min_confidence <= 1.0):
            raise ValueError("min_confidence must be in [0,1]")
        if not (0.0 < self.max_position_fraction <= 1.0):
            raise ValueError("max_position_fraction must be in (0,1]")
        if self.min_risk_reward < 0:
            raise ValueError("min_risk_reward must be non-negative")
        if self.min_stop_loss_pct < 0:
            raise ValueError("min_stop_loss_pct must be non-negative")


@dataclass(frozen=True)
class StrategySpec:
    id: str
    name: str
    version: str
    description: str
    brains: tuple[str, ...]
    position_fraction: float = 0.10
    risk_gate: RiskGateSpec = field(default_factory=RiskGateSpec)
    warmup_candles: int = 0
    timeframe: str = "15m"

    def __post_init__(self):
        if not self.id or not self.id.strip():
            raise ValueError("id must be non-empty")
        if not self.name or not self.name.strip():
            raise ValueError("name must be non-empty")
        if not self.brains or len(self.brains) < 2:
            raise ValueError("brains must contain at least 2 entries")
        _require_finite(self.position_fraction, "position_fraction")
        if not (0.0 < self.position_fraction <= 1.0):
            raise ValueError("position_fraction must be in (0,1]")
        if self.warmup_candles < 0:
            raise ValueError("warmup_candles must be non-negative")
        if not self.timeframe or not self.timeframe.strip():
            raise ValueError("timeframe must be non-empty")


@dataclass
class SummarySection:
    total_return: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate_pct: float
    profit_factor: float
    final_equity: float
    initial_cash: float


@dataclass
class PerformanceSection:
    total_return: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate_pct: float
    profit_factor: float
    final_equity: float
    initial_cash: float


@dataclass
class AuditSection:
    total_orders: int
    executed: int
    rejected: int
    skipped: int
    trace_sample: list[dict[str, Any]]


@dataclass
class EquitySection:
    initial: float
    peak: float
    final: float
    points: list[tuple[datetime, float]]


@dataclass
class StrategyReport:
    title: str
    generated_at: datetime
    input_hash: str
    strategy: dict[str, Any]
    config: dict[str, Any]
    summary: SummarySection
    performance: PerformanceSection
    audit: AuditSection
    equity: EquitySection
    trades: list[dict[str, Any]]

    def to_json(self) -> str:
        return json.dumps(
            {
                "title": self.title,
                "generated_at": self.generated_at.isoformat(),
                "input_hash": self.input_hash,
                "strategy": self.strategy,
                "config": self.config,
                "summary": self.summary.__dict__,
                "performance": self.performance.__dict__,
                "audit": self.audit.__dict__,
                "equity": {
                    "initial": self.equity.initial,
                    "peak": self.equity.peak,
                    "final": self.equity.final,
                    "points": [
                        {"timestamp": ts.isoformat(), "equity": eq}
                        for ts, eq in self.equity.points
                    ],
                },
                "trades": self.trades,
            },
            indent=2,
            sort_keys=True,
        )


def canonical_hash(payload: Any) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
