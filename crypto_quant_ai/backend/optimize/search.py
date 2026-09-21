"""Stage 8 - search driver and top-level orchestrator.

Evaluates each parameter combination through the Stage 4 paper backtest
simulator (risk_gate=None is the same paper-only path used for real-chain
verification: no venue, no order is submitted, no network). Ranking reuses
Stage 6 ComparisonEngine semantics; reporting reuses Stage 6 shapes.
"""
from __future__ import annotations

import math
import random
from typing import Any, Callable, Sequence

from crypto_quant_ai.backend.backtest.simulator import BacktestSimulator, CandleSignal
from crypto_quant_ai.backend.backtest.types import TradeAction
from crypto_quant_ai.backend.paper.audit import AuditLog
from crypto_quant_ai.backend.replay.types import ReplayConfig

from .types import (
    ParamSpace,
    SearchConfig,
    WalkForwardConfig,
    CandidateResult,
    OptimizationResult,
)
from .report import build_result


_METRIC_FIELDS = (
    "total_return",
    "total_return_pct",
    "max_drawdown_pct",
    "sharpe_ratio",
    "sortino_ratio",
    "win_rate_pct",
    "profit_factor",
    "final_equity",
    "total_trades",
)


def _metrics_dict(metrics: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    for f in _METRIC_FIELDS:
        v = getattr(metrics, f, 0.0)
        try:
            fv = float(v)
        except (TypeError, ValueError):
            fv = 0.0
        out[f] = fv if math.isfinite(fv) else 0.0
    return out


def _signal_factory(params: dict[str, float]) -> Callable:
    """Deterministic, parameterised moving-average crossover signal."""
    state: dict[str, list[float]] = {"closes": []}

    def _signal(candle: Any, account: Any) -> CandleSignal | None:
        close = float(getattr(candle, "close", 0.0))
        ts = getattr(candle, "timestamp", None)
        symbol = str(getattr(candle, "symbol", "BTC"))
        state["closes"].append(close)
        closes = state["closes"]
        sw = max(1, int(round(params.get("short_window", 5))))
        lw = max(1, int(round(params.get("long_window", 20))))
        frac = float(params.get("position_fraction", 0.1))
        thr = float(params.get("threshold", 0.0))
        if lw <= 0 or len(closes) < lw:
            return None
        short_ma = sum(closes[-sw:]) / max(len(closes[-sw:]), 1)
        long_ma = sum(closes[-lw:]) / lw
        price = close
        if short_ma > long_ma * (1.0 + thr):
            qty = (getattr(account, "cash", 0.0) * frac) / max(price, 1e-9)
            if qty <= 0:
                return None
            return CandleSignal(
                timestamp=ts, symbol=symbol, action=TradeAction.BUY,
                price=price, quantity=qty, reason="ma_cross_up",
            )
        if short_ma < long_ma * (1.0 - thr):
            pos = getattr(account, "positions", {}) or {}
            qty = 0.0
            for _sym, p in pos.items():
                qty = float(getattr(p, "quantity", 0.0))
                break
            if qty <= 0:
                return None
            return CandleSignal(
                timestamp=ts, symbol=symbol, action=TradeAction.SELL,
                price=price, quantity=qty, reason="ma_cross_down",
            )
        return CandleSignal(
            timestamp=ts, symbol=symbol, action=TradeAction.HOLD,
            price=price, quantity=0.0, reason="hold",
        )

    return _signal


def _evaluate(params: dict[str, float], candles: Sequence[Any],
              config: ReplayConfig) -> CandidateResult:
    bcfg = config.to_backtest_config()
    sim = BacktestSimulator(bcfg, risk_gate=None, audit_log=AuditLog())
    signal = _signal_factory(params)
    try:
        result = sim.run(candles, signal_fn=signal, symbol=config.symbol)
    except Exception as exc:  # noqa: BLE001 - record, never fake success
        return CandidateResult(params=params, metrics={}, is_completed=False, error=str(exc))
    if not result.is_completed or result.metrics is None:
        return CandidateResult(
            params=params, metrics={}, is_completed=False,
            error=result.error_message or "incomplete",
        )
    return CandidateResult(params=params, metrics=_metrics_dict(result.metrics), is_completed=True)


def enumerate_points(space: ParamSpace, config: SearchConfig) -> list[dict[str, float]]:
    if config.method == "random":
        rng = random.Random(config.random_seed)
        return space.sample(config.random_samples, rng)
    return space.grid_points(config.max_points)


def rank_candidates(candidates: list[CandidateResult], metric: str) -> list[CandidateResult]:
    completed = [c for c in candidates if c.is_completed]
    return sorted(
        completed,
        key=lambda c: float(c.metrics.get(metric, float("-inf"))),
        reverse=True,
    )


def optimize(space: ParamSpace, candles: Sequence[Any], config: SearchConfig,
             replay_config: ReplayConfig) -> tuple[list[CandidateResult], CandidateResult | None]:
    points = enumerate_points(space, config)
    candidates = [_evaluate(p, candles, replay_config) for p in points]
    ranked = rank_candidates(candidates, config.metric)
    best = ranked[0] if ranked else None
    return candidates, best


def run_optimization(space: ParamSpace, candles: Sequence[Any], search: SearchConfig,
                     wf: WalkForwardConfig, replay_config: ReplayConfig) -> OptimizationResult:
    from .walkforward import walk_forward
    from .metrics import compute_robustness

    candidates, best = optimize(space, candles, search, replay_config)
    windows = walk_forward(space, candles, search, wf, replay_config)
    robustness = compute_robustness(windows, search.metric) if windows else None
    return build_result(space, search, wf, candidates, best, windows, robustness, search.metric)
