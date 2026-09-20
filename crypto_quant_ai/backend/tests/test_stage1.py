from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from crypto_quant_ai.backend.api.app import app
from crypto_quant_ai.backend.core.config import settings
from crypto_quant_ai.backend.core.models import BrainAnalysis, MarketData, RiskAssessment
from crypto_quant_ai.backend.decision.decision_engine import DecisionEngine
from crypto_quant_ai.backend.execution.execution import ExecutionService


def test_live_trading_default_false() -> None:
    assert settings.live_trading is False


def test_market_data_model_creates() -> None:
    data = MarketData(
        symbol="BTC/USDT",
        timestamp="2024-01-01T00:00:00Z",
        open=40000.0,
        high=41000.0,
        low=39500.0,
        close=40500.0,
        volume=100.0,
        timeframe="15m",
    )
    assert data.symbol == "BTC/USDT"
    assert data.timeframe == "15m"


def test_brain_analysis_model_creates() -> None:
    analysis = BrainAnalysis(
        brain_name="quant",
        decision="NO_TRADE",
        confidence=0.55,
        reasoning="No entry",
        warnings=["safe"],
    )
    assert analysis.decision == "NO_TRADE"


def test_veto_causes_no_trade() -> None:
    risk = RiskAssessment(veto=True, veto_reason="unsafe")
    decision = DecisionEngine().decide("BTC/USDT", "15m", risk, "veto triggered")
    assert decision.decision == "NO_TRADE"
    assert decision.veto is True


def test_execution_service_rejects_live_trading() -> None:
    service = ExecutionService()
    with pytest.raises(RuntimeError, match="Live trading is disabled"):
        service.place_order(symbol="BTC/USDT")


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "crypto-quant-ai"


def test_root_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
