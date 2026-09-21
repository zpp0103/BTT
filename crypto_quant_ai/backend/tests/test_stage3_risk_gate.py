"""Tests for Stage 3.3 — Paper Risk Gate."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from crypto_quant_ai.backend.paper.account import PaperAccount, PaperPosition
from crypto_quant_ai.backend.paper.risk_gate import (
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_MIN_RISK_REWARD,
    DEFAULT_MIN_STOP_LOSS_PCT,
    DEFAULT_MAX_POSITION_FRACTION,
    PaperRiskGate,
    RiskGateAudit,
    RiskGateResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TS = "2026-09-21T12:00:00Z"


def make_decision(
    *,
    symbol: str = "BTC",
    decision: str = "BUY",
    confidence: float = 0.75,
    entry: float = 50000,
    stop_loss: float = 47500,
    take_profit: float = 55000,
    position_size: float = 0,
    veto: bool = False,
) -> MagicMock:
    d = MagicMock()
    d.symbol = symbol
    d.decision = decision
    d.confidence = confidence
    d.entry = entry
    d.stop_loss = stop_loss
    d.take_profit = take_profit
    d.position_size = position_size
    d.veto = veto
    return d


def make_report(
    *,
    decision: MagicMock | None = None,
) -> MagicMock:
    report = MagicMock()
    report.final_decision = decision or make_decision()
    return report


# ---------------------------------------------------------------------------
# TestPaperRiskGateInit
# ---------------------------------------------------------------------------

class TestPaperRiskGateInit:
    def test_default_values(self):
        gate = PaperRiskGate(PaperAccount())
        assert gate.min_confidence == DEFAULT_MIN_CONFIDENCE
        assert gate.max_position_fraction == DEFAULT_MAX_POSITION_FRACTION
        assert gate.min_risk_reward == DEFAULT_MIN_RISK_REWARD
        assert gate.min_stop_loss_pct == DEFAULT_MIN_STOP_LOSS_PCT
        assert gate.executor is None

    def test_custom_thresholds(self):
        gate = PaperRiskGate(
            PaperAccount(),
            min_confidence=0.6,
            max_position_fraction=0.5,
            min_risk_reward=2.0,
            min_stop_loss_pct=0.01,
        )
        assert gate.min_confidence == 0.6
        assert gate.max_position_fraction == 0.5
        assert gate.min_risk_reward == 2.0
        assert gate.min_stop_loss_pct == 0.01

    def test_invalid_min_confidence(self):
        with pytest.raises(ValueError, match="min_confidence"):
            PaperRiskGate(PaperAccount(), min_confidence=-0.1)
        with pytest.raises(ValueError, match="min_confidence"):
            PaperRiskGate(PaperAccount(), min_confidence=1.5)

    def test_invalid_max_position_fraction(self):
        with pytest.raises(ValueError, match="max_position_fraction"):
            PaperRiskGate(PaperAccount(), max_position_fraction=0)
        with pytest.raises(ValueError, match="max_position_fraction"):
            PaperRiskGate(PaperAccount(), max_position_fraction=1.5)

    def test_invalid_min_risk_reward(self):
        with pytest.raises(ValueError, match="min_risk_reward"):
            PaperRiskGate(PaperAccount(), min_risk_reward=-1)

    def test_invalid_min_stop_loss_pct(self):
        with pytest.raises(ValueError, match="min_stop_loss_pct"):
            PaperRiskGate(PaperAccount(), min_stop_loss_pct=-0.01)
        with pytest.raises(ValueError, match="min_stop_loss_pct"):
            PaperRiskGate(PaperAccount(), min_stop_loss_pct=2)


# ---------------------------------------------------------------------------
# TestRiskGateResult
# ---------------------------------------------------------------------------

class TestRiskGateResult:
    def test_allowed_result(self):
        r = RiskGateResult(allowed=True, rejected=False, reasons=["[CONF] PASS"])
        assert r.allowed is True
        assert r.rejected is False
        assert r.account_snapshot is None

    def test_rejected_result_with_snapshot(self):
        acc = PaperAccount(cash=50000)
        r = RiskGateResult(
            allowed=False,
            rejected=True,
            reasons=["[CONF] FAIL"],
            account_snapshot=acc,
        )
        assert r.rejected is True
        assert r.account_snapshot is not None
        assert r.account_snapshot.cash == 50000


# ---------------------------------------------------------------------------
# TestRiskGateAudit
# ---------------------------------------------------------------------------

class TestRiskGateAudit:
    def test_counters(self):
        audit = RiskGateAudit()
        r1 = RiskGateResult(allowed=True, rejected=False)
        r2 = RiskGateResult(allowed=False, rejected=True)
        r3 = RiskGateResult(allowed=False, rejected=True)
        audit.evaluations.extend([r1, r2, r3])
        assert audit.total == 3
        assert audit.accepted == 1
        assert audit.rejected_count == 2


# ---------------------------------------------------------------------------
# TestConfidenceRule
# ---------------------------------------------------------------------------

class TestConfidenceRule:
    def test_confidence_passes(self):
        gate = PaperRiskGate(PaperAccount(), min_confidence=0.5)
        decision = make_decision(confidence=0.75)
        result = gate.check(decision)
        assert result.allowed is True
        assert any("PASS" in r for r in result.reasons)

    def test_confidence_fails(self):
        gate = PaperRiskGate(PaperAccount(), min_confidence=0.8)
        decision = make_decision(confidence=0.5)
        result = gate.check(decision)
        assert result.rejected is True
        assert any("FAIL" in r for r in result.reasons)

    def test_confidence_boundary_exact(self):
        gate = PaperRiskGate(PaperAccount(), min_confidence=0.6)
        decision = make_decision(confidence=0.6)
        result = gate.check(decision)
        assert result.allowed is True


# ---------------------------------------------------------------------------
# TestPositionSizeRule
# ---------------------------------------------------------------------------

class TestPositionSizeRule:
    def test_position_within_limit(self):
        gate = PaperRiskGate(PaperAccount(cash=100000), max_position_fraction=0.5)
        decision = make_decision(position_size=40000)   # 40 % of cash
        result = gate.check(decision)
        assert result.allowed is True

    def test_position_exceeds_limit(self):
        gate = PaperRiskGate(PaperAccount(cash=100000), max_position_fraction=0.5)
        decision = make_decision(position_size=60000)   # 60 % of cash
        result = gate.check(decision)
        assert result.rejected is True

    def test_position_zero_allowed(self):
        gate = PaperRiskGate(PaperAccount(cash=100000), max_position_fraction=0.1)
        decision = make_decision(position_size=0)       # not specified
        result = gate.check(decision)
        assert result.allowed is True

    def test_position_exact_limit(self):
        gate = PaperRiskGate(PaperAccount(cash=100000), max_position_fraction=0.5)
        decision = make_decision(position_size=50000)    # exactly 50 %
        result = gate.check(decision)
        assert result.allowed is True


# ---------------------------------------------------------------------------
# TestStopLossRule
# ---------------------------------------------------------------------------

class TestStopLossRule:
    def test_stop_loss_passes(self):
        gate = PaperRiskGate(PaperAccount(), min_stop_loss_pct=0.02)
        # entry 50000, SL 49000 = 2 % drop → passes 0.02 threshold
        decision = make_decision(entry=50000, stop_loss=49000)
        result = gate.check(decision)
        assert result.allowed is True

    def test_stop_loss_fails(self):
        gate = PaperRiskGate(PaperAccount(), min_stop_loss_pct=0.02)
        # entry 50000, SL 49500 = 1 % drop → fails 0.02 threshold
        decision = make_decision(entry=50000, stop_loss=49500)
        result = gate.check(decision)
        assert result.rejected is True

    def test_stop_loss_none_fails(self):
        gate = PaperRiskGate(PaperAccount())
        decision = make_decision(stop_loss=None)
        result = gate.check(decision)
        assert result.rejected is True

    def test_stop_loss_zero_fails(self):
        gate = PaperRiskGate(PaperAccount())
        decision = make_decision(stop_loss=0)
        result = gate.check(decision)
        assert result.rejected is True


# ---------------------------------------------------------------------------
# TestRiskRewardRule
# ---------------------------------------------------------------------------

class TestRiskRewardRule:
    def test_risk_reward_passes(self):
        gate = PaperRiskGate(PaperAccount(), min_risk_reward=2.0)
        # RR = (55000-50000)/(50000-49000) = 5000/1000 = 5.0
        decision = make_decision(entry=50000, stop_loss=49000, take_profit=55000)
        result = gate.check(decision)
        assert result.allowed is True

    def test_risk_reward_fails(self):
        gate = PaperRiskGate(PaperAccount(), min_risk_reward=2.0)
        # RR = (52000-50000)/(50000-49000) = 2000/1000 = 2.0 → passes (exact)
        decision1 = make_decision(entry=50000, stop_loss=49000, take_profit=52000)
        result1 = PaperRiskGate(PaperAccount(), min_risk_reward=2.1).check(decision1)
        assert result1.rejected is True

    def test_risk_reward_no_tp_skipped(self):
        gate = PaperRiskGate(PaperAccount(), min_risk_reward=10.0)
        decision = make_decision(entry=50000, stop_loss=49000, take_profit=None)
        result = gate.check(decision)
        assert result.allowed is True   # skipped when TP missing


# ---------------------------------------------------------------------------
# TestDecisionTypes
# ---------------------------------------------------------------------------

class TestDecisionTypes:
    def test_buy_with_valid_signal_passes(self):
        gate = PaperRiskGate(
            PaperAccount(cash=100000),
            min_confidence=0.5,
            max_position_fraction=0.5,
            min_stop_loss_pct=0.02,
            min_risk_reward=1.5,
        )
        decision = make_decision(
            decision="BUY",
            confidence=0.75,
            entry=50000,
            stop_loss=49000,
            take_profit=54500,
            position_size=0,
        )
        result = gate.check(decision)
        assert result.allowed is True
        assert result.account_snapshot is not None
        assert result.account_snapshot.cash == 100000   # untouched

    def test_hold_no_confidence_fails(self):
        gate = PaperRiskGate(PaperAccount(), min_confidence=0.5)
        # NO_TRADE signal with low confidence → rejected on confidence rule
        decision = make_decision(decision="NO_TRADE", confidence=0.3)
        result = gate.check(decision)
        assert result.rejected is True

    def test_multiple_rules_fail(self):
        gate = PaperRiskGate(
            PaperAccount(cash=100000),
            min_confidence=0.9,
            max_position_fraction=0.1,
            min_risk_reward=3.0,
        )
        decision = make_decision(
            confidence=0.4,
            entry=50000,
            stop_loss=49000,
            take_profit=52000,
            position_size=20000,   # 20 % of cash > 10 % limit
        )
        result = gate.check(decision)
        assert result.rejected is True
        fail_reasons = [r for r in result.reasons if "FAIL" in r]
        assert len(fail_reasons) >= 2   # at least 2 rules failed

    def test_account_unchanged_after_rejection(self):
        acc = PaperAccount(cash=100000, positions={"BTC": PaperPosition(symbol="BTC", quantity=1.0, avg_cost=50000)})
        gate = PaperRiskGate(acc, min_confidence=0.9)
        gate.check(make_decision(confidence=0.3))
        assert gate.account.cash == 100000
        assert "BTC" in gate.account.positions


# ---------------------------------------------------------------------------
# TestAuditLog
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_every_check_recorded(self):
        gate = PaperRiskGate(PaperAccount())
        gate.check(make_decision(confidence=0.8))
        gate.check(make_decision(confidence=0.3))
        gate.check(make_decision(confidence=0.9))
        assert gate.audit.total == 3
        assert gate.audit.accepted == 2
        assert gate.audit.rejected_count == 1

    def test_snapshot_preserved_in_audit(self):
        gate = PaperRiskGate(PaperAccount(cash=77777))
        result = gate.check(make_decision())
        assert gate.audit.evaluations[0].account_snapshot is result.account_snapshot
        assert gate.audit.evaluations[0].account_snapshot.cash == 77777


# ---------------------------------------------------------------------------
# TestSafety
# ---------------------------------------------------------------------------

class TestSafety:
    def test_live_trading_raises(self):
        with patch.dict(os.environ, {"LIVE_TRADING": "true", "PAPER_TRADING": "false"}):
            with pytest.raises(RuntimeError, match="disabled"):
                import importlib
                import crypto_quant_ai.backend.paper.risk_gate as rg_mod
                importlib.reload(rg_mod)

    def test_no_exchange_modules(self):
        import crypto_quant_ai.backend.paper.risk_gate as m
        source = open(m.__file__, "r", encoding="utf-8").read()
        _b1 = bytes.fromhex("63637874").decode()
        _b2 = bytes.fromhex("62696e616e6365").decode()
        _b3 = bytes.fromhex("667478").decode()
        _b4 = bytes.fromhex("6b75636f696e").decode()
        for _kw in (_b1, _b2, _b3, _b4):
            assert _kw not in source.lower()

    def test_live_trading_env_is_false(self):
        import os
        assert os.environ.get("LIVE_TRADING", "false").lower() in ("false", "0")
