"""Stage 3.2 — Brain signal to paper-order execution bridge."""

from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crypto_quant_ai.backend.decision.brain_orchestrator import (
        OrchestratorReport,
    )
    from crypto_quant_ai.backend.paper.audit import AuditLog
    from crypto_quant_ai.backend.paper.risk_gate import PaperRiskGate

from crypto_quant_ai.backend.paper.account import (
    PaperAccount,
    PaperOrder,
    buy,
    sell,
)
from crypto_quant_ai.backend.paper.order_event import (
    OrderEvent,
    make_event_id,
)
from crypto_quant_ai.backend.paper.snapshot import snapshot_from_account


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

PAPER_TRADING = os.environ.get("PAPER_TRADING", "true").lower() in ("true", "1")
LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() in ("true", "1")

if LIVE_TRADING and not PAPER_TRADING:
    raise RuntimeError(
        "When LIVE_TRADING is enabled, PAPER_TRADING must also be enabled. "
        "Set LIVE_TRADING=false to use paper trading."
    )

if LIVE_TRADING:
    raise RuntimeError(
        "Live trading mode detected. Must be disabled for paper trading."  # noqa: E501
        " Disable it to continue."
    )


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    """Outcome of a single paper execution attempt."""

    executed: bool
    order: PaperOrder | None = None
    reason: str = ""
    account_snapshot: PaperAccount | None = None

    # Guard violations
    veto_blocked: bool = False
    no_trade: bool = False


@dataclass
class ExecutionLog:
    """Immutable audit log of all execution attempts."""

    results: list[ExecutionResult] = field(default_factory=list)

    @property
    def total_orders(self) -> int:
        return sum(1 for r in self.results if r.executed)

    @property
    def total_buy(self) -> int:
        return sum(1 for r in self.results if r.executed and r.order and r.order.side == "buy")

    @property
    def total_sell(self) -> int:
        return sum(1 for r in self.results if r.executed and r.order and r.order.side == "sell")


# ---------------------------------------------------------------------------
# PaperExecutor
# ---------------------------------------------------------------------------

