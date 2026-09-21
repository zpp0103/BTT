"""Stage 10 - prompt construction from MarketData.

Builds a deterministic, read-only prompt. No market credentials, no venue, no
order details are ever embedded.
"""
from __future__ import annotations

from typing import Any

from crypto_quant_ai.backend.core.models import MarketData


def build_prompt(market_data: MarketData, template: str | None = None) -> str:
    if template:
        try:
            return template.format(
                symbol=market_data.symbol,
                timeframe=market_data.timeframe,
                open=market_data.open,
                high=market_data.high,
                low=market_data.low,
                close=market_data.close,
                volume=market_data.volume,
            )
        except (KeyError, ValueError):
            pass
    return (
        f"symbol={market_data.symbol} timeframe={market_data.timeframe} "
        f"open={market_data.open} high={market_data.high} low={market_data.low} "
        f"close={market_data.close} volume={market_data.volume}"
    )
