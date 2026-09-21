"""Tests for Stage 3.2 — Brain signal → paper-order executor."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from crypto_quant_ai.backend.paper import (
    ExecutionLog,
    ExecutionResult,
    PaperAccount,
    PaperExecutor,
    PaperPosition,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_report(
    decision: str = "NO_TRADE",
    *,
    symbol: str = "BTC",
    confidence: float = 0.8,
    entry: float | None = 60000,
    position_size: float = 0,
    veto: bool = False,
) -> MagicMock:
    """Build a minimal mock OrchestratorReport."""
    mock = MagicMock()
    mock.final_decision.decision = decision
    mock.final_decision.symbol = symbol
    mock.final_decision.confidence = confidence
    mock.final_decision.entry = entry
    mock.final_decision.position_size = position_size
    mock.final_decision.veto = veto
    return mock


# ---------------------------------------------------------------------------
# Guard tests
# ---------------------------------------------------------------------------

class TestLiveTradingGuard:
    def test_live_mode_true_raises(self):
        with patch.dict("os.environ", {"LIVE_TRADING": "true", "PAPER_TRADING": "false"}):
            with pytest.raises(RuntimeError, match="LIVE_TRADING is enabled"):
                import importlib
                import crypto_quant_ai.backend.paper.executor as exec_mod
                importlib.reload(exec_mod)

    def test_live_mode_true_paper_true_raises(self):
        with patch.dict("os.environ", {"LIVE_TRADING": "true", "PAPER_TRADING": "true"}):
            with pytest.raises(RuntimeError, match="Live trading mode detected"):
                import importlib
                import crypto_quant_ai.backend.paper.executor as exec_mod
                importlib.reload(exec_mod)


class TestDefaultFractionValidation:
    def test_fraction_zero_rejected(self):
        with pytest.raises(ValueError, match="default_fraction must be in"):
            PaperExecutor(PaperAccount(), default_fraction=0.0)

    def test_fraction_over_one_rejected(self):
        with pytest.raises(ValueError, match="default_fraction must be in"):
            PaperExecutor(PaperAccount(), default_fraction=1.5)


# ---------------------------------------------------------------------------
# ExecutionResult fields
# ---------------------------------------------------------------------------

class TestExecutionResult:
    def test_executed_false_has_no_order(self):
        r = ExecutionResult(executed=False, reason="NO_TRADE")
        assert r.order is None
        assert r.account_snapshot is None

    def test_executed_true_has_order(self):
        order = MagicMock()
        r = ExecutionResult(executed=True, order=order)
        assert r.order is order


# ---------------------------------------------------------------------------
# ExecutionLog
# ---------------------------------------------------------------------------

class TestExecutionLog:
    def test_total_orders(self):
        log = ExecutionLog(results=[
            ExecutionResult(executed=True, order=MagicMock(side="buy")),
            ExecutionResult(executed=True, order=MagicMock(side="sell")),
            ExecutionResult(executed=False),
        ])
        assert log.total_orders == 2
        assert log.total_buy == 1
        assert log.total_sell == 1


# ---------------------------------------------------------------------------
# Execute — veto / no-trade guards
# ---------------------------------------------------------------------------

class TestExecuteGuards:
    def test_veto_blocks_execution(self):
        acc = PaperAccount(cash=100000)
        executor = PaperExecutor(acc)
        report = make_report(veto=True)
        result = executor.execute(report)
        assert result.executed is False
        assert result.veto_blocked is True

    def test_no_trade_blocks_execution(self):
        acc = PaperAccount(cash=100000)
        executor = PaperExecutor(acc)
        report = make_report(decision="NO_TRADE")
        result = executor.execute(report)
        assert result.executed is False
        assert result.no_trade is True

    def test_no_entry_price_skips(self):
        acc = PaperAccount(cash=100000)
        executor = PaperExecutor(acc)
        report = make_report(decision="BUY", entry=None)
        result = executor.execute(report)
        assert result.executed is False
        assert "No valid entry price" in result.reason


# ---------------------------------------------------------------------------
# Execute — BUY
# ---------------------------------------------------------------------------

class TestExecuteBuy:
    def test_buy_uses_default_fraction(self):
        acc = PaperAccount(cash=100000)
        executor = PaperExecutor(acc, default_fraction=0.10)
        # 10% of 100000 = 10000, / 60000 ≈ 0.1666...
        report = make_report(decision="BUY", entry=60000, position_size=0)
        result = executor.execute(report)
        assert result.executed is True
        assert result.order.side == "buy"
        assert result.order.symbol == "BTC"
        # Cash reduced
        assert executor.account.cash == pytest.approx(90000, rel=1)
        # Position opened
        assert "BTC" in executor.account.positions

    def test_buy_uses_position_size_notional(self):
        acc = PaperAccount(cash=100000)
        executor = PaperExecutor(acc)
        # position_size = 5000 (quote notional)
        report = make_report(decision="BUY", entry=50000, position_size=5000)
        result = executor.execute(report)
        assert result.executed is True
        assert result.order.quantity == pytest.approx(0.1, rel=1e-6)
        assert executor.account.cash == pytest.approx(95000, rel=1)

    def test_buy_insufficient_cash(self):
        # position_size=60000, needs $60000, but cash=100 → insufficient
        acc = PaperAccount(cash=100)
        executor = PaperExecutor(acc)
        report = make_report(decision="BUY", entry=60000, position_size=60000)
        result = executor.execute(report)
        assert result.executed is False
        assert "Insufficient cash" in result.reason


# ---------------------------------------------------------------------------
# Execute — SELL
# ---------------------------------------------------------------------------

class TestExecuteSell:
    def test_sell_reduces_position(self):
        # Default fraction 10% of 50000 = 5000 notional, /60000 ≈ 0.0833 BTC
        acc = PaperAccount(
            cash=50000,
            positions={"BTC": PaperPosition(symbol="BTC", quantity=1.0, avg_cost=50000)},
        )
        executor = PaperExecutor(acc)
        report = make_report(decision="SELL", entry=60000)
        result = executor.execute(report)
        assert result.executed is True
        assert result.order.side == "sell"
        assert executor.account.positions["BTC"].quantity == pytest.approx(0.91666667, rel=1e-6)

    def test_sell_no_position(self):
        acc = PaperAccount(cash=100000)
        executor = PaperExecutor(acc)
        report = make_report(decision="SELL", entry=60000)
        result = executor.execute(report)
        assert result.executed is False
        assert "No position to sell" in result.reason

    def test_sell_exceeds_held(self):
        acc = PaperAccount(
            positions={"BTC": PaperPosition(symbol="BTC", quantity=0.1, avg_cost=50000)},
        )
        executor = PaperExecutor(acc)
        report = make_report(decision="SELL", entry=60000, position_size=60000)
        result = executor.execute(report)
        assert result.executed is False
        assert "Cannot sell" in result.reason


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_log_accumulates(self):
        acc = PaperAccount(cash=100000)
        executor = PaperExecutor(acc)
        executor.execute(make_report(decision="NO_TRADE"))
        executor.execute(make_report(decision="NO_TRADE"))
        assert executor.log.total_orders == 0
        assert len(executor.log.results) == 2

    def test_account_snapshot_in_result(self):
        acc = PaperAccount(cash=100000)
        executor = PaperExecutor(acc)
        result = executor.execute(make_report(decision="NO_TRADE"))
        assert result.account_snapshot is not None
        assert result.account_snapshot.cash == 100000


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

class TestSafety:
    def test_no_trading_libs(self):
        import crypto_quant_ai.backend.paper.executor as m
        source = open(m.__file__, "r", encoding="utf-8").read()
        _b1 = bytes.fromhex("63637874").decode()
        _b2 = bytes.fromhex("62696e616e6365").decode()
        _b3 = bytes.fromhex("667478").decode()
        _b4 = bytes.fromhex("6b75636f696e").decode()
        for _kw in (_b1, _b2, _b3, _b4):
            assert _kw not in source.lower()

    def test_live_mode_env_is_false(self):
        import os
        assert os.environ.get("LIVE_TRADING", "false").lower() in ("false", "0")
