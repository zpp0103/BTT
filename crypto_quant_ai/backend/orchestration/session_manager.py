from __future__ import annotations

import csv
import io
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from crypto_quant_ai.backend.gateway import (
    CircuitBreaker,
    ExternalVenueAdapter,
    GatewayConfig,
    LiveTradingSession,
    compute_gateway_hash,
)
from crypto_quant_ai.backend.paper.account import PaperAccount

from .orchestrator import Stage13Orchestrator
from .types import Stage13Request

from .session_store import LocalSessionStore
from .session_types import (
    Stage14AuditSummary,
    Stage14ReconciliationSnapshot,
    Stage14RunRecord,
    Stage14SessionRunRequest,
    Stage14SessionState,
    Stage14SessionView,
)


class Stage14SessionManager:
    def __init__(
        self,
        *,
        store: LocalSessionStore | None = None,
        orchestrator_factory: Any | None = None,
    ) -> None:
        self._store = store or LocalSessionStore()
        self._orchestrator_factory = orchestrator_factory or Stage13Orchestrator

    def open_session(self, config: GatewayConfig) -> Stage14SessionView:
        session_id = self._store.session_id_for_config(config)
        if self._store.exists(session_id):
            return self._to_view(self._store.load(session_id))
        state = self._store.create_empty_state(
            config, gateway_hash=compute_gateway_hash(config)
        )
        self._store.save(state)
        return self._to_view(state)

    def get_session(self, session_id: str) -> Stage14SessionView:
        return self._to_view(self._store.load(session_id))

    def run_session(
        self,
        session_id: str,
        request: Stage14SessionRunRequest,
        *,
        orchestrator: Stage13Orchestrator | None = None,
    ):
        state = self._store.load(session_id)
        session = self._session_from_state(state)
        stage13_request = Stage13Request(
            candles=list(request.candles),
            symbol=state.gateway_config.symbol,
            timeframe=state.gateway_config.timeframe,
            timeframes=tuple(request.timeframes),
            gateway_config=state.gateway_config,
        )
        orch = orchestrator or self._orchestrator_factory()
        try:
            report = orch.run_with_session(stage13_request, session)
            updated = self._state_from_runtime(state, session, report)
            self._store.save(updated)
            return report
        finally:
            session.stop()

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        state = self._store.load(session_id)
        return [asdict(item) for item in state.history]

    def export_history_csv(self, session_id: str) -> str:
        rows = self.get_history(session_id)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "run_id",
                "created_at",
                "report_hash",
                "verification_passed",
                "executed",
                "blocked",
                "final_decision",
                "block_reason",
                "reconciliation_ok",
                "reconciliation_mismatches",
            ]
        )
        for item in rows:
            writer.writerow(
                [
                    item["run_id"],
                    item["created_at"],
                    item["report_hash"],
                    item["verification_passed"],
                    item["executed"],
                    item["blocked"],
                    item["final_decision"],
                    item["block_reason"],
                    item["reconciliation_ok"],
                    item["reconciliation_mismatches"],
                ]
            )
        return buf.getvalue()

    def _session_from_state(self, state: Stage14SessionState) -> LiveTradingSession:
        audit_log = self._store.build_audit_log(state.audit_events)
        ledger = self._store.build_ledger(state.venue_fills)
        venue = ExternalVenueAdapter(ledger)
        breaker = CircuitBreaker(state.gateway_config.circuit_breaker)
        if state.breaker_state:
            breaker.restore_state(state.breaker_state)
        return LiveTradingSession(
            state.gateway_config,
            account=PaperAccount.model_validate(state.account.model_dump()),
            audit_log=audit_log,
            venue_adapter=venue,
            circuit_breaker=breaker,
            initial_order_seq=state.order_seq,
        )

    def _state_from_runtime(self, previous: Stage14SessionState, session: LiveTradingSession, report) -> Stage14SessionState:
        audit_events: list[dict[str, Any]] = []
        for event in session.audit_log.all_events():
            snap = None
            if event.snapshot is not None:
                snap = {
                    "timestamp": event.snapshot.timestamp.isoformat(),
                    "cash": event.snapshot.cash,
                    "positions": dict(event.snapshot.positions),
                    "total_equity": event.snapshot.total_equity,
                    "total_exposure": event.snapshot.total_exposure,
                    "exposure_pct": event.snapshot.exposure_pct,
                    "source": event.snapshot.source,
                }
            audit_events.append(
                {
                    "event_id": event.event_id,
                    "order_id": event.order_id,
                    "event_type": event.event_type,
                    "symbol": event.symbol,
                    "side": event.side,
                    "timestamp": event.timestamp.isoformat(),
                    "quantity": event.quantity,
                    "price": event.price,
                    "status": event.status,
                    "reasons": list(event.reasons),
                    "source": event.source,
                    "snapshot": snap,
                }
            )
        venue_fills = [
            {
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "side": fill.side,
                "quantity": fill.quantity,
                "price": fill.price,
                "timestamp": fill.timestamp.isoformat(),
                "venue": fill.venue,
            }
            for fill in session.venue.ledger.all()
        ]
        recon = session.reconcile()
        reconciliation = recon.ok
        mismatches = (
            len(recon.mismatches)
        )
        history = list(previous.history)
        history.append(
            Stage14RunRecord(
                run_id=uuid.uuid4().hex[:12],
                created_at=datetime.now(timezone.utc).isoformat(),
                report_hash=report.report_hash,
                verification_passed=report.result.verification_passed,
                executed=report.result.executed,
                blocked=report.result.blocked,
                final_decision=report.result.final_decision.decision,
                block_reason=report.result.block_reason,
                reconciliation_ok=reconciliation,
                reconciliation_mismatches=mismatches,
            )
        )
        latest_result = {
            "verification_passed": report.result.verification_passed,
            "executed": report.result.executed,
            "blocked": report.result.blocked,
            "final_decision": report.result.final_decision.decision,
            "block_reason": report.result.block_reason,
        }
        return Stage14SessionState(
            session_id=previous.session_id,
            gateway_hash=compute_gateway_hash(session.config),
            gateway_config=session.config,
            account=session.account,
            audit_summary=Stage14AuditSummary(
                total_orders=session.audit_log.total_orders,
                executed_count=session.audit_log.executed_count,
                rejected_count=session.audit_log.rejected_count,
                skipped_count=session.audit_log.skipped_count,
                total_events=len(session.audit_log.all_events()),
            ),
            reconciliation=Stage14ReconciliationSnapshot(
                ok=reconciliation,
                matched=recon.matched,
                mismatches=mismatches,
            ),
            latest_report_hash=report.report_hash,
            latest_report_generated_at=report.generated_at,
            latest_result=latest_result,
            history=history,
            breaker_state=session.circuit_breaker.export_state(),
            order_seq=session.order_sequence,
            audit_events=audit_events,
            venue_fills=venue_fills,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _to_view(state: Stage14SessionState) -> Stage14SessionView:
        return Stage14SessionView(
            session_id=state.session_id,
            gateway_hash=state.gateway_hash,
            gateway_config=state.gateway_config,
            account=state.account,
            audit_summary=state.audit_summary,
            reconciliation=state.reconciliation,
            latest_report_hash=state.latest_report_hash,
            latest_report_generated_at=state.latest_report_generated_at,
            latest_result=dict(state.latest_result),
            history_length=len(state.history),
            updated_at=state.updated_at,
        )
