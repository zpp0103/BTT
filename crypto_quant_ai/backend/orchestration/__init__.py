"""Stage 13 - end-to-end paper-only execution orchestration."""
from __future__ import annotations

import os

if os.environ.get("LIVE_TRADING", "false").lower() == "true":
    raise RuntimeError(
        "LIVE_TRADING enabled; paper-only safety guard tripped in orchestration package."
    )

from .formatters import export_report, render_csv, render_json, render_markdown, report_to_dict
from .orchestrator import Stage13Orchestrator
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
    "default_stage13_committee_config",
    "export_report",
    "render_csv",
    "render_json",
    "render_markdown",
    "report_to_dict",
    "stage13_hash",
]
