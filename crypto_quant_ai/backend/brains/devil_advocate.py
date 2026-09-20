from __future__ import annotations

from crypto_quant_ai.backend.brains.base import BrainBase
from crypto_quant_ai.backend.core.models import BrainAnalysis, MarketData


class DevilsAdvocateBrain(BrainBase):
    name = "devil_advocate"

    def analyze(self, market_data: MarketData) -> BrainAnalysis:
        return BrainAnalysis(
            brain_name=self.name,
            decision="NO_TRADE",
            confidence=0.9,
            reasoning="The safety reviewer vetoes execution during Stage 1.",
            warnings=["No live or simulated order execution is permitted."],
        )
