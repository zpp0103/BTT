"""Stage 9 - Layer 1: Market Intelligence (regime classification).

Local, paper-only analysis of historical OHLCV. No network, no external
venue, no order submission. Reads only the candles passed in.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from crypto_quant_ai.backend.data.ohlcv import OHLCVBar


class Regime(str, Enum):
    TREND = "trend"
    RANGE = "range"
    HIGH_VOL = "high_vol"
    LOW_VOL = "low_vol"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MarketState:
    regime: Regime
    confidence: float
    features: dict[str, float]
    summary: str


def _finite(x: float, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _returns(closes: Sequence[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        cur = closes[i]
        if prev > 0:
            out.append((cur - prev) / prev)
    return out


def _mean(xs: Sequence[float]) -> float:
    xs = [x for x in xs if math.isfinite(x)]
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: Sequence[float]) -> float:
    xs = [x for x in xs if math.isfinite(x)]
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    var = _mean([(x - m) ** 2 for x in xs])
    return math.sqrt(var)


def _trend_strength(closes: Sequence[float], short: int = 5, long: int = 20) -> float:
    if len(closes) < long or long <= 0:
        return 0.0
    s = _mean(closes[-short:]) if len(closes) >= short else _mean(closes)
    l = _mean(closes[-long:])
    if l == 0:
        return 0.0
    return _finite((s - l) / abs(l))


def classify_regime(candles: Sequence[OHLCVBar], window: int = 20) -> MarketState:
    if not candles:
        return MarketState(Regime.UNKNOWN, 0.0, {}, "no candles provided")
    window = max(2, min(window, len(candles)))
    recent = list(candles[-window:])
    closes = [_finite(c.close) for c in recent]
    rets = _returns(closes)
    if not rets:
        return MarketState(Regime.UNKNOWN, 0.0, {"window": float(window)}, "insufficient variation")
    vol = _stdev(rets)
    trend = _trend_strength(closes)
    vol_norm = min(1.0, _finite(vol) / 0.05)
    trend_abs = min(1.0, abs(trend) / 0.1)
    features = {
        "volatility": _finite(vol),
        "volatility_norm": vol_norm,
        "trend_strength": _finite(trend),
        "trend_abs": trend_abs,
        "window": float(window),
    }
    if vol_norm >= 0.6:
        regime = Regime.HIGH_VOL
        conf = vol_norm
        summary = f"high volatility regime (vol_norm={vol_norm:.2f})"
    elif vol_norm <= 0.2 and trend_abs <= 0.3:
        regime = Regime.LOW_VOL
        conf = 1.0 - vol_norm
        summary = f"low volatility / quiet regime (vol_norm={vol_norm:.2f})"
    elif trend_abs >= 0.5:
        regime = Regime.TREND
        conf = trend_abs
        direction = "up" if trend > 0 else "down"
        summary = f"trending regime ({direction}, trend_abs={trend_abs:.2f})"
    else:
        regime = Regime.RANGE
        conf = 1.0 - max(vol_norm, trend_abs)
        summary = f"range-bound regime (vol_norm={vol_norm:.2f}, trend_abs={trend_abs:.2f})"
    conf = _finite(min(1.0, max(0.0, conf)), 0.0)
    return MarketState(regime, conf, features, summary)


def consensus_regime(
    candles: Sequence[OHLCVBar],
    timeframes: Sequence[int] | None = None,
) -> MarketState:
    if timeframes is None:
        timeframes = (20, 50, 100)
    timeframes = [t for t in timeframes if t >= 2]
    if not timeframes:
        timeframes = (20,)
    states = [classify_regime(candles, w) for w in timeframes]
    tally: dict[Regime, float] = {}
    weight_total = 0.0
    for st in states:
        w = 0.5 + st.confidence
        tally[st.regime] = tally.get(st.regime, 0.0) + w
        weight_total += w
    if not tally:
        return MarketState(Regime.UNKNOWN, 0.0, {}, "no timeframe classifications")
    best = max(tally.items(), key=lambda kv: kv[1])[0]
    consensus_conf = _finite(tally[best] / weight_total, 0.0) if weight_total > 0 else 0.0
    parts = [f"{s.regime.value}:{s.confidence:.2f}" for s in states]
    summary = f"consensus={best.value} across {len(states)} timeframes [{', '.join(parts)}]"
    return MarketState(best, consensus_conf, {"timeframes": float(len(states))}, summary)
