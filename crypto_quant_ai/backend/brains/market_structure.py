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
            warnings=[],
        )


class QuantBrain(BrainBase):
    name = "quant"

    def analyze(self, market_data: MarketData) -> BrainAnalysis:
        if market_data.close > market_data.open:
            return BrainAnalysis(
                brain_name=self.name,
                decision="NO_TRADE",
                confidence=0.6,
                reasoning="Momentum remains positive but insufficient for trade execution in stage 1.",
                warnings=["Waiting for full strategy implementation."],
            )
        return BrainAnalysis(
            brain_name=self.name,
            decision="NO_TRADE",
            confidence=0.55,
            reasoning="Momentum is weak; no entry is generated in stage 1.",
            warnings=["No real signal generated."],
        )


class RiskManagerBrain(BrainBase):
    name = "risk"

    def analyze(self, market_data: MarketData) -> BrainAnalysis:
        return BrainAnalysis(
            brain_name=self.name,
            decision="NO_TRADE",
            confidence=0.95,
            reasoning="Risk engine blocks any trade until live trading is enabled and validated.",
            warnings=["Stage 1 is safety-only."],
        )


class DevilsAdvocateBrain(BrainBase):
    name = "devil_advocate"

    def analyze(self, market_data: MarketData) -> BrainAnalysis:
        return BrainAnalysis(
            brain_name=self.name,
            decision="NO_TRADE",
            confidence=0.9,
            reasoning="Devil advocate vetoes all trades until the risk framework is fully validated.",
            warnings=["Stage 1 denies live or simulated order risk."],
        )
