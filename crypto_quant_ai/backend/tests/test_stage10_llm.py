"""Stage 10 - test suite (paper-only, local, no network, no order submission).

All inputs synthetic/deterministic. No MagicMock, no fake orders, no network.
"""
from __future__ import annotations

import binascii
import glob
import json
import math
import os
import pathlib

import pytest

from crypto_quant_ai.backend.llm import (
    LLMConfig,
    LLMResponse,
    LLMAdapter,
    LocalStubAdapter,
    OpenAIStyleAdapter,
    BrainRegistry,
    get_registry,
    register_adapter,
    build_adapter,
    build_prompt,
    LLMBrain,
    build_llm_brain,
    with_llm_brain,
    LLMIntelligenceExtension,
    render_llm_contribution,
    _live_guard,
)
from crypto_quant_ai.backend.core.models import MarketData
from crypto_quant_ai.backend.data.ohlcv import OHLCVBar
from crypto_quant_ai.backend.optimize.types import (
    ParamSpace, ParamSpec, SearchConfig, WalkForwardConfig,
)
from crypto_quant_ai.backend.replay.types import ReplayConfig


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def make_candles(n=120, trend=0.004, noise=0.008, start=100.0):
    from datetime import datetime, timedelta
    bars = []
    price = start
    for i in range(n):
        price = price * (1.0 + trend + noise * math.sin(i * 0.7))
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


class _BuyAdapter(LLMAdapter):
    name = "buy"

    def complete(self, prompt, timeout_s=5.0):
        return json.dumps({"decision": "BUY", "confidence": 0.7, "reasoning": "test buy"})


class _FakeMD:
    symbol = "BTC"
    timeframe = "15m"
    open = 1.0
    high = 2.0
    low = 0.5
    close = 1.5
    volume = 10.0
    stop_loss = 1.0


# --------------------------------------------------------------------------
# types
# --------------------------------------------------------------------------
def test_llmconfig_defaults():
    c = LLMConfig()
    assert c.enabled is False
    assert c.adapter_name == "local_stub"
    assert c.fallback_decision == "NO_TRADE"
    assert c.allow_active_decisions is False


# --------------------------------------------------------------------------
# adapters
# --------------------------------------------------------------------------
def test_local_stub_returns_no_trade():
    a = LocalStubAdapter()
    out = json.loads(a.complete("anything"))
    assert out["decision"] == "NO_TRADE"
    assert out["confidence"] == 0.0


def test_openai_style_disabled_raises():
    a = OpenAIStyleAdapter()
    with pytest.raises(RuntimeError):
        a.complete("anything")


# --------------------------------------------------------------------------
# registry (BrainRegistry)
# --------------------------------------------------------------------------
def test_registry_default_has_local_stub():
    reg = get_registry()
    assert "local_stub" in reg.list_adapters()


def test_registry_register_get():
    reg = BrainRegistry()
    reg.register("custom", LocalStubAdapter)
    assert reg.get("custom") is LocalStubAdapter
    assert "custom" in reg.list_adapters()


def test_registry_unknown_raises():
    reg = BrainRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_build_adapter():
    a = build_adapter("local_stub")
    assert isinstance(a, LocalStubAdapter)


# --------------------------------------------------------------------------
# prompt
# --------------------------------------------------------------------------
def test_build_prompt_deterministic():
    md = MarketData(symbol="BTC", timestamp="2024-01-01T00:00:00", open=1.0, high=2.0,
                    low=0.5, close=1.5, volume=10.0, timeframe="15m")
    p1 = build_prompt(md)
    p2 = build_prompt(md)
    assert p1 == p2
    assert "BTC" in p1


def test_build_prompt_template():
    md = MarketData(symbol="ETH", timestamp="2024-01-01T00:00:00", open=1.0, high=2.0,
                    low=0.5, close=1.5, volume=10.0, timeframe="1h")
    tpl = "symbol={symbol} close={close}"
    p = build_prompt(md, tpl)
    assert "symbol=ETH" in p and "close=1.5" in p


# --------------------------------------------------------------------------
# LLMBrain
# --------------------------------------------------------------------------
def test_brain_disabled_returns_no_trade():
    b = LLMBrain(config=LLMConfig(enabled=False))
    a = b.analyze(_FakeMD())
    assert a.decision == "NO_TRADE"
    assert a.confidence == 0.0


def test_brain_enabled_local_stub_no_trade():
    b = LLMBrain(config=LLMConfig(enabled=True, adapter_name="local_stub"))
    a = b.analyze(_FakeMD())
    assert a.decision == "NO_TRADE"


def test_brain_adapter_error_safe_fallback():
    class _Boom(LLMAdapter):
        name = "boom"
        def complete(self, prompt, timeout_s=5.0):
            raise RuntimeError("network down")
    b = LLMBrain(config=LLMConfig(enabled=True), adapter=_Boom())
    a = b.analyze(_FakeMD())
    assert a.decision == "NO_TRADE"
    assert any("error" in w.lower() for w in a.warnings)


def test_brain_active_blocked_by_config():
    b = LLMBrain(config=LLMConfig(enabled=True, allow_active_decisions=False), adapter=_BuyAdapter())
    a = b.analyze(_FakeMD())
    assert a.decision == "NO_TRADE"


def test_brain_active_allowed_with_stop_loss():
    b = LLMBrain(config=LLMConfig(enabled=True, allow_active_decisions=True,
                                  require_stop_loss_for_active=True), adapter=_BuyAdapter())
    a = b.analyze(_FakeMD())
    assert a.decision == "BUY"
    assert a.confidence == 0.7


