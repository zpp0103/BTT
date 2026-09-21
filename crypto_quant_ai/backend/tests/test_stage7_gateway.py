"""Stage 7 (Plan A) - Safe paper trading gateway tests.

No real venue, no real orders, no credentials. LIVE_TRADING stays false.
The forbidden-token test uses hex-encoded tokens so it never matches itself.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from crypto_quant_ai.backend.core.models import FinalDecision
from crypto_quant_ai.backend.gateway import (
    CircuitBreaker,
    CircuitBreakerConfig,
    ExternalVenueAdapter,
    GatewayConfig,
    GatewayReportGenerator,
    GatewayStatus,
    LiveTradingSession,
    Monitor,
    PostTradeReconciliation,
    RiskManagerConfig,
    SimulatedVenueLedger,
    VenueFill,
    compute_gateway_hash,
    export_report,
)
from crypto_quant_ai.backend.paper.account import PaperAccount, PaperOrder
from crypto_quant_ai.backend.paper.audit import AuditLog
from crypto_quant_ai.backend.paper.risk_gate import PaperRiskGate


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def buy_decision(symbol="BTC/USDT", entry=100.0, stop_loss=99.0, confidence=0.9,
                 position_size=5000.0, timeframe="15m", reasoning="t"):
    return FinalDecision(
        symbol=symbol, timeframe=timeframe, decision="BUY", confidence=confidence,
        entry=entry, stop_loss=stop_loss, position_size=position_size,
        reasoning=reasoning, timestamp=_ts(),
    )


def no_trade_decision(symbol="BTC/USDT"):
    return FinalDecision(
        symbol=symbol, decision="NO_TRADE", confidence=0.5,
        reasoning="t", timestamp=_ts(),
    )


def sell_decision(symbol="BTC/USDT", entry=100.0, confidence=0.9, position_size=2500.0):
    return FinalDecision(
        symbol=symbol, timeframe="15m", decision="SELL", confidence=confidence,
        entry=entry, position_size=position_size, reasoning="t", timestamp=_ts(),
    )


def veto_decision(symbol="BTC/USDT"):
    return FinalDecision(
        symbol=symbol, decision="BUY", confidence=0.9, entry=100.0, stop_loss=99.0,
        position_size=5000.0, veto=True, veto_reason="manual", reasoning="t",
        timestamp=_ts(),
    )


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def test_gateway_config_defaults_frozen():
    cfg = GatewayConfig()
    with pytest.raises(Exception):
        cfg.initial_cash = 5.0  # frozen -> raises


def test_gateway_config_rejects_blank_symbol():
    with pytest.raises(Exception):
        GatewayConfig(symbol="   ")


def test_gateway_config_rejects_nonfinite_cash():
    with pytest.raises(Exception):
        GatewayConfig(initial_cash=float("nan"))


def test_risk_manager_config_isfinite():
    with pytest.raises(Exception):
        RiskManagerConfig(min_confidence=float("inf"))


def test_circuit_breaker_config_isfinite():
    with pytest.raises(Exception):
        CircuitBreakerConfig(daily_loss_limit=float("-inf"))


def test_compute_gateway_hash_deterministic():
    a = compute_gateway_hash(GatewayConfig(initial_cash=100000.0))
    b = compute_gateway_hash(GatewayConfig(initial_cash=100000.0))
    assert a == b
    c = compute_gateway_hash(GatewayConfig(initial_cash=200000.0))
    assert c != a


def test_compute_gateway_hash_excludes_runtime():
    # Two configs identical -> identical hash (no started/stopped/now involved).
    assert compute_gateway_hash(GatewayConfig()) == compute_gateway_hash(GatewayConfig())


# --------------------------------------------------------------------------
# Session lifecycle
# --------------------------------------------------------------------------

def test_session_start_stop_status():
    s = LiveTradingSession(GatewayConfig())
    assert s.status == GatewayStatus.STOPPED
    s.start()
    assert s.status == GatewayStatus.RUNNING
    s.stop()
    assert s.status == GatewayStatus.STOPPED


def test_session_submit_requires_start():
    s = LiveTradingSession(GatewayConfig())
    with pytest.raises(RuntimeError):
        s.submit_decision(buy_decision())


def test_reuse_wiring():
    s = LiveTradingSession(GatewayConfig())
    assert isinstance(s.audit_log, AuditLog)
    assert isinstance(s.venue, ExternalVenueAdapter)
    assert isinstance(s.circuit_breaker, CircuitBreaker)
    assert isinstance(s.monitor, Monitor)
    assert isinstance(s._executor.risk_gate, PaperRiskGate)


# --------------------------------------------------------------------------
# Order execution chain (reuses Stage 3)
# --------------------------------------------------------------------------

def test_session_buy_executes_paper_order():
    s = LiveTradingSession(GatewayConfig(initial_cash=100000.0))
    s.start()
    res = s.submit_decision(buy_decision())
    assert res.executed
    assert res.order_id is not None
    assert s.account.cash < 100000.0
    assert len(s.account.orders) == 1


def test_session_buy_without_stop_loss_rejected_by_gate():
    s = LiveTradingSession(GatewayConfig())
    s.start()
    res = s.submit_decision(buy_decision(stop_loss=None))
    assert not res.executed
    assert res.rejected_by_gate
    assert s.account.cash == 100000.0


def test_session_low_confidence_rejected():
    s = LiveTradingSession(GatewayConfig())
    s.start()
    res = s.submit_decision(buy_decision(confidence=0.3))
    assert not res.executed
    assert res.rejected_by_gate
    assert s.account.cash == 100000.0


def test_session_no_trade_skipped():
    s = LiveTradingSession(GatewayConfig())
    s.start()
    res = s.submit_decision(no_trade_decision())
    assert not res.executed
    assert res.no_trade
    assert s.account.cash == 100000.0


def test_session_veto_blocked():
    s = LiveTradingSession(GatewayConfig())
    s.start()
    res = s.submit_decision(veto_decision())
    assert not res.executed
    assert res.veto_blocked
    assert s.account.cash == 100000.0


def test_session_buy_then_sell():
    s = LiveTradingSession(GatewayConfig(initial_cash=100000.0))
    s.start()
    r1 = s.submit_decision(buy_decision())
    assert r1.executed
    r2 = s.submit_decision(sell_decision(position_size=2500.0))
    assert r2.executed
    sym = "BTC/USDT"
    assert s.account.positions[sym].quantity == 25.0


def test_audit_log_records_lifecycle():
    s = LiveTradingSession(GatewayConfig())
    s.start()
    s.submit_decision(buy_decision())
    types = [e.event_type for e in s.audit_log.all_events()]
    for needed in ("created", "accepted", "executed", "closed"):
        assert needed in types


# --------------------------------------------------------------------------
# Circuit breaker (Stage 7 hard stops)
# --------------------------------------------------------------------------

def test_circuit_breaker_per_order_notional_blocks():
    cfg = GatewayConfig(circuit_breaker=CircuitBreakerConfig(max_order_notional=1000.0))
    s = LiveTradingSession(cfg)
    s.start()
    res = s.submit_decision(buy_decision(position_size=5000.0))
    assert res.circuit_breaker_tripped
    assert not res.executed
    assert s.status == GatewayStatus.TRIPPED
    assert s.account.cash == 100000.0


def test_circuit_breaker_price_anomaly_blocks():
    cfg = GatewayConfig(circuit_breaker=CircuitBreakerConfig(price_anomaly_pct=0.01))
    s = LiveTradingSession(cfg)
    s.start()
    res = s.submit_decision(
        buy_decision(entry=102.0, stop_loss=101.0, position_size=5000.0),
        reference_price=100.0,
    )
    assert res.circuit_breaker_tripped
    assert not res.executed


def test_circuit_breaker_daily_loss_trips():
    cfg = GatewayConfig(circuit_breaker=CircuitBreakerConfig(daily_loss_limit=10.0))
    s = LiveTradingSession(cfg)
    s.start()
    s.submit_decision(buy_decision(entry=100.0, stop_loss=99.0, position_size=5000.0))
    s.submit_decision(sell_decision(entry=99.0, position_size=2500.0))
    assert s.circuit_breaker.triggered
    assert s.circuit_breaker.reason != ""


def test_circuit_breaker_stays_tripped():
    cfg = GatewayConfig(circuit_breaker=CircuitBreakerConfig(daily_loss_limit=10.0))
    s = LiveTradingSession(cfg)
    s.start()
    s.submit_decision(buy_decision(entry=100.0, stop_loss=99.0, position_size=5000.0))
    s.submit_decision(sell_decision(entry=99.0, position_size=2500.0))
    res = s.submit_decision(buy_decision())
    assert res.circuit_breaker_tripped
    assert not res.executed


# --------------------------------------------------------------------------
# Venue adapter (gated stub)
# --------------------------------------------------------------------------

def test_venue_adapter_mirrors_fill():
    s = LiveTradingSession(GatewayConfig())
    s.start()
    s.submit_decision(buy_decision())
    fills = s.venue.ledger.all()
    assert len(fills) == 1
    assert fills[0].side == "buy"
    assert fills[0].quantity == 50.0
    assert fills[0].venue == "simulated"


def test_venue_adapter_refuses_live(monkeypatch):
    adapter = ExternalVenueAdapter()
    order = PaperOrder(
        symbol="BTC/USDT", side="buy", quantity=1.0, price=100.0,
        timestamp=datetime.now(timezone.utc),
    )
    with monkeypatch.context() as m:
        m.setenv("LIVE_TRADING", "true")
        with pytest.raises(RuntimeError):
            adapter.submit("ord-x", order)


def test_session_start_refuses_live(monkeypatch):
    s = LiveTradingSession(GatewayConfig())
    with monkeypatch.context() as m:
        m.setenv("LIVE_TRADING", "true")
        with pytest.raises(RuntimeError):
            s.start()


# --------------------------------------------------------------------------
# Monitor / alerts
# --------------------------------------------------------------------------

def test_monitor_records_alerts_on_rejection():
    s = LiveTradingSession(GatewayConfig())
    s.start()
    s.submit_decision(buy_decision(stop_loss=None))
    alerts = s.monitor.alerts()
    assert any("Risk gate rejected" in a.message for a in alerts)


# --------------------------------------------------------------------------
# Reconciliation
# --------------------------------------------------------------------------

def test_reconciliation_ok_after_buy():
    s = LiveTradingSession(GatewayConfig())
    s.start()
    s.submit_decision(buy_decision())
    report = s.reconcile()
    assert report.ok
    assert report.matched >= 1


def test_reconciliation_detects_mismatch():
    s = LiveTradingSession(GatewayConfig())
    s.start()
    s.submit_decision(buy_decision())  # appends executed events to audit, fills ledger
    oid = s.venue.ledger.all()[0].order_id
    # Overwrite the real venue fill with a wrong price for the same order id.
    s.venue.ledger.record(VenueFill(
        order_id=oid, symbol="BTC/USDT", side="buy",
        quantity=50.0, price=999.0, timestamp=datetime.now(timezone.utc),
    ))
    report = s.reconcile()
    assert not report.ok
    assert any(m.field == "price" for m in report.mismatches)


# --------------------------------------------------------------------------
# Report / formatters
# --------------------------------------------------------------------------

def test_report_generation_and_formatters():
    s = LiveTradingSession(GatewayConfig())
    s.start()
    s.submit_decision(buy_decision())
    h = compute_gateway_hash(GatewayConfig())
    rep = GatewayReportGenerator().build(s, gateway_hash=h, reconciliation=s.reconcile())
    md = export_report(rep, "markdown")
    js = export_report(rep, "json")
    cv = export_report(rep, "csv")
    assert "Stage 7" in md
    assert "gateway_hash" in js
    assert "field" in cv
    assert rep.total_executed >= 1


def test_gateway_status_enum_values():
    assert {GatewayStatus.STOPPED.value, GatewayStatus.RUNNING.value,
            GatewayStatus.TRIPPED.value} == {"stopped", "running", "tripped"}


# --------------------------------------------------------------------------
# Safety scan (self-contained)
# --------------------------------------------------------------------------

_FORBIDDEN_HEX = [
    "63637874", "62696e616e6365", "636f696e62617365", "6b72616b656e",
    "65786368616e67655f636c69656e74", "6170695f6b6579", "6170695f736563726574",
    "706c6163655f6f72646572", "6372656174655f6f72646572", "7265616c5f6f72646572",
    "6175746f5f7472616465", "6c6976655f74726164696e67", "72657175657374732e",
    "68747470782e", "75726c6c69622e72657175657374",
]


def test_no_forbidden_tokens():
    root = Path(__file__).resolve().parents[2]
    scan_dirs = [
        root / "crypto_quant_ai" / "backend" / "gateway",
        root / "crypto_quant_ai" / "docs",
    ]
    pattern = re.compile(
        "|".join(bytes.fromhex(h).decode() for h in _FORBIDDEN_HEX)
    )
    hits = []
    for d in scan_dirs:
        for f in d.rglob("*.py"):
            if "test_stage7" in f.name:
                continue
            text = f.read_text(encoding="utf-8")
            if pattern.search(text):
                hits.append(str(f))
        for f in d.rglob("*.md"):
            if f.name == "stage7-gateway.md":
                text = f.read_text(encoding="utf-8")
                if pattern.search(text):
                    hits.append(str(f))
    assert hits == [], f"forbidden tokens found in: {hits}"
