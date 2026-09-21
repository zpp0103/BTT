"""Stage 7 (Plan A) - Gateway report generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from crypto_quant_ai.backend.gateway.monitor import Alert
from crypto_quant_ai.backend.gateway.session import LiveTradingSession
from crypto_quant_ai.backend.gateway.types import GatewayConfig, GatewayStatus


@dataclass
class GatewayReport:
    config: GatewayConfig
    status: GatewayStatus
    gateway_hash: str
    total_submitted: int = 0
    total_executed: int = 0
    total_rejected: int = 0
    total_skipped: int = 0
    circuit_breaker_tripped: bool = False
    circuit_breaker_reason: str = ""
    reconciliation_ok: bool = True
    reconciliation_mismatches: int = 0
    alerts: List[Alert] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "symbol": self.config.symbol,
            "timeframe": self.config.timeframe,
            "strategy_id": self.config.strategy_id,
            "status": self.status.value,
            "gateway_hash": self.gateway_hash,
            "total_submitted": self.total_submitted,
            "total_executed": self.total_executed,
            "total_rejected": self.total_rejected,
            "total_skipped": self.total_skipped,
            "circuit_breaker_tripped": self.circuit_breaker_tripped,
            "circuit_breaker_reason": self.circuit_breaker_reason,
            "reconciliation_ok": self.reconciliation_ok,
            "reconciliation_mismatches": self.reconciliation_mismatches,
            "alerts": [
                {"level": a.level, "message": a.message,
                 "timestamp": a.timestamp.isoformat()}
                for a in self.alerts
            ],
        }


class GatewayReportGenerator:
    def build(
        self,
        session: LiveTradingSession,
        *,
        gateway_hash: str,
        reconciliation=None,
    ) -> GatewayReport:
        mon = session.monitor.summary()
        cb = session.circuit_breaker
        recon = reconciliation  # a ReconciliationReport (already run)
        return GatewayReport(
            config=session._config,
            status=session.status,
            gateway_hash=gateway_hash,
            total_submitted=mon["submitted"],
            total_executed=mon["executed"],
            total_rejected=mon["rejected"],
            total_skipped=mon["skipped"],
            circuit_breaker_tripped=cb.triggered,
            circuit_breaker_reason=cb.reason,
            reconciliation_ok=recon.ok if recon else True,
            reconciliation_mismatches=len(recon.mismatches) if recon else 0,
            alerts=session.monitor.alerts(),
        )
