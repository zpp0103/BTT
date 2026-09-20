from __future__ import annotations

from crypto_quant_ai.backend.brains.base import BrainBase
from crypto_quant_ai.backend.core.models import BrainAnalysis, MarketData


class QuantBrain(BrainBase):
    name = "quant"

    def analyze(self, market_data: MarketData) -> BrainAnalysis:
        momentum = "positive" if market_data.close > market_data.open else "weak"
        return BrainAnalysis(
            brain_name=self.name,
            decision="NO_TRADE",
            confidence=0.6 if momentum == "positive" else 0.55,
            reasoning=f"Momentum is {momentum}; no executable signal exists in Stage 1.",
            warnings=["Waiting for the Stage 2 data and indicator layer."],
        )
