from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

api_app_module = importlib.import_module("crypto_quant_ai.backend.api.app")
from crypto_quant_ai.backend.api.app import app
from crypto_quant_ai.backend.brains.base import BrainBase
from crypto_quant_ai.backend.core.models import BrainAnalysis
from crypto_quant_ai.backend.data.ohlcv import OHLCVBar
from crypto_quant_ai.backend.gateway import GatewayConfig, RiskManagerConfig, CircuitBreakerConfig
from crypto_quant_ai.backend.intelligence import (
    DecisionBrief,
    IntelligenceReport,
    MarketState,
    Regime,
    ResearchReport,
    build_intelligence_report,
)
from crypto_quant_ai.backend.orchestration import Stage13Orchestrator, Stage14SessionManager
from crypto_quant_ai.backend.orchestration.session_store import LocalSessionStore
from crypto_quant_ai.backend.orchestration.session_types import (
    Stage14SessionOpenRequest,
    Stage14SessionRunRequest,
)


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


class DummyStage14Manager:
    def __init__(self, session_view, report):
        self._session_view = session_view
        self._report = report

    def open_session(self, config):
        return self._session_view

    def get_session(self, session_id):
        return self._session_view

    def run_session(self, session_id, request):
        return self._report

    def get_history(self, session_id):
        return [{"run_id": "abc", "executed": False}]

    def export_history_csv(self, session_id):
        return "run_id,executed\nabc,False\n"



def make_candles(n: int = 120, trend: float = 0.004, start: float = 100.0):
    bars = []
    price = start
    for i in range(n):
        price = price * (1.0 + trend)
        o = price * 0.998
        h = max(o, price) * 1.003
        l = min(o, price) * 0.997
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
        bars.append(OHLCVBar(timestamp=ts, open=o, high=h, low=l, close=price, volume=1000.0 + i))
    return bars



def make_intelligence_report(
    *,
    action: str,
    stability: float = 0.95,
    recommendation: str = "stable plan",
    total_return_pct: float = 10.0,
) -> IntelligenceReport:
    return build_intelligence_report(
        symbol="BTC/USDT",
        market_state=MarketState(Regime.TREND, 0.9, {"trend_strength": 0.8}, "trend"),
        decision=DecisionBrief(
            action=action,
            confidence=0.9,
            supporters=["quant"],
            opponents=[],
            rationale="ok",
            failure_conditions=[],
            alternatives=["wait"],
        ),
        research=ResearchReport(
            objective="sharpe_ratio",
            candidates_count=4,
            completed_count=4,
            best_params={"short_window": 5.0},
            best_metrics={
                "sharpe_ratio": 1.2,
                "total_return_pct": total_return_pct,
                "max_drawdown_pct": 0.05,
            },
            robustness={"stability_score": stability},
            sensitivity=[],
            overfit_flags=[],
            stability_score=stability,
        ),
        recommendation=recommendation,
        risk_notes=[],
    )



def make_manager(tmp_path):
    store = LocalSessionStore(str(tmp_path))
    return Stage14SessionManager(store=store)



def test_stage14_create_and_reload_session(tmp_path):
    manager = make_manager(tmp_path)
    view1 = manager.open_session(GatewayConfig(symbol="BTC/USDT", timeframe="15m"))
    view2 = manager.get_session(view1.session_id)
    assert view1.session_id == view2.session_id
    assert view2.account.cash == 100000.0
    assert view2.history_length == 0



