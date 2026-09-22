from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
import json

import pytest
from fastapi.testclient import TestClient

api_app_module = importlib.import_module("crypto_quant_ai.backend.api.app")
from crypto_quant_ai.backend.api.app import app
from crypto_quant_ai.backend.brains.base import BrainBase
from crypto_quant_ai.backend.core.models import BrainAnalysis
from crypto_quant_ai.backend.data.ohlcv import OHLCVBar
from crypto_quant_ai.backend.gateway import GatewayConfig, RiskManagerConfig
from crypto_quant_ai.backend.gateway import compute_gateway_hash
from crypto_quant_ai.backend.intelligence import (
    DecisionBrief,
    IntelligenceReport,
    MarketState,
    Regime,
    ResearchReport,
    build_intelligence_report,
)
from crypto_quant_ai.backend.orchestration import (
    Stage13Orchestrator,
    Stage13Report,
    Stage13Request,
    Stage13RequestSummary,
    default_stage13_committee_config,
    render_csv,
    render_json,
    render_markdown,
    report_to_dict,
)
from crypto_quant_ai.backend.orchestration.types import (
    Stage13ExecutionResult,
    Stage13MarketContext,
    stage13_hash,
)
from crypto_quant_ai.backend.evidence import EvidenceCollector, EvidenceVerifier


class ScriptedBrain(BrainBase):
    def __init__(self, name: str, decision: str, confidence: float, reasoning: str = "ok"):
        self.name = name
        self._decision = decision
        self._confidence = confidence
        self._reasoning = reasoning

    def analyze(self, market_data):
        return BrainAnalysis(
            brain_name=self.name,
            decision=self._decision,
            confidence=self._confidence,
            reasoning=self._reasoning,
            warnings=[],
        )


class FakeIntelligenceOrchestrator:
    def __init__(self, report: IntelligenceReport):
        self._report = report

    def analyze(self, candles, **kwargs):
        return self._report


class DummyStage13Orchestrator:
    def __init__(self, report: Stage13Report):
        self._report = report

    def run(self, request):
        return self._report



def make_candles(n: int = 120, trend: float = 0.004, noise: float = 0.002, start: float = 100.0):
    bars = []
    price = start
    for i in range(n):
        jitter = noise * ((i % 5) - 2) / 10.0
        ret = trend + jitter
        price = price * (1.0 + ret)
        o = price * 0.998
        h = max(o, price) * 1.003
        l = min(o, price) * 0.997
        v = 1000.0 + 10.0 * i
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
        bars.append(OHLCVBar(timestamp=ts, open=o, high=h, low=l, close=price, volume=v))
    return bars



def make_intelligence_report(
    *,
    action: str = "BUY",
    decision_confidence: float = 0.9,
    stability: float = 0.9,
    overfit_flags: list[str] | None = None,
    recommendation: str = "stable paper trade plan",
    total_return_pct: float = 12.0,
) -> IntelligenceReport:
    market_state = MarketState(
        Regime.TREND,
        0.85,
        {"trend_strength": 0.8},
        "trending regime",
    )
    decision = DecisionBrief(
        action=action,
        confidence=decision_confidence,
        supporters=["quant", "market_structure"],
        opponents=[],
        rationale="api_key=abc should be hidden",
        failure_conditions=[],
        alternatives=["wait"],
    )
    research = ResearchReport(
        objective="sharpe_ratio",
        candidates_count=4,
        completed_count=4,
        best_params={"short_window": 5.0, "long_window": 15.0},
        best_metrics={
            "sharpe_ratio": 1.4,
            "total_return_pct": total_return_pct,
            "max_drawdown_pct": 0.05,
        },
        robustness={"stability_score": stability},
        sensitivity=[],
        overfit_flags=list(overfit_flags or []),
        stability_score=stability,
    )
    return build_intelligence_report(
        symbol="BTC/USDT",
        market_state=market_state,
        decision=decision,
        research=research,
        recommendation=recommendation,
        risk_notes=["token-secret should be hidden"],
    )



