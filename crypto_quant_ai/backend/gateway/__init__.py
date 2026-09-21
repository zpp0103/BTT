"""Stage 7 (Plan A) - Safe paper trading gateway.

Architecture (safe-by-construction):
  decision -> CircuitBreaker (pre-trade) -> PaperRiskGate -> PaperExecutor
           -> PaperAccount mutation -> AuditLog  (reused Stage 3 modules)
           -> SimulatedVenueLedger (gated stub, no network)
           -> Monitor / Alert + PostTradeReconciliation

No external venue connection, no external orders, no credentials, LIVE_TRADING=false.
"""
from crypto_quant_ai.backend.gateway.formatters import (
    export_report,
    to_csv,
    to_json,
    to_markdown,
)
from crypto_quant_ai.backend.gateway.hashing import compute_gateway_hash
from crypto_quant_ai.backend.gateway.monitor import Alert, Monitor
from crypto_quant_ai.backend.gateway.reconcile import (
    PostTradeReconciliation,
    ReconciliationMismatch,
    ReconciliationReport,
)
from crypto_quant_ai.backend.gateway.report import (
    GatewayReport,
    GatewayReportGenerator,
)
from crypto_quant_ai.backend.gateway.risk import CircuitBreaker, RiskManager
from crypto_quant_ai.backend.gateway.session import (
    GatewayExecutionResult,
    LiveTradingSession,
)
from crypto_quant_ai.backend.gateway.types import (
    CircuitBreakerConfig,
    GatewayConfig,
    GatewayStatus,
    RiskManagerConfig,
)
from crypto_quant_ai.backend.gateway.venue import (
    ExternalVenueAdapter,
    SimulatedVenueLedger,
    VenueFill,
)

__all__ = [
    "CircuitBreakerConfig",
    "GatewayConfig",
    "GatewayStatus",
    "RiskManagerConfig",
    "ExternalVenueAdapter",
    "SimulatedVenueLedger",
    "VenueFill",
    "CircuitBreaker",
    "RiskManager",
    "Alert",
    "Monitor",
    "PostTradeReconciliation",
    "ReconciliationMismatch",
    "ReconciliationReport",
    "GatewayExecutionResult",
    "LiveTradingSession",
    "GatewayReport",
    "GatewayReportGenerator",
    "export_report",
    "to_csv",
    "to_json",
    "to_markdown",
    "compute_gateway_hash",
]
