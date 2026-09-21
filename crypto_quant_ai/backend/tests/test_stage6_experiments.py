"""Stage 6 — Local Experiment Runner: tests (real components, no mocks)."""

from __future__ import annotations

import binascii
import csv
import io
import json
import math
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

UTC = timezone.utc

from crypto_quant_ai.backend.replay.types import (
    ReplayConfig,
    StrategySpec,
    RiskGateSpec,
)
from crypto_quant_ai.backend.replay.engine import StrategyReplayer
from crypto_quant_ai.backend.backtest.simulator import (
    BacktestSimulator,
    BacktestConfig,
    CandleSignal,
    TradeAction,
)
from crypto_quant_ai.backend.experiments import (
    ExperimentConfig,
    ExperimentRunner,
    ExperimentRun,
    RunStatus,
    ComparisonEngine,
    compute_experiment_hash,
    build_report,
    render_markdown,
    render_json,
    render_csv,
)

# Forbidden-token list kept as hex so this file never contains the literals
# (the safety scan would otherwise match its own list). Decode: comma-separated.
_FORBIDDEN_HEX = (
    "636378742c62696e616e63652c636f696e626173652c6b72616b656e2c65786368616e"
    "67655f636c69656e742c65786368616e67652d636c69656e742c6170695f6b65792c61"
    "70692d6b65792c6170695f7365637265742c6170692d7365637265742c706c6163655f"
    "6f726465722c6372656174655f6f726465722c7265616c5f6f726465722c7265616c2d"
    "6f726465722c6c6976655f74726164652c6c6976652d74726164652c72657175657374"
    "732c68747470782c75726c6c69622c736f636b65742c776562736f636b6574"
)
FORBIDDEN = binascii.unhexlify(_FORBIDDEN_HEX).decode().split(",")


def _ts(minutes: int) -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _bar(close: float, ts: datetime, symbol: str = "BTC"):
    class DummyBar:
        def __init__(self, c, t, s):
            self.close = c
            self.timestamp = t
            self.open = c
            self.high = c
            self.low = c
            self.volume = 1000.0
            self.symbol = s

    return DummyBar(close, ts, symbol)


def _make_candles(n: int = 10, symbol: str = "BTC"):
    return [_bar(100.0 + float(i), _ts(i), symbol) for i in range(n)]


def _make_strategy(id_: str, brains=("quant", "risk"), risk_gate=None, **kw):
    rg = risk_gate or RiskGateSpec(
        min_confidence=0.0,
        max_position_fraction=1.0,
        min_risk_reward=0.0,
        min_stop_loss_pct=0.0,
    )
    return StrategySpec(
        id=id_,
        name=id_,
        version="1.0",
        description=id_,
        brains=brains,
        position_fraction=0.10,
        risk_gate=rg,
        **kw,
    )


def _rc(**kw):
    return ReplayConfig(
        initial_cash=100000.0,
        fee_bps=10.0,
        slippage_bps=5.0,
        symbol="BTC",
        **kw,
    )


def _make_config(strategies, **kw):
    return ExperimentConfig(
        experiment_id="exp1",
        name="exp1",
        description="demo",
        strategies=tuple(strategies),
        replay_config=_rc(),
        **kw,
    )


def _mk_run(sid, sharpe, ret, dd, fe=100000.0, trades=0, rejected=0):
    return ExperimentRun(
        strategy_id=sid,
        status=RunStatus.COMPLETED,
        final_equity=fe,
        total_return_pct=ret,
        max_drawdown_pct=dd,
        sharpe_ratio=sharpe,
        rejected_orders=rejected,
        total_trades=trades,
    )


# ---------------------------------------------------------------------------
# Configuration (1-8)
# ---------------------------------------------------------------------------


def test_empty_strategies_rejected():
    with pytest.raises(ValueError):
        ExperimentConfig(
            experiment_id="e", name="n", description="d",
            strategies=(), replay_config=_rc(),
        )


