"""Stage 9 - Intelligence Orchestration Layer (paper-only research system).

Imports require LIVE_TRADING=false. This package adds a local, explainable
research loop on top of Stage 1-8 capabilities. It never submits orders, never
contacts an external venue, and never relaxes the existing risk boundaries.
"""
from __future__ import annotations

import os as _os

from .market_state import Regime, MarketState, classify_regime, consensus_regime
from .decision_board import DecisionBrief, build_decision_brief
from .research import ParamSensitivity, ResearchReport, run_research
from .report import IntelligenceReport, build_intelligence_report
from .orchestrator import IntelligenceOrchestrator, _live_guard
from .formatters import render_markdown, render_json, render_csv, export_report

if _os.environ.get("LIVE_TRADING", "false").lower() == "true":
    raise RuntimeError("Stage 9 intelligence requires LIVE_TRADING=false (paper only).")

__all__ = [
    "Regime", "MarketState", "classify_regime", "consensus_regime",
    "DecisionBrief", "build_decision_brief",
    "ParamSensitivity", "ResearchReport", "run_research",
    "IntelligenceReport", "build_intelligence_report",
    "IntelligenceOrchestrator", "render_markdown", "render_json",
    "render_csv", "export_report",
]
