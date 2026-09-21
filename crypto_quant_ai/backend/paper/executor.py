"""Stage 3.2 — Brain signal to paper-order execution bridge."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crypto_quant_ai.backend.decision.brain_orchestrator import (
        OrchestratorReport,
    )

from crypto_quant_ai.backend.paper.account import (
    PaperAccount,
    PaperOrder,
    buy,
    sell,
)


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
    ) -> None:
        if not (0 < default_fraction <= 1):
            raise ValueError("default_fraction must be in (0, 1]")
        self.account = account
        self.default_fraction = default_fraction
        self._log: ExecutionLog = ExecutionLog()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, report: OrchestratorReport) -> ExecutionResult:
        """
        Convert an OrchestratorReport into a paper order and update self.account.

        Returns an ExecutionResult (never raises; errors are captured in the result).
        """
        decision = report.final_decision

        # ── Guard 2: veto ──────────────────────────────────────────────
        if decision.veto:
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
            result = ExecutionResult(
                executed=False,
                reason=f"No valid entry price for {symbol} (entry={price})",
                account_snapshot=self._snapshot(),
            )
            self._log.results.append(result)
            return result

        # ── Determine quantity ─────────────────────────────────────────
        try:
            quantity = self._calc_quantity(decision, price)
        except ValueError as exc:
            result = ExecutionResult(
                executed=False,
                reason=f"position_size error: {exc}",
                account_snapshot=self._snapshot(),
            )
            self._log.results.append(result)
            return result

        # ── Execute ────────────────────────────────────────────────────
        try:
            if decision.decision in ("BUY", "LONG"):
                new_account, order = buy(self.account, symbol, quantity, price)
                self.account = new_account
            elif decision.decision in ("SELL", "SHORT"):
                new_account, order = sell(self.account, symbol, quantity, price)
                self.account = new_account
            else:
                result = ExecutionResult(
                    executed=False,
                    reason=f"Unknown decision: {decision.decision}",
                    account_snapshot=self._snapshot(),
                )
                self._log.results.append(result)
                return result

            execution_result = ExecutionResult(
                executed=True,
                order=order,
                reason=f"Executed {order.side.upper()} {quantity} {symbol} @ {price}",
                account_snapshot=self._snapshot(),
            )
            self._log.results.append(execution_result)
            return execution_result

        except ValueError as exc:
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

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _calc_quantity(self, decision, price: float) -> float:
        """
        Resolve quantity in base units.

        If ``decision.position_size > 0`` it is treated as the quote-currency
        notional (e.g. $5,000 USDT).  Otherwise fall back to
        ``default_fraction`` of current cash.
        """
        if decision.position_size > 0:
            # position_size is a quote-currency notional
            notional = float(decision.position_size)
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
