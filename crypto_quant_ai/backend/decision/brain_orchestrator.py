from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from crypto_quant_ai.backend.core.models import BrainAnalysis, FinalDecision

if TYPE_CHECKING:
    from crypto_quant_ai.backend.brains.base import BrainBase


@dataclass
class BrainResult:
    """Result from a single brain after analysis."""

    brain_name: str
    analysis: BrainAnalysis
    latency_ms: float | None = None


@dataclass
class OrchestratorReport:
    """Aggregated report from all brains and the final decision."""

    symbol: str
    timeframe: str
    brain_results: list[BrainResult]
    final_decision: FinalDecision
    total_latency_ms: float | None = None

    @property
    def unanimous_buy(self) -> bool:
        return all(r.analysis.decision == "BUY" for r in self.brain_results)

    @property
    def unanimous_sell(self) -> bool:
        return all(r.analysis.decision == "SELL" for r in self.brain_results)

    @property
    def vote_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.brain_results:
            counts[r.analysis.decision] = counts.get(r.analysis.decision, 0) + 1
        return counts


class MultiBrainOrchestrator:
    """
    Runs multiple BrainBase instances on the same MarketData and
    aggregates their analyses into a single OrchestratorReport + FinalDecision.

    Voting rules
    ------------
    BUY  : ≥ 2 brains vote BUY  (and none vetoes)
    SELL : ≥ 2 brains vote SELL (and none vetoes)
    HOLD : any other combination
    veto : any brain returns veto=True → final = NO_TRADE
    """

    def __init__(self, brains: list[BrainBase], max_workers: int = 4) -> None:
        if not brains:
            raise ValueError("At least one brain must be provided.")
        self.brains = brains
        self.max_workers = max_workers

    def run(self, market_data) -> OrchestratorReport:
        """
        Execute all brains (parallel via ThreadPoolExecutor) and return
        an OrchestratorReport with a FinalDecision.
        """
        import time

        from datetime import datetime, timezone

        from crypto_quant_ai.backend.core.models import (
            FinalDecision,
            RiskAssessment,
        )

        brain_results: list[BrainResult] = []
        start = time.perf_counter()

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_to_brain = {
                pool.submit(brain.analyze, market_data): brain
                for brain in self.brains
            }
            for future in as_completed(future_to_brain):
                brain = future_to_brain[future]
                t0 = time.perf_counter()
                try:
                    analysis = future.result()
                except Exception as exc:  # pragma: no cover
                    analysis = BrainAnalysis(
                        brain_name=brain.name,
                        decision="NO_TRADE",
                        confidence=0.0,
                        reasoning=f"Brain error: {exc}",
                        warnings=[f"Error in {brain.name}"],
                    )
                latency = (time.perf_counter() - t0) * 1000
                brain_results.append(
                    BrainResult(brain_name=brain.name, analysis=analysis, latency_ms=latency)
                )

        total_ms = (time.perf_counter() - start) * 1000

        # Aggregate decision
        decision, confidence, reasoning = self._aggregate(brain_results)

        final = FinalDecision(
            symbol=market_data.symbol,
            timeframe=market_data.timeframe,
            decision=decision,
            confidence=confidence,
            entry=market_data.close if decision in ("BUY", "LONG") else None,
            stop_loss=None,
            take_profit=None,
            position_size=0.0,
            risk_reward=0.0,
            veto=False,
            reasoning=reasoning,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        return OrchestratorReport(
            symbol=market_data.symbol,
            timeframe=market_data.timeframe,
            brain_results=brain_results,
            final_decision=final,
            total_latency_ms=total_ms,
        )

    def _aggregate(
        self, results: list[BrainResult]
    ) -> tuple[str, float, str]:
        """Voting + confidence aggregation logic."""
        from crypto_quant_ai.backend.core.models import RiskAssessment

        # Veto check
        for r in results:
            risk: RiskAssessment = getattr(r.analysis, "risk", None)
            if risk and getattr(r.analysis, "veto", False):
                return (
                    "NO_TRADE",
                    0.0,
                    f"Veto from {r.brain_name}: {getattr(r.analysis, 'veto_reason', 'blocked')}",
                )

        votes: dict[str, list[float]] = {}
        for r in results:
            d = r.analysis.decision
            votes.setdefault(d, []).append(r.analysis.confidence)

        buy_votes = len(votes.get("BUY", [])) + len(votes.get("LONG", []))
        sell_votes = len(votes.get("SELL", [])) + len(votes.get("SHORT", []))

        if buy_votes >= 2:
            avg_conf = sum(votes.get("BUY", []) + votes.get("LONG", [])) / (buy_votes or 1)
            return "BUY", avg_conf, f"{buy_votes} brains voted BUY"
        if sell_votes >= 2:
            avg_conf = sum(votes.get("SELL", []) + votes.get("SHORT", [])) / (sell_votes or 1)
            return "SELL", avg_conf, f"{sell_votes} brains voted SELL"

        # Majority of HOLD / NO_TRADE → NO_TRADE
        all_confs = [r.analysis.confidence for r in results]
        avg_conf = sum(all_confs) / len(all_confs) if all_confs else 0.0
        return "NO_TRADE", avg_conf, "No majority consensus; defaulting to NO_TRADE"
