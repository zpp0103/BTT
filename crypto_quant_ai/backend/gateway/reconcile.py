"""Stage 7 (Plan A) - Post-trade reconciliation (local audit vs simulated venue)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from crypto_quant_ai.backend.gateway.venue import SimulatedVenueLedger
from crypto_quant_ai.backend.paper.audit import AuditLog


@dataclass
class ReconciliationMismatch:
    order_id: str
    field: str
    audit_value: object
    venue_value: object


@dataclass
class ReconciliationReport:
    matched: int = 0
    mismatches: List[ReconciliationMismatch] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.mismatches) == 0


class PostTradeReconciliation:
    """Compares the local AuditLog with the simulated venue ledger."""

    def __init__(self, audit_log: AuditLog, ledger: SimulatedVenueLedger) -> None:
        self._audit = audit_log
        self._ledger = ledger

    def run(self) -> ReconciliationReport:
        report = ReconciliationReport()
        audit_fills = self._audit_fills()
        for fill in self._ledger.all():
            af = audit_fills.get(fill.order_id)
            if af is None:
                report.mismatches.append(
                    ReconciliationMismatch(fill.order_id, "present", "missing", "present")
                )
                continue
            report.matched += 1
            if af["side"] != fill.side:
                report.mismatches.append(
                    ReconciliationMismatch(fill.order_id, "side", af["side"], fill.side)
                )
            if abs(af["quantity"] - fill.quantity) > 1e-9:
                report.mismatches.append(
                    ReconciliationMismatch(
                        fill.order_id, "quantity", af["quantity"], fill.quantity
                    )
                )
            if abs(af["price"] - fill.price) > 1e-9:
                report.mismatches.append(
                    ReconciliationMismatch(
                        fill.order_id, "price", af["price"], fill.price
                    )
                )
        return report

    def _audit_fills(self) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        seen = set()
        for event in self._audit.all_events():
            if event.event_type in ("executed", "closed") and event.order_id not in seen:
                seen.add(event.order_id)
                out[event.order_id] = {
                    "side": event.side,
                    "quantity": event.quantity,
                    "price": event.price,
                }
        return out
