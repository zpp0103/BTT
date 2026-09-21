from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

UTC = timezone.utc


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
