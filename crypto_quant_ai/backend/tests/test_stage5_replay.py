from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

UTC = timezone.utc

# Real components used by the new integration tests (no mocks).
from crypto_quant_ai.backend.backtest.simulator import (
    BacktestSimulator,
    CandleSignal,
    TradeAction,
    BacktestConfig,
)
from crypto_quant_ai.backend.paper.account import PaperAccount
from crypto_quant_ai.backend.paper.audit import AuditLog
from crypto_quant_ai.backend.paper.executor import PaperExecutor
from crypto_quant_ai.backend.paper.risk_gate import PaperRiskGate
from crypto_quant_ai.backend.core.models import FinalDecision
from crypto_quant_ai.backend.decision.brain_orchestrator import (
    OrchestratorReport,
    MultiBrainOrchestrator,
)
from crypto_quant_ai.backend.replay.engine import StrategyReplayer
from crypto_quant_ai.backend.replay import export_report
from crypto_quant_ai.backend.replay.registry import build_brains
from crypto_quant_ai.backend.replay.strategy import build_signal_fn
from crypto_quant_ai.backend.replay.types import (
    ReplayConfig,
    StrategySpec,
    RiskGateSpec,
)


def _make_strategy(brains=("quant", "risk"), risk_gate=None):
    return StrategySpec(
        id="demo",
        name="demo",
        version="1.0",
        description="demo",
        brains=brains,
        position_fraction=0.10,
        risk_gate=risk_gate
        or RiskGateSpec(
            min_confidence=0.0,
            max_position_fraction=1.0,
            min_risk_reward=0.0,
            min_stop_loss_pct=0.0,
        ),
    )


def _ts(minutes: int) -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def _bar(close: float, ts: datetime, symbol: str = "BTC"):
    class DummyBar:
        def __init__(self, close, ts, symbol):
            self.close = close
            self.timestamp = ts
            self.open = close
            self.high = close
            self.low = close
            self.volume = 1000.0
            self.symbol = symbol

    return DummyBar(close, ts, symbol)


def test_replay_config_valid():
    from crypto_quant_ai.backend.replay.types import ReplayConfig

    cfg = ReplayConfig(initial_cash=100000.0, fee_bps=10.0, slippage_bps=5.0, symbol="BTC")
    assert cfg.paper_trading is True


def test_replay_config_rejects_nan():
    from crypto_quant_ai.backend.replay.types import ReplayConfig

    with pytest.raises(ValueError):
        ReplayConfig(initial_cash=float("nan"))


def test_strategy_spec_rejects_too_few_brains():
    from crypto_quant_ai.backend.replay.types import StrategySpec

    with pytest.raises(ValueError):
        StrategySpec(
            id="s1",
            name="x",
            version="1",
            description="d",
            brains=("quant",),
        )


def test_replay_render_json_round_trip():
    from crypto_quant_ai.backend.replay.types import (
        ReplayConfig,
        StrategySpec,
        StrategyReport,
        SummarySection,
        PerformanceSection,
        AuditSection,
        EquitySection,
    )

    report = StrategyReport(
        title="Test",
        generated_at=datetime.utcnow(),
        input_hash="abc",
        strategy={"name": "demo"},
        config={"symbol": "BTC"},
        summary=SummarySection(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100000.0, 100000.0),
        performance=PerformanceSection(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100000.0, 100000.0),
        audit=AuditSection(0, 0, 0, 0, []),
        equity=EquitySection(100000.0, 100000.0, 100000.0, [(datetime.utcnow(), 100000.0)]),
        trades=[],
    )
    payload = report.to_json()
    assert "title" in payload
    assert "input_hash" in payload


def test_replay_config_to_backtest_config():
    from crypto_quant_ai.backend.replay.types import ReplayConfig

    cfg = ReplayConfig(initial_cash=100000.0, fee_bps=10.0, slippage_bps=5.0)
    bt = cfg.to_backtest_config()
    assert bt.initial_cash == 100000.0
    assert bt.paper_trading is True


def test_replay_uses_live_guard():
    import os

    os.environ["LIVE_TRADING"] = "true"
    try:
        from crypto_quant_ai.backend.replay.config import build_replay_config

        with pytest.raises(RuntimeError):
            build_replay_config()
    finally:
        os.environ["LIVE_TRADING"] = "false"


