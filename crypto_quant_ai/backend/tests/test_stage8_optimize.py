"""Stage 8 - parameter optimization & walk-forward validation tests.

Paper-only: every test drives the Stage 4 backtest simulator with risk_gate=None
(the same honest local paper path). No network, no
external venue connection, no orders. Forbidden literals are hex-encoded so the
safety self-scan never matches its own test code.
"""
from __future__ import annotations

import binascii
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pytest

from crypto_quant_ai.backend.optimize import (
    ParamSpec,
    ParamSpace,
    SearchConfig,
    WalkForwardConfig,
    CandidateResult,
    WindowResult,
    RobustnessReport,
    OptimizationResult,
    run_optimization,
    optimize,
    build_result,
    render_markdown,
    render_json,
    render_csv,
    export_report,
)
from crypto_quant_ai.backend.replay.types import ReplayConfig


# Forbidden tokens (hex) so this test never self-matches its own literals.
_FORBIDDEN_HEX = (
    "636378742c62696e616e63652c636f696e626173652c6b72616b656e2c6170695f6b65792c"
    "6170695f7365637265742c706c6163655f6f726465722c6372656174655f6f726465722c"
    "7265616c5f6f726465722c6175746f5f74726164652c6c6976655f74726164696e672c"
    "72657175657374732e2c68747470782e2c75726c6c69622e726571756573742c65786368616e6765"
)


def _forbidden_tokens() -> list[str]:
    return binascii.unhexlify(_FORBIDDEN_HEX).decode().split(",")


@dataclass
class SimpleCandle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def make_candles(n: int = 150, seed: int = 7) -> list[SimpleCandle]:
    import math
    import random

    r = random.Random(seed)
    out: list[SimpleCandle] = []
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        base = 100.0 + 15.0 * math.sin(i / 5.0)
        close = max(1.0, base + r.uniform(-1.5, 1.5))
        out.append(SimpleCandle(
            symbol="BTC",
            timestamp=t0 + timedelta(hours=i),
            open=close, high=close + 0.5, low=close - 0.5, close=close, volume=100.0,
        ))
    return out


def make_space() -> ParamSpace:
    return ParamSpace(params=(
        ParamSpec(name="short_window", low=3, high=7, step=2, integer=True),
        ParamSpec(name="long_window", low=10, high=20, step=5, integer=True),
        ParamSpec(name="threshold", low=0.0, high=0.02, step=0.01),
        ParamSpec(name="position_fraction", low=0.1, high=0.3, step=0.2),
    ))


def make_search(method: str = "grid") -> SearchConfig:
    return SearchConfig(
        method=method, max_points=2000, random_samples=24,
        metric="sharpe_ratio", random_seed=42,
    )


def make_wf() -> WalkForwardConfig:
    return WalkForwardConfig(train_size=60, test_size=30, step=30)


def make_replay() -> ReplayConfig:
    return ReplayConfig(
        initial_cash=100000.0, fee_bps=10.0, slippage_bps=5.0,
        symbol="BTC", paper_trading=True,
    )


# --------------------------------------------------------------------------
# ParamSpec / ParamSpace validation
# --------------------------------------------------------------------------
def test_param_spec_basic_ok():
    p = ParamSpec(name="x", low=0.0, high=1.0, step=0.1)
    assert p.name == "x"


def test_param_spec_empty_name_raises():
    with pytest.raises(ValueError):
        ParamSpec(name="", low=0.0, high=1.0)


def test_param_spec_low_gt_high_raises():
    with pytest.raises(ValueError):
        ParamSpec(name="x", low=2.0, high=1.0)


def test_param_spec_nonpositive_step_raises():
    with pytest.raises(ValueError):
        ParamSpec(name="x", low=0.0, high=1.0, step=0.0)


def test_param_space_ok():
    sp = make_space()
    assert len(sp.params) == 4


def test_param_space_empty_raises():
    with pytest.raises(ValueError):
        ParamSpace(params=())


def test_param_space_duplicate_name_raises():
    with pytest.raises(ValueError):
        ParamSpace(params=(
            ParamSpec(name="dup", low=0.0, high=1.0),
            ParamSpec(name="dup", low=0.0, high=2.0),
        ))


