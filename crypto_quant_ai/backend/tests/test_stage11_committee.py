from __future__ import annotations

import os

import pytest

from crypto_quant_ai.backend.brains.base import BrainBase
from crypto_quant_ai.backend.brains.llm_stub import LLMStubBrain
from crypto_quant_ai.backend.committee import (
    CommitteeVerdict,
    FusionStrategy,
    ModelCommittee,
    ModelCommitteeConfig,
    render_committee_report,
)
from crypto_quant_ai.backend.committee.fusions import (
    consensus_quorum,
    simple_majority,
    unanimous,
    weighted_majority,
)
from crypto_quant_ai.backend.committee.policy import gate_active
from crypto_quant_ai.backend.committee.types import ModelContribution
from crypto_quant_ai.backend.core.models import BrainAnalysis, MarketData
from crypto_quant_ai.backend.intelligence.market_state import (
    MarketState,
    Regime,
    classify_regime,
)
from crypto_quant_ai.backend.llm.safety import forbidden_tokens
from crypto_quant_ai.backend.replay.registry import build_brains


class ScriptedBrain(BrainBase):
    def __init__(self, name, decision, confidence=0.5, reasoning="", warnings=None):
        self.name = name
        self._decision = decision
        self._confidence = confidence
        self._reasoning = reasoning
        self._warnings = warnings or []

    def analyze(self, market_data):
        return BrainAnalysis(
            brain_name=self.name,
            decision=self._decision,
            confidence=self._confidence,
            reasoning=self._reasoning,
            warnings=self._warnings,
        )


def _md():
    return MarketData(
        symbol="BTC", timestamp="2024-01-01T00:00:00", open=1.0, high=2.0,
        low=0.5, close=1.5, volume=10.0, timeframe="15m",
    )


# ---------------- fusions ----------------
def _c(name, decision, confidence):
    return ModelContribution(name, decision, confidence)


def test_weighted_buy_wins():
    d, conf, conflict, quorum = weighted_majority(
        [_c("a", "BUY", 0.8), _c("b", "BUY", 0.6), _c("c", "NO_TRADE", 0.1)], quorum=2
    )
    assert d == "BUY" and quorum and not conflict and conf > 0.0


def test_weighted_sell_wins():
    d, conf, conflict, quorum = weighted_majority(
        [_c("a", "SELL", 0.9), _c("b", "BUY", 0.2)], quorum=2
    )
    assert d == "SELL"


def test_weighted_conflict_flag():
    _, _, conflict, _ = weighted_majority(
        [_c("a", "BUY", 0.9), _c("b", "SELL", 0.9)], quorum=2
    )
    assert conflict is True


def test_simple_majority_buy():
    d, _, _, quorum = simple_majority([_c("a", "BUY", 0.5), _c("b", "BUY", 0.5)], quorum=2)
    assert d == "BUY" and quorum


def test_simple_majority_single_buy_no_quorum():
    d, _, _, quorum = simple_majority([_c("a", "BUY", 0.5)], quorum=2)
    assert d == "NO_TRADE" and not quorum


def test_unanimous_agree():
    d, conf, conflict, quorum = unanimous([_c("a", "BUY", 0.7), _c("b", "BUY", 0.5)], quorum=2)
    assert d == "BUY" and not conflict and quorum


def test_unanimous_disagree_fails_closed():
    d, _, conflict, quorum = unanimous([_c("a", "BUY", 0.7), _c("b", "SELL", 0.5)], quorum=2)
    assert d == "NO_TRADE" and conflict and not quorum


def test_consensus_quorum_met():
    d, _, conflict, quorum = consensus_quorum(
        [_c("a", "BUY", 0.7), _c("b", "BUY", 0.6), _c("c", "NO_TRADE", 0.1)], quorum=2
    )
    assert d == "BUY" and quorum


def test_consensus_quorum_not_met():
    d, _, _, quorum = consensus_quorum([_c("a", "BUY", 0.7)], quorum=2)
    assert d == "NO_TRADE" and not quorum


def test_long_short_normalized():
    d, _, _, _ = weighted_majority([_c("a", "LONG", 0.9), _c("b", "SHORT", 0.8)], quorum=2)
    assert d in ("BUY", "SELL")


# ---------------- policy ----------------
def test_gate_blocks_active_when_disallowed():
    cfg = ModelCommitteeConfig(allow_active_decisions=False)
    assert gate_active("BUY", cfg) is False


def test_gate_allows_active_when_allowed():
    cfg = ModelCommitteeConfig(allow_active_decisions=True)
    assert gate_active("BUY", cfg) is True


# ---------------- committee ----------------
def test_committee_default_buy_with_quorum():
    models = [ScriptedBrain("a", "BUY", 0.8), ScriptedBrain("b", "BUY", 0.6)]
    v = ModelCommittee(models).evaluate(_md())
    assert v.final_decision == "BUY" and v.quorum_met and not v.conflict


def test_committee_single_buy_fails_closed():
    v = ModelCommittee([ScriptedBrain("a", "BUY", 0.9)]).evaluate(_md())
    assert v.final_decision == "NO_TRADE"


def test_committee_conflict_fail_closed():
    models = [ScriptedBrain("a", "BUY", 0.9), ScriptedBrain("b", "SELL", 0.9)]
    v = ModelCommittee(models, ModelCommitteeConfig(fail_closed=True)).evaluate(_md())
    assert v.final_decision == "NO_TRADE" and v.conflict


