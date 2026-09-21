from __future__ import annotations

from crypto_quant_ai.backend.brains.base import BrainBase
from crypto_quant_ai.backend.core.models import BrainAnalysis, MarketData


class LLMStubBrain(BrainBase):
    """Deterministic, offline stub brain. Always returns a safe hold.

    Useful as a drop-in default, a test double, or when no provider is wired.
    """
    name = "llm_stub"

    def __init__(self, confidence: float = 0.0) -> None:
        self._confidence = max(0.0, min(1.0, float(confidence)))

    def analyze(self, market_data: MarketData) -> BrainAnalysis:
        return BrainAnalysis(
            brain_name=self.name,
            decision="NO_TRADE",
            confidence=self._confidence,
            reasoning="stub brain: deterministic conservative hold",
            warnings=["stub"],
        )