def test_brain_active_requires_stop_loss():
    class _NoSL(_FakeMD):
        stop_loss = None
    b = LLMBrain(config=LLMConfig(enabled=True, allow_active_decisions=True,
                                  require_stop_loss_for_active=True), adapter=_BuyAdapter())
    a = b.analyze(_NoSL())
    assert a.decision == "NO_TRADE"


def test_brain_invalid_decision_fallback():
    class _Weird(LLMAdapter):
        name = "weird"
        def complete(self, prompt, timeout_s=5.0):
            return json.dumps({"decision": "MOON", "confidence": 0.9})
    b = LLMBrain(config=LLMConfig(enabled=True, allow_active_decisions=True), adapter=_Weird())
    a = b.analyze(_FakeMD())
    assert a.decision == "NO_TRADE"


def test_brain_unparsable_fallback():
    class _Garbage(LLMAdapter):
        name = "garbage"
        def complete(self, prompt, timeout_s=5.0):
            return "not json at all"
    b = LLMBrain(config=LLMConfig(enabled=True, allow_active_decisions=True), adapter=_Garbage())
    a = b.analyze(_FakeMD())
    assert a.decision == "NO_TRADE"


def test_brain_confidence_clamped():
    class _Over(LLMAdapter):
        name = "over"
        def complete(self, prompt, timeout_s=5.0):
            return json.dumps({"decision": "NO_TRADE", "confidence": 5.0})
    b = LLMBrain(config=LLMConfig(enabled=True), adapter=_Over())
    a = b.analyze(_FakeMD())
    assert 0.0 <= a.confidence <= 1.0


def test_brain_parse_helper():
    r = LLMBrain._parse('{"decision":"SELL","confidence":0.4,"reasoning":"x"}', "local_stub")
    assert isinstance(r, LLMResponse)
    assert r.decision == "SELL"


# --------------------------------------------------------------------------
# integration with Stage 9 (optional extension, no modification of Stage 9)
# --------------------------------------------------------------------------
def test_build_llm_brain_none_when_disabled():
    assert build_llm_brain(None) is None
    assert build_llm_brain(LLMConfig(enabled=False)) is None


def test_with_llm_brain_appends():
    base = []
    out = with_llm_brain(base, LLMConfig(enabled=True))
    assert len(out) == 1
    assert isinstance(out[0], LLMBrain)
    assert with_llm_brain(base, None) == base


def test_extension_disabled_runs_stage9():
    pytest.importorskip("crypto_quant_ai.backend.intelligence")
    ext = LLMIntelligenceExtension(llm_config=LLMConfig(enabled=False))
    rep = ext.analyze(make_candles(), space=small_space(), search=small_search(), wf=small_wf())
    assert rep.symbol


def test_extension_enabled_injects_llm():
    pytest.importorskip("crypto_quant_ai.backend.intelligence")
    from crypto_quant_ai.backend.decision.brain_orchestrator import MultiBrainOrchestrator
    from crypto_quant_ai.backend.replay.registry import build_brains
    from crypto_quant_ai.backend.core.models import MarketData

    md = MarketData(symbol="BTC", timestamp="2024-01-01T00:00:00", open=1.0, high=2.0,
                    low=0.5, close=1.5, volume=10.0, timeframe="15m")
    brains = build_brains(["quant", "market_structure", "risk", "devil_advocate"]) + [
        LLMBrain(config=LLMConfig(enabled=True))
    ]
    rep = MultiBrainOrchestrator(brains).run(md)
    assert any(r.brain_name == "llm" for r in rep.brain_results)


# --------------------------------------------------------------------------
# formatters
# --------------------------------------------------------------------------
def _make_orchestrator_report_with_llm():
    from crypto_quant_ai.backend.decision.brain_orchestrator import (
        MultiBrainOrchestrator, BrainResult,
    )
    from crypto_quant_ai.backend.core.models import FinalDecision, BrainAnalysis
    from crypto_quant_ai.backend.replay.registry import build_brains
    from datetime import datetime, timezone

    brains = build_brains(["quant", "market_structure", "risk", "devil_advocate"]) + [
        LLMBrain(config=LLMConfig(enabled=True))
    ]
    md = MarketData(symbol="BTC", timestamp="2024-01-01T00:00:00", open=1.0, high=2.0,
                    low=0.5, close=1.5, volume=10.0, timeframe="15m")
    return MultiBrainOrchestrator(brains).run(md)


def test_render_llm_contribution_present():
    rep = _make_orchestrator_report_with_llm()
    txt = render_llm_contribution(rep)
    assert "LLM" in txt


def test_render_llm_contribution_absent():
    from crypto_quant_ai.backend.decision.brain_orchestrator import MultiBrainOrchestrator
    from crypto_quant_ai.backend.replay.registry import build_brains
    md = MarketData(symbol="BTC", timestamp="2024-01-01T00:00:00", open=1.0, high=2.0,
                    low=0.5, close=1.5, volume=10.0, timeframe="15m")
    rep = MultiBrainOrchestrator(build_brains(["quant", "market_structure", "risk", "devil_advocate"])).run(md)
    txt = render_llm_contribution(rep)
    assert "not injected" in txt


# --------------------------------------------------------------------------
# live guard
# --------------------------------------------------------------------------
def test_live_guard_runtime(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING", "true")
    with pytest.raises(RuntimeError):
        _live_guard()


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
    files = glob.glob(str(root / "backend" / "llm" / "*.py"))
    files.append(str(pathlib.Path(__file__).resolve()))
    bad = []
    for f in files:
        txt = open(f, encoding="utf-8").read()
        for t in toks:
            if t and t in txt:
                bad.append((f, t))
    assert not bad, f"forbidden tokens found: {bad}"
