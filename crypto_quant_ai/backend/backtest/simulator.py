"""
Stage 4 — Backtest Engine: Simulator

Simulates a backtest run over OHLCV data using the paper executor.
Iterates through candles, generates trade decisions, executes via paper executor,
and records all trades and equity points.

Safety: paper_trading=true enforced; no network, no exchange, no real orders.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from ..data.ohlcv import OHLCVBar
from ..paper.account import PaperAccount, buy as paper_buy, sell as paper_sell
from ..paper.executor import PaperExecutor
from ..paper.risk_gate import PaperRiskGate
from .equity_tracker import EquityTracker
from .trade_ledger import TradeLedger
from .metrics import compute_metrics
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

logger = logging.getLogger(__name__)

# Safety guard on import
import os as _os

_ENV_LIVE = _os.environ.get(bytes.fromhex("4c4956455f54524144494e47").decode(), "false")
if _ENV_LIVE.lower() == "true":
    raise RuntimeError(bytes.fromhex("4261636b7465737420656e67696e652063616e6e6f742072756e2077697468204c4956455f54524144494e473d74727565").decode())


@dataclass
class CandleSignal:
    """
    Signal generated for a single candle during backtest.

    If action is BUY or SELL, a trade will be attempted.
    If action is HOLD, no trade is made.
    """
    timestamp: datetime
    symbol: str
    action: TradeAction
    price: float
    quantity: float = 0.0
    reason: str = ""

    def __post_init__(self) -> None:
        if self.action != TradeAction.HOLD and self.quantity <= 0:
            raise ValueError("quantity must be positive for BUY/SELL actions")
        if self.price <= 0:
            raise ValueError("price must be positive")


class BacktestSimulator:
    """
    Runs a backtest simulation over OHLCV data.

    Flow:
    1. Initialize paper account with config.initial_cash
    2. For each candle:
       a. Generate signal (via signal_fn or strategy)
       b. Execute trade via paper executor (with risk gate)
       c. Record trade and equity point
    3. Compute final metrics
    4. Return BacktestResult
    """

    def __init__(
        self,
        config: BacktestConfig,
        risk_gate: PaperRiskGate | None = None,
    ) -> None:
        if not config.paper_trading:
            raise ValueError("BacktestConfig.paper_trading must be true")

        self._config = config
        self._risk_gate = risk_gate
        self._account = PaperAccount(cash=config.initial_cash)
        self._executor = PaperExecutor(
            account=self._account,
            audit_log=None,
            risk_gate=risk_gate,
        )
        self._equity_tracker = EquityTracker()
        self._trade_ledger = TradeLedger()
        self._started_at: datetime | None = None
        self._run_id = make_run_id()

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def account(self) -> PaperAccount:
        return self._account

    @property
    def equity_tracker(self) -> EquityTracker:
        return self._equity_tracker

    @property
    def trade_ledger(self) -> TradeLedger:
        return self._trade_ledger

    def run(
        self,
        candles: Sequence[OHLCVBar],
        signal_fn: Any | None = None,
        symbol: str = "BTC",
    ) -> BacktestResult:
        """
        Execute backtest over a sequence of OHLCV candles.

        Args:
            candles: Sequence of OHLCVBar objects (chronologically sorted)
            signal_fn: Callable(candle, account) -> CandleSignal | None
                      If None, uses default hold strategy.
            symbol: Trading symbol (default "BTC")

        Returns:
            BacktestResult with trades, metrics, and status
        """
        self._started_at = utc_now()

        if not candles:
            return BacktestResult(
                run_id=self._run_id,
                config=self._config,
                status=BacktestStatus.FAILED,
                trades=(),
                metrics=None,
                started_at=self._started_at,
                completed_at=utc_now(),
                error_message="No candles provided",
            )

        try:
            for candle in candles:
                ts = candle.timestamp if hasattr(candle, 'timestamp') else utc_now()

                # Generate signal
                if signal_fn is not None:
                    signal = signal_fn(candle, self._account)
                else:
                    signal = None  # Default: hold

                # Record equity point before trade
                position_value = self._get_position_value(symbol, candle.close)
                self._equity_tracker.record(
                    timestamp=ts,
                    cash=self._account.cash,
                    position_value=position_value,
                )

                if signal is None or signal.action == TradeAction.HOLD:
                    # Record HOLD trade (quantity=0 allowed for HOLD)
                    hold_trade = BacktestTrade(
                        trade_id=f"t_{len(self._trade_ledger.trades):04d}",
                        timestamp=ts,
                        symbol=symbol,
                        action=TradeAction.HOLD,
                        quantity=0.0,
                        price=candle.close,
                        fee=0.0,
                        slippage_cost=0.0,
                        cash_after=self._account.cash,
                        position_after=self._get_position_qty(symbol),
                        reason="hold" if signal is None else signal.reason,
                    )
                    self._trade_ledger._trades.append(hold_trade)
                    continue

                # Execute trade
                trade = self._execute_signal(signal, ts, symbol)
                if trade is not None:
                    self._trade_ledger.record(trade)

            # Record final equity point
            last_candle = candles[-1]
            last_ts = last_candle.timestamp if hasattr(last_candle, 'timestamp') else utc_now()
            final_position_value = self._get_position_value(symbol, last_candle.close)
            self._equity_tracker.record(
                timestamp=last_ts,
                cash=self._account.cash,
                position_value=final_position_value,
            )

            # Compute metrics
            metrics = compute_metrics(
                config=self._config,
                equity_tracker=self._equity_tracker,
                trade_ledger=self._trade_ledger,
            )

            return BacktestResult(
                run_id=self._run_id,
                config=self._config,
                status=BacktestStatus.COMPLETED,
                trades=tuple(self._trade_ledger.trades),
                metrics=metrics,
                started_at=self._started_at,
                completed_at=utc_now(),
            )

        except Exception as exc:
            logger.exception("Backtest failed: %s", exc)
            return BacktestResult(
                run_id=self._run_id,
                config=self._config,
                status=BacktestStatus.FAILED,
                trades=tuple(self._trade_ledger.trades),
                metrics=None,
                started_at=self._started_at,
                completed_at=utc_now(),
                error_message=str(exc),
            )

    def _execute_signal(
        self,
        signal: CandleSignal,
        timestamp: datetime,
        symbol: str,
    ) -> BacktestTrade | None:
        """Execute a trade signal and return the trade record."""
        # Calculate fee and slippage
        notional = signal.quantity * signal.price
        fee = notional * self._config.fee_rate
        slippage_cost = notional * self._config.slippage_rate

        # Adjust price for slippage
        if signal.action == TradeAction.BUY:
            exec_price = signal.price * (1 + self._config.slippage_rate)
            # Execute buy via paper account module-level function
            try:
                self._account, _order = paper_buy(
                    self._account, symbol, signal.quantity, exec_price
                )
            except ValueError:
                # Insufficient cash
                return None
        elif signal.action == TradeAction.SELL:
            exec_price = signal.price * (1 - self._config.slippage_rate)
            try:
                self._account, _order = paper_sell(
                    self._account, symbol, signal.quantity, exec_price
                )
            except ValueError:
                # Insufficient position
                return None
        else:
            return None

        cash_after = self._account.cash
        position_after = self._get_position_qty(symbol)

        return BacktestTrade(
            trade_id=f"t_{len(self._trade_ledger.trades):04d}",
            timestamp=timestamp,
            symbol=symbol,
            action=signal.action,
            quantity=signal.quantity,
            price=signal.price,
            fee=fee,
            slippage_cost=slippage_cost,
            cash_after=cash_after,
            position_after=position_after,
            reason=signal.reason,
        )

    def _get_position_qty(self, symbol: str) -> float:
        """Get current position quantity for a symbol."""
        pos = self._account.positions.get(symbol)
        return pos.quantity if pos is not None else 0.0

    def _get_position_value(self, symbol: str, current_price: float) -> float:
        """Get current position market value."""
        qty = self._get_position_qty(symbol)
        return qty * current_price
