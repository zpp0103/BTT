from __future__ import annotations

from crypto_quant_ai.backend.brains.base import BrainBase
from crypto_quant_ai.backend.core.models import BrainAnalysis, MarketData


class RiskManagerBrain(BrainBase):
    name = "risk"

    def analyze(self, market_data: MarketData) -> BrainAnalysis:
        return BrainAnalysis(
            brain_name=self.name,
            decision="NO_TRADE",
            confidence=0.95,
            reasoning="Risk blocks trade activity until the safety framework is validated.",
            warnings=["Stage 1 is safety-only."],
        )
