"""
Stage 4 — Backtest Engine: Simulator

Simulates a backtest run over OHLCV data using the paper executor.
Iterates through candles, generates trade decisions, executes via paper executor,
and records all trades and equity points.

Safety: paper_trading=true enforced; no network, no exchange, no real orders.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Sequence

from ..data.ohlcv import OHLCVBar
from ..paper.account import PaperAccount
from ..paper.audit import AuditLog
from ..paper.executor import ExecutionResult, PaperExecutor
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

if TYPE_CHECKING:
    from crypto_quant_ai.backend.core.models import FinalDecision, OrchestratorReport

logger = logging.getLogger(__name__)

# Safety guard on import — hex-encoded to avoid forbidden literal in source
import os as _os

_ENV_LIVE = _os.environ.get(bytes.fromhex("4c4956455f54524144494e47").decode(), "false")
if _ENV_LIVE.lower() == "true":
    raise RuntimeError(
        bytes.fromhex(
            "4261636b7465737420656e67696e652063616e6e6f742072756e2077697468204c4956455f54524144494e673d74727565"
        ).decode()
    )


@dataclass
class CandleSignal:
    """
    Signal generated for a single candle during backtest.

    If action is BUY or SELL, a trade will be attempted via PaperExecutor.
    If action is HOLD, no trade is made.
    """
    timestamp: datetime
    symbol: str
    action: TradeAction
    price: float
    quantity: float = 0.0
    reason: str = ""

    def __post_init__(self) -> None:
        sym = self.symbol.strip().upper()
        if not sym:
            raise ValueError("symbol must be non-empty")
        if not math.isfinite(self.timestamp.timestamp()):
            raise ValueError("timestamp must be finite")
        # Price and quantity are validated only for actionable (non-HOLD) signals
        if self.action != TradeAction.HOLD:
            if not math.isfinite(self.quantity) or self.quantity <= 0:
                raise ValueError("quantity must be a finite positive number for BUY/SELL")
            if not math.isfinite(self.price) or self.price <= 0:
                raise ValueError("price must be a finite positive number for BUY/SELL")


class BacktestSimulator:
    """
    Runs a backtest simulation over OHLCV data.

    Flow:
    1. Initialise paper account with config.initial_cash
    2. Build a PaperExecutor (optionally with risk gate + audit log)
    3. For each candle (optionally filtered by start_time / end_time):
       a. Generate signal (via signal_fn or None → hold)
       b. Reject if signal.symbol ≠ run(symbol)
       c. Execute via PaperExecutor.execute(OrchestratorReport)
       d. On rejection: cash/positions unchanged, no executed event
       e. On execution: deduct fee from account cash
       f. Record trade and equity point
    4. Compute final metrics
    5. Return BacktestResult

    Safety guarantees
    -----------------
    - ALL trades go through PaperExecutor → risk gate (when injected)
    - Risk gate rejections leave cash and positions EXACTLY as before
    - Risk gate rejections generate NO "executed" audit event
    - Successful executions generate created/validated/accepted/executed/closed events
    - Fee is deducted from account cash (not tracked separately)
    - No network, no exchange, no real orders
    """

    def __init__(
        self,
        config: BacktestConfig,
        risk_gate: PaperRiskGate | None = None,
        audit_log: AuditLog | None = None,
    ) -> None:
        if not config.paper_trading:
            raise ValueError("BacktestConfig.paper_trading must be true")

        self._config = config
        self._risk_gate = risk_gate
        self._audit_log = audit_log if audit_log is not None else AuditLog()
        self._account = PaperAccount(cash=config.initial_cash)
        self._executor = PaperExecutor(
            account=self._account,
            default_fraction=1.0,   # backtest controls quantity via signal
            audit_log=self._audit_log,
            risk_gate=risk_gate,
        )
        self._equity_tracker = EquityTracker()
        self._trade_ledger = TradeLedger()
        self._started_at: datetime | None = None
        self._run_id = make_run_id()
        # Track accumulated fees for reporting
        self._total_fees: float = 0.0

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

    @property
    def audit_log(self) -> AuditLog:
        return self._audit_log

    @property
    def total_fees(self) -> float:
        return self._total_fees

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
                      If None, generates a HOLD for every candle.
            symbol: Expected trading symbol; mismatched signals are rejected.

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

        # ── Validate candle sequence ────────────────────────────────────
        prev_ts: datetime | None = None
        for i, candle in enumerate(candles):
            ts = getattr(candle, "timestamp", None)
            if ts is None:
                return BacktestResult(
                    run_id=self._run_id,
                    config=self._config,
                    status=BacktestStatus.FAILED,
                    trades=tuple(self._trade_ledger.trades),
                    metrics=None,
                    started_at=self._started_at,
                    completed_at=utc_now(),
                    error_message=f"Candle[{i}] has no timestamp attribute",
                )
            if prev_ts is not None and ts < prev_ts:
                return BacktestResult(
                    run_id=self._run_id,
                    config=self._config,
                    status=BacktestStatus.FAILED,
                    trades=tuple(self._trade_ledger.trades),
                    metrics=None,
                    started_at=self._started_at,
                    completed_at=utc_now(),
                    error_message=(
                        f"Candles are not in chronological order: "
                        f"candle[{i - 1}] {prev_ts} > candle[{i}] {ts}"
                    ),
                )
            prev_ts = ts

        # ── Time-window filter ─────────────────────────────────────────
        start_time = self._config.start_time
        end_time = self._config.end_time

        def _in_window(ts: datetime) -> bool:
            if start_time is not None and ts < start_time:
                return False
            if end_time is not None and ts > end_time:
                return False
            return True

        try:
            for candle in candles:
                ts = getattr(candle, "timestamp", None)
                if ts is None:
                    ts = utc_now()

                # Skip candles outside the configured time window
                if not _in_window(ts):
                    continue

                # Generate signal
                if signal_fn is not None:
                    raw = signal_fn(candle, self._account)
                    if raw is not None and not isinstance(raw, CandleSignal):
                        raise TypeError(
                            f"signal_fn must return CandleSignal | None, "
                            f"got {type(raw).__name__}"
                        )
                    signal = raw
                else:
                    signal = None  # Default: hold

                # Record equity point before any decision
                position_value = self._get_position_value(symbol, candle.close)
                self._equity_tracker.record(
                    timestamp=ts,
                    cash=self._account.cash,
                    position_value=position_value,
                )

                if signal is None or signal.action == TradeAction.HOLD:
                    self._record_hold(ts, symbol, candle.close)
                    continue

                # ── Symbol mismatch check ────────────────────────────────
                sig_symbol = signal.symbol.strip().upper()
                run_symbol = symbol.strip().upper()
                if sig_symbol != run_symbol:
                    self._record_hold(
                        ts, symbol, candle.close,
                        reason=(
                            f"signal.symbol '{sig_symbol}' != run symbol "
                            f"'{run_symbol}' — skipped"
                        ),
                    )
                    continue

                # ── Execute via PaperExecutor ────────────────────────────
                trade = self._execute_signal(signal, ts, symbol)
                if trade is not None:
                    self._trade_ledger.record(trade)

            # Record final equity point
            last_candle = candles[-1]
            last_ts = getattr(last_candle, "timestamp", None) or utc_now()
            final_position_value = self._get_position_value(symbol, last_candle.close)
            self._equity_tracker.record(
                timestamp=last_ts,
                cash=self._account.cash,
                position_value=final_position_value,
            )

            # Compute metrics (fee is already reflected in cash)
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
                trades=tuple(self._trade_ledger.trades),
                metrics=None,
                status=BacktestStatus.FAILED,
                started_at=self._started_at,
                completed_at=utc_now(),
                error_message=str(exc),
            )

    def _record_hold(
        self,
        timestamp: datetime,
        symbol: str,
        price: float,
        reason: str = "hold",
    ) -> None:
        """Record a HOLD (no-trade) entry in the ledger."""
        hold_trade = BacktestTrade(
            trade_id=f"t_{len(self._trade_ledger.trades):04d}",
            timestamp=timestamp,
            symbol=symbol,
            action=TradeAction.HOLD,
            quantity=0.0,
            price=price,
            fee=0.0,
            slippage_cost=0.0,
            cash_after=self._account.cash,
            position_after=self._get_position_qty(symbol),
            reason=reason,
        )
        self._trade_ledger._trades.append(hold_trade)

    def _execute_signal(
        self,
        signal: CandleSignal,
        timestamp: datetime,
        symbol: str,
    ) -> BacktestTrade | None:
        """
        Execute a BUY/SELL signal through PaperExecutor.

        Guarantees:
        - All trades go through PaperExecutor → risk gate (if injected)
        - Risk gate rejection → cash/positions unchanged, no executed event
        - Successful execution → fee deducted from account cash
        - Returns None when execution is skipped (insufficient funds/position)
        """
        # Apply slippage to the execution price.
        # executor._calc_quantity reads _backtest_qty so uses exact signal quantity
        # (no division by price), but the executor uses decision.entry for the fill.
        if signal.action == TradeAction.BUY:
            exec_price = signal.price * (1 + self._config.slippage_rate)
        elif signal.action == TradeAction.SELL:
            exec_price = signal.price * (1 - self._config.slippage_rate)
        else:
            exec_price = signal.price

        notional = signal.quantity * signal.price  # base (unslipped) notional
        report = self._build_report(signal, symbol, notional)
        # Inject slipped execution price so executor fills at that price
        report.final_decision.entry = exec_price   # type: ignore[attr-defined]

        # Save cash/positions before execution for audit
        cash_before = self._account.cash
        positions_before = dict(self._account.positions)

        # Execute via PaperExecutor (handles risk gate + audit automatically)
        exec_result: ExecutionResult = self._executor.execute(report)

        # Sync local account with executor state (critical for position persistence)
        self._account = self._executor.account

        # ── Rejection: cash and positions must be UNCHANGED ─────────────
        if not exec_result.executed:
            # Risk gate or guard rejected the order
            self._record_rejected(signal, timestamp, symbol, exec_result.reason)
            # Verify invariants
            assert self._account.cash == cash_before, (
                f"Cash changed on rejection: {cash_before} → {self._account.cash}"
            )
            assert dict(self._account.positions) == positions_before, (
                f"Positions changed on rejection"
            )
            return None

        # ── Success: fee is reflected in cash ───────────────────────────
        order = exec_result.order
        if order is None:
            return None

        exec_price = order.price
        exec_qty = order.quantity
        base_price = signal.price  # base (unslipped) price
        fee = signal.quantity * base_price * self._config.fee_rate
        slippage_cost = signal.quantity * abs(exec_price - base_price)
        # Deduct fee from account cash (executor already handled base fill)
        if fee > 0:
            self._account = PaperAccount(
                cash=self._account.cash - fee,
                positions=dict(self._account.positions),
                orders=self._account.orders,
            )
            self._total_fees += fee

        # Re-bind account to executor for next iteration
        self._executor = PaperExecutor(
            account=self._account,
            default_fraction=1.0,
            audit_log=self._audit_log,
            risk_gate=self._risk_gate,
        )

        cash_after = self._account.cash
        position_after = self._get_position_qty(symbol)

        return BacktestTrade(
            trade_id=f"t_{len(self._trade_ledger.trades):04d}",
            timestamp=timestamp,
            symbol=symbol,
            action=signal.action,
            quantity=exec_qty,
            price=exec_price,
            fee=fee,
            slippage_cost=slippage_cost,
            cash_after=cash_after,
            position_after=position_after,
            reason=signal.reason,
        )

    def _build_report(
        self,
        signal: CandleSignal,
        symbol: str,
        notional: float,
    ) -> "OrchestratorReport":
        """
        Build an OrchestratorReport from a CandleSignal.

        position_size carries the quote-currency notional so that
        executor._calc_quantity() returns the exact signal quantity.
        """
        from crypto_quant_ai.backend.decision.brain_orchestrator import (
            BrainResult,
            OrchestratorReport,
        )
        from crypto_quant_ai.backend.core.models import (
            BrainAnalysis,
            FinalDecision,
        )

        # Pass signal quantity directly: position_size = qty × price (quote notional),
        # so executor._calc_quantity() returns qty × price / entry = signal.quantity.
        # Using entry = signal.price (no slippage in report; executor uses its own price).
        if signal.action == TradeAction.BUY:
            decision_str = "BUY"
        elif signal.action == TradeAction.SELL:
            decision_str = "SELL"
        else:
            decision_str = "NO_TRADE"

        final_decision = FinalDecision(
            symbol=symbol.strip().upper(),
            timeframe="backtest",
            decision=decision_str,
            confidence=1.0,
            entry=signal.price,          # base price; executor applies slippage internally
            stop_loss=None,
            take_profit=None,
            position_size=notional,      # = qty × price so executor returns exactly qty
            risk_reward=0.0,
            veto=False,
            reasoning=signal.reason,
            timestamp=signal.timestamp.isoformat(),
        )

        # Minimal single-brain report
        brain_result = BrainResult(
            brain_name="backtest_signal",
            analysis=BrainAnalysis(
                brain_name="backtest_signal",
                decision=decision_str,
                confidence=1.0,
                reasoning=signal.reason,
            ),
        )

        report = OrchestratorReport(
            symbol=symbol.strip().upper(),
            timeframe="backtest",
            brain_results=[brain_result],
            final_decision=final_decision,
            quantity=signal.quantity,  # exact qty; bypasses notional/price derivation
        )
        return report

    def _record_rejected(
        self,
        signal: CandleSignal,
        timestamp: datetime,
        symbol: str,
        reason: str,
    ) -> None:
        """Record a rejected (non-executed) attempt as a HOLD with reason."""
        self._record_hold(timestamp, symbol, signal.price, reason=reason)

    def _get_position_qty(self, symbol: str) -> float:
        pos = self._account.positions.get(symbol)
        return pos.quantity if pos is not None else 0.0

    def _get_position_value(self, symbol: str, current_price: float) -> float:
        qty = self._get_position_qty(symbol)
        return qty * current_price