def test_committee_conflict_not_fail_closed_uses_weighted():
    models = [ScriptedBrain("a", "BUY", 0.9), ScriptedBrain("b", "SELL", 0.4)]
    v = ModelCommittee(
        models, ModelCommitteeConfig(fail_closed=False, fusion=FusionStrategy.WEIGHTED_MAJORITY)
    ).evaluate(_md())
    assert v.final_decision == "BUY"


def test_committee_model_error_is_fail_closed():
    class Boom(BrainBase):
        name = "boom"
        def analyze(self, md):
            raise RuntimeError("boom")

    v = ModelCommittee([Boom(), ScriptedBrain("b", "BUY", 0.9)]).evaluate(_md())
    names = [c.model_name for c in v.contributions]
    assert "boom" in names
    assert v.final_decision == "NO_TRADE"


def test_committee_active_blocked_by_policy():
    models = [ScriptedBrain("a", "BUY", 0.9), ScriptedBrain("b", "BUY", 0.8)]
    v = ModelCommittee(
        models, ModelCommitteeConfig(allow_active_decisions=False)
    ).evaluate(_md())
    assert v.final_decision == "NO_TRADE"


def test_committee_active_allowed_by_policy():
    models = [ScriptedBrain("a", "BUY", 0.9), ScriptedBrain("b", "BUY", 0.8)]
    v = ModelCommittee(
        models, ModelCommitteeConfig(allow_active_decisions=True)
    ).evaluate(_md())
    assert v.final_decision == "BUY"


def test_committee_unanimous_strategy():
    models = [ScriptedBrain("a", "SELL", 0.7), ScriptedBrain("b", "SELL", 0.6)]
    v = ModelCommittee(
        models, ModelCommitteeConfig(fusion=FusionStrategy.UNANIMOUS, quorum=2)
    ).evaluate(_md())
    assert v.final_decision == "SELL"


def test_committee_weights_applied():
    models = [
        ScriptedBrain("strong", "BUY", 1.0),
        ScriptedBrain("weak", "SELL", 0.1),
    ]
    v = ModelCommittee(
        models,
        ModelCommitteeConfig(
            fusion=FusionStrategy.WEIGHTED_MAJORITY,
            weights={"strong": 5.0, "weak": 1.0},
            fail_closed=False,
        ),
    ).evaluate(_md())
    assert v.final_decision == "BUY"


def test_committee_routing_filters_by_regime():
    state = MarketState(Regime.HIGH_VOL, 0.9, {}, "high vol")
    models = [
        ScriptedBrain("quant", "BUY", 0.5),
        ScriptedBrain("risk", "NO_TRADE", 0.1),
        ScriptedBrain("devil_advocate", "NO_TRADE", 0.1),
        ScriptedBrain("llm_stub", "NO_TRADE", 0.1),
    ]
    v = ModelCommittee(
        models, ModelCommitteeConfig(routing=True)
    ).evaluate(_md(), market_state=state)
    kept = v.routing.get("kept")
    assert v.routing.get("enabled") is True
    # HIGH_VOL keeps risk/devil_advocate/llm -> quant excluded
    assert "quant" not in kept


def test_committee_routing_safety_keeps_all_when_few():
    state = MarketState(Regime.UNKNOWN, 0.0, {}, "unknown")
    models = [ScriptedBrain("quant", "BUY", 0.5), ScriptedBrain("risk", "NO_TRADE", 0.1)]
    v = ModelCommittee(
        models, ModelCommitteeConfig(routing=True)
    ).evaluate(_md(), market_state=state)
    assert v.routing.get("kept") == "all(unknown)"


def test_committee_requires_models():
    with pytest.raises(ValueError):
        ModelCommittee([])


def test_committee_to_final_decision():
    models = [ScriptedBrain("a", "BUY", 0.8), ScriptedBrain("b", "BUY", 0.6)]
    v = ModelCommittee(models).evaluate(_md())
    fd = ModelCommittee(models).to_final_decision(_md(), v)
    assert fd.decision == "BUY" and fd.symbol == "BTC"


def test_committee_with_real_brains_no_error():
    brains = build_brains(["quant", "market_structure", "risk", "devil_advocate"])
    brains += [LLMStubBrain()]
    v = ModelCommittee(brains).evaluate(_md())
    assert isinstance(v, CommitteeVerdict)
    assert len(v.contributions) == 5


def test_render_committee_report():
    models = [ScriptedBrain("a", "BUY", 0.8), ScriptedBrain("b", "BUY", 0.6)]
    v = ModelCommittee(models).evaluate(_md())
    out = render_committee_report(v)
    assert "Model Committee Verdict" in out and "BUY" in out


def test_live_guard_tripped():
    os.environ["LIVE_TRADING"] = "true"
    try:
        with pytest.raises(RuntimeError):
            from crypto_quant_ai.backend.committee import ModelCommittee as _MC
            _MC([ScriptedBrain("a", "NO_TRADE", 0.0)])
    finally:
        os.environ.pop("LIVE_TRADING", None)


# ---------------- self-scan: no forbidden literals ----------------
def test_no_forbidden_tokens_in_committee():
    import glob

    files = (
        glob.glob("crypto_quant_ai/backend/committee/*.py")
        + ["crypto_quant_ai/backend/tests/test_stage11_committee.py",
           "crypto_quant_ai/docs/stage11-model-committee.md"]
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