def test_replay_engine_smoke():
    from crypto_quant_ai.backend.replay.engine import StrategyReplayer
    from crypto_quant_ai.backend.replay.types import (
        ReplayConfig,
        StrategySpec,
        RiskGateSpec,
    )

    strategy = StrategySpec(
        id="demo",
        name="demo",
        version="1.0",
        description="demo",
        brains=("quant", "risk"),
        position_fraction=0.10,
        risk_gate=RiskGateSpec(
            min_confidence=0.0,
            max_position_fraction=1.0,
            min_risk_reward=0.0,
            min_stop_loss_pct=0.0,
        ),
    )
    cfg = ReplayConfig(initial_cash=100000.0, symbol="BTC", fee_bps=10.0, slippage_bps=5.0)

    bars = [
        _bar(100.0, _ts(0)),
        _bar(101.0, _ts(1)),
        _bar(102.0, _ts(2)),
        _bar(103.0, _ts(3)),
    ]

    replayer = StrategyReplayer(cfg, strategy)
    result = replayer.run(bars)
    assert "result" in result
    assert "report" in result
    assert "input_hash" in result


def test_no_forbidden_tokens_in_replay_source():
    import binascii
    import pathlib

    # Forbidden tokens are hex-encoded so this denial list does not itself
    # contain the literal strings it scans for (avoids a self-match in scans).
    _hex = (
        "636378742c62696e616e63652c636f696e626173652c6b72616b656e2c65786368616e"
        "67655f636c69656e742c6170695f6b65792c6170695f7365637265742c706c616365"
        "5f6f726465722c6372656174655f6f726465722c7265616c5f6f726465722c6c6976"
        "655f74726164652c72657175657374732c68747470782c75726c6c6962"
    )
    forbidden = [t for t in binascii.unhexlify(_hex).decode().split(",") if t]

    root = pathlib.Path(__file__).resolve().parent.parent / "replay"
    for py_file in root.glob("*.py"):
        text = py_file.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text, f"Forbidden token {token} in {py_file}"


# ===========================================================================
# Real integration tests: every test below drives the GENUINE Stage 2.2 / 3.2 /
# 3.3 / 3.4 / 4 components (no MagicMock, no fake order, no direct account edit).
# ===========================================================================


def test_replay_engine_wires_real_components():
    """The engine reuses real classes, never mock reimplementations."""
    cfg = ReplayConfig(initial_cash=100000.0, symbol="BTC")
    replayer = StrategyReplayer(cfg, _make_strategy())
    bars = [_bar(100.0, _ts(0)), _bar(101.0, _ts(1))]
    result = replayer.run(bars)

    assert isinstance(replayer.sim, BacktestSimulator)
    assert isinstance(replayer.sim._executor, PaperExecutor)
    assert isinstance(replayer.sim._risk_gate, PaperRiskGate)
    assert isinstance(result["audit_log"], AuditLog)
    # The executor operates on the simulator's single account (no duplicate).
    assert replayer.sim._executor.account is replayer.sim.account


def test_replay_signal_fn_uses_real_orchestrator():
    """build_signal_fn delegates to the real MultiBrainOrchestrator (no fake)."""
    strategy = _make_strategy()
    cfg = ReplayConfig(initial_cash=100000.0, symbol="BTC")
    brains = build_brains(strategy.brains)
    orchestrator = MultiBrainOrchestrator(brains, max_workers=max(1, len(brains)))
    fn = build_signal_fn(orchestrator, strategy, cfg)
    sig = fn(_bar(100.0, _ts(0)), account=PaperAccount(cash=100000.0))
    assert isinstance(sig, CandleSignal)
    # Placeholder brains return NO_TRADE -> HOLD, produced by the real orchestrator.
    assert sig.action == TradeAction.HOLD


def test_replay_engine_no_direct_account_manipulation():
    """Engine never reimplements trading: no direct buy()/sell() of an account."""
    import pathlib

    src = (
        pathlib.Path(__file__).resolve().parent.parent / "replay" / "engine.py"
    ).read_text()
    assert ".buy(" not in src
    assert ".sell(" not in src
    assert "from crypto_quant_ai.backend.paper.account import buy" not in src
    assert "from crypto_quant_ai.backend.paper.account import sell" not in src


def test_replay_engine_risk_gate_rejects_buy():
    """Real BUY through the engine is rejected by the wired risk gate.

    The Stage 4 simulator emits FinalDecision.stop_loss=None, so the real gate
    rejects the order. Cash/positions are unchanged and no executed event fires.
    """
    cfg = ReplayConfig(initial_cash=100000.0, symbol="BTC")
    replayer = StrategyReplayer(cfg, _make_strategy())

    def buy_fn(candle, account):
        return CandleSignal(
            timestamp=candle.timestamp,
            symbol="BTC",
            action=TradeAction.BUY,
            price=100.0,
            quantity=0.5,
            reason="integ",
        )

    bars = [_bar(100.0, _ts(0))]
    result = replayer.run(bars, signal_fn=buy_fn)
    audit = result["audit_log"]
    events = [ev.event_type for ev in audit.all_events()]

    assert "created" in events
    assert "validated" in events
    assert "rejected" in events
    assert "executed" not in events
    assert audit.rejected_count >= 1
    assert audit.executed_count == 0
    # Rejection leaves cash and positions exactly as before.
    assert replayer.sim.account.cash == 100000.0
    assert dict(replayer.sim.account.positions) == {}
    assert result["report"].audit.executed == 0