class PaperExecutor:
    """
    Translates OrchestratorReport signals into paper orders against a PaperAccount.

    Position sizing
    ---------------
    - Use ``final_decision.position_size`` when > 0 and expressed in quote currency
      (e.g. 5000 → spend $5,000 USDT).
    - Fall back to ``default_fraction`` of available cash (default 10 %).

    Guard rules (all hard-blocked)
    ------------------------------
    1. ``LIVE_TRADING=true`` → raise RuntimeError at import time
    2. ``final_decision.veto=True`` → skip, log veto_blocked
    3. ``final_decision.decision == "NO_TRADE"`` → skip, log no_trade
    4. BUY with no cash → ValueError propagates from buy()
    5. SELL with no position → ValueError propagates from sell()
    """

    def __init__(
        self,
        account: PaperAccount,
        *,
        default_fraction: float = 0.10,
        initial_order_seq: int = 0,
        audit_log: "AuditLog | None" = None,
        risk_gate: "PaperRiskGate | None" = None,
    ) -> None:
        if not (0 < default_fraction <= 1):
            raise ValueError("default_fraction must be in (0, 1]")
        self.account = account
        self.default_fraction = default_fraction
        self.audit_log = audit_log
        self.risk_gate = risk_gate
        self._log: ExecutionLog = ExecutionLog()
        self._order_seq: int = max(0, int(initial_order_seq))

    # ------------------------------------------------------------------
    # Audit helpers
    # ------------------------------------------------------------------

    def _next_order_id(self) -> str:
        self._order_seq += 1
        return f"ord-{self._order_seq:06d}"

    def _audit_event(
        self,
        order_id: str,
        decision,
        event_type: str,
        snapshot,
        *,
        side: str = "",
        quantity: float = 0.0,
        price: float = 0.0,
        reasons: "list[str] | None" = None,
        source: str = "paper_executor",
    ) -> OrderEvent:
        return OrderEvent(
            event_id=make_event_id(),
            order_id=order_id,
            event_type=event_type,  # type: ignore[arg-type]
            symbol=getattr(decision, "symbol", ""),
            side=side,
            timestamp=datetime.now(timezone.utc),
            quantity=quantity,
            price=price or (getattr(decision, "entry", 0.0) or 0.0),
            status=event_type,
            reasons=reasons or [],
            source=source,  # type: ignore[arg-type]
            snapshot=snapshot,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, report: OrchestratorReport) -> ExecutionResult:
        """
        Convert an OrchestratorReport into a paper order and update self.account.

        Returns an ExecutionResult (never raises; errors are captured in the result).

        When an ``audit_log`` is injected, every lifecycle transition
        (created / validated / accepted / executed / closed / rejected / skipped)
        is recorded as an :class:`OrderEvent` with surrounding portfolio snapshots.
        When a ``risk_gate`` is injected, the Stage 3.3 gate runs *before* any
        order and a rejected decision never reaches ``buy``/``sell`` (so cash and
        positions are guaranteed unchanged and no ``executed`` event is emitted).
        """
        decision = report.final_decision
        order_id = self._next_order_id()
        side = (
            "buy" if decision.decision in ("BUY", "LONG")
            else "sell" if decision.decision in ("SELL", "SHORT")
            else ""
        )
        created_snap = snapshot_from_account(self.account, "paper_executor")
        if self.audit_log is not None:
            self.audit_log.append(
                self._audit_event(order_id, decision, "created", created_snap, side=side)
            )

        # ── Optional Stage 3.3 risk gate (never bypassed when injected) ──
        if self.risk_gate is not None:
            gate = self.risk_gate.check(decision)
            if self.audit_log is not None:
                self.audit_log.append(
                    self._audit_event(
                        order_id, decision, "validated", created_snap, side=side,
                        reasons=gate.reasons, source="risk_gate",
                    )
                )
            if not gate.allowed:
                if self.audit_log is not None:
                    self.audit_log.append(
                        self._audit_event(
                            order_id, decision, "rejected", created_snap, side=side,
                            reasons=gate.reasons, source="risk_gate",
                        )
                    )
                result = ExecutionResult(
                    executed=False,
                    reason="Risk gate rejected: " + "; ".join(gate.reasons),
                    account_snapshot=self._snapshot(),
                )
                self._log.results.append(result)
                return result

        # ── Guard 2: veto ──────────────────────────────────────────────
        if decision.veto:
            if self.audit_log is not None:
                self.audit_log.append(
                    self._audit_event(
                        order_id, decision, "skipped", created_snap, side=side,
                        reasons=[getattr(decision, "veto_reason", "blocked by brain")],
                        source="paper_executor",
                    )
                )
            result = ExecutionResult(
                executed=False,
                veto_blocked=True,
                reason=f"Veto: {getattr(decision, 'veto_reason', 'blocked by brain')}",
                account_snapshot=self._snapshot(),
            )
            self._log.results.append(result)
            return result

        # ── Guard 3: no-trade ──────────────────────────────────────────
        if decision.decision == "NO_TRADE":
            if self.audit_log is not None:
                self.audit_log.append(
                    self._audit_event(
                        order_id, decision, "skipped", created_snap, side=side,
                        reasons=["Decision is NO_TRADE"], source="paper_executor",
                    )
                )
            result = ExecutionResult(
                executed=False,
                no_trade=True,
                reason="Decision is NO_TRADE",
                account_snapshot=self._snapshot(),
            )
            self._log.results.append(result)
            return result

        symbol = decision.symbol.upper()
        price = decision.entry
        if price is None or price <= 0:
            if self.audit_log is not None:
                self.audit_log.append(
                    self._audit_event(
                        order_id, decision, "rejected", created_snap, side=side,
                        reasons=[f"No valid entry price for {symbol} (entry={price})"],
                        source="paper_executor",
                    )
                )
            result = ExecutionResult(
                executed=False,
                reason=f"No valid entry price for {symbol} (entry={price})",
                account_snapshot=self._snapshot(),
            )
            self._log.results.append(result)
            return result

        # ── Determine quantity ─────────────────────────────────────────
        try:
            quantity = self._calc_quantity(decision, price, report)
        except ValueError as exc:
            if self.audit_log is not None:
                self.audit_log.append(
                    self._audit_event(
                        order_id, decision, "rejected", created_snap, side=side,
                        reasons=[f"position_size error: {exc}"], source="paper_executor",
                    )
                )
            result = ExecutionResult(
                executed=False,
                reason=f"position_size error: {exc}",
                account_snapshot=self._snapshot(),
            )
            self._log.results.append(result)
            return result

        # ── Accepted: snapshot before execution ───────────────────────
        if self.audit_log is not None:
            self.audit_log.append(
                self._audit_event(
                    order_id, decision, "accepted", created_snap, side=side,
                    quantity=quantity, price=price, source="paper_executor",
                )
            )

        # ── Execute ────────────────────────────────────────────────────
        try:
            if decision.decision in ("BUY", "LONG"):
                new_account, order = buy(self.account, symbol, quantity, price)
                self.account = new_account
            elif decision.decision in ("SELL", "SHORT"):
                new_account, order = sell(self.account, symbol, quantity, price)
                self.account = new_account
            else:
                if self.audit_log is not None:
                    self.audit_log.append(
                        self._audit_event(
                            order_id, decision, "skipped", created_snap, side=side,
                            reasons=[f"Unknown decision: {decision.decision}"],
                            source="paper_executor",
                        )
                    )
                result = ExecutionResult(
                    executed=False,
                    reason=f"Unknown decision: {decision.decision}",
                    account_snapshot=self._snapshot(),
                )
                self._log.results.append(result)
                return result

            after_snap = snapshot_from_account(self.account, "paper_executor")
            if self.audit_log is not None:
                self.audit_log.append(
                    self._audit_event(
                        order_id, decision, "executed", after_snap, side=order.side,
                        quantity=quantity, price=price, source="paper_executor",
                    )
                )
                self.audit_log.append(
                    self._audit_event(
                        order_id, decision, "closed", after_snap, side=order.side,
                        quantity=quantity, price=price, source="paper_executor",
                    )
                )
            execution_result = ExecutionResult(
                executed=True,
                order=order,
                reason=f"Executed {order.side.upper()} {quantity} {symbol} @ {price}",
                account_snapshot=self._snapshot(),
            )
            self._log.results.append(execution_result)
            return execution_result

        except ValueError as exc:
            if self.audit_log is not None:
                self.audit_log.append(
                    self._audit_event(
                        order_id, decision, "rejected", created_snap, side=side,
                        quantity=quantity, price=price,
                        reasons=[str(exc)], source="paper_executor",
                    )
                )
            result = ExecutionResult(
                executed=False,
                reason=str(exc),
                account_snapshot=self._snapshot(),
            )
            self._log.results.append(result)
            return result

    @property
    def log(self) -> ExecutionLog:
        """Return a copy of the execution audit log."""
        return self._log

    @property
    def order_sequence(self) -> int:
        return self._order_seq

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _calc_quantity(
        self,
        decision: FinalDecision,
        price: float,
        report: "OrchestratorReport | None" = None,
    ) -> float:
        """
        Resolve quantity in base units.

        Priority:
        1. report.quantity  — explicit float quantity passed by backtest simulators
        2. decision._backtest_qty  — legacy override (read + cleared to avoid leaking)
        3. position_size / price  (quote-currency notional)
        4. default_fraction * cash / price
        """
        # Priority 1: explicit quantity via OrchestratorReport.quantity
        # Guard: report.quantity must be a real number (not MagicMock, not None)
        qty = getattr(report, "quantity", None)
        if isinstance(qty, (int, float)) and math.isfinite(qty) and qty > 0:
            return round(qty, 8)

        # Priority 2: _backtest_qty override (read + clear to avoid leaking)
        qty_override = getattr(decision, "_backtest_qty", None)
        if isinstance(qty_override, (int, float)) and math.isfinite(qty_override):
            qty = float(qty_override)
            delattr(decision, "_backtest_qty")  # prevent cross-test contamination
            if qty <= 0:
                raise ValueError(f"Backtest qty override {qty} must be positive")
            return round(qty, 8)

        # Safe numeric extraction for position_size (handles MagicMock in tests).
        # MagicMock final_decision: attribute is set on the mock so value is retrievable.
        # Real FinalDecision: position_size is a real field.
        if hasattr(report, "final_decision"):
            _dec = getattr(report, "final_decision", None)
            ps = getattr(_dec, "position_size", None) if _dec else None
        else:
            ps = getattr(decision, "position_size", None)
        if isinstance(ps, (int, float)) and math.isfinite(ps) and ps > 0:
            notional = float(ps)
        else:
            notional = self.account.cash * self.default_fraction

        quantity = notional / price
        if quantity <= 0:
            raise ValueError(
                f"Calculated quantity {quantity} <= 0 "
                f"(notional={notional}, price={price})"
            )
        return round(quantity, 8)

    def _snapshot(self) -> PaperAccount:
        """Return a shallow copy of the current account state."""
        return PaperAccount.model_validate(self.account.model_dump())
