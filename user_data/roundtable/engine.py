"""Deterministic four-role roundtable decision engine.

The first implementation is deliberately local and deterministic: it does not call
an LLM or an exchange. This makes backtesting and paper trading reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnalystOpinion:
    role: str
    direction: str
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Verification:
    approved: bool
    reason: str
    risk_level: str


@dataclass(frozen=True)
class RoundtableDecision:
    approved: bool
    direction: str
    confidence: float
    reason: str
    analyst_one: AnalystOpinion
    analyst_two: AnalystOpinion
    verification: Verification

    @property
    def as_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "direction": self.direction,
            "confidence": self.confidence,
            "reason": self.reason,
            "verification": {
                "approved": self.verification.approved,
                "reason": self.verification.reason,
                "risk_level": self.verification.risk_level,
            },
        }


def _direction(score: float) -> str:
    if score >= 0.5:
        return "long"
    if score <= -0.5:
        return "short"
    return "pass"


def _analyst_one(row: Any) -> AnalystOpinion:
    score = 0.0
    reasons: list[str] = []
    if row.close > row.ema_fast > row.ema_slow:
        score += 1.0
        reasons.append("EMA trend is bullish")
    elif row.close < row.ema_fast < row.ema_slow:
        score -= 1.0
        reasons.append("EMA trend is bearish")
    if row.rsi >= 52:
        score += 0.5
        reasons.append("RSI confirms positive momentum")
    elif row.rsi <= 48:
        score -= 0.5
        reasons.append("RSI confirms negative momentum")
    return AnalystOpinion("strategy", _direction(score), min(abs(score) / 1.5, 1.0), tuple(reasons))


def _analyst_two(row: Any) -> AnalystOpinion:
    score = 0.0
    reasons: list[str] = []
    if row.close > row.bb_mid and row.volume_ratio >= 1.0:
        score += 1.0
        reasons.append("price is above Bollinger midline with volume")
    elif row.close < row.bb_mid and row.volume_ratio >= 1.0:
        score -= 1.0
        reasons.append("price is below Bollinger midline with volume")
    if row.adx >= 20:
        score += 0.5 if row.close >= row.bb_mid else -0.5
        reasons.append("ADX confirms a tradable trend")
    return AnalystOpinion("confirmation", _direction(score), min(abs(score) / 1.5, 1.0), tuple(reasons))


def evaluate(row: Any, *, min_confidence: float = 0.67) -> RoundtableDecision:
    """Run roles 1-4. The verifier is a hard veto; failures always return PASS."""
    one = _analyst_one(row)
    two = _analyst_two(row)
    same_direction = one.direction == two.direction and one.direction in {"long", "short"}
    confidence = (one.score + two.score) / 2.0
    volatility_ok = 0.005 <= float(row.atr_pct) <= 0.08
    approved = same_direction and confidence >= min_confidence and volatility_ok
    verification = Verification(
        approved=approved,
        reason=("independent opinions agree and volatility is within limits" if approved
                else "analysts disagree, confidence is low, or volatility is unsafe"),
        risk_level="normal" if approved else "high",
    )
    return RoundtableDecision(
        approved=approved,
        direction=one.direction if approved else "pass",
        confidence=confidence if approved else 0.0,
        reason=verification.reason,
        analyst_one=one,
        analyst_two=two,
        verification=verification,
    )
