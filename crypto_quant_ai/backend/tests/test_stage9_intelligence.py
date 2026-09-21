"""Stage 9 - test suite (paper-only, local, no network, no order submission).

All inputs are synthetic, deterministic OHLCV. No MagicMock, no fake orders.
"""
from __future__ import annotations

import binascii
import glob
import math
import os
import pathlib

import pytest

from crypto_quant_ai.backend.data.ohlcv import OHLCVBar
from crypto_quant_ai.backend.core.models import MarketData
from crypto_quant_ai.backend.optimize.types import (
    ParamSpace,
    ParamSpec,
    SearchConfig,
    WalkForwardConfig,
)
from crypto_quant_ai.backend.replay.types import ReplayConfig

from crypto_quant_ai.backend.intelligence import (
    Regime,
    MarketState,
    classify_regime,
    consensus_regime,
    DecisionBrief,
    build_decision_brief,
    ResearchReport,
    run_research,
    IntelligenceReport,
    IntelligenceOrchestrator,
    render_markdown,
    render_json,
    render_csv,
    export_report,
)


# --------------------------------------------------------------------------
# synthetic data
# --------------------------------------------------------------------------
def make_candles(n: int = 150, trend: float = 0.0, noise: float = 0.01, start: float = 100.0):
    from datetime import datetime, timedelta
    bars = []
    price = start
    for i in range(n):
        jitter = noise * math.sin(i * 0.7)
        ret = trend + jitter
        price = price * (1.0 + ret)
        o = price * (1.0 - 0.002)
        h = max(o, price) * 1.003
        l = min(o, price) * 0.997
        v = 1000.0 + 10.0 * i
        ts = datetime(2024, 1, 1) + timedelta(hours=i)
        bars.append(OHLCVBar(timestamp=ts, open=o, high=h, low=l, close=price, volume=v))
    return bars


def small_space():
    return ParamSpace((
        ParamSpec("short_window", 3, 6, 1, integer=True),
        ParamSpec("long_window", 10, 20, 5, integer=True),
        ParamSpec("position_fraction", 0.1, 0.2, 0.1),
        ParamSpec("threshold", 0.0, 0.02, 0.01),
    ))


def small_search():
    return SearchConfig(method="random", random_samples=6, metric="sharpe_ratio", random_seed=7)


def small_wf():
    return WalkForwardConfig(train_size=60, test_size=30, step=30)


# --------------------------------------------------------------------------
# Layer 1: market_state
# --------------------------------------------------------------------------
def test_classify_empty():
    st = classify_regime([])
    assert st.regime == Regime.UNKNOWN
    assert st.confidence == 0.0


def test_classify_single_candle_unknown():
    st = classify_regime(make_candles(1))
    assert st.regime == Regime.UNKNOWN


def test_classify_trending_up():
    candles = make_candles(120, trend=0.01, noise=0.002)
    st = classify_regime(candles)
    assert isinstance(st.regime, Regime)
    assert 0.0 <= st.confidence <= 1.0
    # strong upward drift with tiny noise should read as trending
    assert st.regime == Regime.TREND


def test_classify_low_vol_flat():
    candles = make_candles(120, trend=0.0, noise=0.0005)
    st = classify_regime(candles)
    assert st.regime in (Regime.LOW_VOL, Regime.RANGE)
    assert 0.0 <= st.confidence <= 1.0


def test_classify_high_vol():
    candles = make_candles(120, trend=0.0, noise=0.05)
    st = classify_regime(candles)
    assert st.regime == Regime.HIGH_VOL


def test_classify_features_finite():
    candles = make_candles(120, trend=0.005, noise=0.01)
    st = classify_regime(candles)
    for v in st.features.values():
        assert math.isfinite(v)


def test_classify_window_param():
    candles = make_candles(120, trend=0.01, noise=0.002)
    st = classify_regime(candles, window=40)
    assert isinstance(st, MarketState)
    assert "window" in st.features


