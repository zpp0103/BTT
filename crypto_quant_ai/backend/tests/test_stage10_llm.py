from __future__ import annotations

import json

import pytest

from crypto_quant_ai.backend.brains.llm_base import LLMBrain, build_llm_brain
from crypto_quant_ai.backend.brains.llm_stub import LLMStubBrain
from crypto_quant_ai.backend.core.models import BrainAnalysis, MarketData
from crypto_quant_ai.backend.decision.brain_orchestrator import MultiBrainOrchestrator
from crypto_quant_ai.backend.llm.formatters import render_llm_contribution
from crypto_quant_ai.backend.llm.providers import (
    LLMProvider,
    LLMResponse,
    LocalStubProvider,
    OpenAIGatedProvider,
    build_provider,
    parse_suggestion,
)
from crypto_quant_ai.backend.llm.registry import ProviderRegistry, get_provider_registry
from crypto_quant_ai.backend.llm.safety import (
    DecisionGate,
    assert_paper_only,
    contains_forbidden,
    forbidden_tokens,
)
from crypto_quant_ai.backend.llm.types import LLMConfig, ParsedSuggestion, _live_guard
from crypto_quant_ai.backend.replay.registry import build_brains


def _md():
    return MarketData(
        symbol="BTC",
        timestamp="2024-01-01T00:00:00",
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=10.0,
        timeframe="15m",
    )


class ScriptedProvider(LLMProvider):
    name = "scripted"

    def __init__(self, payload, model="scripted"):
        self._payload = payload
        self.model = model

    def complete(self, prompt, timeout_s=5.0):
        return LLMResponse(
            text=json.dumps(self._payload), provider=self.name, model=self.model
        )


# ---------------- types ----------------
def test_default_config_disabled():
    assert LLMConfig().enabled is False


def test_parsed_suggestion_defaults():
    p = ParsedSuggestion(decision="NO_TRADE", confidence=0.0, reasoning="")
    assert p.stop_loss is None and p.warnings == []


def test_live_guard_ok_when_disabled(monkeypatch):
    monkeypatch.delenv("LIVE_TRADING", raising=False)
    _live_guard()  # should not raise


