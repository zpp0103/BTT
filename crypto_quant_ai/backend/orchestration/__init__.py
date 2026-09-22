"""Stage 13/14 - paper-only execution orchestration and local session state."""
from __future__ import annotations

import os

if os.environ.get("LIVE_TRADING", "false").lower() == "true":
    raise RuntimeError(
        "LIVE_TRADING enabled; paper-only safety guard tripped in orchestration package."
    )

from .formatters import export_report, render_csv, render_json, render_markdown, report_to_dict
from .orchestrator import Stage13Orchestrator
from .session_manager import Stage14SessionManager
from .session_types import (
    Stage14AuditSummary,
    Stage14ReconciliationSnapshot,
    Stage14RunRecord,
    Stage14SessionOpenRequest,
    Stage14SessionRunRequest,
    Stage14SessionState,
    Stage14SessionView,
)
from .types import (
    Stage13ApiRequest,
    Stage13ExecutionResult,
    Stage13MarketContext,
    Stage13Report,
    Stage13Request,
    Stage13RequestSummary,
    default_stage13_committee_config,
    stage13_hash,
)

__all__ = [
    "Stage13ApiRequest",
    "Stage13ExecutionResult",
    "Stage13MarketContext",
    "Stage13Orchestrator",
    "Stage13Report",
    "Stage13Request",
    "Stage13RequestSummary",
    "Stage14AuditSummary",
    "Stage14ReconciliationSnapshot",
    "Stage14RunRecord",
    "Stage14SessionManager",
    "Stage14SessionOpenRequest",
    "Stage14SessionRunRequest",
    "Stage14SessionState",
    "Stage14SessionView",
    "default_stage13_committee_config",
    "export_report",
    "render_csv",
    "render_json",
    "render_markdown",
    "report_to_dict",
    "stage13_hash",
]