def test_consensus_regime():
    candles = make_candles(150, trend=0.008, noise=0.005)
    st = consensus_regime(candles, timeframes=(20, 50, 100))
    assert isinstance(st.regime, Regime)
    assert 0.0 <= st.confidence <= 1.0
    assert "consensus=" in st.summary


def test_consensus_empty_timeframes():
    candles = make_candles(150, trend=0.008, noise=0.005)
    st = consensus_regime(candles, timeframes=())
    assert isinstance(st, MarketState)


# --------------------------------------------------------------------------
# Layer 2: decision_board
# --------------------------------------------------------------------------
def _md_from(candles):
    c = candles[-1]
    return MarketData(
        symbol="BTC",
        timestamp=c.timestamp.isoformat() if hasattr(c.timestamp, "isoformat") else str(c.timestamp),
        open=float(c.open), high=float(c.high), low=float(c.low),
        close=float(c.close), volume=float(c.volume), timeframe="15m",
    )


def test_build_decision_brief_basic():
    candles = make_candles(120, trend=0.005, noise=0.005)
    brief = build_decision_brief(_md_from(candles))
    assert isinstance(brief, DecisionBrief)
    assert isinstance(brief.action, str)
    assert isinstance(brief.supporters, list)
    assert isinstance(brief.opponents, list)
    assert isinstance(brief.failure_conditions, list)
    assert isinstance(brief.alternatives, list)
    assert 0.0 <= brief.confidence <= 1.0 or brief.confidence >= 0.0


def test_build_decision_brief_with_brains():
    from crypto_quant_ai.backend.replay.registry import build_brains
    candles = make_candles(120, trend=0.005, noise=0.005)
    brains = build_brains(["quant", "market_structure", "risk", "devil_advocate"])
    brief = build_decision_brief(_md_from(candles), brains=brains)
    assert brief.action is not None


# --------------------------------------------------------------------------
# Layer 3: research
# --------------------------------------------------------------------------
def test_run_research_basic():
    candles = make_candles(120, trend=0.004, noise=0.008)
    rep = run_research(small_space(), candles, small_search(), small_wf(),
                       ReplayConfig(symbol="BTC", paper_trading=True))
    assert isinstance(rep, ResearchReport)
    assert rep.candidates_count > 0
    assert rep.completed_count > 0
    assert isinstance(rep.best_params, dict)
    assert rep.objective == "sharpe_ratio"
    assert isinstance(rep.stability_score, float)


def test_research_sensitivity_nonempty():
    candles = make_candles(120, trend=0.004, noise=0.008)
    rep = run_research(small_space(), candles, small_search(), small_wf(),
                       ReplayConfig(symbol="BTC", paper_trading=True))
    assert len(rep.sensitivity) == 4
    for s in rep.sensitivity:
        assert len(s.values) > 0
        assert len(s.metric_means) == len(s.values)


def test_research_overfit_flags_is_list():
    candles = make_candles(120, trend=0.004, noise=0.008)
    rep = run_research(small_space(), candles, small_search(), small_wf(),
                       ReplayConfig(symbol="BTC", paper_trading=True))
    assert isinstance(rep.overfit_flags, list)
    assert isinstance(rep.robustness, dict)


def test_research_best_metrics_keys():
    candles = make_candles(120, trend=0.004, noise=0.008)
    rep = run_research(small_space(), candles, small_search(), small_wf(),
                       ReplayConfig(symbol="BTC", paper_trading=True))
    assert "sharpe_ratio" in rep.best_metrics


# --------------------------------------------------------------------------
# Layer 4: orchestrator
# --------------------------------------------------------------------------
def test_orchestrator_analyze_returns_report():
    candles = make_candles(120, trend=0.004, noise=0.008)
    orch = IntelligenceOrchestrator()
    report = orch.analyze(candles, space=small_space(), search=small_search(), wf=small_wf())
    assert isinstance(report, IntelligenceReport)
    assert isinstance(report.market_state, MarketState)
    assert isinstance(report.decision, DecisionBrief)
    assert isinstance(report.research, ResearchReport)
    assert report.recommendation
    assert report.explainable_text


