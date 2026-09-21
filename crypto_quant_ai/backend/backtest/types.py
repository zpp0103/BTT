"""
Stage 4 — Backtest Engine: Types & Enums

Pure local backtest types. No network, no exchange, no real trading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class BacktestStatus(Enum):
    """Lifecycle status of a backtest run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TradeAction(Enum):
    """Trade direction for a backtest trade record."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class BacktestConfig:
    """
    Immutable backtest configuration.

    Safety: PAPER_TRADING must be true; LIVE mode must be false.
    All fields are validated at construction time.
    """
    initial_cash: float = 100_000.0
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    start_time: datetime | None = None
    end_time: datetime | None = None
    paper_trading: bool = True

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.fee_bps < 0:
            raise ValueError("fee_bps must be non-negative")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps must be non-negative")
        if not self.paper_trading:
            raise ValueError("paper_trading must be true for backtest")
        if self.start_time is not None and self.end_time is not None:
            if self.start_time >= self.end_time:
                raise ValueError("start_time must be before end_time")

    @property
    def fee_rate(self) -> float:
        """Fee as a decimal fraction (e.g. 10 bps → 0.001)."""
        return self.fee_bps / 10_000.0

    @property
    def slippage_rate(self) -> float:
        """Slippage as a decimal fraction."""
        return self.slippage_bps / 10_000.0


@dataclass(frozen=True)
class BacktestTrade:
    """
    Immutable record of a single backtest trade.

    A trade represents a fill (buy or sell) at a specific price/time.
    """
    trade_id: str
    timestamp: datetime
    symbol: str
    action: TradeAction
    quantity: float
    price: float
    fee: float
    slippage_cost: float
    cash_after: float
    position_after: float
    reason: str = ""

    def __post_init__(self) -> None:
        if self.action != TradeAction.HOLD and self.quantity <= 0:
            raise ValueError("quantity must be positive for BUY/SELL actions")
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.fee < 0:
            raise ValueError("fee must be non-negative")
        if self.slippage_cost < 0:
            raise ValueError("slippage_cost must be non-negative")
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be non-empty")


@dataclass(frozen=True)
class BacktestMetrics:
    """
    Immutable backtest performance metrics.

    All ratios are decimal fractions (e.g. 0.15 = 15%).
    """
    total_return: float
    total_return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate: float
    win_rate_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    profit_factor: float
    final_equity: float
    initial_cash: float

    def __post_init__(self) -> None:
        if self.total_trades < 0:
            raise ValueError("total_trades must be non-negative")
        if self.winning_trades < 0 or self.losing_trades < 0:
            raise ValueError("trade counts must be non-negative")
        if self.winning_trades + self.losing_trades > self.total_trades:
            raise ValueError("winning + losing must be <= total_trades")


@dataclass(frozen=True)
class BacktestResult:
    """
    Immutable backtest result: config + trades + metrics + status.
    """
    run_id: str
    config: BacktestConfig
    status: BacktestStatus
    trades: tuple[BacktestTrade, ...]
    metrics: BacktestMetrics | None
    started_at: datetime
    completed_at: datetime | None
    error_message: str = ""

    @property
    def is_completed(self) -> bool:
        return self.status == BacktestStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.status == BacktestStatus.FAILED


def make_run_id() -> str:
    """Generate a unique backtest run ID."""
    return f"bt_{uuid4().hex[:12]}"


def utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)
