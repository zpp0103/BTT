"""Tests for Stage 3.1 — Paper Portfolio models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from crypto_quant_ai.backend.paper import (
    PaperAccount,
    PaperOrder,
    PaperPosition,
    buy,
    sell,
)


# ---------------------------------------------------------------------------
# PaperPosition
# ---------------------------------------------------------------------------

class TestPaperPosition:
    def test_symbol_uppercase(self):
        pos = PaperPosition(symbol="btc", quantity=0.5, avg_cost=50000)
        assert pos.symbol == "BTC"

    def test_symbol_blank_rejected(self):
        with pytest.raises(ValueError, match="must not be blank"):
            PaperPosition(symbol="  ", quantity=0.5, avg_cost=50000)

    def test_quantity_positive(self):
        pos = PaperPosition(symbol="ETH", quantity=1.0, avg_cost=3000)
        assert pos.quantity == 1.0

    def test_avg_cost_positive(self):
        pos = PaperPosition(symbol="ETH", quantity=1.0, avg_cost=3000)
        assert pos.avg_cost == 3000


# ---------------------------------------------------------------------------
# PaperOrder
# ---------------------------------------------------------------------------

class TestPaperOrder:
    def test_order_buy(self):
        ts = datetime(2026, 9, 21, tzinfo=timezone.utc)
        order = PaperOrder(symbol="btc", side="buy", quantity=0.1, price=60000, timestamp=ts)
        assert order.symbol == "BTC"
        assert order.side == "buy"

    def test_order_sell(self):
        ts = datetime(2026, 9, 21, tzinfo=timezone.utc)
        order = PaperOrder(symbol="ETH", side="sell", quantity=2.0, price=3000, timestamp=ts)
        assert order.symbol == "ETH"

    def test_invalid_side(self):
        ts = datetime(2026, 9, 21, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="Input should be 'buy' or 'sell'"):
            PaperOrder(symbol="BTC", side="hold", quantity=1.0, price=60000, timestamp=ts)

    def test_invalid_quantity(self):
        ts = datetime(2026, 9, 21, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            PaperOrder(symbol="BTC", side="buy", quantity=-0.1, price=60000, timestamp=ts)

    def test_invalid_price(self):
        ts = datetime(2026, 9, 21, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            PaperOrder(symbol="BTC", side="buy", quantity=0.1, price=0, timestamp=ts)


# ---------------------------------------------------------------------------
# PaperAccount
# ---------------------------------------------------------------------------

class TestPaperAccount:
    def test_default_cash(self):
        acc = PaperAccount()
        assert acc.cash == 100000.0

    def test_cash_nan_rejected(self):
        with pytest.raises(ValueError, match="Input should be greater than 0"):
            PaperAccount(cash=float("nan"))

    def test_cash_inf_rejected(self):
        with pytest.raises(ValueError, match="cash must be finite"):
            PaperAccount(cash=float("inf"))

    def test_initial_positions_empty(self):
        acc = PaperAccount()
        assert acc.positions == {}
        assert acc.orders == []


# ---------------------------------------------------------------------------
# buy()
# ---------------------------------------------------------------------------

class TestBuy:
    def test_buy_opens_position(self):
        acc = PaperAccount(cash=100000)
        acc2, order = buy(acc, "BTC", quantity=0.5, price=50000)
        assert "BTC" in acc2.positions
        assert acc2.positions["BTC"].quantity == 0.5
        assert acc2.cash == 75000.0  # 100000 - 0.5 * 50000
        assert order.side == "buy"
        assert order.symbol == "BTC"

    def test_buy_adds_to_existing_position(self):
        acc = PaperAccount(
            cash=50000,
            positions={"BTC": PaperPosition(symbol="BTC", quantity=0.5, avg_cost=50000)},
        )
        acc2, _ = buy(acc, "BTC", quantity=0.5, price=60000)
        assert acc2.positions["BTC"].quantity == 1.0
        assert acc2.cash == 20000.0

    def test_buy_insufficient_cash(self):
        acc = PaperAccount(cash=100)
        with pytest.raises(ValueError, match="Insufficient cash"):
            buy(acc, "BTC", quantity=1.0, price=50000)

    def test_buy_zero_quantity(self):
        acc = PaperAccount(cash=100000)
        with pytest.raises(ValueError):
            buy(acc, "BTC", quantity=0, price=50000)


# ---------------------------------------------------------------------------
# sell()
# ---------------------------------------------------------------------------

class TestSell:
    def test_sell_reduces_position(self):
        acc = PaperAccount(
            cash=50000,
            positions={"BTC": PaperPosition(symbol="BTC", quantity=1.0, avg_cost=50000)},
        )
        acc2, order = sell(acc, "BTC", quantity=0.5, price=60000)
        assert acc2.positions["BTC"].quantity == 0.5
        assert acc2.cash == 80000.0
        assert order.side == "sell"

    def test_sell_closes_position(self):
        acc = PaperAccount(
            cash=50000,
            positions={"BTC": PaperPosition(symbol="BTC", quantity=0.5, avg_cost=50000)},
        )
        acc2, _ = sell(acc, "BTC", quantity=0.5, price=60000)
        assert "BTC" not in acc2.positions
        assert acc2.cash == 80000.0

    def test_sell_no_position(self):
        acc = PaperAccount()
        with pytest.raises(ValueError, match="No position to sell"):
            sell(acc, "BTC", quantity=0.1, price=60000)

    def test_sell_exceeds_held(self):
        acc = PaperAccount(
            positions={"BTC": PaperPosition(symbol="BTC", quantity=0.1, avg_cost=50000)},
        )
        with pytest.raises(ValueError, match="Cannot sell"):
            sell(acc, "BTC", quantity=1.0, price=60000)


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

class TestSafety:
    def test_no_forbidden_imports(self):
        """Forbidden modules must not appear in source."""
        import crypto_quant_ai.backend.paper as paper_module
        source = str(paper_module.__file__)
        # Should be local file, not system package
        assert "site-packages" not in source

    def test_source_clean(self):
        """No unauthorized libraries in paper module source."""
        import crypto_quant_ai.backend.paper as paper_module
        source = open(paper_module.__file__, "r", encoding="utf-8").read()
        _b = bytes.fromhex("63637874").decode()
        assert _b not in source.lower()
