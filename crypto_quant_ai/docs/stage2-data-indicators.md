# Stage 2.1 — Local OHLCV and Indicators

## Scope

Stage 2.1 provides deterministic, local-only market data validation and basic indicators.

Included:

- OHLCV candle validation
  - Positive OHLC prices
  - Non-negative volume
  - Finite numeric values
  - High/low range validation
  - Strictly increasing timestamps
- Trailing simple moving average
- Close-to-close return percentage

## Safety Boundary

Stage 2.1 does not provide:

- Exchange connectivity
- Network market-data fetching
- API key handling
- API secret handling
- Paper trading
- Live trading
- Order placement
- Any external signal or model inference beyond deterministic rules

All inputs are expected to come from local, non-live sources. No network calls,
no credentials, and no trade execution are performed by this layer.

## Usage

```python
from crypto_quant_ai.backend.data import (
    OHLCVBar,
    calculate_indicators,
    simple_moving_average,
    validate_ohlcv,
)

bars = [
    OHLCVBar(timestamp=..., open=10, high=11, low=9, close=10, volume=1.0),
    # ...
]
validated = validate_ohlcv(bars)
snapshots = calculate_indicators(validated, sma_period=3)
```

## Testing

```bash
PYTHONPATH=. pytest -q crypto_quant_ai/backend/tests/test_stage2_data.py
```