def make_dummy_report() -> Stage13Report:
    collector = EvidenceCollector(stability_threshold=0.7)
    evidence = collector.collect(
        intelligence_report={"decision": "BUY", "stability": 0.9, "overfit_flags": []},
        committee_verdict={
            "final_decision": "BUY",
            "confidence": 0.9,
            "quorum_met": True,
            "conflict": False,
        },
        model_contributions=[{"model_name": "quant", "decision": "BUY", "confidence": 0.9}],
        replay_metrics={"stability": 0.9, "pnl": 1.0, "drawdown": 0.02},
    )
    verification = EvidenceVerifier(min_items=2).verify(evidence)
    intelligence = make_intelligence_report()
    final_decision = api_app_module.Stage13Orchestrator(
        models=[ScriptedBrain("quant", "BUY", 0.9), ScriptedBrain("risk", "BUY", 0.8)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(intelligence),
    ).run(Stage13Request(candles=make_candles())).result.final_decision
    report = Stage13Report(
        request=Stage13RequestSummary(
            symbol="BTC/USDT",
            timeframe="15m",
            candles_count=120,
            timeframes=[20, 50, 100],
            committee_fusion=default_stage13_committee_config().fusion.value,
            gateway_hash="dummy",
        ),
        market_context=Stage13MarketContext(
            symbol="BTC/USDT",
            timeframe="15m",
            candles_count=120,
            first_timestamp="2024-01-01T00:00:00+00:00",
            last_timestamp="2024-01-05T23:00:00+00:00",
            last_close=123.45,
        ),
        intelligence=intelligence,
        committee_verdict=api_app_module.Stage13Orchestrator(
            models=[ScriptedBrain("quant", "BUY", 0.9), ScriptedBrain("risk", "BUY", 0.8)],
            intelligence_orchestrator=FakeIntelligenceOrchestrator(intelligence),
        ).run(Stage13Request(candles=make_candles())).committee_verdict,
        evidence=evidence,
        verification=verification,
        contradictions=[],
        result=Stage13ExecutionResult(
            verification_passed=True,
            gateway_allowed=True,
            executed=True,
            blocked=False,
            block_reason="",
            final_decision=final_decision,
            gateway_result=None,
        ),
        gateway_report=None,
    )
    report.report_hash = stage13_hash(report_to_dict(report))
    return report



def test_stage13_executes_when_verification_passes():
    intelligence = make_intelligence_report()
    orch = Stage13Orchestrator(
        models=[
            ScriptedBrain("quant", "BUY", 0.95),
            ScriptedBrain("market_structure", "BUY", 0.90),
        ],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(intelligence),
    )
    report = orch.run(Stage13Request(candles=make_candles()))
    assert report.result.verification_passed is True
    assert report.result.gateway_allowed is True
    assert report.result.executed is True
    assert report.result.blocked is False
    assert report.result.gateway_result is not None and report.result.gateway_result.executed
    assert report.gateway_report is not None and report.gateway_report.total_executed == 1
    assert report.result.final_decision.stop_loss is not None
    assert report.result.final_decision.take_profit is not None



def test_stage13_fail_closed_on_unstable_evidence():
    intelligence = make_intelligence_report(stability=0.2, overfit_flags=["wf_gap"])
    orch = Stage13Orchestrator(
        models=[ScriptedBrain("quant", "BUY", 0.95), ScriptedBrain("risk", "BUY", 0.8)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(intelligence),
    )
    report = orch.run(Stage13Request(candles=make_candles()))
    assert report.result.verification_passed is False
    assert report.result.gateway_allowed is False
    assert report.result.executed is False
    assert report.result.blocked is True
    assert report.result.gateway_result is None
    assert "low stability" in report.result.block_reason or "contradictions" in report.result.block_reason



def test_stage13_blocks_when_committee_returns_no_trade():
    intelligence = make_intelligence_report(action="BUY", stability=0.95)
    orch = Stage13Orchestrator(
        models=[ScriptedBrain("quant", "BUY", 0.9), ScriptedBrain("risk", "SELL", 0.9)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(intelligence),
    )
    report = orch.run(Stage13Request(candles=make_candles()))
    assert report.committee_verdict.final_decision == "NO_TRADE"
    assert report.result.final_decision.decision == "NO_TRADE"
    assert report.result.gateway_allowed is False
    assert report.result.executed is False
    assert report.result.blocked is True



def test_stage13_reports_gateway_rejection():
    intelligence = make_intelligence_report(decision_confidence=0.85)
    cfg = GatewayConfig(risk_manager=RiskManagerConfig(min_confidence=0.95))
    orch = Stage13Orchestrator(
        models=[ScriptedBrain("quant", "BUY", 0.9), ScriptedBrain("risk", "BUY", 0.9)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(intelligence),
    )
    report = orch.run(Stage13Request(candles=make_candles(), gateway_config=cfg))
    assert report.result.verification_passed is True
    assert report.result.gateway_allowed is True
    assert report.result.executed is False
    assert report.result.blocked is True
    assert report.result.gateway_result is not None
    assert "Risk gate rejected" in report.result.block_reason



def test_stage13_report_formats_redact_sensitive_values():
    intelligence = make_intelligence_report(recommendation="token-secret should be hidden")
    orch = Stage13Orchestrator(
        models=[ScriptedBrain("quant", "BUY", 0.95, "api_key=abc should be hidden"), ScriptedBrain("risk", "BUY", 0.9)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(intelligence),
    )
    report = orch.run(Stage13Request(candles=make_candles()))
    js = render_json(report)
    md = render_markdown(report)
    csv_text = render_csv(report)
    assert "token-secret should be hidden" not in js
    assert "token-secret should be hidden" not in md
    assert "token-secret should be hidden" not in csv_text
    assert "api_key=abc should be hidden" not in js
    payload = json.loads(js)
    assert payload["result"]["executed"] is True



def test_stage13_live_guard(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING", "true")
    with pytest.raises(RuntimeError):
        Stage13Orchestrator()



def test_stage13_api_endpoint(monkeypatch):
    dummy_report = make_dummy_report()
    monkeypatch.setattr(
        api_app_module,
        "Stage13Orchestrator",
        lambda: DummyStage13Orchestrator(dummy_report),
    )
    client = TestClient(app)
    candles = [
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000.0,
        },
        {
            "timestamp": "2024-01-01T01:00:00Z",
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1010.0,
        },
    ]
    response = client.post(
        "/stage13/run",
        json={"symbol": "BTC/USDT", "timeframe": "15m", "candles": candles},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["request"]["symbol"] == "BTC/USDT"
    assert "result" in payload and "market_context" in payload


def test_stage13_api_request_syncs_gateway_config():
    request = api_app_module.Stage13ApiRequest(
        symbol="ETH/USDT",
        timeframe="1h",
        candles=make_candles(5),
        timeframes=[10, 20],
    ).to_request()
    assert request.gateway_config.symbol == "ETH/USDT"
    assert request.gateway_config.timeframe == "1h"

    intelligence = make_intelligence_report()
    orch = Stage13Orchestrator(
        models=[ScriptedBrain("quant", "BUY", 0.9), ScriptedBrain("risk", "BUY", 0.8)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(intelligence),
    )
    report = orch.run(request)
    assert report.request.gateway_hash == compute_gateway_hash(
        GatewayConfig(symbol="ETH/USDT", timeframe="1h")
    )


def test_stage13_api_invalid_candles_return_422():
    client = TestClient(app)
    bad = [
        {
            "timestamp": "2024-01-01T01:00:00Z",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000.0,
        },
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1010.0,
        },
    ]
    response = client.post(
        "/stage13/run",
        json={"symbol": "BTC/USDT", "timeframe": "15m", "candles": bad},
    )
    assert response.status_code == 422
    assert "strictly increasing" in response.json()["detail"]


def test_stage13_api_endpoint_real_example_succeeds():
    client = TestClient(app)
    candles = [
        {
            "timestamp": candle.timestamp.isoformat(),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in make_candles(120)
    ]
    response = client.post(
        "/stage13/run",
        json={"symbol": "BTC/USDT", "timeframe": "15m", "candles": candles},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["request"]["symbol"] == "BTC/USDT"
    assert "result" in payload
