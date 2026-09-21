"""
Stage 4 — Backtest Engine: Types & Enums

Pure local backtest types. No network, no exchange, no real trading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
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
        if not isfinite(self.initial_cash) or self.initial_cash <= 0:
            raise ValueError("initial_cash must be a finite positive number")
        if not isfinite(self.fee_bps) or self.fee_bps < 0:
            raise ValueError("fee_bps must be a finite non-negative number")
        if not isfinite(self.slippage_bps) or self.slippage_bps < 0:
            raise ValueError("slippage_bps must be a finite non-negative number")
        if not self.paper_trading:
            raise ValueError("paper_trading must be true for backtest")
        if self.start_time is not None:
            ts_val = self.start_time.timestamp()
            if not isfinite(ts_val):
                raise ValueError("start_time must be a finite timestamp")
        if self.end_time is not None:
            ts_val = self.end_time.timestamp()
            if not isfinite(ts_val):
                raise ValueError("end_time must be a finite timestamp")
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
        if self.action != TradeAction.HOLD:
            if not isfinite(self.quantity) or self.quantity <= 0:
                raise ValueError("quantity must be a finite positive number for BUY/SELL")
        if not isfinite(self.price) or self.price <= 0:
            raise ValueError("price must be a finite positive number")
        if not isfinite(self.fee) or self.fee < 0:
            raise ValueError("fee must be a finite non-negative number")
        if not isfinite(self.slippage_cost) or self.slippage_cost < 0:
            raise ValueError("slippage_cost must be a finite non-negative number")
        if not isfinite(self.cash_after) or self.cash_after < 0:
            raise ValueError("cash_after must be a finite non-negative number")
        if not isfinite(self.position_after) or self.position_after < 0:
            raise ValueError("position_after must be a finite non-negative number")
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        ts_val = self.timestamp.timestamp()
        if not isfinite(ts_val):
            raise ValueError("timestamp must be finite")


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
        if not isfinite(self.total_return):
            raise ValueError("total_return must be finite")
        if not isfinite(self.total_return_pct):
            raise ValueError("total_return_pct must be finite")
        if not isfinite(self.max_drawdown) or self.max_drawdown < 0:
            raise ValueError("max_drawdown must be a finite non-negative number")
        if not isfinite(self.max_drawdown_pct) or self.max_drawdown_pct < 0:
            raise ValueError("max_drawdown_pct must be a finite non-negative number")
        if not isfinite(self.sharpe_ratio):
            raise ValueError("sharpe_ratio must be finite")
        if not isfinite(self.sortino_ratio):
            raise ValueError("sortino_ratio must be finite")
        if not isfinite(self.win_rate) or not (0 <= self.win_rate <= 1):
            raise ValueError("win_rate must be in [0, 1]")
        if not isfinite(self.win_rate_pct) or not (0 <= self.win_rate_pct <= 100):
            raise ValueError("win_rate_pct must be in [0, 100]")
        if self.total_trades < 0:
            raise ValueError("total_trades must be non-negative")
        if self.winning_trades < 0 or self.losing_trades < 0:
            raise ValueError("trade counts must be non-negative")
        if self.winning_trades + self.losing_trades > self.total_trades:
            raise ValueError("winning + losing must be <= total_trades")
        if not isfinite(self.avg_win):
            raise ValueError("avg_win must be finite")
        if not isfinite(self.avg_loss):
            raise ValueError("avg_loss must be finite")
        if self.profit_factor < 0:
            raise ValueError("profit_factor must be non-negative")
        if not isfinite(self.profit_factor) and self.profit_factor != float("inf"):
            raise ValueError("profit_factor must be finite or +inf")
        if not isfinite(self.final_equity) or self.final_equity < 0:
            raise ValueError("final_equity must be a finite non-negative number")
        if not isfinite(self.initial_cash) or self.initial_cash <= 0:
            raise ValueError("initial_cash must be a finite positive number")


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