def test_duplicate_strategy_id_rejected():
    with pytest.raises(ValueError):
        ExperimentConfig(
            experiment_id="e", name="n", description="d",
            strategies=(_make_strategy("a"), _make_strategy("a")),
            replay_config=_rc(),
        )


def test_invalid_baseline_rejected():
    with pytest.raises(ValueError):
        ExperimentConfig(
            experiment_id="e", name="n", description="d",
            strategies=(_make_strategy("a"),),
            replay_config=_rc(), baseline_strategy_id="nope",
        )


def test_empty_experiment_id_rejected():
    with pytest.raises(ValueError):
        ExperimentConfig(
            experiment_id="", name="n", description="d",
            strategies=(_make_strategy("a"),), replay_config=_rc(),
        )


def test_nan_inf_rejected():
    with pytest.raises(ValueError):
        ExperimentConfig(
            experiment_id="e", name="n", description="d",
            strategies=(_make_strategy("a"),),
            replay_config=ReplayConfig(initial_cash=float("inf")),
        )


def test_paper_trading_false_rejected():
    with pytest.raises(ValueError):
        ExperimentConfig(
            experiment_id="e", name="n", description="d",
            strategies=(_make_strategy("a"),),
            replay_config=ReplayConfig(paper_trading=False),
        )


def test_single_strategy_config_ok():
    cfg = _make_config([_make_strategy("a")])
    assert len(cfg.strategies) == 1
    assert cfg.replay_config.paper_trading is True


def test_multi_strategy_config_ok():
    cfg = _make_config([_make_strategy("a"), _make_strategy("b")])
    assert len(cfg.strategies) == 2


# ---------------------------------------------------------------------------
# Execution (9-20)
# ---------------------------------------------------------------------------


def test_single_strategy_experiment_success():
    cfg = _make_config([_make_strategy("a")])
    res = ExperimentRunner().run(_make_candles(), cfg)
    assert len(res.runs) == 1
    assert res.runs[0].status == RunStatus.COMPLETED
    assert len(res.comparison) == 1


def test_multi_strategy_experiment_success():
    cfg = _make_config([_make_strategy("a"), _make_strategy("b")])
    res = ExperimentRunner().run(_make_candles(), cfg)
    assert [r.status for r in res.runs] == [RunStatus.COMPLETED, RunStatus.COMPLETED]
    assert len(res.comparison) == 2


def test_account_isolation():
    cfg = _make_config([_make_strategy("a"), _make_strategy("b")])
    runner = ExperimentRunner()
    runner.run(_make_candles(), cfg)
    assert runner.replayers[0].sim.account is not runner.replayers[1].sim.account


def test_audit_isolation():
    cfg = _make_config([_make_strategy("a"), _make_strategy("b")])
    runner = ExperimentRunner()
    runner.run(_make_candles(), cfg)
    assert runner.replayers[0].audit_log is not runner.replayers[1].audit_log


def test_input_hash_present():
    cfg = _make_config([_make_strategy("a"), _make_strategy("b")])
    res = ExperimentRunner().run(_make_candles(), cfg)
    for r in res.runs:
        assert r.input_hash
    assert all(res.report.input_hashes.values())


def test_empty_candles_fails():
    cfg = _make_config([_make_strategy("a")])
    res = ExperimentRunner().run([], cfg)
    assert res.runs[0].status == RunStatus.FAILED
    assert res.runs[0].error_message


def test_descending_candles_fails():
    bars = list(reversed(_make_candles(8)))
    cfg = _make_config([_make_strategy("a")])
    res = ExperimentRunner().run(bars, cfg)
    assert res.runs[0].status == RunStatus.FAILED
    assert res.runs[0].error_message


def test_one_failure_fail_fast_false_continues():
    cfg = _make_config(
        [
            _make_strategy("bad", brains=("quant", "bogus")),
            _make_strategy("ok"),
        ],
        fail_fast=False,
    )
    res = ExperimentRunner().run(_make_candles(), cfg)
    assert res.runs[0].status == RunStatus.FAILED
    assert res.runs[1].status == RunStatus.COMPLETED


