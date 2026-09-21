"""Stage 9 - Layer 4: System Orchestrator (Intelligence Orchestration Layer).

Ties Layers 1-3 into one local, paper-only, explainable research loop:

    market state -> decision board -> research (optimize/walk-forward)
    -> recommendation + risk notes + explainable text

No network, no external venue, no order submission. LIVE_TRADING must be false.
"""
from __future__ import annotations

import os
from typing import Any, Sequence

from crypto_quant_ai.backend.data.ohlcv import OHLCVBar
from crypto_quant_ai.backend.core.models import MarketData
from crypto_quant_ai.backend.optimize.types import (
    ParamSpace,
    ParamSpec,
    SearchConfig,
    WalkForwardConfig,
)
from crypto_quant_ai.backend.replay.types import ReplayConfig

from .market_state import consensus_regime, MarketState
from .decision_board import build_decision_brief, DecisionBrief
from .research import run_research, ResearchReport
from .report import build_intelligence_report, IntelligenceReport


def _live_guard() -> None:
    if os.environ.get("LIVE_TRADING", "false").lower() == "true":
        raise RuntimeError("Stage 9 intelligence requires LIVE_TRADING=false (paper only).")


def _to_market_data(candle: OHLCVBar, symbol: str, timeframe: str) -> MarketData:
    ts = candle.timestamp
    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    return MarketData(
        symbol=symbol,
        timestamp=ts_str,
        open=float(candle.open),
        high=float(candle.high),
        low=float(candle.low),
        close=float(candle.close),
        volume=float(candle.volume),
        timeframe=timeframe,
    )


def _default_space() -> ParamSpace:
    return ParamSpace((
        ParamSpec("short_window", 3, 20, 1, integer=True),
        ParamSpec("long_window", 10, 60, 5, integer=True),
        ParamSpec("position_fraction", 0.05, 0.3, 0.05),
        ParamSpec("threshold", 0.0, 0.05, 0.01),
    ))


class IntelligenceOrchestrator:
    def __init__(
        self,
        brains: Sequence[Any] | None = None,
        default_timeframe: str = "15m",
    ) -> None:
        _live_guard()
        self._brains = list(brains) if brains is not None else None
        self._default_timeframe = default_timeframe

    def analyze(
        self,
        candles: Sequence[OHLCVBar],
        *,
        symbol: str = "BTC",
        timeframes: Sequence[int] | None = None,
        space: ParamSpace | None = None,
        search: SearchConfig | None = None,
        wf: WalkForwardConfig | None = None,
        replay_config: ReplayConfig | None = None,
    ) -> IntelligenceReport:
        _live_guard()
        if not candles:
            raise ValueError("IntelligenceOrchestrator.analyze requires non-empty candles")
        if space is None:
            space = _default_space()
        if search is None:
            search = SearchConfig(method="grid", metric="sharpe_ratio", max_points=2000)
        if wf is None:
            wf = WalkForwardConfig(train_size=60, test_size=30, step=30)
        if replay_config is None:
            replay_config = ReplayConfig(symbol=symbol, paper_trading=True)

        market_state: MarketState = consensus_regime(candles, timeframes)
        md = _to_market_data(candles[-1], symbol, self._default_timeframe)
        decision: DecisionBrief = build_decision_brief(md, self._brains)
        research: ResearchReport = run_research(space, candles, search, wf, replay_config)

        risk_notes = list(research.overfit_flags)
        if market_state.regime.value == "high_vol":
            risk_notes.append("high volatility regime: widen risk controls")
        if decision.confidence < 0.3:
            risk_notes.append("low decision confidence: prefer smaller exposure")

        recommendation = self._recommend(market_state, decision, research)
        return build_intelligence_report(
            symbol=symbol,
            market_state=market_state,
            decision=decision,
            research=research,
            recommendation=recommendation,
            risk_notes=risk_notes,
        )

    @staticmethod
    def _recommend(market: MarketState, decision: DecisionBrief, research: ResearchReport) -> str:
        best = research.best_params
        metric = research.objective
        if decision.action.upper() in ("BUY", "SELL") and not research.overfit_flags:
            return (
                f"Proceed with research-backed plan. "
                f"Market {market.regime.value}; brains={decision.action}. "
                f"Use params {best} (objective {metric}). Monitor risk notes."
            )
        if research.overfit_flags:
            return (
                f"Do NOT deploy yet: overfitting detected ({len(research.overfit_flags)} flags). "
                f"Market {market.regime.value}. Refine parameter space before trusting results."
            )
        return (
            f"Hold / observe. Market {market.regime.value} (conf {market.confidence:.2f}); "
            f"brain consensus is {decision.action}. Research suggests params {best} "
            f"but no active trade signal. Re-evaluate on regime change."
        )
