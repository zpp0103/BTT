from __future__ import annotations

from collections.abc import Sequence
from math import isfinite

from pydantic import BaseModel, Field

from crypto_quant_ai.backend.data.ohlcv import OHLCVBar, validate_ohlcv


def simple_moving_average(
    values: Sequence[float],
    period: int,
) -> list[float | None]:
    """Calculate a trailing SMA without using future values."""

    if period < 1:
        raise ValueError("period must be at least 1")

    if any(not isfinite(value) for value in values):
        raise ValueError("indicator inputs must be finite")

    result: list[float | None] = [None] * len(values)

    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        result[index] = sum(window) / period

    return result


class IndicatorSnapshot(BaseModel):
    timestamp: str
    close: float = Field(gt=0)
    sma: float | None = Field(default=None, gt=0)
    return_pct: float | None = None


def calculate_indicators(
    bars: Sequence[OHLCVBar],
    sma_period: int = 3,
) -> list[IndicatorSnapshot]:
    """Calculate deterministic indicators for validated local OHLCV bars."""

    validated = validate_ohlcv(bars)
    closes = [bar.close for bar in validated]
    sma_values = simple_moving_average(closes, sma_period)

    snapshots: list[IndicatorSnapshot] = []
    previous_close: float | None = None

    for bar, sma in zip(validated, sma_values):
        return_pct = (
            None
            if previous_close is None
            else (bar.close / previous_close - 1.0) * 100
        )

        snapshots.append(
            IndicatorSnapshot(
                timestamp=bar.timestamp.isoformat(),
                close=bar.close,
                sma=sma,
                return_pct=return_pct,
            )
        )

        previous_close = bar.close

    return snapshots
