"""Stage 11 - Model Committee: aggregate multiple brains/models into one verdict.

Runs each model (BrainBase) on the same MarketData, collects contributions,
applies the configured fusion strategy, enforces quorum, fail-closed on
conflict, and gates active decisions through the Stage 10 safety gate. No
network, no external venue, no order submission.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Sequence

from crypto_quant_ai.backend.core.models import FinalDecision
from crypto_quant_ai.backend.intelligence.market_state import MarketState, Regime
from crypto_quant_ai.backend.llm.safety import assert_paper_only

from .fusions import (
    consensus_quorum,
    simple_majority,
    unanimous,
    weighted_majority,
)
from .policy import gate_active, gate_active_reason
from .router import route_models
from .types import (
    CommitteeVerdict,
    FusionStrategy,
    ModelCommitteeConfig,
    ModelContribution,
)

_FUSIONS = {
    FusionStrategy.WEIGHTED_MAJORITY: weighted_majority,
    FusionStrategy.SIMPLE_MAJORITY: simple_majority,
    FusionStrategy.UNANIMOUS: unanimous,
    FusionStrategy.CONSENSUS_QUORUM: consensus_quorum,
}


def _dummy_state() -> MarketState:
    return MarketState(Regime.UNKNOWN, 0.0, {}, "no state provided")


class ModelCommittee:
    def __init__(
        self,
        models: Sequence[Any],
        config: ModelCommitteeConfig | None = None,
    ) -> None:
        if not models:
            raise ValueError("At least one model must be provided.")
        assert_paper_only()  # LIVE_TRADING guard at construction time
        self.models = list(models)
        self.config = config or ModelCommitteeConfig()

    def evaluate(self, market_data, market_state: MarketState | None = None) -> CommitteeVerdict:
        routed, routing = route_models(
            self.models, market_state or _dummy_state(), self.config
        )
        contributions: list[ModelContribution] = []
        for m in routed:
            t0 = time.perf_counter()
            try:
                a = m.analyze(market_data)
                decision = getattr(a, "decision", "NO_TRADE") or "NO_TRADE"
                conf = float(getattr(a, "confidence", 0.0) or 0.0)
                reasoning = getattr(a, "reasoning", "") or ""
                warnings = list(getattr(a, "warnings", []) or [])
            except Exception as exc:  # fail-closed per model
                decision = "NO_TRADE"
                conf = 0.0
                reasoning = f"model error: {exc}"
                warnings = [f"error in {getattr(m, 'name', '?')}"]
            lat = (time.perf_counter() - t0) * 1000
            contributions.append(
                ModelContribution(
                    model_name=getattr(m, "name", "?"),
                    decision=decision,
                    confidence=conf,
                    reasoning=reasoning,
                    warnings=warnings,
                    latency_ms=lat,
                )
            )

        fn = _FUSIONS[self.config.fusion]
        if self.config.fusion == FusionStrategy.WEIGHTED_MAJORITY:
            decision, conf, conflict, quorum_met = fn(
                contributions, self.config.weights, self.config.quorum
            )
        else:
            decision, conf, conflict, quorum_met = fn(contributions, self.config.quorum)

        if conflict and self.config.fail_closed:
            decision, conf = "NO_TRADE", 0.0
            reasoning = "conflicting signals; fail-closed to NO_TRADE"
        elif not quorum_met:
            decision, conf = "NO_TRADE", 0.0
            reasoning = f"quorum ({self.config.quorum}) not met; defaulting to NO_TRADE"
        else:
            reasoning = (
                f"{self.config.fusion.value}: {decision} "
                f"(conf={conf:.2f}, conflict={conflict}, quorum_met={quorum_met})"
            )

        gate_reason = gate_active_reason(decision, self.config, stop_loss=None)
        if decision in ("BUY", "SELL") and not gate_active(
            decision, self.config, stop_loss=None
        ):
            decision, conf = "NO_TRADE", 0.0
            reason_detail = gate_reason or "stop-loss policy requirement unmet"
            reasoning = f"active decision blocked by policy gate ({reason_detail})"

        return CommitteeVerdict(
            final_decision=decision,
            confidence=conf,
            contributions=contributions,
            conflict=conflict,
            quorum_met=quorum_met,
            routing=routing,
            reasoning=reasoning,
        )

    def to_final_decision(self, market_data, verdict: CommitteeVerdict) -> FinalDecision:
        decision = verdict.final_decision
        return FinalDecision(
            symbol=market_data.symbol,
            timeframe=market_data.timeframe,
            decision=decision,
            confidence=verdict.confidence,
            entry=market_data.close if decision in ("BUY", "SELL") else None,
            stop_loss=None,
            take_profit=None,
            position_size=0.0,
            risk_reward=0.0,
            veto=False,
            reasoning=verdict.reasoning,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
