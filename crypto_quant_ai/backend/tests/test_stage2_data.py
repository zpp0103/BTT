from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from crypto_quant_ai.backend.data.indicators import (
    calculate_indicators,
    simple_moving_average,
)
from crypto_quant_ai.backend.data.ohlcv import OHLCVBar, validate_ohlcv


def bar(
    minute: int,
    close: float,
    *,
    high: float | None = None,
    low: float | None = None,
) -> OHLCVBar:
    return OHLCVBar(
        timestamp=datetime(
            2024,
            1,
            1,
            0,
            minute,
            tzinfo=timezone.utc,
        ),
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=1.0,
    )


def test_ohlcv_rejects_invalid_price_range() -> None:
    with pytest.raises(ValidationError, match="high/low"):
        OHLCVBar(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=10,
            high=9,
            low=8,
            close=10,
            volume=1,
        )


def test_validate_ohlcv_rejects_duplicate_timestamps() -> None:
    first = bar(0, 10)

    with pytest.raises(ValueError, match="strictly increasing"):
        validate_ohlcv([first, first])


def test_sma_has_no_value_before_warmup_and_uses_trailing_window() -> None:
    assert simple_moving_average(
        [1.0, 2.0, 3.0, 4.0],
        3,
    ) == [None, None, 2.0, 3.0]


def test_calculate_indicators_is_local_and_deterministic() -> None:
    result = calculate_indicators(
        [bar(0, 10), bar(1, 12), bar(2, 15)],
        sma_period=2,
    )

    assert [item.sma for item in result] == [None, 11.0, 13.5]
    assert result[0].return_pct is None
    assert result[1].return_pct == pytest.approx(20.0)


def test_invalid_period_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        simple_moving_average([1.0], 0)
