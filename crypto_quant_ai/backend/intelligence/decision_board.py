"""Stage 9 - Layer 2: Decision Intelligence (structured decision committee).

Wraps the multi-brain orchestrator to produce an explainable decision brief.
No execution, no order submission, no network. Reuses existing brains and the
orchestrator; adds structure (supporters / opponents / failure conditions).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from crypto_quant_ai.backend.decision.brain_orchestrator import (
    MultiBrainOrchestrator,
    OrchestratorReport,
)
from crypto_quant_ai.backend.replay.registry import build_brains
from crypto_quant_ai.backend.core.models import MarketData


@dataclass(frozen=True)
class DecisionBrief:
    action: str
    confidence: float
    supporters: list[str]
    opponents: list[str]
    rationale: str
    failure_conditions: list[str]
    alternatives: list[str]


_DEFAULT_BRAINS = ("quant", "market_structure", "risk", "devil_advocate")


def build_decision_brief(
    market_data: MarketData,
    brains: Sequence[Any] | None = None,
) -> DecisionBrief:
    if brains is None:
        brains = build_brains(list(_DEFAULT_BRAINS))
    orch = MultiBrainOrchestrator(list(brains))
    report: OrchestratorReport = orch.run(market_data)
    fd = report.final_decision

    supporters: list[str] = []
    opponents: list[str] = []
    for r in report.brain_results:
        a = r.analysis
        d = (a.decision or "").upper()
        if d in ("BUY", "SELL") or a.confidence >= 0.6:
            supporters.append(a.brain_name)
        elif d in ("NO_TRADE", "HOLD") or a.confidence < 0.3:
            opponents.append(a.brain_name)

    failure_conditions: list[str] = []
    for r in report.brain_results:
        for w in (r.analysis.warnings or []):
            failure_conditions.append(f"{r.brain_name}: {w}")
    if getattr(fd, "veto", False):
        failure_conditions.append("final decision vetoed")
    if fd.stop_loss is None and fd.decision.upper() in ("BUY", "SELL"):
        failure_conditions.append("no stop_loss defined for an active decision")

    alternatives: list[str] = []
    if fd.decision.upper() in ("BUY", "SELL"):
        alternatives.append("reduce position_fraction to lower risk")
        alternatives.append("widen stop_loss before committing")
    else:
        alternatives.append("wait for a higher-confidence regime or signal")

    rationale = (fd.reasoning or "no reasoning provided")[:500]

    return DecisionBrief(
        action=fd.decision,
        confidence=float(fd.confidence),
        supporters=supporters,
        opponents=opponents,
        rationale=rationale,
        failure_conditions=failure_conditions,
        alternatives=alternatives,
    )
