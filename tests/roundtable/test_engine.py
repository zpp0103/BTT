"""Unit tests for the deterministic roundtable veto pipeline."""

from types import SimpleNamespace

from user_data.roundtable.engine import evaluate


def row(**overrides):
    values = {
        "close": 110.0,
        "ema_fast": 105.0,
        "ema_slow": 100.0,
        "rsi": 60.0,
        "bb_mid": 104.0,
        "volume_ratio": 1.2,
        "adx": 25.0,
        "atr_pct": 0.02,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_roundtable_approves_agreeing_long_opinions():
    decision = evaluate(row())
    assert decision.approved is True
    assert decision.direction == "long"
    assert decision.verification.approved is True


def test_roundtable_approves_agreeing_short_opinions():
    decision = evaluate(
        row(close=90.0, ema_fast=95.0, ema_slow=100.0, rsi=40.0, bb_mid=96.0)
    )
    assert decision.approved is True
    assert decision.direction == "short"


def test_verifier_vetoes_unsafe_volatility():
    decision = evaluate(row(atr_pct=0.20))
    assert decision.approved is False
    assert decision.direction == "pass"
    assert decision.verification.approved is False
