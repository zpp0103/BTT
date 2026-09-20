from __future__ import annotations

from crypto_quant_ai.backend.core.config import settings


class ExecutionService:
    def __init__(self) -> None:
        self.live_trading = settings.live_trading

    def place_order(self, *args, **kwargs) -> None:
        if not self.live_trading:
            raise RuntimeError("Live trading is disabled.")
        raise RuntimeError("Real execution is not implemented in stage 1.")