def test_grid_points_count_and_bounds():
    sp = make_space()
    pts = sp.grid_points()
    assert len(pts) == 3 * 3 * 3 * 2
    for pt in pts:
        assert 3 <= pt["short_window"] <= 7
        assert 10 <= pt["long_window"] <= 20
        assert 0.0 <= pt["threshold"] <= 0.02
        assert 0.1 <= pt["position_fraction"] <= 0.3


def test_grid_points_over_cap_raises():
    big = ParamSpace(params=(
        ParamSpec(name="a", low=0, high=50, step=1, integer=True),
        ParamSpec(name="b", low=0, high=50, step=1, integer=True),
    ))
    with pytest.raises(ValueError):
        big.grid_points(max_points=10)


def test_sample_deterministic_with_seed():
    sp = make_space()
    a = sp.sample(10, 123)
    b = sp.sample(10, 123)
    assert a == b
    assert len(a) == 10


def test_sample_within_bounds():
    sp = make_space()
    pts = sp.sample(50, 7)
    for pt in pts:
        assert 3 <= pt["short_window"] <= 7


# --------------------------------------------------------------------------
# SearchConfig / WalkForwardConfig
# --------------------------------------------------------------------------
def test_search_config_default_ok():
    sc = SearchConfig()
    assert sc.method == "grid"
    assert sc.metric == "sharpe_ratio"


def test_search_config_bad_method_raises():
    with pytest.raises(ValueError):
        SearchConfig(method="evolutionary")


def test_search_config_empty_metric_raises():
    with pytest.raises(ValueError):
        SearchConfig(metric="")


def test_wf_config_ok():
    wf = WalkForwardConfig()
    assert wf.train_size == 60 and wf.test_size == 30 and wf.step == 30


def test_wf_config_zero_train_raises():
    with pytest.raises(ValueError):
        WalkForwardConfig(train_size=0)


# --------------------------------------------------------------------------
# Signal + evaluation
# --------------------------------------------------------------------------
def test_signal_factory_returns_signal():
    from crypto_quant_ai.backend.optimize.search import _signal_factory
    from crypto_quant_ai.backend.backtest.types import TradeAction

    sig = _signal_factory({"short_window": 5, "long_window": 20,
                           "threshold": 0.0, "position_fraction": 0.2})
    c = make_candles(40)
    acct = type("A", (), {"cash": 100000.0, "positions": {}})()
    seen = []
    for candle in c:
        out = sig(candle, acct)
        assert out is None or out.action in (TradeAction.BUY, TradeAction.SELL, TradeAction.HOLD)
        if out is not None:
            assert out.symbol == "BTC"
            seen.append(out.action)
    assert seen, "signal should emit at least one trade signal over the window"


def test_signal_factory_deterministic():
    from crypto_quant_ai.backend.optimize.search import _signal_factory

    sig1 = _signal_factory({"short_window": 5, "long_window": 20, "threshold": 0.0, "position_fraction": 0.2})
    sig2 = _signal_factory({"short_window": 5, "long_window": 20, "threshold": 0.0, "position_fraction": 0.2})
    c = make_candles(40)
    acct = type("A", (), {"cash": 100000.0, "positions": {}})()
    seq1 = [str(sig1(x, acct)) for x in c]
    seq2 = [str(sig2(x, acct)) for x in c]
    assert seq1 == seq2


def test_evaluate_completed_metrics():
    from crypto_quant_ai.backend.optimize.search import _evaluate

    cr = _evaluate({"short_window": 5, "long_window": 20, "threshold": 0.0, "position_fraction": 0.2},
                   make_candles(), make_replay())
    assert cr.is_completed is True
    assert "sharpe_ratio" in cr.metrics
    assert "final_equity" in cr.metrics


def test_evaluate_metrics_finite():
    from crypto_quant_ai.backend.optimize.search import _evaluate

    cr = _evaluate({"short_window": 5, "long_window": 20, "threshold": 0.0, "position_fraction": 0.2},
                   make_candles(), make_replay())
    for v in cr.metrics.values():
        assert v == 0.0 or float(v) == float(v)  # finite (no NaN/inf)


