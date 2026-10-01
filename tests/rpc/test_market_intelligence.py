from datetime import UTC, datetime, timedelta

from freqtrade.rpc.api_server.market_intelligence import (
    build_unconfigured_intelligence,
    evaluate_risk_gate,
)


def test_unconfigured_intelligence_is_honest_and_observe_only():
    result = build_unconfigured_intelligence({})

    assert result.source_mode == "live"
    assert result.events == []
    assert {provider.status for provider in result.providers} == {"unconfigured"}
    assert result.roundtable.status == "unavailable"
    assert all(opinion.status == "unavailable" for opinion in result.roundtable.opinions)
    assert result.risk_decision.approved is False
    assert "market_data_unavailable" in result.risk_decision.veto_reasons
    assert "ai_service_unavailable" in result.risk_decision.veto_reasons
    assert result.execution.mode == "observe_only"
    assert result.execution.status == "disabled"


def test_stale_market_data_is_vetoed():
    now = datetime.now(UTC)
    freshness, decision = evaluate_risk_gate(
        generated_at=now - timedelta(minutes=10),
        now=now,
        max_age_seconds=300,
        intelligence_available=True,
        ai_available=True,
    )

    assert freshness.status == "stale"
    assert decision.status == "rejected"
    assert decision.veto_reasons == ["market_data_stale"]


def test_fresh_intelligence_can_pass_risk_gate():
    now = datetime.now(UTC)
    freshness, decision = evaluate_risk_gate(
        generated_at=now - timedelta(seconds=15),
        now=now,
        max_age_seconds=300,
        intelligence_available=True,
        ai_available=True,
    )

    assert freshness.status == "fresh"
    assert decision.status == "approved"
    assert decision.approved is True


def test_hard_risk_limits_veto_ai_proposal():
    now = datetime.now(UTC)
    _, decision = evaluate_risk_gate(
        generated_at=now,
        now=now,
        max_age_seconds=300,
        intelligence_available=True,
        ai_available=True,
        proposed_position_pct=0.11,
        current_drawdown_pct=0.13,
        daily_loss_pct=0.05,
    )

    assert decision.approved is False
    assert decision.veto_reasons == [
        "max_position_exceeded",
        "max_drawdown_exceeded",
        "max_daily_loss_exceeded",
    ]