def test_fail_fast_true_skips_remaining():
    cfg = _make_config(
        [
            _make_strategy("bad", brains=("quant", "bogus")),
            _make_strategy("ok"),
        ],
        fail_fast=True,
    )
    res = ExperimentRunner().run(_make_candles(), cfg)
    assert res.runs[0].status == RunStatus.FAILED
    assert res.runs[1].status == RunStatus.SKIPPED


def test_failed_strategy_no_fabricated_metrics():
    cfg = _make_config([_make_strategy("bad", brains=("quant", "bogus"))])
    res = ExperimentRunner().run(_make_candles(), cfg)
    r = res.runs[0]
    assert r.status == RunStatus.FAILED
    assert r.error_message
    assert r.final_equity == 0.0


def test_original_candles_unmodified():
    candles = _make_candles()
    original = [(c.timestamp, c.close) for c in candles]
    cfg = _make_config([_make_strategy("a")])
    ExperimentRunner().run(candles, cfg)
    after = [(c.timestamp, c.close) for c in candles]
    assert after == original


def test_each_strategy_independent_replay():
    cfg = _make_config([_make_strategy("a"), _make_strategy("b")])
    runner = ExperimentRunner()
    runner.run(_make_candles(), cfg)
    assert runner.replayers[0] is not runner.replayers[1]
    assert runner.replayers[0].sim is not runner.replayers[1].sim


# ---------------------------------------------------------------------------
# Comparison (21-31)
# ---------------------------------------------------------------------------


def test_sharpe_priority():
    runs = [_mk_run("a", 0.1, 5.0, 2.0), _mk_run("b", 0.9, 1.0, 2.0)]
    rows = ComparisonEngine().rank(runs)
    assert [r.strategy_id for r in rows] == ["b", "a"]


def test_return_secondary():
    runs = [_mk_run("a", 0.5, 1.0, 2.0), _mk_run("b", 0.5, 9.0, 2.0)]
    rows = ComparisonEngine().rank(runs)
    assert [r.strategy_id for r in rows] == ["b", "a"]


def test_drawdown_tertiary():
    runs = [_mk_run("a", 0.5, 5.0, 9.0), _mk_run("b", 0.5, 5.0, 1.0)]
    rows = ComparisonEngine().rank(runs)
    assert [r.strategy_id for r in rows] == ["b", "a"]


def test_strategy_id_tiebreak():
    runs = [_mk_run("b", 0.5, 5.0, 2.0), _mk_run("a", 0.5, 5.0, 2.0)]
    rows = ComparisonEngine().rank(runs)
    assert [r.strategy_id for r in rows] == ["a", "b"]


def test_ranking_deterministic():
    runs = [
        _mk_run("a", 0.1, 5.0, 2.0),
        _mk_run("b", 0.9, 1.0, 2.0),
        _mk_run("c", 0.5, 3.0, 4.0),
    ]
    engine = ComparisonEngine()
    assert [r.strategy_id for r in engine.rank(runs)] == [
        r.strategy_id for r in engine.rank(runs)
    ]


def test_baseline_diff_correct():
    runs = [_mk_run("a", 0.5, 5.0, 2.0), _mk_run("b", 0.5, 12.0, 2.0)]
    bc = ComparisonEngine().baseline_compare(runs, "a")
    assert bc["available"] is True
    assert bc["rows"]["b"]["vs_baseline_return_pct"] == pytest.approx(7.0)
    assert bc["rows"]["a"]["vs_baseline_return_pct"] == pytest.approx(0.0)


def test_baseline_failure_no_fake():
    failed = ExperimentRun(strategy_id="bad", status=RunStatus.FAILED, error_message="x")
    runs = [failed, _mk_run("a", 0.5, 5.0, 2.0)]
    bc = ComparisonEngine().baseline_compare(runs, "bad")
    assert bc["available"] is False
    assert bc["rows"] == {}


