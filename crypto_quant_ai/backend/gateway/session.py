"""Stage 7 (Plan A) - Explicit, single-user paper trading session.

A session runs only after an explicit start() and stops on stop(). There is no
daemon and no background automation: every decision is submitted by an explicit
call. The order chain reuses Stage 3 modules unchanged:

    decision -> CircuitBreaker (pre-trade)
            -> PaperRiskGate.check  (Stage 3.3)
            -> PaperExecutor.execute (Stage 3.2, gate-then-execute)
            -> PaperAccount mutation (Stage 3.1)
            -> AuditLog              (Stage 3.4)
            -> SimulatedVenueLedger  (gated stub, no network)
            -> Monitor / Alert + PostTradeReconciliation
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from crypto_quant_ai.backend.core.models import BrainAnalysis, FinalDecision
from crypto_quant_ai.backend.decision.brain_orchestrator import (
    BrainResult,
    OrchestratorReport,
)
from crypto_quant_ai.backend.gateway.monitor import Monitor
from crypto_quant_ai.backend.gateway.reconcile import PostTradeReconciliation
from crypto_quant_ai.backend.gateway.risk import CircuitBreaker, RiskManager
from crypto_quant_ai.backend.gateway.types import GatewayConfig, GatewayStatus
from crypto_quant_ai.backend.gateway.venue import ExternalVenueAdapter
from crypto_quant_ai.backend.paper.account import PaperAccount
from crypto_quant_ai.backend.paper.audit import AuditLog
from crypto_quant_ai.backend.paper.executor import ExecutionResult, PaperExecutor


LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() in ("true", "1")
if LIVE_TRADING:
    raise RuntimeError(
        "Stage 7 gateway requires paper mode. Disable LIVE_TRADING to continue."
    )


@dataclass(frozen=True)
class GatewayExecutionResult:
    order_id: Optional[str]
    executed: bool
    decision: str
    reason: str
    circuit_breaker_tripped: bool = False
    rejected_by_gate: bool = False
    veto_blocked: bool = False
    no_trade: bool = False


class LiveTradingSession:
    """Single user / single account / single symbol / single strategy runner."""

    def __init__(
        self,
        config: GatewayConfig,
        *,
        account: Optional[PaperAccount] = None,
        audit_log: Optional[AuditLog] = None,
        alert_sink: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._config = config
        self._account = account or PaperAccount(cash=config.initial_cash)
        self._audit_log = audit_log or AuditLog()
        self._venue = ExternalVenueAdapter()
        self._risk_manager = RiskManager(config.risk_manager, self._account)
        self._circuit_breaker = CircuitBreaker(config.circuit_breaker)
        self._monitor = Monitor()
        self._alert_sink = alert_sink
        self._status = GatewayStatus.STOPPED
        self._started_at: Optional[datetime] = None
        self._stopped_at: Optional[datetime] = None
        self._last_price: Optional[float] = None
        self._executor = PaperExecutor(
            self._account,
            audit_log=self._audit_log,
            risk_gate=self._risk_manager.gate,
        )
        self._reconciliation = PostTradeReconciliation(
            self._audit_log, self._venue.ledger
        )

    @property
    def status(self) -> GatewayStatus:
        return self._status

    @property
    def account(self) -> PaperAccount:
        return self._account

    @property
    def audit_log(self) -> AuditLog:
        return self._audit_log

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    @property
    def monitor(self) -> Monitor:
        return self._monitor

    @property
    def venue(self) -> ExternalVenueAdapter:
        return self._venue

    def start(self) -> None:
        if os.environ.get("LIVE_TRADING", "false").lower() in ("true", "1"):
            raise RuntimeError("Cannot start gateway in live trading mode.")
        if self._status == GatewayStatus.RUNNING:
            return
        self._status = GatewayStatus.RUNNING
        self._started_at = datetime.now(timezone.utc)
        self._circuit_breaker.arm(self._equity())

    def stop(self) -> None:
        self._status = GatewayStatus.STOPPED
        self._stopped_at = datetime.now(timezone.utc)

    def _equity(self) -> float:
        eq = self._account.cash
        for pos in self._account.positions.values():
            price = self._last_price or pos.avg_cost
            eq += pos.quantity * price
        return eq

    def submit_decision(
        self,
        decision: FinalDecision,
        reference_price: Optional[float] = None,
    ) -> GatewayExecutionResult:
        if self._status != GatewayStatus.RUNNING:
            raise RuntimeError("Session is not running. Call start() first.")
        self._monitor.record_submission(decision)

        # Layer 1 (Stage 7): circuit breaker pre-trade guard.
        ref = reference_price if reference_price is not None else self._last_price
        blocked, reason = self._circuit_breaker.pre_trade(decision, self._account, ref)
        if blocked:
            msg = f"Circuit breaker tripped: {reason}"
            self._monitor.emit("CRITICAL", msg)
            if self._alert_sink:
                self._alert_sink("CRITICAL", msg)
            self._status = GatewayStatus.TRIPPED
            return GatewayExecutionResult(
                order_id=None,
                executed=False,
                decision=decision.decision,
                reason=reason,
                circuit_breaker_tripped=True,
            )

        # Layer 2 (Stage 3.3 + 3.2): gate -> execute -> audit (reused, unchanged).
        report = self._build_report(decision)
        result: ExecutionResult = self._executor.execute(report)

        # Resync account references (buy/sell return a new PaperAccount).
        self._account = self._executor.account
        self._risk_manager.gate.account = self._account

        order_id = self._latest_order_id()
        if result.executed and result.order is not None and order_id:
            self._venue.submit(order_id, result.order)
            self._last_price = result.order.price

        self._circuit_breaker.post_trade(self._equity())
        self._monitor.record_result(result, decision)

        return GatewayExecutionResult(
            order_id=order_id,
            executed=result.executed,
            decision=decision.decision,
            reason=result.reason,
            rejected_by_gate=(
                result.executed is False and "Risk gate rejected" in result.reason
            ),
            veto_blocked=result.veto_blocked,
            no_trade=result.no_trade,
        )

    def _build_report(self, decision: FinalDecision) -> OrchestratorReport:
        analysis = BrainAnalysis(
            brain_name="gateway",
            decision=decision.decision,
            confidence=decision.confidence,
            reasoning=decision.reasoning,
        )
        brain_result = BrainResult(
            brain_name="gateway", analysis=analysis, latency_ms=0.0
        )
        return OrchestratorReport(
            symbol=decision.symbol,
            timeframe=decision.timeframe,
            brain_results=[brain_result],
            final_decision=decision,
        )

    def _latest_order_id(self) -> Optional[str]:
        recent = self._audit_log.query_recent(1)
        return recent[0].order_id if recent else None

    def reconcile(self):
        return self._reconciliation.run()