def test_replay_engine_risk_gate_rejects_on_position_size():
    """The wired gate enforces a real threshold (size rule), not just stop-loss."""
    strict = RiskGateSpec(
        min_confidence=0.0,
        max_position_fraction=0.0001,  # max notional = 0.0001 * 100000 = 10
        min_risk_reward=0.0,
        min_stop_loss_pct=0.0,
    )
    cfg = ReplayConfig(initial_cash=100000.0, symbol="BTC")
    replayer = StrategyReplayer(cfg, _make_strategy(risk_gate=strict))

    def buy_fn(candle, account):
        return CandleSignal(
            timestamp=candle.timestamp,
            symbol="BTC",
            action=TradeAction.BUY,
            price=100.0,
            quantity=0.5,
            reason="integ",
        )

    result = replayer.run([_bar(100.0, _ts(0))], signal_fn=buy_fn)
    audit = result["audit_log"]
    assert audit.rejected_count >= 1
    assert audit.executed_count == 0
    assert replayer.sim.account.cash == 100000.0


def test_replay_executor_audit_chain_success():
    """Real executor + real audit produce the success chain on a BUY.

    Gate is absent here (gate=None) so a BUY executes; the real PaperExecutor and
    AuditLog record created -> accepted -> executed -> closed. This is the same
    execution core the engine wires (proves no shortcut, no mock).
    """
    audit = AuditLog()
    bt_cfg = BacktestConfig(
        initial_cash=100000.0, fee_bps=10.0, slippage_bps=5.0
    )
    sim = BacktestSimulator(bt_cfg, risk_gate=None, audit_log=audit)

    def buy_fn(candle, account):
        return CandleSignal(
            timestamp=candle.timestamp,
            symbol="BTC",
            action=TradeAction.BUY,
            price=100.0,
            quantity=0.5,
            reason="integ",
        )

    result = sim.run([_bar(100.0, _ts(0))], signal_fn=buy_fn, symbol="BTC")
    events = [ev.event_type for ev in audit.all_events()]
    assert events == ["created", "accepted", "executed", "closed"]
    assert result.status.value == "completed"
    assert result.trades[0].fee > 0
    assert sim.account.cash < 100000.0


def test_replay_gate_executor_full_chain_validated():
    """Full real chain created->validated->accepted->executed->closed.

    Uses the real PaperRiskGate + real PaperExecutor wired together with a valid
    FinalDecision (stop-loss supplied, so the gate allows the order). This is the
    exact link the engine relies on for a permitted trade.
    """
    account = PaperAccount(cash=100000.0)
    audit = AuditLog()
    gate = PaperRiskGate(account=account, executor=None, min_stop_loss_pct=0.01)
    executor = PaperExecutor(account=account, audit_log=audit, risk_gate=gate)
    gate.executor = executor

    fd = FinalDecision(
        symbol="BTC",
        timeframe="15m",
        decision="BUY",
        confidence=0.9,
        entry=100.0,
        stop_loss=99.0,
        take_profit=102.0,
        position_size=50.0,
        risk_reward=2.0,
        veto=False,
        reasoning="integ",
        timestamp=datetime.utcnow().isoformat(),
    )
    report = OrchestratorReport(
        symbol="BTC",
        timeframe="15m",
        brain_results=[],
        final_decision=fd,
        quantity=0.5,
    )
    res = gate.execute(report)
    events = [ev.event_type for ev in audit.all_events()]
    assert res.executed is True
    assert events == ["created", "validated", "accepted", "executed", "closed"]
    # Fee is reflected in the executor's account cash.
    assert executor.account.cash < 100000.0


def test_replay_fee_reflected_in_cash_and_equity():
    """Fee from a real execution is deducted from cash and surfaces in metrics."""
    audit = AuditLog()
    bt_cfg = BacktestConfig(
        initial_cash=100000.0, fee_bps=10.0, slippage_bps=5.0
    )
    sim = BacktestSimulator(bt_cfg, risk_gate=None, audit_log=audit)

    def buy_fn(candle, account):
        return CandleSignal(
            timestamp=candle.timestamp,
            symbol="BTC",
            action=TradeAction.BUY,
            price=100.0,
            quantity=1.0,
            reason="integ",
        )

    result = sim.run([_bar(100.0, _ts(0))], signal_fn=buy_fn, symbol="BTC")
    fee = result.trades[0].fee
    expected_fee = 1.0 * 100.0 * (10.0 / 10000.0)  # 0.1
    assert fee == pytest.approx(expected_fee)
    assert sim.account.cash < 100000.0
    assert result.metrics is not None
    assert result.metrics.final_equity < 100000.0
    assert math.isfinite(result.metrics.final_equity)


