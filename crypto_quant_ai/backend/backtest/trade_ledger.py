"""
Stage 4 — Backtest Engine: Trade Ledger

Records all trades executed during a backtest run.
Provides query and analysis methods for win/loss computation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

from .types import BacktestTrade, TradeAction


@dataclass
class _PositionLot:
    """Internal representation of a buy lot (FIFO accounting)."""
    symbol: str
    quantity: float
    price: float
    timestamp: datetime


@dataclass
class ClosedTrade:
    """
    A completed round-trip trade (buy then sell) for P&L analysis.
    """
    symbol: str
    buy_price: float
    sell_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    buy_timestamp: datetime
    sell_timestamp: datetime

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.buy_price <= 0:
            raise ValueError("buy_price must be positive")
        if self.sell_price <= 0:
            raise ValueError("sell_price must be positive")

    @property
    def is_win(self) -> bool:
        """True if the trade was profitable."""
        return self.pnl > 0


class TradeLedger:
    """
    Records backtest trades and computes win/loss statistics.

    Uses FIFO accounting to match buys with sells for P&L calculation.
    """

    def __init__(self) -> None:
        self._trades: list[BacktestTrade] = []
        self._open_lots: dict[str, list[_PositionLot]] = defaultdict(list)
        self._closed_trades: list[ClosedTrade] = []

    def record(self, trade: BacktestTrade) -> None:
        """Record a trade and update FIFO lots."""
        self._trades.append(trade)

        if trade.action == TradeAction.BUY:
            self._open_lots[trade.symbol].append(
                _PositionLot(
                    symbol=trade.symbol,
                    quantity=trade.quantity,
                    price=trade.price,
                    timestamp=trade.timestamp,
                )
            )
        elif trade.action == TradeAction.SELL:
            self._match_sell(trade)
        # HOLD: no position change

    def _match_sell(self, sell_trade: BacktestTrade) -> None:
        """Match a sell against open lots using FIFO."""
        remaining = sell_trade.quantity
        lots = self._open_lots[sell_trade.symbol]

        while remaining > 0 and lots:
            lot = lots[0]
            match_qty = min(remaining, lot.quantity)

            pnl = (sell_trade.price - lot.price) * match_qty
            cost = lot.price * match_qty
            pnl_pct = pnl / cost if cost > 0 else 0.0

            self._closed_trades.append(
                ClosedTrade(
                    symbol=sell_trade.symbol,
                    buy_price=lot.price,
                    sell_price=sell_trade.price,
                    quantity=match_qty,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    buy_timestamp=lot.timestamp,
                    sell_timestamp=sell_trade.timestamp,
                )
            )

            remaining -= match_qty
            lot.quantity -= match_qty  # type: ignore[misc]
            if lot.quantity <= 0:
                lots.pop(0)

    @property
    def trades(self) -> Sequence[BacktestTrade]:
        """All recorded trades (read-only)."""
        return tuple(self._trades)

    @property
    def closed_trades(self) -> Sequence[ClosedTrade]:
        """All completed round-trip trades (read-only)."""
        return tuple(self._closed_trades)

    @property
    def total_trades(self) -> int:
        """Total number of recorded trades (including HOLD)."""
        return len(self._trades)

    @property
    def executed_trades(self) -> int:
        """Number of trades that were BUY or SELL (excluding HOLD)."""
        return sum(
            1 for t in self._trades
            if t.action in (TradeAction.BUY, TradeAction.SELL)
        )

    @property
    def winning_trades(self) -> int:
        """Number of profitable closed trades."""
        return sum(1 for ct in self._closed_trades if ct.is_win)

    @property
    def losing_trades(self) -> int:
        """Number of unprofitable closed trades."""
        return sum(1 for ct in self._closed_trades if not ct.is_win)

    @property
    def win_rate(self) -> float:
        """Win rate as a fraction (e.g. 0.6 = 60%)."""
        total = len(self._closed_trades)
        if total == 0:
            return 0.0
        return self.winning_trades / total

    @property
    def avg_win(self) -> float:
        """Average P&L of winning trades."""
        wins = [ct.pnl for ct in self._closed_trades if ct.is_win]
        if not wins:
            return 0.0
        return sum(wins) / len(wins)

    @property
    def avg_loss(self) -> float:
        """Average P&L of losing trades."""
        losses = [ct.pnl for ct in self._closed_trades if not ct.is_win]
        if not losses:
            return 0.0
        return sum(losses) / len(losses)

    @property
    def profit_factor(self) -> float:
        """Gross profit / gross loss (absolute)."""
        gross_profit = sum(ct.pnl for ct in self._closed_trades if ct.is_win)
        gross_loss = abs(sum(ct.pnl for ct in self._closed_trades if not ct.is_win))
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def reset(self) -> None:
        """Clear all recorded trades."""
        self._trades.clear()
        self._open_lots.clear()
        self._closed_trades.clear()
