from __future__ import annotations

from abc import ABC, abstractmethod

from crypto_quant_ai.backend.core.models import BrainAnalysis, MarketData


class BrainBase(ABC):
    name: str

    @abstractmethod
    def analyze(self, market_data: MarketData) -> BrainAnalysis:
        raise NotImplementedError