def test_live_guard_raises_when_enabled(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING", "true")
    with pytest.raises(RuntimeError):
        _live_guard()


# ---------------- providers ----------------
def test_local_stub_returns_no_trade():
    parsed = parse_suggestion(LocalStubProvider().complete("x").text)
    assert parsed is not None and parsed.decision == "NO_TRADE"


def test_local_stub_accepts_model_kwarg():
    LocalStubProvider(model="m")  # must accept model


def test_local_stub_provider_name():
    assert LocalStubProvider.name == "local_stub"


def test_openai_gated_refuses_by_default():
    with pytest.raises(RuntimeError):
        OpenAIGatedProvider().complete("x")


def test_openai_gated_no_network_even_if_allowed():
    resp = OpenAIGatedProvider(allow_network=True).complete("x")
    assert resp.error is not None  # never performs a real call


def test_build_provider_local_stub():
    assert isinstance(build_provider("local_stub"), LocalStubProvider)


def test_build_provider_unknown_raises():
    with pytest.raises(ValueError):
        build_provider("nope")


def test_parse_suggestion_valid():
    p = parse_suggestion('{"decision":"BUY","confidence":0.5,"reasoning":"r","stop_loss":1.0}')
    assert p is not None and p.decision == "BUY" and p.stop_loss == 1.0


def test_parse_suggestion_invalid_json():
    assert parse_suggestion("not json") is None


def test_parse_suggestion_float_stop_loss():
    p = parse_suggestion('{"decision":"SELL","stop_loss":"1.2"}')
    assert p is not None and p.stop_loss == 1.2


def test_parse_suggestion_missing_keys():
    p = parse_suggestion("{}")
    assert p is not None and p.decision == "NO_TRADE" and p.confidence == 0.0


# ---------------- registry ----------------
def test_default_registry_has_local_stub():
    assert "local_stub" in get_provider_registry().names()


def test_default_registry_no_online_by_default():
    assert "openai_gated" not in get_provider_registry().names()


def test_register_and_get():
    reg = ProviderRegistry()
    reg.register("openai_gated", OpenAIGatedProvider)
    assert reg.get("openai_gated") is OpenAIGatedProvider


def test_build_provider_after_register():
    reg = ProviderRegistry()
    reg.register("openai_gated", OpenAIGatedProvider)
    assert isinstance(reg.get("openai_gated")(model="x"), OpenAIGatedProvider)


# ---------------- safety ----------------
def test_assert_paper_only_ok(monkeypatch):
    monkeypatch.delenv("LIVE_TRADING", raising=False)
    assert_paper_only()  # no raise


def test_assert_paper_only_raises(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING", "true")
    with pytest.raises(RuntimeError):
        assert_paper_only()


def test_gate_allows_no_trade():
    cfg = LLMConfig(allow_active_decisions=True, require_stop_loss_for_active=True)
    assert DecisionGate.gate("NO_TRADE", ParsedSuggestion("NO_TRADE", 0.0, ""), cfg)


def test_gate_blocks_active_when_disallowed():
    cfg = LLMConfig(allow_active_decisions=False, require_stop_loss_for_active=True)
    assert not DecisionGate.gate(
        "BUY", ParsedSuggestion("BUY", 0.5, "", stop_loss=1.0), cfg
    )


def test_gate_blocks_active_without_stop_loss():
    cfg = LLMConfig(allow_active_decisions=True, require_stop_loss_for_active=True)
    assert not DecisionGate.gate(
        "BUY", ParsedSuggestion("BUY", 0.5, "", stop_loss=None), cfg
    )


def test_gate_allows_active_with_stop_loss():
    cfg = LLMConfig(allow_active_decisions=True, require_stop_loss_for_active=True)
    assert DecisionGate.gate(
        "BUY", ParsedSuggestion("BUY", 0.5, "", stop_loss=1.0), cfg
    )


def test_gate_allows_active_when_stop_loss_not_required():
    cfg = LLMConfig(allow_active_decisions=True, require_stop_loss_for_active=False)
    assert DecisionGate.gate(
        "BUY", ParsedSuggestion("BUY", 0.5, "", stop_loss=None), cfg
    )


def test_contains_forbidden_detects():
    tok = next(t for t in forbidden_tokens() if t)
    found = contains_forbidden("ab" + tok + "cd")
    assert tok in found


def test_contains_forbidden_clean():
    assert contains_forbidden("clean paper-only analysis text") == []


# ---------------- formatters ----------------
def test_render_no_llm_brain():
    brains = build_brains(["quant", "market_structure", "risk", "devil_advocate"])
    rep = MultiBrainOrchestrator(brains).run(_md())
    out = render_llm_contribution(rep)
    assert "No LLM brain" in out


def test_render_with_llm_brain():
    brains = build_brains(["quant", "market_structure", "risk", "devil_advocate"])
    brains.append(LLMBrain(LLMConfig(enabled=False)))
    rep = MultiBrainOrchestrator(brains).run(_md())
    out = render_llm_contribution(rep)
    assert "llm" in out and "NO_TRADE" in out


# ---------------- brains/llm_base ----------------
def test_llm_brain_disabled_returns_no_trade():
    a = LLMBrain(LLMConfig(enabled=False)).analyze(_md())
    assert a.decision == "NO_TRADE" and a.confidence == 0.0


def test_llm_brain_enabled_local_stub_no_trade():
    a = LLMBrain(LLMConfig(enabled=True)).analyze(_md())
    assert a.decision == "NO_TRADE" and a.confidence == 0.0


def test_llm_brain_init_guard_raises(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING", "true")
    with pytest.raises(RuntimeError):
        LLMBrain(LLMConfig(enabled=True))


def test_llm_brain_provider_error_fallback():
    class Boom(LLMProvider):
        name = "boom"
        def complete(self, prompt, timeout_s=5.0):
            raise RuntimeError("boom")

    a = LLMBrain(LLMConfig(enabled=True), provider=Boom()).analyze(_md())
    assert a.decision == "NO_TRADE" and any("fallback" in w for w in a.warnings)


def test_llm_brain_unparsable_fallback():
    class Garbage(LLMProvider):
        name = "garbage"
        def complete(self, prompt, timeout_s=5.0):
            return LLMResponse(text="%%%", provider="garbage", model="g")

    a = LLMBrain(LLMConfig(enabled=True), provider=Garbage()).analyze(_md())
    assert a.decision == "NO_TRADE"


def test_llm_brain_active_allowed_with_stop_loss():
    p = ScriptedProvider({"decision": "BUY", "confidence": 0.8, "reasoning": "r", "stop_loss": 100.0})
    a = LLMBrain(LLMConfig(enabled=True, allow_active_decisions=True), provider=p).analyze(_md())
    assert a.decision == "BUY" and a.confidence == 0.8


def test_llm_brain_active_blocked_no_stop_loss():
    p = ScriptedProvider({"decision": "BUY", "confidence": 0.8, "reasoning": "r", "stop_loss": None})
    a = LLMBrain(
        LLMConfig(enabled=True, allow_active_decisions=True, require_stop_loss_for_active=True),
        provider=p,
    ).analyze(_md())
    assert a.decision == "NO_TRADE"


def test_llm_brain_active_blocked_when_disallowed():
    p = ScriptedProvider({"decision": "BUY", "confidence": 0.8, "reasoning": "r", "stop_loss": 100.0})
    a = LLMBrain(LLMConfig(enabled=True, allow_active_decisions=False), provider=p).analyze(_md())
    assert a.decision == "NO_TRADE"


def test_llm_brain_confidence_clamped():
    p = ScriptedProvider({"decision": "BUY", "confidence": 5.0, "reasoning": "r", "stop_loss": 1.0})
    a = LLMBrain(LLMConfig(enabled=True, allow_active_decisions=True), provider=p).analyze(_md())
    assert a.confidence == 1.0


def test_build_llm_brain_helper():
    assert isinstance(build_llm_brain(LLMConfig(enabled=False)), LLMBrain)


# ---------------- brains/llm_stub ----------------
def test_llm_stub_always_no_trade():
    a = LLMStubBrain().analyze(_md())
    assert a.decision == "NO_TRADE" and a.brain_name == "llm_stub"


def test_llm_stub_confidence():
    a = LLMStubBrain(confidence=0.3).analyze(_md())
    assert a.confidence == 0.3


# ---------------- integration ----------------
def test_inject_llm_into_orchestrator():
    brains = build_brains(["quant", "market_structure", "risk", "devil_advocate"])
    brains += [LLMBrain(LLMConfig(enabled=False)), LLMStubBrain()]
    rep = MultiBrainOrchestrator(brains).run(_md())
    names = [r.brain_name for r in rep.brain_results]
    assert "llm" in names and "llm_stub" in names


def test_full_report_has_llm_contribution():
    brains = build_brains(["quant", "market_structure", "risk", "devil_advocate"])
    brains.append(LLMBrain(LLMConfig(enabled=False)))
    rep = MultiBrainOrchestrator(brains).run(_md())
    out = render_llm_contribution(rep)
    assert "LLM contribution" in out


# ---------------- self-scan for forbidden literals ----------------
def test_no_forbidden_tokens_in_new_files():
    import glob

    files = (
        glob.glob("crypto_quant_ai/backend/llm/*.py")
        + glob.glob("crypto_quant_ai/backend/brains/llm_*.py")
        + ["crypto_quant_ai/backend/tests/test_stage10_llm.py",
           "crypto_quant_ai/docs/stage10-llm-adapter.md"]
    )
    toks = forbidden_tokens()
    bad = []
    for f in files:
        try:
            txt = open(f, encoding="utf-8").read()
        except FileNotFoundError:
            continue
        for t in toks:
            if t and t in txt:
                bad.append((f, t))
    assert bad == [], f"forbidden tokens found: {bad}"
