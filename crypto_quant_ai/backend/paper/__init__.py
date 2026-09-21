"""Local paper trading models for Stage 3.1+."""

from crypto_quant_ai.backend.paper.account import (
    PaperAccount,
    PaperOrder,
    PaperPosition,
    buy,
    sell,
)
from crypto_quant_ai.backend.paper.executor import (
    ExecutionLog,
    ExecutionResult,
    PaperExecutor,
)
from crypto_quant_ai.backend.paper.risk_gate import (
    PaperRiskGate,
    RiskGateAudit,
    RiskGateResult,
)
from crypto_quant_ai.backend.paper.audit import (
    AuditLog,
    PaperAuditLedger,
)
from crypto_quant_ai.backend.paper.execution_trace import (
    ExecutionTrace,
    new_trace,
    trace_from_execution,
)
from crypto_quant_ai.backend.paper.order_event import (
    OrderEvent,
    OrderEventType,
    make_event_id,
)
from crypto_quant_ai.backend.paper.snapshot import (
    PortfolioSnapshot,
    snapshot_from_account,
)

__all__ = [
    # Stage 3.1
    "PaperAccount",
    "PaperOrder",
    "PaperPosition",
    "buy",
    "sell",
    # Stage 3.2
    "PaperExecutor",
    "ExecutionLog",
    "ExecutionResult",
    # Stage 3.3
    "PaperRiskGate",
    "RiskGateAudit",
    "RiskGateResult",
    # Stage 3.4
    "AuditLog",
    "PaperAuditLedger",
    "ExecutionTrace",
    "OrderEvent",
    "OrderEventType",
    "make_event_id",
    "new_trace",
    "trace_from_execution",
    "PortfolioSnapshot",
    "snapshot_from_account",
]