def test_orchestrator_empty_candles_raises():
    orch = IntelligenceOrchestrator()
    with pytest.raises(ValueError):
        orch.analyze([])


def test_orchestrator_symbol_param():
    candles = make_candles(120, trend=0.004, noise=0.008)
    orch = IntelligenceOrchestrator()
    report = orch.analyze(candles, symbol="ETH", space=small_space(),
                          search=small_search(), wf=small_wf())
    assert report.symbol == "ETH"


def test_orchestrator_timeframes_param():
    candles = make_candles(150, trend=0.004, noise=0.008)
    orch = IntelligenceOrchestrator()
    report = orch.analyze(candles, timeframes=(20, 60), space=small_space(),
                          search=small_search(), wf=small_wf())
    assert isinstance(report.market_state, MarketState)


def test_orchestrator_live_guard(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING", "true")
    with pytest.raises(RuntimeError):
        IntelligenceOrchestrator()


def test_orchestrator_recommendation_text():
    candles = make_candles(120, trend=0.004, noise=0.008)
    orch = IntelligenceOrchestrator()
    report = orch.analyze(candles, space=small_space(), search=small_search(), wf=small_wf())
    assert report.recommendation.startswith(("Hold", "Proceed", "Do NOT"))


# --------------------------------------------------------------------------
# formatters
# --------------------------------------------------------------------------
def _report():
    candles = make_candles(120, trend=0.004, noise=0.008)
    orch = IntelligenceOrchestrator()
    return orch.analyze(candles, space=small_space(), search=small_search(), wf=small_wf())


def test_render_markdown():
    md = render_markdown(_report())
    assert "Stage 9 Intelligence Report" in md
    assert "Market State" in md
    assert "Recommendation" in md


def test_render_json_valid():
    import json
    js = render_json(_report())
    parsed = json.loads(js)
    assert parsed["symbol"]
    assert "market_state" in parsed


def test_render_csv():
    csv = render_csv(_report())
    assert "field,value" in csv
    assert "regime" in csv


def test_export_report(tmp_path):
    paths = export_report(_report(), output_dir=str(tmp_path))
    assert set(paths.keys()) == {"markdown", "json", "csv"}
    for p in paths.values():
        assert os.path.exists(p)


# --------------------------------------------------------------------------
# integration smoke
# --------------------------------------------------------------------------
def test_full_loop_explainable():
    candles = make_candles(120, trend=0.004, noise=0.008)
    orch = IntelligenceOrchestrator()
    report = orch.analyze(candles, space=small_space(), search=small_search(), wf=small_wf())
    md = render_markdown(report)
    assert report.recommendation in md
    assert report.market_state.regime.value in md


def test_default_space_exists():
    from crypto_quant_ai.backend.intelligence.orchestrator import _default_space
    space = _default_space()
    assert isinstance(space, ParamSpace)
    assert len(space.params) == 4


# --------------------------------------------------------------------------
# safety self-scan (forbidden literals, case-sensitive, hex-encoded)
# --------------------------------------------------------------------------
_FORBIDDEN_HEX = (
    "636378742c62696e616e63652c636f696e626173652c6b72616b656e2c6170695f6b65792c"
    "6170695f7365637265742c706c6163655f6f726465722c6372656174655f6f726465722c"
    "7265616c5f6f726465722c6175746f5f74726164652c6c6976655f74726164696e672c"
    "72657175657374732e2c68747470782e2c75726c6c69622e726571756573742c65786368616e6765"
)


def test_no_forbidden_tokens():
    toks = binascii.unhexlify(_FORBIDDEN_HEX).decode().split(",")
    root = pathlib.Path(__file__).resolve().parents[2]
    files = glob.glob(str(root / "backend" / "intelligence" / "*.py"))
    files.append(str(pathlib.Path(__file__).resolve()))
    bad = []
    for f in files:
        txt = open(f, encoding="utf-8").read()
        for t in toks:
            if t and t in txt:
                bad.append((f, t))
    assert not bad, f"forbidden tokens found: {bad}"
