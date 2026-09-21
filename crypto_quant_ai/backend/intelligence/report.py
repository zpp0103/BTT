"""Stage 9 - Layer 4 support: IntelligenceReport data contract + builder."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .market_state import MarketState
from .decision_board import DecisionBrief
from .research import ResearchReport


@dataclass(frozen=True)
class IntelligenceReport:
    generated_at: datetime
    symbol: str
    market_state: MarketState
    decision: DecisionBrief
    research: ResearchReport
    recommendation: str
    risk_notes: list[str]
    explainable_text: str


def build_intelligence_report(
    symbol: str,
    market_state: MarketState,
    decision: DecisionBrief,
    research: ResearchReport,
    recommendation: str,
    risk_notes: list[str],
) -> IntelligenceReport:
    lines = [
        f"Symbol: {symbol}",
        f"Market: {market_state.regime.value} (conf={market_state.confidence:.2f}) - {market_state.summary}",
        f"Decision: {decision.action} (conf={decision.confidence:.2f})",
        f"  supporters: {', '.join(decision.supporters) or 'none'}",
        f"  opponents: {', '.join(decision.opponents) or 'none'}",
        f"  rationale: {decision.rationale}",
        f"Research: best {research.objective} params={research.best_params}",
        f"  candidates={research.candidates_count} completed={research.completed_count}",
        f"  stability_score={research.stability_score:.3f}",
        f"  overfit_flags={len(research.overfit_flags)}",
    ]
    explainable_text = "\n".join(lines)
    return IntelligenceReport(
        generated_at=datetime.now(timezone.utc),
        symbol=symbol,
        market_state=market_state,
        decision=decision,
        research=research,
        recommendation=recommendation,
        risk_notes=risk_notes,
        explainable_text=explainable_text,
    )
