from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Callable, Sequence

from crypto_quant_ai.backend.core.models import MarketData
from crypto_quant_ai.backend.decision.brain_orchestrator import (
    MultiBrainOrchestrator,
    OrchestratorReport,
)
from crypto_quant_ai.backend.backtest.simulator import CandleSignal
from crypto_quant_ai.backend.backtest.types import TradeAction

from .types import StrategySpec, ReplayConfig


def _ts(value: Any) -> datetime:
    ts = getattr(value, "timestamp", None)
    if ts is None:
        return datetime.utcnow()
    if isinstance(ts, datetime):
        return ts
    # tolerate string timestamps
    try:
        return datetime.fromisoformat(str(ts))
    except Exception:
        return datetime.utcnow()


def build_signal_fn(
    orchestrator: MultiBrainOrchestrator,
    strategy: StrategySpec,
    replay_config: ReplayConfig,
):
    def _signal_fn(candle: Any, account: Any) -> CandleSignal | None:
        market_data = MarketData(
            symbol=replay_config.symbol,
            timestamp=_ts(candle).isoformat(),
            open=float(getattr(candle, "open", getattr(candle, "close", 0.0))),
            high=float(getattr(candle, "high", getattr(candle, "close", 0.0))),
            low=float(getattr(candle, "low", getattr(candle, "close", 0.0))),
            close=float(getattr(candle, "close", 0.0)),
            volume=float(getattr(candle, "volume", 0.0)),
            timeframe=strategy.timeframe,
        )

        report: OrchestratorReport = orchestrator.run(market_data)
        decision = getattr(report, "final_decision", None)
        if decision is None:
            return None

        action = getattr(decision, "decision", None)
        qty = getattr(decision, "position_size", None)
        if qty is None:
            qty = getattr(report, "quantity", None)
        if qty is not None and not isinstance(qty, (int, float)):
            qty = None

        close = float(getattr(candle, "close", 0.0))

        if action in ("HOLD", "NO_TRADE", "NONE", None):
            return CandleSignal(
                timestamp=_ts(candle),
                symbol=replay_config.symbol,
                action=TradeAction.HOLD,
                price=close,
                quantity=0.0,
                reason="hold",
            )

        if action in ("BUY", "LONG"):
            if qty is None:
                qty = max(
                    0.0,
                    account.cash * strategy.position_fraction / max(close, 1e-9),
                )
            if qty <= 0:
                return CandleSignal(
                    timestamp=_ts(candle),
                    symbol=replay_config.symbol,
                    action=TradeAction.HOLD,
                    price=close,
                    quantity=0.0,
                    reason="qty <= 0",
                )
            return CandleSignal(
                timestamp=_ts(candle),
                symbol=replay_config.symbol,
                action=TradeAction.BUY,
                price=close,
                quantity=float(qty),
                reason=str(action),
            )

        if action in ("SELL", "SHORT"):
            current_qty = account.positions.get(replay_config.symbol, None)
            if current_qty is None:
                current_qty = 0.0
            else:
                current_qty = getattr(current_qty, "quantity", float(current_qty))
            qty = current_qty if qty is None else float(qty)
            if qty <= 0:
                return CandleSignal(
                    timestamp=_ts(candle),
                    symbol=replay_config.symbol,
                    action=TradeAction.HOLD,
                    price=close,
                    quantity=0.0,
                    reason="no position to sell",
                )
            return CandleSignal(
                timestamp=_ts(candle),
                symbol=replay_config.symbol,
                action=TradeAction.SELL,
                price=close,
                quantity=float(qty),
                reason=str(action),
            )

        # Fallback: hold
        return CandleSignal(
            timestamp=_ts(candle),
            symbol=replay_config.symbol,
            action=TradeAction.HOLD,
            price=close,
            quantity=0.0,
            reason="unsupported action",
        )

    return _signal_fn
