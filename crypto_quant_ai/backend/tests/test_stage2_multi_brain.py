from __future__ import annotations

import pytest

from crypto_quant_ai.backend.brains import (
    DevilsAdvocateBrain,
    MarketStructureBrain,
    QuantBrain,
    RiskManagerBrain,
)
from crypto_quant_ai.backend.core.models import BrainAnalysis, MarketData
from crypto_quant_ai.backend.decision.brain_orchestrator import (
    BrainResult,
    MultiBrainOrchestrator,
    OrchestratorReport,
)


def sample_market_data() -> MarketData:
    return MarketData(
        symbol="BTC/USDT",
        timestamp="2024-01-01T00:00:00Z",
        open=40000.0,
        high=41000.0,
        low=39500.0,
        close=40500.0,
        volume=100.0,
        timeframe="15m",
    )


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------


class MockBrain:
    """Minimal BrainBase-compatible mock that returns a fixed BrainAnalysis."""

    def __init__(self, name: str, decision: str, confidence: float, reasoning: str = "") -> None:
        self.name = name
        self._decision = decision
        self._confidence = confidence
        self._reasoning = reasoning

    def analyze(self, market_data: MarketData) -> BrainAnalysis:
        return BrainAnalysis(
            brain_name=self.name,
            decision=self._decision,
            confidence=self._confidence,
            reasoning=self._reasoning,
            warnings=[],
        )


# ---------------------------------------------------------------------------
# OrchestratorReport helpers
# ---------------------------------------------------------------------------


def test_report_unanimous_buy() -> None:
    results = [
        BrainResult("b1", BrainAnalysis(brain_name="b1", decision="BUY", confidence=0.7)),
        BrainResult("b2", BrainAnalysis(brain_name="b2", decision="BUY", confidence=0.6)),
        BrainResult("b3", BrainAnalysis(brain_name="b3", decision="HOLD", confidence=0.5)),
    ]
    report = OrchestratorReport(
        symbol="BTC/USDT",
        timeframe="15m",
        brain_results=results,
        final_decision=None,
    )
    assert report.unanimous_buy is False
    assert report.vote_summary == {"BUY": 2, "HOLD": 1}


def test_report_unanimous_sell() -> None:
    results = [
        BrainResult("b1", BrainAnalysis(brain_name="b1", decision="SELL", confidence=0.7)),
        BrainResult("b2", BrainAnalysis(brain_name="b2", decision="SELL", confidence=0.6)),
    ]
    report = OrchestratorReport(
        symbol="BTC/USDT",
        timeframe="15m",
        brain_results=results,
        final_decision=None,
    )
    assert report.unanimous_sell is True


# ---------------------------------------------------------------------------
# MultiBrainOrchestrator.run()
# ---------------------------------------------------------------------------


def test_single_brain_no_trade() -> None:
    orch = MultiBrainOrchestrator([MockBrain("mock", "NO_TRADE", 0.5)])
    data = sample_market_data()
    report = orch.run(data)
    assert report.final_decision.decision == "NO_TRADE"


def test_two_buy_votes_triggers_buy() -> None:
    orch = MultiBrainOrchestrator([
        MockBrain("mock1", "BUY", 0.70),
        MockBrain("mock2", "BUY", 0.65),
        MockBrain("mock3", "HOLD", 0.50),
    ])
    report = orch.run(sample_market_data())
    assert report.final_decision.decision == "BUY"


def test_two_sell_votes_triggers_sell() -> None:
    orch = MultiBrainOrchestrator([
        MockBrain("mock1", "SELL", 0.70),
        MockBrain("mock2", "SELL", 0.65),
    ])
    report = orch.run(sample_market_data())
    assert report.final_decision.decision == "SELL"


def test_no_majority_no_trade() -> None:
    orch = MultiBrainOrchestrator([
        MockBrain("mock1", "BUY", 0.60),
        MockBrain("mock2", "SELL", 0.60),
        MockBrain("mock3", "NO_TRADE", 0.50),
    ])
    report = orch.run(sample_market_data())
    assert report.final_decision.decision == "NO_TRADE"


def test_single_buy_does_not_trigger() -> None:
    orch = MultiBrainOrchestrator([
        MockBrain("mock1", "BUY", 0.70),
        MockBrain("mock2", "NO_TRADE", 0.50),
    ])
    report = orch.run(sample_market_data())
    assert report.final_decision.decision == "NO_TRADE"


def test_latency_reported() -> None:
    orch = MultiBrainOrchestrator([MockBrain("mock", "NO_TRADE", 0.5)])
    report = orch.run(sample_market_data())
    assert report.total_latency_ms is not None
    assert report.total_latency_ms >= 0


def test_all_real_brains_import_and_run() -> None:
    """Verify all Stage 1 brains can be used inside the orchestrator."""
    brains = [
        MarketStructureBrain(),
        QuantBrain(),
        RiskManagerBrain(),
        DevilsAdvocateBrain(),
    ]
    orch = MultiBrainOrchestrator(brains)
    report = orch.run(sample_market_data())
    assert len(report.brain_results) == 4
    assert all(r.latency_ms is not None for r in report.brain_results)


def test_vote_summary_counts_correctly() -> None:
    orch = MultiBrainOrchestrator([
        MockBrain("b1", "BUY", 0.7),
        MockBrain("b2", "BUY", 0.6),
        MockBrain("b3", "SELL", 0.7),
    ])
    report = orch.run(sample_market_data())
    assert report.vote_summary == {"BUY": 2, "SELL": 1}


def test_empty_brains_raises() -> None:
    with pytest.raises(ValueError, match="At least one brain"):
        MultiBrainOrchestrator([])


def test_report_final_decision_has_correct_symbol() -> None:
    orch = MultiBrainOrchestrator([MockBrain("mock", "NO_TRADE", 0.5)])
    report = orch.run(sample_market_data())
    assert report.final_decision.symbol == "BTC/USDT"
    assert report.final_decision.timeframe == "15m"