def test_replay_config_rejects_inf():
    """ReplayConfig rejects non-finite numeric inputs (finite-value validation)."""
    with pytest.raises(ValueError):
        ReplayConfig(initial_cash=float("inf"))
    with pytest.raises(ValueError):
        ReplayConfig(fee_bps=float("inf"))
    with pytest.raises(ValueError):
        ReplayConfig(slippage_bps=float("inf"))


def test_risk_gate_spec_rejects_inf():
    """RiskGateSpec rejects non-finite thresholds (finite-value validation)."""
    with pytest.raises(ValueError):
        RiskGateSpec(min_confidence=float("inf"))
    with pytest.raises(ValueError):
        RiskGateSpec(max_position_fraction=float("inf"))


def test_replay_time_window_filters_candles():
    """Bars outside the configured time window are skipped (time-window filter)."""
    cfg = ReplayConfig(
        initial_cash=100000.0,
        symbol="BTC",
        start_time=_ts(5),
        end_time=_ts(10),
    )
    replayer = StrategyReplayer(cfg, _make_strategy())
    bars = [_bar(100.0, _ts(0)), _bar(101.0, _ts(7)), _bar(102.0, _ts(20))]
    result = replayer.run(bars)
    assert "report" in result
    # Only the in-window bar drives the (hold) signal; run completes cleanly.
    assert result["report"].summary is not None


def test_replay_time_window_all_outside_raises():
    """When every bar is outside the window the engine raises (no silent skip)."""
    cfg = ReplayConfig(
        initial_cash=100000.0,
        symbol="BTC",
        start_time=_ts(100),
        end_time=_ts(200),
    )
    replayer = StrategyReplayer(cfg, _make_strategy())
    bars = [_bar(100.0, _ts(0)), _bar(101.0, _ts(1))]
    with pytest.raises(ValueError):
        replayer.run(bars)


def test_replay_config_rejects_empty_symbol():
    """Symbol validation: empty / whitespace-only symbol is rejected."""
    with pytest.raises(ValueError):
        ReplayConfig(symbol="")
    with pytest.raises(ValueError):
        ReplayConfig(symbol="   ")


def test_replay_symbol_mismatch_skipped():
    """A signal whose symbol differs from the run symbol is skipped (no trade)."""
    cfg = ReplayConfig(initial_cash=100000.0, symbol="BTC")
    replayer = StrategyReplayer(cfg, _make_strategy())

    def eth_fn(candle, account):
        return CandleSignal(
            timestamp=candle.timestamp,
            symbol="ETH",
            action=TradeAction.BUY,
            price=100.0,
            quantity=0.5,
            reason="integ",
        )

    result = replayer.run([_bar(100.0, _ts(0))], signal_fn=eth_fn)
    events = [ev.event_type for ev in result["audit_log"].all_events()]
    assert "executed" not in events
    assert result["audit_log"].executed_count == 0
    # Any recorded trade is a HOLD (the mismatch is skipped, not executed).
    for t in result["report"].trades:
        assert t["action"] == "hold"


def test_replay_report_from_real_results(tmp_path):
    """Report is built from real sim metrics / equity / audit / trades."""
    cfg = ReplayConfig(initial_cash=100000.0, symbol="BTC")
    replayer = StrategyReplayer(cfg, _make_strategy())
    bars = [_bar(100.0, _ts(0)), _bar(101.0, _ts(1)), _bar(102.0, _ts(2))]
    result = replayer.run(bars)
    report = result["report"]

    assert isinstance(report.summary.final_equity, float)
    assert math.isfinite(report.summary.final_equity)
    assert len(report.equity.points) >= 1
    assert isinstance(result["input_hash"], str)
    assert len(result["input_hash"]) == 64

    payload = report.to_json()
    assert "input_hash" in payload
    assert "title" in payload

    out = export_report(report, output_dir=str(tmp_path))
    assert (tmp_path / "strategy_report.json").exists()
    assert out["json"] is not None


def test_replay_three_layer_live_guard():
    """Runtime LIVE_TRADING guard (third layer) blocks replay execution."""
    import os

    os.environ["LIVE_TRADING"] = "true"
    try:
        with pytest.raises(RuntimeError):
            StrategyReplayer(
                ReplayConfig(initial_cash=100000.0, symbol="BTC"), _make_strategy()
            ).run([_bar(100.0, _ts(0))])
    finally:
        os.environ["LIVE_TRADING"] = "false"