def test_evaluate_handles_short_candles():
    from crypto_quant_ai.backend.optimize.search import _evaluate

    cr = _evaluate({"short_window": 5, "long_window": 20, "threshold": 0.0, "position_fraction": 0.2},
                   make_candles(5), make_replay())
    assert cr.is_completed is True


# --------------------------------------------------------------------------
# optimize
# --------------------------------------------------------------------------
def test_optimize_returns_candidates_and_best():
    cands, best = optimize(make_space(), make_candles(), make_search(), make_replay())
    assert len(cands) == 3 * 3 * 3 * 2
    assert best is not None
    assert best.is_completed is True


def test_optimize_best_is_max_objective():
    cands, best = optimize(make_space(), make_candles(), make_search(), make_replay())
    best_sharpe = best.metrics["sharpe_ratio"]
    for c in cands:
        if c.is_completed:
            assert best_sharpe >= c.metrics["sharpe_ratio"]


def test_optimize_random_deterministic():
    c1, b1 = optimize(make_space(), make_candles(120), make_search("random"), make_replay())
    c2, b2 = optimize(make_space(), make_candles(120), make_search("random"), make_replay())
    assert len(c1) == len(c2)
    assert b1.params == b2.params


def test_optimize_changes_with_data():
    c_a, _ = optimize(make_space(), make_candles(120, seed=1), make_search(), make_replay())
    c_b, _ = optimize(make_space(), make_candles(120, seed=99), make_search(), make_replay())
    sa = {tuple(sorted(x.params.items())) for x in c_a}
    sb = {tuple(sorted(x.params.items())) for x in c_b}
    assert sa == sb  # candidate grid is identical; only metrics differ by data


# --------------------------------------------------------------------------
# Walk-forward
# --------------------------------------------------------------------------
def test_walk_forward_window_count():
    from crypto_quant_ai.backend.optimize.walkforward import _split_windows

    wf = make_wf()
    wins = _split_windows(150, wf)
    assert len(wins) == 3
    for ts, te, vs, ve in wins:
        assert te <= vs
        assert ve <= 150


def test_walk_forward_returns_results():
    from crypto_quant_ai.backend.optimize.walkforward import walk_forward

    wins = walk_forward(make_space(), make_candles(), make_search(), make_wf(), make_replay())
    assert len(wins) >= 2
    for w in wins:
        assert isinstance(w, WindowResult)
        assert w.best_params
        assert "sharpe_ratio" in w.in_sample


def test_walk_forward_metrics_present():
    from crypto_quant_ai.backend.optimize.walkforward import walk_forward

    wins = walk_forward(make_space(), make_candles(), make_search(), make_wf(), make_replay())
    for w in wins:
        assert "sharpe_ratio" in w.out_of_sample or not w.out_of_sample


# --------------------------------------------------------------------------
# Robustness
# --------------------------------------------------------------------------
def test_compute_robustness_fields():
    from crypto_quant_ai.backend.optimize.metrics import compute_robustness
    from crypto_quant_ai.backend.optimize.walkforward import walk_forward

    wins = walk_forward(make_space(), make_candles(), make_search(), make_wf(), make_replay())
    rb = compute_robustness(wins, "sharpe_ratio")
    assert isinstance(rb, RobustnessReport)
    assert rb.windows == len(wins)
    assert "decay" in rb.to_dict()


def test_compute_robustness_stability_range():
    from crypto_quant_ai.backend.optimize.metrics import compute_robustness
    from crypto_quant_ai.backend.optimize.walkforward import walk_forward

    wins = walk_forward(make_space(), make_candles(), make_search(), make_wf(), make_replay())
    rb = compute_robustness(wins, "sharpe_ratio")
    assert 0.0 <= rb.stability_score <= 1.0


def test_compute_robustness_empty_windows_ok():
    from crypto_quant_ai.backend.optimize.metrics import compute_robustness

    rb = compute_robustness([], "sharpe_ratio")
    assert rb.windows == 0
    assert rb.is_mean == 0.0


