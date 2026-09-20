from __future__ import annotations

from crypto_quant_ai.backend.brains.base import BrainBase


class BrainRegistry:
    def __init__(self, brains: list[BrainBase]) -> None:
        self.brains = brains

    def run(self, market_data):
        results = []
        for brain in self.brains:
            results.append(brain.analyze(market_data))
        return results
