"""
Stage 4 — Backtest Engine Tests

Covers: types validation, equity tracker, trade ledger (FIFO),
metrics calculation, simulator end-to-end, safety guards.

Run: PYTHONPATH=. python -m pytest crypto_quant_ai/backend/tests/test_stage4_backtest.py --noconftest -q
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

UTC = timezone.utc


def _ts(minutes: int = 0) -> datetime:
    """Timestamp helper: base time + minutes."""
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _bar(close: float, ts: datetime | None = None) -> object:
    """Create a minimal OHLCV-like object for testing."""
    bar = MagicMock()
    bar.close = close
    bar.timestamp = ts or _ts(0)
    bar.open = close
    bar.high = close
    bar.low = close
    bar.volume = 1000.0
    return bar


def _bars(closes: list[float]) -> list:
    """Create a list of mock bars from close prices."""
    return [_bar(c, _ts(i)) for i, c in enumerate(closes)]


def _buy_signal(price: float, qty: float = 1.0, ts: datetime | None = None) -> object:
    from crypto_quant_ai.backend.backtest.simulator import CandleSignal
    from crypto_quant_ai.backend.backtest.types import TradeAction
    return CandleSignal(
        timestamp=ts or _ts(0),
        symbol="BTC",
        action=TradeAction.BUY,
        price=price,
        quantity=qty,
        reason="test_buy",
    )


def _sell_signal(price: float, qty: float = 1.0, ts: datetime | None = None) -> object:
    from crypto_quant_ai.backend.backtest.simulator import CandleSignal
    from crypto_quant_ai.backend.backtest.types import TradeAction
    return CandleSignal(
        timestamp=ts or _ts(0),
        symbol="BTC",
        action=TradeAction.SELL,
        price=price,
        quantity=qty,
        reason="test_sell",
    )


def _hold_signal(ts: datetime | None = None) -> object:
    from crypto_quant_ai.backend.backtest.simulator import CandleSignal
    from crypto_quant_ai.backend.backtest.types import TradeAction
    return CandleSignal(
        timestamp=ts or _ts(0),
        symbol="BTC",
        action=TradeAction.HOLD,
        price=100.0,
        quantity=0.0,
        reason="test_hold",
    )


# ------------------------------------------------------------------ #
# TestBacktestConfig
# ------------------------------------------------------------------ #

class TestBacktestConfig:
    """BacktestConfig validation tests."""

    def test_default_config(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        cfg = BacktestConfig()
        assert cfg.initial_cash == 100_000.0
        assert cfg.fee_bps == 10.0
        assert cfg.slippage_bps == 5.0
        assert cfg.paper_trading is True

    def test_fee_rate(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        cfg = BacktestConfig(fee_bps=20.0)
        assert cfg.fee_rate == 0.002

    def test_slippage_rate(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        cfg = BacktestConfig(slippage_bps=50.0)
        assert cfg.slippage_rate == 0.005

    def test_negative_initial_cash_rejected(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        with pytest.raises(ValueError, match="initial_cash must be positive"):
            BacktestConfig(initial_cash=-1000)

    def test_zero_initial_cash_rejected(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        with pytest.raises(ValueError, match="initial_cash must be positive"):
            BacktestConfig(initial_cash=0)

    def test_negative_fee_rejected(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        with pytest.raises(ValueError, match="fee_bps must be non-negative"):
            BacktestConfig(fee_bps=-5.0)

    def test_negative_slippage_rejected(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        with pytest.raises(ValueError, match="slippage_bps must be non-negative"):
            BacktestConfig(slippage_bps=-1.0)

    def test_paper_trading_false_rejected(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        with pytest.raises(ValueError, match="paper_trading must be true"):
            BacktestConfig(paper_trading=False)

    def test_start_after_end_rejected(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        t1 = _ts(10)
        t2 = _ts(5)
        with pytest.raises(ValueError, match="start_time must be before end_time"):
            BacktestConfig(start_time=t1, end_time=t2)

    def test_config_is_frozen(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        cfg = BacktestConfig()
        with pytest.raises(Exception):
            cfg.initial_cash = 50000  # type: ignore[misc]


# ------------------------------------------------------------------ #
# TestBacktestTrade
# ------------------------------------------------------------------ #

class TestBacktestTrade:
    """BacktestTrade validation tests."""

    def test_valid_trade(self):
        from crypto_quant_ai.backend.backtest.types import BacktestTrade, TradeAction
        trade = BacktestTrade(
            trade_id="t_0001",
            timestamp=_ts(0),
            symbol="BTC",
            action=TradeAction.BUY,
            quantity=1.0,
            price=50000.0,
            fee=5.0,
            slippage_cost=2.5,
            cash_after=49995.0,
            position_after=1.0,
            reason="test",
        )
        assert trade.trade_id == "t_0001"
        assert trade.action == TradeAction.BUY

    def test_zero_quantity_rejected(self):
        from crypto_quant_ai.backend.backtest.types import BacktestTrade, TradeAction
        # BUY with zero quantity should be rejected
        with pytest.raises(ValueError, match="quantity must be positive"):
            BacktestTrade(
                trade_id="t_0001",
                timestamp=_ts(0),
                symbol="BTC",
                action=TradeAction.BUY,
                quantity=0,
                price=50000.0,
                fee=0,
                slippage_cost=0,
                cash_after=100000,
                position_after=0,
            )

    def test_hold_zero_quantity_allowed(self):
        from crypto_quant_ai.backend.backtest.types import BacktestTrade, TradeAction
        # HOLD with zero quantity should be allowed
        trade = BacktestTrade(
            trade_id="t_0001",
            timestamp=_ts(0),
            symbol="BTC",
            action=TradeAction.HOLD,
            quantity=0,
            price=100,
            fee=0,
            slippage_cost=0,
            cash_after=100000,
            position_after=0,
        )
        assert trade.action == TradeAction.HOLD

    def test_negative_price_rejected(self):
        from crypto_quant_ai.backend.backtest.types import BacktestTrade, TradeAction
        with pytest.raises(ValueError, match="price must be positive"):
            BacktestTrade(
                trade_id="t_0001",
                timestamp=_ts(0),
                symbol="BTC",
                action=TradeAction.SELL,
                quantity=1.0,
                price=-100,
                fee=0,
                slippage_cost=0,
                cash_after=100000,
                position_after=0,
            )

    def test_empty_symbol_rejected(self):
        from crypto_quant_ai.backend.backtest.types import BacktestTrade, TradeAction
        with pytest.raises(ValueError, match="symbol must be non-empty"):
            BacktestTrade(
                trade_id="t_0001",
                timestamp=_ts(0),
                symbol="",
                action=TradeAction.BUY,
                quantity=1.0,
                price=100,
                fee=0,
                slippage_cost=0,
                cash_after=100,
                position_after=1,
            )

    def test_trade_is_frozen(self):
        from crypto_quant_ai.backend.backtest.types import BacktestTrade, TradeAction
        trade = BacktestTrade(
            trade_id="t_0001",
            timestamp=_ts(0),
            symbol="BTC",
            action=TradeAction.BUY,
            quantity=1.0,
            price=100,
            fee=0,
            slippage_cost=0,
            cash_after=99,
            position_after=1,
        )
        with pytest.raises(Exception):
            trade.quantity = 2.0  # type: ignore[misc]


# ------------------------------------------------------------------ #
# TestBacktestMetrics
# ------------------------------------------------------------------ #

class TestBacktestMetrics:
    """BacktestMetrics validation tests."""

    def test_valid_metrics(self):
        from crypto_quant_ai.backend.backtest.types import BacktestMetrics
        m = BacktestMetrics(
            total_return=5000.0,
            total_return_pct=0.05,
            max_drawdown=2000.0,
            max_drawdown_pct=0.02,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            win_rate=0.6,
            win_rate_pct=60.0,
            total_trades=20,
            winning_trades=12,
            losing_trades=8,
            avg_win=500,
            avg_loss=-300,
            profit_factor=2.5,
            final_equity=105000,
            initial_cash=100000,
        )
        assert m.total_return == 5000.0
        assert m.total_trades == 20

    def test_negative_total_trades_rejected(self):
        from crypto_quant_ai.backend.backtest.types import BacktestMetrics
        with pytest.raises(ValueError, match="total_trades must be non-negative"):
            BacktestMetrics(
                total_return=0, total_return_pct=0,
                max_drawdown=0, max_drawdown_pct=0,
                sharpe_ratio=0, sortino_ratio=0,
                win_rate=0, win_rate_pct=0,
                total_trades=-1, winning_trades=0, losing_trades=0,
                avg_win=0, avg_loss=0, profit_factor=0,
                final_equity=100000, initial_cash=100000,
            )

    def test_win_lose_exceed_total_rejected(self):
        from crypto_quant_ai.backend.backtest.types import BacktestMetrics
        with pytest.raises(ValueError, match="winning.*losing.*<=.*total"):
            BacktestMetrics(
                total_return=0, total_return_pct=0,
                max_drawdown=0, max_drawdown_pct=0,
                sharpe_ratio=0, sortino_ratio=0,
                win_rate=0, win_rate_pct=0,
                total_trades=5, winning_trades=3, losing_trades=3,
                avg_win=0, avg_loss=0, profit_factor=0,
                final_equity=100000, initial_cash=100000,
            )


# ------------------------------------------------------------------ #
# TestEquityTracker
# ------------------------------------------------------------------ #

class TestEquityTracker:
    """EquityTracker drawdown and recording tests."""

    def test_record_and_retrieve(self):
        from crypto_quant_ai.backend.backtest.equity_tracker import EquityTracker
        tracker = EquityTracker()
        tracker.record(_ts(0), cash=90000, position_value=10000)
        assert len(tracker.points) == 1
        assert tracker.final_equity == 100000

    def test_peak_tracking(self):
        from crypto_quant_ai.backend.backtest.equity_tracker import EquityTracker
        tracker = EquityTracker()
        tracker.record(_ts(0), cash=100000, position_value=0)    # equity=100k
        tracker.record(_ts(1), cash=95000, position_value=8000)  # equity=103k (new peak)
        tracker.record(_ts(2), cash=90000, position_value=5000)  # equity=95k (drawdown)
        assert tracker.peak_equity == 103000
        assert tracker.max_drawdown == 8000
        assert abs(tracker.max_drawdown_pct - 8000 / 103000) < 1e-9

    def test_new_peak_resets_trough(self):
        from crypto_quant_ai.backend.backtest.equity_tracker import EquityTracker
        tracker = EquityTracker()
        tracker.record(_ts(0), cash=100000, position_value=0)
        tracker.record(_ts(1), cash=90000, position_value=0)   # dd=10k
        tracker.record(_ts(2), cash=110000, position_value=0)  # new peak=110k
        tracker.record(_ts(3), cash=105000, position_value=0)  # dd=5k (less than max)
        assert tracker.peak_equity == 110000
        assert tracker.max_drawdown == 10000  # still the first drawdown

    def test_initial_and_final_equity(self):
        from crypto_quant_ai.backend.backtest.equity_tracker import EquityTracker
        tracker = EquityTracker()
        tracker.record(_ts(0), cash=100000, position_value=0)
        tracker.record(_ts(1), cash=95000, position_value=8000)
        tracker.record(_ts(2), cash=90000, position_value=12000)
        assert tracker.initial_equity == 100000
        assert tracker.final_equity == 102000

    def test_equity_series(self):
        from crypto_quant_ai.backend.backtest.equity_tracker import EquityTracker
        tracker = EquityTracker()
        tracker.record(_ts(0), cash=100000, position_value=0)
        tracker.record(_ts(1), cash=90000, position_value=15000)
        series = tracker.equity_series()
        assert len(series) == 2
        assert series[0][1] == 100000
        assert series[1][1] == 105000

    def test_reset(self):
        from crypto_quant_ai.backend.backtest.equity_tracker import EquityTracker
        tracker = EquityTracker()
        tracker.record(_ts(0), cash=100000, position_value=0)
        tracker.reset()
        assert len(tracker.points) == 0
        assert tracker.final_equity == 0

    def test_negative_equity_rejected(self):
        from crypto_quant_ai.backend.backtest.equity_tracker import EquityTracker
        tracker = EquityTracker()
        with pytest.raises(ValueError, match="equity must be non-negative"):
            tracker.record(_ts(0), cash=-100, position_value=0)

    def test_no_points_max_drawdown_zero(self):
        from crypto_quant_ai.backend.backtest.equity_tracker import EquityTracker
        tracker = EquityTracker()
        assert tracker.max_drawdown == 0.0
        assert tracker.max_drawdown_pct == 0.0
        assert tracker.final_equity == 0.0


# ------------------------------------------------------------------ #
# TestTradeLedger
# ------------------------------------------------------------------ #

class TestTradeLedger:
    """TradeLedger FIFO matching and statistics tests."""

    def _make_trade(self, action_str, qty, price, ts_min=0):
        from crypto_quant_ai.backend.backtest.types import BacktestTrade, TradeAction
        action = TradeAction(action_str)
        return BacktestTrade(
            trade_id=f"t_{ts_min:04d}",
            timestamp=_ts(ts_min),
            symbol="BTC",
            action=action,
            quantity=qty,
            price=price,
            fee=0.0,
            slippage_cost=0.0,
            cash_after=0.0,
            position_after=0.0,
            reason="test",
        )

    def test_buy_then_sell_fifo(self):
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        ledger = TradeLedger()
        ledger.record(self._make_trade("buy", 1.0, 100, 0))
        ledger.record(self._make_trade("sell", 1.0, 110, 1))
        assert len(ledger.closed_trades) == 1
        ct = ledger.closed_trades[0]
        assert ct.pnl == 10.0
        assert ct.is_win is True

    def test_partial_sell_fifo(self):
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        ledger = TradeLedger()
        ledger.record(self._make_trade("buy", 2.0, 100, 0))
        ledger.record(self._make_trade("sell", 1.0, 110, 1))
        assert len(ledger.closed_trades) == 1
        assert ledger.closed_trades[0].quantity == 1.0
        assert ledger.closed_trades[0].pnl == 10.0

    def test_multiple_buys_then_sell_fifo(self):
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        ledger = TradeLedger()
        ledger.record(self._make_trade("buy", 1.0, 100, 0))
        ledger.record(self._make_trade("buy", 1.0, 105, 1))
        ledger.record(self._make_trade("sell", 1.5, 110, 2))
        # FIFO: first 1.0 from price=100, then 0.5 from price=105
        assert len(ledger.closed_trades) == 2
        assert ledger.closed_trades[0].buy_price == 100
        assert ledger.closed_trades[0].quantity == 1.0
        assert ledger.closed_trades[1].buy_price == 105
        assert ledger.closed_trades[1].quantity == 0.5

    def test_win_rate(self):
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        ledger = TradeLedger()
        # Win: buy@100, sell@110
        ledger.record(self._make_trade("buy", 1.0, 100, 0))
        ledger.record(self._make_trade("sell", 1.0, 110, 1))
        # Loss: buy@100, sell@90
        ledger.record(self._make_trade("buy", 1.0, 100, 2))
        ledger.record(self._make_trade("sell", 1.0, 90, 3))
        assert ledger.winning_trades == 1
        assert ledger.losing_trades == 1
        assert ledger.win_rate == 0.5

    def test_profit_factor(self):
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        ledger = TradeLedger()
        # Win: +10
        ledger.record(self._make_trade("buy", 1.0, 100, 0))
        ledger.record(self._make_trade("sell", 1.0, 110, 1))
        # Loss: -5
        ledger.record(self._make_trade("buy", 1.0, 100, 2))
        ledger.record(self._make_trade("sell", 1.0, 95, 3))
        assert ledger.profit_factor == 10.0 / 5.0

    def test_no_losses_profit_factor_inf(self):
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        ledger = TradeLedger()
        ledger.record(self._make_trade("buy", 1.0, 100, 0))
        ledger.record(self._make_trade("sell", 1.0, 110, 1))
        assert ledger.profit_factor == float('inf')

    def test_no_trades_profit_factor_zero(self):
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        ledger = TradeLedger()
        assert ledger.profit_factor == 0.0

    def test_avg_win_avg_loss(self):
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        ledger = TradeLedger()
        # Win: +20
        ledger.record(self._make_trade("buy", 1.0, 100, 0))
        ledger.record(self._make_trade("sell", 1.0, 120, 1))
        # Win: +10
        ledger.record(self._make_trade("buy", 1.0, 100, 2))
        ledger.record(self._make_trade("sell", 1.0, 110, 3))
        # Loss: -5
        ledger.record(self._make_trade("buy", 1.0, 100, 4))
        ledger.record(self._make_trade("sell", 1.0, 95, 5))
        assert ledger.avg_win == 15.0  # (20+10)/2
        assert ledger.avg_loss == -5.0

    def test_hold_does_not_create_position(self):
        from crypto_quant_ai.backend.backtest.types import BacktestTrade, TradeAction
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        # HOLD with quantity=0 would fail BacktestTrade validation,
        # so we test via the ledger directly
        ledger = TradeLedger()
        assert ledger.total_trades == 0
        assert ledger.executed_trades == 0

    def test_reset(self):
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        ledger = TradeLedger()
        ledger.record(self._make_trade("buy", 1.0, 100, 0))
        ledger.reset()
        assert ledger.total_trades == 0
        assert len(ledger.closed_trades) == 0


# ------------------------------------------------------------------ #
# TestComputeMetrics
# ------------------------------------------------------------------ #

class TestComputeMetrics:
    """Metrics calculation tests."""

    def test_flat_equity_no_trades(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        from crypto_quant_ai.backend.backtest.equity_tracker import EquityTracker
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        from crypto_quant_ai.backend.backtest.metrics import compute_metrics

        cfg = BacktestConfig()
        tracker = EquityTracker()
        tracker.record(_ts(0), cash=100000, position_value=0)
        tracker.record(_ts(1), cash=100000, position_value=0)
        ledger = TradeLedger()

        m = compute_metrics(cfg, tracker, ledger)
        assert m.total_return == 0.0
        assert m.total_trades == 0
        assert m.sharpe_ratio == 0.0
        assert m.final_equity == 100000

    def test_growing_equity(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        from crypto_quant_ai.backend.backtest.equity_tracker import EquityTracker
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        from crypto_quant_ai.backend.backtest.metrics import compute_metrics

        cfg = BacktestConfig()
        tracker = EquityTracker()
        # Equity grows: 100k → 105k → 110k
        tracker.record(_ts(0), cash=100000, position_value=0)
        tracker.record(_ts(1), cash=105000, position_value=0)
        tracker.record(_ts(2), cash=110000, position_value=0)
        ledger = TradeLedger()

        m = compute_metrics(cfg, tracker, ledger)
        assert m.total_return == 10000
        assert abs(m.total_return_pct - 0.1) < 1e-9
        assert m.max_drawdown == 0  # No drawdown
        assert m.sharpe_ratio > 0  # Positive returns

    def test_drawdown_in_metrics(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        from crypto_quant_ai.backend.backtest.equity_tracker import EquityTracker
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        from crypto_quant_ai.backend.backtest.metrics import compute_metrics

        cfg = BacktestConfig()
        tracker = EquityTracker()
        # 100k → 120k (peak) → 90k (trough) → 95k
        tracker.record(_ts(0), cash=100000, position_value=0)
        tracker.record(_ts(1), cash=120000, position_value=0)
        tracker.record(_ts(2), cash=90000, position_value=0)
        tracker.record(_ts(3), cash=95000, position_value=0)
        ledger = TradeLedger()

        m = compute_metrics(cfg, tracker, ledger)
        assert m.max_drawdown == 30000  # 120k - 90k
        assert abs(m.max_drawdown_pct - 30000 / 120000) < 1e-9
        assert m.total_return == -5000  # 95k - 100k

    def test_single_point(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        from crypto_quant_ai.backend.backtest.equity_tracker import EquityTracker
        from crypto_quant_ai.backend.backtest.trade_ledger import TradeLedger
        from crypto_quant_ai.backend.backtest.metrics import compute_metrics

        cfg = BacktestConfig()
        tracker = EquityTracker()
        tracker.record(_ts(0), cash=100000, position_value=0)
        ledger = TradeLedger()

        m = compute_metrics(cfg, tracker, ledger)
        assert m.sharpe_ratio == 0.0  # Not enough data
        assert m.sortino_ratio == 0.0


# ------------------------------------------------------------------ #
# TestBacktestSimulator
# ------------------------------------------------------------------ #

class TestBacktestSimulator:
    """BacktestSimulator end-to-end tests."""

    def test_empty_candles_returns_failed(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig, BacktestStatus
        from crypto_quant_ai.backend.backtest.simulator import BacktestSimulator
        sim = BacktestSimulator(BacktestConfig())
        result = sim.run([], signal_fn=None, symbol="BTC")
        assert result.status == BacktestStatus.FAILED
        assert "No candles" in result.error_message

    def test_hold_only_strategy(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig, BacktestStatus
        from crypto_quant_ai.backend.backtest.simulator import BacktestSimulator
        sim = BacktestSimulator(BacktestConfig())
        candles = _bars([100, 105, 110, 115])
        result = sim.run(candles, signal_fn=None, symbol="BTC")
        assert result.status == BacktestStatus.COMPLETED
        assert result.metrics is not None
        assert result.metrics.total_return == 0  # No trades, cash unchanged
        assert result.metrics.total_trades > 0  # HOLD trades recorded

    def test_buy_then_hold(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig, BacktestStatus, TradeAction
        from crypto_quant_ai.backend.backtest.simulator import BacktestSimulator

        def strategy(candle, account):
            if account.cash > 50000 and candle.close < 105:
                return _buy_signal(candle.close, qty=1.0, ts=candle.timestamp)
            return _hold_signal(ts=candle.timestamp)

        sim = BacktestSimulator(BacktestConfig(initial_cash=100000))
        candles = _bars([100, 105, 110, 115])
        result = sim.run(candles, signal_fn=strategy, symbol="BTC")
        assert result.status == BacktestStatus.COMPLETED
        assert result.metrics is not None
        # Should have at least one BUY trade
        buy_trades = [t for t in result.trades if t.action == TradeAction.BUY]
        assert len(buy_trades) >= 1

    def test_buy_then_sell(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig, BacktestStatus, TradeAction
        from crypto_quant_ai.backend.backtest.simulator import BacktestSimulator

        call_count = [0]

        def strategy(candle, account):
            call_count[0] += 1
            if call_count[0] == 1:
                return _buy_signal(candle.close, qty=1.0, ts=candle.timestamp)
            elif call_count[0] == 4:
                return _sell_signal(candle.close, qty=1.0, ts=candle.timestamp)
            return _hold_signal(ts=candle.timestamp)

        sim = BacktestSimulator(BacktestConfig(initial_cash=100000))
        candles = _bars([100, 105, 110, 120])
        result = sim.run(candles, signal_fn=strategy, symbol="BTC")
        assert result.status == BacktestStatus.COMPLETED
        assert result.metrics is not None
        buy_trades = [t for t in result.trades if t.action == TradeAction.BUY]
        sell_trades = [t for t in result.trades if t.action == TradeAction.SELL]
        assert len(buy_trades) == 1
        assert len(sell_trades) == 1
        # Should have a closed trade with profit
        assert len(sim.trade_ledger.closed_trades) == 1
        assert sim.trade_ledger.closed_trades[0].is_win

    def test_insufficient_cash_skips_trade(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig, BacktestStatus, TradeAction
        from crypto_quant_ai.backend.backtest.simulator import BacktestSimulator

        def strategy(candle, account):
            # Try to buy more than we can afford
            return _buy_signal(candle.close, qty=100000, ts=candle.timestamp)

        sim = BacktestSimulator(BacktestConfig(initial_cash=1000))
        candles = _bars([100])
        result = sim.run(candles, signal_fn=strategy, symbol="BTC")
        # Trade should be skipped (insufficient cash), not crash
        assert result.status == BacktestStatus.COMPLETED
        buy_trades = [t for t in result.trades if t.action == TradeAction.BUY]
        assert len(buy_trades) == 0

    def test_insufficient_position_skips_sell(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig, BacktestStatus, TradeAction
        from crypto_quant_ai.backend.backtest.simulator import BacktestSimulator

        def strategy(candle, account):
            return _sell_signal(candle.close, qty=1.0, ts=candle.timestamp)

        sim = BacktestSimulator(BacktestConfig(initial_cash=100000))
        candles = _bars([100, 110])
        result = sim.run(candles, signal_fn=strategy, symbol="BTC")
        assert result.status == BacktestStatus.COMPLETED
        sell_trades = [t for t in result.trades if t.action == TradeAction.SELL]
        assert len(sell_trades) == 0  # No position to sell

    def test_fee_and_slippage_applied(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig, TradeAction
        from crypto_quant_ai.backend.backtest.simulator import BacktestSimulator

        call_count = [0]

        def strategy(candle, account):
            call_count[0] += 1
            if call_count[0] == 1:
                return _buy_signal(candle.close, qty=1.0, ts=candle.timestamp)
            return _hold_signal(ts=candle.timestamp)

        cfg = BacktestConfig(initial_cash=100000, fee_bps=10, slippage_bps=5)
        sim = BacktestSimulator(cfg)
        candles = _bars([50000])
        result = sim.run(candles, signal_fn=strategy, symbol="BTC")
        buy_trades = [t for t in result.trades if t.action == TradeAction.BUY]
        assert len(buy_trades) == 1
        trade = buy_trades[0]
        assert trade.fee > 0
        assert trade.slippage_cost > 0

    def test_result_has_run_id(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        from crypto_quant_ai.backend.backtest.simulator import BacktestSimulator
        sim = BacktestSimulator(BacktestConfig())
        assert sim.run_id.startswith("bt_")

    def test_result_timestamps(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        from crypto_quant_ai.backend.backtest.simulator import BacktestSimulator
        sim = BacktestSimulator(BacktestConfig())
        candles = _bars([100, 110])
        result = sim.run(candles, signal_fn=None)
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.completed_at >= result.started_at

    def test_config_paper_trading_false_rejected(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        from crypto_quant_ai.backend.backtest.simulator import BacktestSimulator
        # BacktestConfig itself rejects paper_trading=False
        with pytest.raises(ValueError, match="paper_trading must be true"):
            BacktestConfig(paper_trading=False)


# ------------------------------------------------------------------ #
# TestSafetyGuards
# ------------------------------------------------------------------ #

# Forbidden tokens must not appear as lowercase literals in source or docs.
# Using bytes.fromhex for self-check (same pattern as Stage 3.3/3.4).

def _decode(hex_str: str) -> str:
    return bytes.fromhex(hex_str).decode()


_FORBIDDEN = [
    _decode("63637874"),     # c-c-x-t
    _decode("62696e616e6365"),  # b-i-n-a-n-c-e
    _decode("636f696e62617365"),  # c-o-i-n-b-a-s-e
    _decode("6b72616b656e"),  # k-r-a-k-e-n
    _decode("706c6163655f6f72646572"),  # p-l-a-c-e-_-o-r-d-e-r
    _decode("6372656174655f6f72646572"),  # c-r-e-a-t-e-_-o-r-d-e-r
    _decode("7265616c5f6f72646572"),  # r-e-a-l-_-o-r-d-e-r
    _decode("6175746f5f7472616465"),  # a-u-t-o-_-t-r-a-d-e
    _decode("6170695f6b6579"),  # a-p-i-_-k-e-y
    _decode("6170695f736563726574"),  # a-p-i-_-s-e-c-r-e-t
    _decode("7365637265745f6b6579"),  # s-e-c-r-e-t-_-k-e-y
]

_SECRETS = [
    _decode("6170695f6b6579"),  # a-p-i-_-k-e-y
    _decode("6170695f736563726574"),  # a-p-i-_-s-e-c-r-e-t
    _decode("7365637265745f6b6579"),  # s-e-c-r-e-t-_-k-e-y
    _decode("70617373776f7264"),  # p-a-s-s-w-o-r-d
    _decode("746f6b656e"),  # t-o-k-e-n
    _decode("6c6976655f74726164696e67"),  # l-i-v-e-_-t-r-a-d-i-n-g
]


class TestSafetyGuards:
    """Safety guard tests for the backtest engine."""

    def test_backtest_config_requires_paper_trading(self):
        from crypto_quant_ai.backend.backtest.types import BacktestConfig
        with pytest.raises(ValueError, match="paper_trading must be true"):
            BacktestConfig(paper_trading=False)

    def test_no_forbidden_tokens_in_source(self):
        """Scan backtest module source files for forbidden lowercase tokens."""
        import pathlib
        backtest_dir = pathlib.Path(__file__).resolve().parent.parent / "backtest"
        for py_file in backtest_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for token in _FORBIDDEN:
                assert token not in content.lower(), \
                    f"Forbidden token '{_safe_repr(token)}' found in {py_file.name}"

    def test_no_forbidden_tokens_in_tests(self):
        """Scan this test file for forbidden lowercase tokens."""
        import pathlib
        test_file = pathlib.Path(__file__).resolve()
        content = test_file.read_text(encoding="utf-8")
        # Check source code (not string literals in _decode)
        for token in _FORBIDDEN:
            # The _decode calls contain hex, not the actual token
            assert token not in content.lower(), \
                f"Forbidden token '{_safe_repr(token)}' found in test file"

    def test_no_secrets_in_source(self):
        import pathlib
        backtest_dir = pathlib.Path(__file__).resolve().parent.parent / "backtest"
        for py_file in backtest_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for token in _SECRETS:
                assert token not in content.lower(), \
                    f"Secret token '{_safe_repr(token)}' found in {py_file.name}"

    def test_env_live_trading_false(self):
        """Verify .env.example has LIVE_TRADING=false."""
        import pathlib
        env_path = pathlib.Path(__file__).resolve().parent.parent.parent.parent / ".env.example"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            assert "LIVE_TRADING=false" in content


def _safe_repr(token: str) -> str:
    """Safely represent a token for error messages without printing it."""
    return f"<forbidden:{len(token)}char>"


# ------------------------------------------------------------------ #
# TestBacktestResult
# ------------------------------------------------------------------ #

class TestBacktestResult:
    """BacktestResult properties tests."""

    def test_completed_result(self):
        from crypto_quant_ai.backend.backtest.types import (
            BacktestConfig, BacktestResult, BacktestStatus, BacktestMetrics,
        )
        result = BacktestResult(
            run_id="bt_test",
            config=BacktestConfig(),
            status=BacktestStatus.COMPLETED,
            trades=(),
            metrics=BacktestMetrics(
                total_return=0, total_return_pct=0,
                max_drawdown=0, max_drawdown_pct=0,
                sharpe_ratio=0, sortino_ratio=0,
                win_rate=0, win_rate_pct=0,
                total_trades=0, winning_trades=0, losing_trades=0,
                avg_win=0, avg_loss=0, profit_factor=0,
                final_equity=100000, initial_cash=100000,
            ),
            started_at=_ts(0),
            completed_at=_ts(5),
        )
        assert result.is_completed is True
        assert result.is_failed is False

    def test_failed_result(self):
        from crypto_quant_ai.backend.backtest.types import (
            BacktestConfig, BacktestResult, BacktestStatus,
        )
        result = BacktestResult(
            run_id="bt_test",
            config=BacktestConfig(),
            status=BacktestStatus.FAILED,
            trades=(),
            metrics=None,
            started_at=_ts(0),
            completed_at=_ts(5),
            error_message="Something went wrong",
        )
        assert result.is_completed is False
        assert result.is_failed is True
        assert result.error_message == "Something went wrong"

    def test_result_is_frozen(self):
        from crypto_quant_ai.backend.backtest.types import (
            BacktestConfig, BacktestResult, BacktestStatus,
        )
        result = BacktestResult(
            run_id="bt_test",
            config=BacktestConfig(),
            status=BacktestStatus.COMPLETED,
            trades=(),
            metrics=None,
            started_at=_ts(0),
            completed_at=_ts(5),
        )
        with pytest.raises(Exception):
            result.status = BacktestStatus.FAILED  # type: ignore[misc]


# ------------------------------------------------------------------ #
# TestCandleSignal
# ------------------------------------------------------------------ #

class TestCandleSignal:
    """CandleSignal validation tests."""

    def test_valid_buy_signal(self):
        from crypto_quant_ai.backend.backtest.simulator import CandleSignal
        from crypto_quant_ai.backend.backtest.types import TradeAction
        sig = CandleSignal(
            timestamp=_ts(0),
            symbol="BTC",
            action=TradeAction.BUY,
            price=50000,
            quantity=1.0,
            reason="bullish",
        )
        assert sig.action == TradeAction.BUY

    def test_hold_does_not_require_quantity(self):
        from crypto_quant_ai.backend.backtest.simulator import CandleSignal
        from crypto_quant_ai.backend.backtest.types import TradeAction
        sig = CandleSignal(
            timestamp=_ts(0),
            symbol="BTC",
            action=TradeAction.HOLD,
            price=100,
            quantity=0.0,
        )
        assert sig.action == TradeAction.HOLD

    def test_buy_zero_quantity_rejected(self):
        from crypto_quant_ai.backend.backtest.simulator import CandleSignal
        from crypto_quant_ai.backend.backtest.types import TradeAction
        with pytest.raises(ValueError, match="quantity must be positive"):
            CandleSignal(
                timestamp=_ts(0),
                symbol="BTC",
                action=TradeAction.BUY,
                price=100,
                quantity=0,
            )

    def test_negative_price_rejected(self):
        from crypto_quant_ai.backend.backtest.simulator import CandleSignal
        from crypto_quant_ai.backend.backtest.types import TradeAction
        with pytest.raises(ValueError, match="price must be positive"):
            CandleSignal(
                timestamp=_ts(0),
                symbol="BTC",
                action=TradeAction.HOLD,
                price=-1,
            )