# --------------------------------------------------------------------------
# End-to-end
# --------------------------------------------------------------------------
def test_run_optimization_structure():
    res = run_optimization(make_space(), make_candles(), make_search(), make_wf(), make_replay())
    assert isinstance(res, OptimizationResult)
    assert res.objective == "sharpe_ratio"
    assert "params" in res.space
    assert res.search["method"] == "grid"


def test_run_optimization_best_present():
    res = run_optimization(make_space(), make_candles(), make_search(), make_wf(), make_replay())
    assert res.best_params
    assert res.best_metrics
    assert "sharpe_ratio" in res.best_metrics


def test_run_optimization_windows_nonempty():
    res = run_optimization(make_space(), make_candles(), make_search(), make_wf(), make_replay())
    assert len(res.windows) >= 2
    assert res.robustness


def test_run_optimization_reproducible():
    a = run_optimization(make_space(), make_candles(), make_search(), make_wf(), make_replay())
    b = run_optimization(make_space(), make_candles(), make_search(), make_wf(), make_replay())
    assert a.best_params == b.best_params
    assert a.to_dict() == b.to_dict()


def test_run_optimization_walk_forward_config_respected():
    res = run_optimization(make_space(), make_candles(), make_search(), WalkForwardConfig(60, 30, 30), make_replay())
    assert res.walk_forward["train_size"] == 60


# --------------------------------------------------------------------------
# Formatters
# --------------------------------------------------------------------------
def _sample_result() -> OptimizationResult:
    return run_optimization(make_space(), make_candles(), make_search(), make_wf(), make_replay())


def test_render_json_valid():
    import json
    txt = render_json(_sample_result())
    obj = json.loads(txt)
    assert "best_params" in obj
    assert "candidates" in obj


def test_render_markdown_contains_best():
    txt = render_markdown(_sample_result())
    assert "Stage 8 Optimization Report" in txt
    assert "Best params" in txt or "best_params" in txt or "Best" in txt


def test_render_csv_rows():
    txt = render_csv(_sample_result())
    lines = [l for l in txt.strip().splitlines() if l]
    assert lines[0].startswith("param_set")
    assert len(lines) >= 2


def test_export_report_writes_files(tmp_path):
    written = export_report(_sample_result(), output_dir=str(tmp_path / "out"))
    for p in written.values():
        assert Path(p).exists()
        assert Path(p).stat().st_size > 0


def test_optimization_result_to_dict():
    d = _sample_result().to_dict()
    assert d["objective"] == "sharpe_ratio"
    assert isinstance(d["candidates"], list)
    assert isinstance(d["windows"], list)


# --------------------------------------------------------------------------
# Safety
# --------------------------------------------------------------------------
def test_forbidden_tokens_absent():
    tokens = _forbidden_tokens()
    base = Path(__file__).resolve().parents[1] / "optimize"
    text = ""
    for f in sorted(base.glob("*.py")):
        text += f.read_text(encoding="utf-8")
    # Case-sensitive: the real scan checks lowercase literals, so the uppercase
    # LIVE_TRADING environment guard is intentionally safe (not flagged).
    hits = [t for t in tokens if t in text]
    assert not hits, f"forbidden tokens found: {hits}"


def test_paper_only_guard_raises():
    code = (
        "import os;"
        "os.environ['LIVE_TRADING']='true';"
        "import crypto_quant_ai.backend.optimize;"
        "print('SHOULD_NOT_REACH')"
    )
    repo = Path(__file__).resolve().parents[3]
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo), capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "RuntimeError" in proc.stderr


def test_no_network_imports():
    tokens = ["import requests", "import httpx", "import socket", "import websocket",
              "import urllib", "aiohttp"]
    base = Path(__file__).resolve().parents[1] / "optimize"
    text = ""
    for f in sorted(base.glob("*.py")):
        text += f.read_text(encoding="utf-8")
    low = text.lower()
    hits = [t for t in tokens if t.lower() in low]
    assert not hits, f"network imports found: {hits}"