def test_stage14_buy_then_sell_persists_across_runs(tmp_path):
    manager = make_manager(tmp_path)
    view = manager.open_session(GatewayConfig(symbol="BTC/USDT", timeframe="15m"))

    buy_orch = Stage13Orchestrator(
        models=[ScriptedBrain("quant", "BUY", 0.95), ScriptedBrain("risk", "BUY", 0.9)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(make_intelligence_report(action="BUY")),
    )
    buy_report = manager.run_session(
        view.session_id,
        Stage14SessionRunRequest(candles=make_candles(120, trend=0.004, start=100.0)),
        orchestrator=buy_orch,
    )
    assert buy_report.result.executed is True

    manager2 = make_manager(tmp_path)
    sell_orch = Stage13Orchestrator(
        models=[ScriptedBrain("quant", "SELL", 0.95), ScriptedBrain("risk", "SELL", 0.9)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(make_intelligence_report(action="SELL", recommendation="sell")),
    )
    sell_report = manager2.run_session(
        view.session_id,
        Stage14SessionRunRequest(candles=make_candles(120, trend=-0.001, start=95.0)),
        orchestrator=sell_orch,
    )
    assert sell_report.result.executed is True
    restored = manager2.get_session(view.session_id)
    assert restored.history_length == 2
    assert "BTC/USDT" not in restored.account.positions



def test_stage14_breaker_state_persists(tmp_path):
    manager = make_manager(tmp_path)
    cfg = GatewayConfig(
        symbol="BTC/USDT",
        timeframe="15m",
        circuit_breaker=CircuitBreakerConfig(daily_loss_limit=10.0),
    )
    view = manager.open_session(cfg)
    buy_orch = Stage13Orchestrator(
        models=[ScriptedBrain("quant", "BUY", 0.95), ScriptedBrain("risk", "BUY", 0.9)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(make_intelligence_report(action="BUY")),
    )
    manager.run_session(
        view.session_id,
        Stage14SessionRunRequest(candles=make_candles(120, trend=0.0, start=100.0)),
        orchestrator=buy_orch,
    )
    sell_orch = Stage13Orchestrator(
        models=[ScriptedBrain("quant", "SELL", 0.95), ScriptedBrain("risk", "SELL", 0.9)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(make_intelligence_report(action="SELL", recommendation="sell")),
    )
    manager.run_session(
        view.session_id,
        Stage14SessionRunRequest(candles=make_candles(120, trend=0.0, start=90.0)),
        orchestrator=sell_orch,
    )
    blocked_orch = Stage13Orchestrator(
        models=[ScriptedBrain("quant", "BUY", 0.95), ScriptedBrain("risk", "BUY", 0.9)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(make_intelligence_report(action="BUY")),
    )
    blocked = manager.run_session(
        view.session_id,
        Stage14SessionRunRequest(candles=make_candles(120, trend=0.0, start=91.0)),
        orchestrator=blocked_orch,
    )
    assert blocked.result.executed is False
    assert "daily loss" in blocked.result.block_reason or "drawdown" in blocked.result.block_reason



def test_stage14_invalid_restore_raises(tmp_path):
    manager = make_manager(tmp_path)
    view = manager.open_session(GatewayConfig(symbol="BTC/USDT", timeframe="15m"))
    path = LocalSessionStore(str(tmp_path)).path_for(view.session_id)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{bad json")
    with pytest.raises(ValueError):
        manager.get_session(view.session_id)


def test_stage14_invalid_session_id_rejected(tmp_path):
    manager = make_manager(tmp_path)
    manager.open_session(GatewayConfig(symbol="BTC/USDT", timeframe="15m"))
    with pytest.raises(ValueError):
        manager.get_session("../escape")



def test_stage14_history_export_csv(tmp_path):
    manager = make_manager(tmp_path)
    view = manager.open_session(GatewayConfig(symbol="BTC/USDT", timeframe="15m"))
    orch = Stage13Orchestrator(
        models=[ScriptedBrain("quant", "BUY", 0.95), ScriptedBrain("risk", "BUY", 0.9)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(make_intelligence_report(action="BUY")),
    )
    manager.run_session(
        view.session_id,
        Stage14SessionRunRequest(candles=make_candles()),
        orchestrator=orch,
    )
    csv_text = manager.export_history_csv(view.session_id)
    assert "run_id,created_at,report_hash" in csv_text


def test_stage14_store_preserves_multiple_sessions_in_shared_file(tmp_path):
    store = LocalSessionStore(str(tmp_path))
    btc_state = store.create_empty_state(
        GatewayConfig(symbol="BTC/USDT", timeframe="15m"),
        gateway_hash="btc",
    )
    eth_state = store.create_empty_state(
        GatewayConfig(symbol="ETH/USDT", timeframe="1h"),
        gateway_hash="eth",
    )

    store.save(btc_state)
    store.save(eth_state)

    assert store.load(btc_state.session_id).gateway_hash == "btc"
    assert store.load(eth_state.session_id).gateway_hash == "eth"


def test_stage14_api_endpoints(monkeypatch, tmp_path):
    real_manager = make_manager(tmp_path)
    real_view = real_manager.open_session(GatewayConfig(symbol="BTC/USDT", timeframe="15m"))
    real_report = Stage13Orchestrator(
        models=[ScriptedBrain("quant", "BUY", 0.95), ScriptedBrain("risk", "BUY", 0.9)],
        intelligence_orchestrator=FakeIntelligenceOrchestrator(make_intelligence_report(action="BUY")),
    ).run(
        api_app_module.Stage13ApiRequest(
            symbol="BTC/USDT",
            timeframe="15m",
            candles=make_candles(),
        ).to_request()
    )
    dummy = DummyStage14Manager(real_view, real_report)
    monkeypatch.setattr(api_app_module, "get_stage14_manager", lambda: dummy)
    client = TestClient(app)

    open_resp = client.post("/stage14/sessions", json=Stage14SessionOpenRequest().model_dump())
    assert open_resp.status_code == 200
    session_id = open_resp.json()["session_id"]

    get_resp = client.get(f"/stage14/sessions/{session_id}")
    assert get_resp.status_code == 200

    candles = [
        {
            "timestamp": candle.timestamp.isoformat(),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in make_candles(5)
    ]
    run_resp = client.post(
        f"/stage14/sessions/{session_id}/run",
        json=Stage14SessionRunRequest(candles=candles).model_dump(mode="json"),
    )
    assert run_resp.status_code == 200
    history_resp = client.get(f"/stage14/sessions/{session_id}/history")
    assert history_resp.status_code == 200
    history_csv_resp = client.get(f"/stage14/sessions/{session_id}/history?format=csv")
    assert history_csv_resp.status_code == 200
    assert "run_id,executed" in history_csv_resp.text