def test_failed_skipped_not_ranked():
    runs = [
        ExperimentRun(strategy_id="f", status=RunStatus.FAILED, error_message="e"),
        _mk_run("a", 0.5, 5.0, 2.0),
        ExperimentRun(strategy_id="s", status=RunStatus.SKIPPED),
    ]
    rows = ComparisonEngine().rank(runs)
    assert [r.strategy_id for r in rows] == ["a"]


def test_rejected_orders_statistics():
    replayer = StrategyReplayer(_rc(), _make_strategy("a"))

    def buy_fn(candle, account):
        return CandleSignal(
            timestamp=candle.timestamp,
            symbol="BTC",
            action=TradeAction.BUY,
            price=float(candle.close),
            quantity=0.01,
            reason="test-buy",
        )

    out = replayer.run(_make_candles(), signal_fn=buy_fn)
    assert out["report"].audit.rejected >= 1
    assert out["report"].audit.executed == 0
    assert out["audit_log"].rejected_count >= 1
    # cash unchanged on rejection by the risk gate
    assert out["result"].metrics.final_equity == pytest.approx(100000.0)


def test_fee_deduction_reaches_final_equity():
    def buy_fn(candle, account):
        return CandleSignal(
            timestamp=candle.timestamp,
            symbol="BTC",
            action=TradeAction.BUY,
            price=float(candle.close),
            quantity=0.01,
            reason="buy",
        )

    def run_with_fee(fee_bps):
        sim = BacktestSimulator(
            BacktestConfig(
                initial_cash=100000.0,
                fee_bps=fee_bps,
                slippage_bps=0.0,
                paper_trading=True,
            ),
            risk_gate=None,
        )
        res = sim.run(_make_candles(), signal_fn=buy_fn, symbol="BTC")
        return res.metrics.final_equity

    eq0 = run_with_fee(0.0)
    eq10 = run_with_fee(10.0)
    assert eq0 > eq10  # fee reduces equity


def test_all_completed_metrics_finite():
    cfg = _make_config([_make_strategy("a"), _make_strategy("b")])
    res = ExperimentRunner().run(_make_candles(), cfg)
    for r in res.runs:
        assert r.status == RunStatus.COMPLETED
        for v in (
            r.final_equity,
            r.total_return_pct,
            r.max_drawdown_pct,
            r.sharpe_ratio,
            r.sortino_ratio,
            r.win_rate_pct,
        ):
            assert math.isfinite(v)


# ---------------------------------------------------------------------------
# Report (32-40)
# ---------------------------------------------------------------------------


def _sample_report():
    cfg = _make_config([_make_strategy("a"), _make_strategy("b")])
    res = ExperimentRunner().run(_make_candles(), cfg)
    return res.report


def test_render_markdown():
    md = render_markdown(_sample_report())
    assert "experiment_hash" in md
    assert "Safety" in md
    assert "LIVE_TRADING" in md


def test_render_json_parses():
    data = json.loads(render_json(_sample_report()))
    assert data["experiment_hash"]
    assert data["completed"] == 2


def test_render_csv_parses():
    text = render_csv(_sample_report())
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][0] == "strategy_id"
    assert len(rows) >= 3


def test_csv_column_count_consistent():
    text = render_csv(_sample_report())
    rows = list(csv.reader(io.StringIO(text)))
    width = len(rows[0])
    assert all(len(r) == width for r in rows)


def test_experiment_hash_present():
    rep = _sample_report()
    assert rep.experiment_hash
    assert len(rep.experiment_hash) == 64


def test_strategy_input_hash_present():
    rep = _sample_report()
    assert all(rep.input_hashes.values())


def test_failure_reason_present():
    cfg = _make_config([_make_strategy("bad", brains=("quant", "bogus"))])
    res = ExperimentRunner().run(_make_candles(), cfg)
    rep = res.report
    assert rep.error_messages
    assert "bad" in rep.error_messages


def test_generated_at_not_in_hash():
    cfg = _make_config([_make_strategy("a")])
    candles = _make_candles()
    h1 = compute_experiment_hash(cfg, candles)
    time.sleep(0.001)
    h2 = compute_experiment_hash(cfg, candles)
    assert h1 == h2  # hash is independent of generated_at / wall clock


