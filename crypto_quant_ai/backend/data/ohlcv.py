from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from math import isfinite

from pydantic import BaseModel, Field, field_validator, model_validator


class OHLCVBar(BaseModel):
    """One validated OHLCV candle from a local, non-live input."""

    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    @field_validator("open", "high", "low", "close", "volume")
    @classmethod
    def require_finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("OHLCV values must be finite")
        return value

    @model_validator(mode="after")
    def validate_price_range(self) -> OHLCVBar:
        if self.high < max(self.open, self.close):
            raise ValueError("high/low must contain open and close")
        if self.low > min(self.open, self.close):
            raise ValueError("high/low must contain open and close")
        if self.low > self.high:
            raise ValueError("low must not exceed high")
        return self


def validate_ohlcv(bars: Iterable[OHLCVBar]) -> list[OHLCVBar]:
    """Return bars after enforcing strictly increasing timestamps."""

    result = list(bars)

    for previous, current in zip(result, result[1:]):
        if current.timestamp <= previous.timestamp:
            raise ValueError("OHLCV timestamps must be strictly increasing")

    return result
