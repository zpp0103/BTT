"""
Stage 4 — Backtest Engine: Public API exports
"""

from .types import (
    BacktestConfig,
    BacktestResult,
    BacktestStatus,
    BacktestTrade,
    BacktestMetrics,
    TradeAction,
    make_run_id,
    utc_now,
)
from .equity_tracker import EquityTracker, EquityPoint
from .trade_ledger import TradeLedger, ClosedTrade
from .metrics import compute_metrics
from .simulator import BacktestSimulator, CandleSignal

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "BacktestStatus",
    "BacktestTrade",
    "BacktestMetrics",
    "TradeAction",
    "make_run_id",
    "utc_now",
    "EquityTracker",
    "EquityPoint",
    "TradeLedger",
    "ClosedTrade",
    "compute_metrics",
    "BacktestSimulator",
    "CandleSignal",
]
