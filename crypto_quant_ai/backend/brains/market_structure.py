from __future__ import annotations

from crypto_quant_ai.backend.brains.base import BrainBase
from crypto_quant_ai.backend.core.models import BrainAnalysis, MarketData


class MarketStructureBrain(BrainBase):
    name = "market_structure"

    def analyze(self, market_data: MarketData) -> BrainAnalysis:
        trend = "bullish" if market_data.close >= market_data.open else "bearish"
        return BrainAnalysis(
            brain_name=self.name,
            decision="NO_TRADE",
            confidence=0.5,
            reasoning=f"Market structure is {trend} for {market_data.symbol}.",
            warnings=["Stage 1 does not produce executable signals."],
        )
