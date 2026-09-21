"""
Stage 4 — Backtest Engine: Performance Metrics Calculator

Computes Sharpe ratio, Sortino ratio, and other performance metrics
from backtest equity curve and trade ledger data.
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Sequence

from .equity_tracker import EquityTracker
from .trade_ledger import TradeLedger
from .types import BacktestConfig, BacktestMetrics


def _safe_mean(values: Sequence[float]) -> float:
    """Mean of a sequence, 0.0 if empty."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _safe_std(values: Sequence[float]) -> float:
    """Population std dev of a sequence, 0.0 if empty or single element."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return math.sqrt(variance)


def _downside_std(values: Sequence[float], target: float = 0.0) -> float:
    """Downside deviation (only negative returns below target)."""
    n = len(values)
    if n < 2:
        return 0.0
    downside = [(min(v - target, 0.0)) ** 2 for v in values]
    return math.sqrt(sum(downside) / n)


def compute_metrics(
    config: BacktestConfig,
    equity_tracker: EquityTracker,
    trade_ledger: TradeLedger,
    risk_free_rate: float = 0.0,
) -> BacktestMetrics:
    """
    Compute backtest performance metrics from equity tracker and trade ledger.

    Args:
        config: Backtest configuration
        equity_tracker: Equity curve data
        trade_ledger: Trade records
        risk_free_rate: Annualized risk-free rate (default 0.0)

    Returns:
        BacktestMetrics with all computed ratios and statistics
    """
    # --- Returns series ---
    equity_points = list(equity_tracker.points)
    if len(equity_points) < 2:
        # Not enough data for ratio calculations
        final_equity = equity_tracker.final_equity
        total_return = final_equity - config.initial_cash
        return BacktestMetrics(
            total_return=total_return,
            total_return_pct=total_return / config.initial_cash if config.initial_cash > 0 else 0.0,
            max_drawdown=equity_tracker.max_drawdown,
            max_drawdown_pct=equity_tracker.max_drawdown_pct,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            win_rate=trade_ledger.win_rate,
            win_rate_pct=trade_ledger.win_rate * 100,
            total_trades=trade_ledger.total_trades,
            winning_trades=trade_ledger.winning_trades,
            losing_trades=trade_ledger.losing_trades,
            avg_win=trade_ledger.avg_win,
            avg_loss=trade_ledger.avg_loss,
            profit_factor=trade_ledger.profit_factor,
            final_equity=final_equity,
            initial_cash=config.initial_cash,
        )

    # Compute period returns
    returns: list[float] = []
    for i in range(1, len(equity_points)):
        prev = equity_points[i - 1].equity
        curr = equity_points[i].equity
        if prev > 0:
            returns.append((curr - prev) / prev)
        else:
            returns.append(0.0)

    # --- Total return ---
    initial = config.initial_cash
    final_equity = equity_tracker.final_equity
    total_return = final_equity - initial
    total_return_pct = total_return / initial if initial > 0 else 0.0

    # --- Drawdown ---
    max_dd = equity_tracker.max_drawdown
    max_dd_pct = equity_tracker.max_drawdown_pct

    # --- Sharpe ratio (annualized, assuming ~252 trading days) ---
    # For intraday: scale by sqrt(number of periods per year)
    # Simplified: use per-period returns directly
    avg_return = _safe_mean(returns)
    std_return = _safe_std(returns)

    # Estimate periods per year from time span
    time_span = equity_points[-1].timestamp - equity_points[0].timestamp
    total_seconds = time_span.total_seconds()
    if total_seconds > 0 and len(returns) > 0:
        avg_period_seconds = total_seconds / len(returns)
        periods_per_year = (365.25 * 24 * 3600) / avg_period_seconds
    else:
        periods_per_year = 252.0  # Default to daily

    annualization_factor = math.sqrt(periods_per_year)
    daily_risk_free = risk_free_rate / periods_per_year

    if std_return > 0:
        sharpe = ((avg_return - daily_risk_free) / std_return) * annualization_factor
    else:
        sharpe = 0.0

    # --- Sortino ratio ---
    downside = _downside_std(returns, target=daily_risk_free)
    if downside > 0:
        sortino = ((avg_return - daily_risk_free) / downside) * annualization_factor
    else:
        sortino = 0.0

    # --- Trade statistics ---
    win_rate = trade_ledger.win_rate
    total_trades = trade_ledger.total_trades
    winning = trade_ledger.winning_trades
    losing = trade_ledger.losing_trades
    avg_win = trade_ledger.avg_win
    avg_loss = trade_ledger.avg_loss
    profit_factor = trade_ledger.profit_factor

    return BacktestMetrics(
        total_return=total_return,
        total_return_pct=total_return_pct,
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        win_rate=win_rate,
        win_rate_pct=win_rate * 100,
        total_trades=total_trades,
        winning_trades=winning,
        losing_trades=losing,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        final_equity=final_equity,
        initial_cash=initial,
    )