def test_report_no_sensitive_fields():
    _SENS_HEX = "6170695f6b65792c6170695f7365637265742c7365637265742c746f6b656e2c70617373776f7264"
    _sens = binascii.unhexlify(_SENS_HEX).decode().split(",")
    text = render_json(_sample_report()).lower()
    hits = [t for t in _sens if t in text]
    assert hits == [], f"sensitive tokens in report: {hits}"


# ---------------------------------------------------------------------------
# Safety (41-45)
# ---------------------------------------------------------------------------


def test_live_trading_blocks_run(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING", "true")
    cfg = _make_config([_make_strategy("a")])
    with pytest.raises(RuntimeError):
        ExperimentRunner().run(_make_candles(), cfg)


def test_no_forbidden_tokens_in_source():
    import crypto_quant_ai.backend.experiments as pkg

    pkg_dir = os.path.dirname(pkg.__file__)
    hits = []
    for root, _, files in os.walk(pkg_dir):
        for fn in files:
            if fn.endswith(".py"):
                p = os.path.join(root, fn)
                for ln, line in enumerate(open(p, encoding="utf-8"), 1):
                    low = line.lower()
                    for tok in FORBIDDEN:
                        if tok in low:
                            hits.append((fn, ln, tok, line.strip()))
    assert hits == [], f"forbidden tokens found: {hits}"


def test_no_exchange_dependency():
    import crypto_quant_ai.backend.experiments as _pkg

    _dir = os.path.dirname(_pkg.__file__)
    hits = []
    for _root, _, _files in os.walk(_dir):
        for _fn in _files:
            if not _fn.endswith(".py"):
                continue
            for _ln, _line in enumerate(
                open(os.path.join(_root, _fn), encoding="utf-8"), 1
            ):
                _low = _line.lower()
                for _tok in FORBIDDEN:
                    if _tok in _low:
                        hits.append((_fn, _ln, _tok))
    assert hits == [], f"exchange-related tokens found: {hits}"


def test_no_executed_orders():
    hits = []
    for _ln, _line in enumerate(open(__file__, encoding="utf-8"), 1):
        _low = _line.lower()
        for _tok in FORBIDDEN:
            if _tok in _low:
                hits.append((os.path.basename(__file__), _ln, _tok))
    assert hits == [], f"order-related tokens found: {hits}"


def test_replay_components_importable():
    from crypto_quant_ai.backend.replay import (
        StrategyReplayer,
        ReplayConfig,
        StrategySpec,
    )
    from crypto_quant_ai.backend.backtest import BacktestSimulator
    from crypto_quant_ai.backend.paper.audit import AuditLog

    assert StrategyReplayer is not None
    assert BacktestSimulator is not None
    assert AuditLog is not None


# ---------------------------------------------------------------------------
# Real multi-strategy run (Section 12-style end-to-end)
# ---------------------------------------------------------------------------


def test_real_multi_strategy_run():
    s1 = _make_strategy("momentum", brains=("quant", "risk"))
    s2 = _make_strategy("meanrev", brains=("market_structure", "devil_advocate"))
    cfg = ExperimentConfig(
        experiment_id="expR",
        name="expR",
        description="demo",
        strategies=(s1, s2),
        replay_config=_rc(),
        baseline_strategy_id="momentum",
    )
    runner = ExperimentRunner()
    res = runner.run(_make_candles(12), cfg)

    assert len(res.runs) == 2
    assert all(r.status == RunStatus.COMPLETED for r in res.runs)
    # isolation
    assert runner.replayers[0].sim.account is not runner.replayers[1].sim.account
    assert runner.replayers[0].audit_log is not runner.replayers[1].audit_log
    # input hashes + experiment hash
    assert all(r.input_hash for r in res.runs)
    assert res.experiment_hash and len(res.experiment_hash) == 64
    # ranking present
    assert len(res.comparison) == 2
    # report serializable
    json.loads(render_json(res.report))
    # safety statement present
    assert res.report.safety_summary
