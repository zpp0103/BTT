from __future__ import annotations

from datetime import datetime, timezone

from crypto_quant_ai.backend.core.models import FinalDecision, RiskAssessment


class DecisionEngine:
    def decide(self, symbol: str, timeframe: str, risk: RiskAssessment, reasoning: str) -> FinalDecision:
        decision = "NO_TRADE"
        veto = bool(risk.veto)
        if veto:
            decision = "NO_TRADE"
        return FinalDecision(
            symbol=symbol,
            timeframe=timeframe,
            decision=decision,
            confidence=0.0,
            entry=None,
            stop_loss=None,
            take_profit=None,
            position_size=0.0,
            risk_reward=0.0,
            veto=veto,
            reasoning=reasoning,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
