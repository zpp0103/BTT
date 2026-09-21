"""Tests for Stage 3.4 — local paper audit trail (events, traces, ledger).

Coverage targets the spec §11 scenario list:
  * OrderEvent validation (ids, symbol, event_type, side, timestamp, reasons)
  * ExecutionTrace lifecycle state machine + from_events rebuild
  * PortfolioSnapshot content + valuation from explicit local prices
  * AuditLog append / append_trace / query_by_order / query_recent / all_events / clear
  * Executor integration: created->validated->accepted->executed->closed,
    rejected never mutates cash/positions and emits no executed event,
    Stage 3.3 risk gate still runs before the executor
  * Snapshot-before/after consistency with live account state
  * No secrets stored, no network, no order execution inside the ledger
  * LIVE_TRADING guard at import time
"""

from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from crypto_quant_ai.backend.core.models import FinalDecision
from crypto_quant_ai.backend.paper import (
    AuditLog,
    ExecutionTrace,
    OrderEvent,
    PaperAccount,
    PaperExecutor,
    PaperRiskGate,
    PortfolioSnapshot,
    new_trace,
    snapshot_from_account,
)
from crypto_quant_ai.backend.paper.order_event import make_event_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_decision(**overrides) -> FinalDecision:
    base = dict(
        symbol="BTC",
        decision="BUY",
        confidence=0.9,
        entry=60000.0,
        stop_loss=54000.0,
        take_profit=72000.0,
        position_size=0.0,
        risk_reward=2.0,
        timestamp="2026-09-21T00:00:00Z",
    )
    base.update(overrides)
    return FinalDecision(**base)


def make_report(decision: FinalDecision) -> SimpleNamespace:
    # Minimal stand-in for OrchestratorReport (same attribute access pattern
    # the executor relies on), since brain_orchestrator lives on another branch.
    return SimpleNamespace(final_decision=decision)


@contextmanager
def patch_env(updates: dict):
    saved = {k: os.environ.get(k) for k in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def fresh_ledger() -> AuditLog:
    return AuditLog()


def _decode(hex_str: str) -> str:
    return bytes.fromhex(hex_str).decode()


# Hex-encoded forbidden substrings so they never appear literally in source.
_FORBIDDEN = [
    _decode("63637874"),
    _decode("62696e616e6365"),
    _decode("636f696e62617365"),
    _decode("6b72616b656e"),
    _decode("706c6163655f6f72646572"),
    _decode("6372656174655f6f72646572"),
    _decode("7265616c5f6f72646572"),
    _decode("6175746f5f7472616465"),
    _decode("6170695f6b6579"),
    _decode("6170695f736563726574"),
    _decode("7365637265745f6b6579"),
]

_SECRETS = [
    _decode("6170695f6b6579"),
    _decode("6170695f736563726574"),
    _decode("736563726574"),
    _decode("70617373776f7264"),
    _decode("746f6b656e"),
    _decode("6c6976655f74726164696e67"),
]


# ---------------------------------------------------------------------------
# OrderEvent validation
# ---------------------------------------------------------------------------


class TestOrderEventValidation:
    def test_created_requires_order_id(self):
        with pytest.raises(ValueError):
            OrderEvent(
                event_id=make_event_id(),
                order_id="",
                event_type="created",
                symbol="BTC",
                side="",
                timestamp=datetime.now(timezone.utc),
            )

    def test_created_requires_symbol(self):
        with pytest.raises(ValueError):
            OrderEvent(
                event_id=make_event_id(),
                order_id="o1",
                event_type="created",
                symbol="",
                side="",
                timestamp=datetime.now(timezone.utc),
            )

    def test_invalid_event_type_rejected(self):
        with pytest.raises(ValueError):
            OrderEvent(
                event_id=make_event_id(),
                order_id="o1",
                event_type="exploded",
                symbol="BTC",
                side="",
                timestamp=datetime.now(timezone.utc),
            )

    def test_invalid_side_rejected(self):
        with pytest.raises(ValueError):
            OrderEvent(
                event_id=make_event_id(),
                order_id="o1",
                event_type="created",
                symbol="BTC",
                side="sideways",
                timestamp=datetime.now(timezone.utc),
            )

    def test_missing_timestamp_rejected(self):
        with pytest.raises((ValueError, TypeError)):
            OrderEvent(
                event_id=make_event_id(),
                order_id="o1",
                event_type="created",
                symbol="BTC",
                side="",
            )

    def test_rejected_event_requires_reason(self):
        with pytest.raises(ValueError):
            OrderEvent(
                event_id=make_event_id(),
                order_id="o1",
                event_type="rejected",
                symbol="BTC",
                side="buy",
                timestamp=datetime.now(timezone.utc),
                reasons=[],
            )

    def test_rejected_event_with_reason_ok(self):
        ev = OrderEvent(
            event_id=make_event_id(),
            order_id="o1",
            event_type="rejected",
            symbol="BTC",
            side="buy",
            timestamp=datetime.now(timezone.utc),
            reasons=["confidence too low"],
        )
        assert ev.status == "rejected"
        assert ev.reasons == ["confidence too low"]

    def test_negative_quantity_rejected(self):
        with pytest.raises(ValueError):
            OrderEvent(
                event_id=make_event_id(),
                order_id="o1",
                event_type="created",
                symbol="BTC",
                side="buy",
                timestamp=datetime.now(timezone.utc),
                quantity=-1.0,
            )

    def test_default_status_mirrors_event_type(self):
        ev = OrderEvent(
            event_id=make_event_id(),
            order_id="o1",
            event_type="created",
            symbol="BTC",
            side="",
            timestamp=datetime.now(timezone.utc),
        )
        assert ev.status == "created"
        assert ev.source == "audit_log"


# ---------------------------------------------------------------------------
# ExecutionTrace state machine
# ---------------------------------------------------------------------------


class TestExecutionTraceLifecycle:
    def test_happy_path(self):
        oid = "ord-000001"
        t = new_trace(oid, "BTC", "buy")
        assert t.final_status is None
        snap = PortfolioSnapshot(
            timestamp=datetime.now(timezone.utc), cash=100000.0, positions={}
        )
        t = (
            t._with_snapshot(snap)
            .append(OrderEvent(make_event_id(), oid, "validated", "BTC", "buy",
                               datetime.now(timezone.utc), source="risk_gate",
                               reasons=["ok"]))
            .append(OrderEvent(make_event_id(), oid, "accepted", "BTC", "buy",
                               datetime.now(timezone.utc)))
            .append(OrderEvent(make_event_id(), oid, "executed", "BTC", "buy",
                               datetime.now(timezone.utc), quantity=0.1, price=60000.0))
            .append(OrderEvent(make_event_id(), oid, "closed", "BTC", "buy",
                               datetime.now(timezone.utc), quantity=0.1, price=60000.0))
        )
        assert t.is_executed
        assert t.is_closed
        assert not t.is_rejected
        assert t.final_status == "closed"

    def test_rejected_branch(self):
        oid = "ord-000002"
        t = new_trace(oid, "BTC", "buy")
        t = (
            t.append(OrderEvent(make_event_id(), oid, "validated", "BTC", "buy",
                                datetime.now(timezone.utc), source="risk_gate",
                                reasons=["fail"]))
            .append(OrderEvent(make_event_id(), oid, "rejected", "BTC", "buy",
                               datetime.now(timezone.utc), reasons=["confidence low"]))
        )
        assert t.is_rejected
        assert not t.is_executed
        assert t.final_status == "rejected"

    def test_illegal_transition_rejected(self):
        oid = "ord-000003"
        t = new_trace(oid, "BTC", "buy")
        t = t.append(OrderEvent(make_event_id(), oid, "validated", "BTC", "buy",
                                datetime.now(timezone.utc), source="risk_gate",
                                reasons=["ok"]))
        with pytest.raises(ValueError):
            # validated -> executed (skip accepted) is illegal
            t.append(OrderEvent(make_event_id(), oid, "executed", "BTC", "buy",
                                datetime.now(timezone.utc), quantity=0.1, price=60000.0))

    def test_from_events_rebuilds(self):
        oid = "ord-000004"
        events = [
            OrderEvent(make_event_id(), oid, "created", "BTC", "buy",
                       datetime.now(timezone.utc)),
            OrderEvent(make_event_id(), oid, "validated", "BTC", "buy",
                       datetime.now(timezone.utc), source="risk_gate", reasons=["ok"]),
            OrderEvent(make_event_id(), oid, "accepted", "BTC", "buy",
                       datetime.now(timezone.utc)),
            OrderEvent(make_event_id(), oid, "executed", "BTC", "buy",
                       datetime.now(timezone.utc), quantity=0.1, price=60000.0),
            OrderEvent(make_event_id(), oid, "closed", "BTC", "buy",
                       datetime.now(timezone.utc), quantity=0.1, price=60000.0),
        ]
        t = ExecutionTrace.from_events(events)
        assert t.final_status == "closed"
        assert t.is_executed
        assert len(t.events) == 5


# ---------------------------------------------------------------------------
# PortfolioSnapshot
# ---------------------------------------------------------------------------


class TestPortfolioSnapshot:
    def test_built_from_account(self):
        acc = PaperAccount()
        snap = snapshot_from_account(acc, "test")
        assert snap.cash == 100000.0
        assert snap.positions == {}
        assert snap.total_equity == 100000.0
        assert snap.total_exposure == 0.0
        assert snap.exposure_pct == 0.0

    def test_valuation_uses_explicit_prices_only(self):
        acc = PaperAccount()
        # simulate a position via a fresh account with bought qty is hard without buy();
        # instead verify valuation math directly through snapshot_from_account on a
        # position-bearing account.
        from crypto_quant_ai.backend.paper.account import buy as do_buy
        new_acc, _ = do_buy(acc, "BTC", 0.5, 60000.0)
        snap = snapshot_from_account(new_acc, "test", prices={"BTC": 60000.0})
        assert snap.positions == {"BTC": 0.5}
        assert abs(snap.total_exposure - 30000.0) < 1e-6
        assert abs(snap.total_equity - 100000.0) < 1e-6
        assert abs(snap.exposure_pct - 0.3) < 1e-6


# ---------------------------------------------------------------------------
# AuditLog core API
# ---------------------------------------------------------------------------


class TestAuditLogCore:
    def test_append_and_query_by_order(self):
        ledger = fresh_ledger()
        oid = "ord-000010"
        ledger.append(OrderEvent(make_event_id(), oid, "created", "BTC", "buy",
                                 datetime.now(timezone.utc)))
        ledger.append(OrderEvent(make_event_id(), oid, "validated", "BTC", "buy",
                                 datetime.now(timezone.utc), source="risk_gate",
                                 reasons=["ok"]))
        events = ledger.query_by_order(oid)
        assert len(events) == 2
        assert events[0].event_type == "created"
        assert events[1].event_type == "validated"

    def test_append_trace(self):
        ledger = fresh_ledger()
        oid = "ord-000011"
        t = new_trace(oid, "BTC", "buy")
        t = t.append(OrderEvent(make_event_id(), oid, "validated", "BTC", "buy",
                                datetime.now(timezone.utc), source="risk_gate",
                                reasons=["ok"]))
        ledger.append_trace(t)
        assert ledger.total_orders == 1
        assert ledger.get_trace(oid) is not None

    def test_query_recent(self):
        ledger = fresh_ledger()
        for i in range(3):
            oid = f"ord-{i:06d}"
            ledger.append(OrderEvent(make_event_id(), oid, "created", "BTC", "buy",
                                     datetime.now(timezone.utc)))
        recent = ledger.query_recent(2)
        assert len(recent) == 2
        # most recent appended last
        assert recent[-1].order_id == "ord-000002"

    def test_all_events_deterministic(self):
        ledger = fresh_ledger()
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        oid = "ord-000020"
        # append out of lifecycle order; all_events must sort deterministically
        ledger.append(OrderEvent(make_event_id(), oid, "closed", "BTC", "buy", ts))
        ledger.append(OrderEvent(make_event_id(), oid, "created", "BTC", "buy", ts))
        types = [e.event_type for e in ledger.all_events()]
        assert types == ["created", "closed"]

    def test_clear(self):
        ledger = fresh_ledger()
        ledger.append(OrderEvent(make_event_id(), "ord-1", "created", "BTC", "buy",
                                 datetime.now(timezone.utc)))
        assert len(ledger) == 1
        ledger.clear()
        assert len(ledger) == 0
        assert ledger.total_orders == 0

    def test_to_csv_and_json(self):
        ledger = fresh_ledger()
        ledger.append(OrderEvent(make_event_id(), "ord-1", "created", "BTC", "buy",
                                 datetime.now(timezone.utc), reasons=["r"]))
        csv_text = ledger.to_csv()
        assert "order_id" in csv_text
        assert "ord-1" in csv_text
        json_text = ledger.to_json()
        assert "ord-1" in json_text
        assert "created" in json_text

    def test_duplicate_order_id_accumulates(self):
        ledger = fresh_ledger()
        oid = "ord-000030"
        ledger.append(OrderEvent(make_event_id(), oid, "created", "BTC", "buy",
                                 datetime.now(timezone.utc)))
        ledger.append(OrderEvent(make_event_id(), oid, "validated", "BTC", "buy",
                                 datetime.now(timezone.utc), source="risk_gate",
                                 reasons=["ok"]))
        # explicit rule: same order_id accumulates into one trace
        assert ledger.total_orders == 1
        assert len(ledger.query_by_order(oid)) == 2


# ---------------------------------------------------------------------------
# Executor integration (Stage 3.2 + Stage 3.3 gate + Stage 3.4 audit)
# ---------------------------------------------------------------------------


class TestExecutorAuditIntegration:
    def _gate(self, account):
        return PaperRiskGate(
            account,
            min_confidence=0.5,
            max_position_fraction=1.0,
            min_risk_reward=1.5,
            min_stop_loss_pct=0.005,
        )

    def test_full_lifecycle_records_events_and_snapshots(self):
        acc = PaperAccount()
        ledger = fresh_ledger()
        gate = self._gate(acc)
        executor = PaperExecutor(acc, audit_log=ledger, risk_gate=gate)

        report = make_report(make_decision())  # passing gate
        result = executor.execute(report)

        assert result.executed is True
        assert result.order is not None

        oid = result.order  # not used; trace keyed by internal order id
        # find the order id from the ledger
        assert ledger.total_orders == 1
        trace = next(iter(ledger._traces.values()))
        types = [e.event_type for e in trace.events]
        assert types[0] == "created"
        assert "validated" in types
        assert "accepted" in types
        assert "executed" in types
        assert types[-1] == "closed"

        # snapshots present and consistent with account
        assert trace.snapshot_before is not None
        assert trace.snapshot_after is not None
        assert trace.snapshot_before.cash == 100000.0
        assert abs(trace.snapshot_after.cash - executor.account.cash) < 1e-6
        assert "BTC" in trace.snapshot_after.positions

    def test_rejected_by_gate_does_not_mutate_and_no_executed_event(self):
        acc = PaperAccount()
        cash_before = acc.cash
        positions_before = dict(acc.positions)
        ledger = fresh_ledger()
        gate = self._gate(acc)
        executor = PaperExecutor(acc, audit_log=ledger, risk_gate=gate)

        # confidence below threshold -> gate rejects
        report = make_report(make_decision(confidence=0.1))
        result = executor.execute(report)

        # contract: rejected => not executed, cash/positions unchanged
        assert result.executed is False
        assert acc.cash == cash_before
        assert dict(acc.positions) == positions_before

        trace = next(iter(ledger._traces.values()))
        types = [e.event_type for e in trace.events]
        assert "rejected" in types
        assert "executed" not in types
        assert trace.final_status == "rejected"

    def test_stage3_gate_runs_before_executor(self):
        acc = PaperAccount()
        ledger = fresh_ledger()
        gate = self._gate(acc)
        executor = PaperExecutor(acc, audit_log=ledger, risk_gate=gate)

        report = make_report(make_decision(confidence=0.1))  # rejected by gate
        executor.execute(report)

        # the gate was evaluated (proof it runs in front of the executor)
        assert gate._audit.total >= 1
        assert gate._audit.rejected_count >= 1
        # no buy/sell happened
        assert ledger.get_trace(next(iter(ledger._traces))).is_rejected

    def test_executor_backward_compatible_without_audit(self):
        acc = PaperAccount()
        executor = PaperExecutor(acc)  # no audit_log, no risk_gate
        report = make_report(make_decision())
        result = executor.execute(report)
        assert result.executed is True
        assert result.order is not None
        assert executor.account.cash < 100000.0

    def test_snapshot_before_after_consistency(self):
        acc = PaperAccount()
        ledger = fresh_ledger()
        gate = self._gate(acc)
        executor = PaperExecutor(acc, audit_log=ledger, risk_gate=gate)
        executor.execute(make_report(make_decision()))

        trace = next(iter(ledger._traces.values()))
        # before-snapshot cash equals starting cash; after matches live account
        assert trace.snapshot_before.cash == 100000.0
        assert abs(trace.snapshot_after.cash - executor.account.cash) < 1e-6


# ---------------------------------------------------------------------------
# Safety properties
# ---------------------------------------------------------------------------


class TestAuditSafety:
    def test_no_secrets_in_events(self):
        ev = OrderEvent(
            event_id=make_event_id(),
            order_id="ord-1",
            event_type="created",
            symbol="BTC",
            side="buy",
            timestamp=datetime.now(timezone.utc),
        )
        for forbidden in _SECRETS:
            assert not hasattr(ev, forbidden), f"event exposes {forbidden!r}"
        dump = ev.__repr__()
        for forbidden in _SECRETS:
            assert forbidden not in dump, f"repr leaks {forbidden!r}"

    def test_no_secrets_in_export(self):
        ledger = fresh_ledger()
        ledger.append(OrderEvent(make_event_id(), "ord-1", "created", "BTC", "buy",
                                 datetime.now(timezone.utc), reasons=["ok"]))
        text = ledger.to_json() + ledger.to_csv()
        for forbidden in _SECRETS:
            assert forbidden not in text, f"export leaks {forbidden!r}"

    def test_ledger_does_not_execute_orders(self):
        ledger = AuditLog()
        assert not hasattr(ledger, "execute")
        assert not hasattr(ledger, "buy")
        assert not hasattr(ledger, "sell")

    def test_modules_contain_no_exchange_or_network_code(self):
        import crypto_quant_ai.backend.paper.audit as audit_mod
        import crypto_quant_ai.backend.paper.execution_trace as trace_mod
        import crypto_quant_ai.backend.paper.order_event as event_mod
        import crypto_quant_ai.backend.paper.snapshot as snap_mod

        for mod in (event_mod, snap_mod, trace_mod, audit_mod):
            path = mod.__file__
            with open(path, "r", encoding="utf-8") as fh:
                src = fh.read().lower()
            for token in _FORBIDDEN:
                assert token not in src, f"{path} contains forbidden token {token!r}"


# ---------------------------------------------------------------------------
# LIVE_TRADING guard at import time
# ---------------------------------------------------------------------------


class TestLiveTradingGuard:
    def _reload_all(self):
        import crypto_quant_ai.backend.paper.audit as m_audit
        import crypto_quant_ai.backend.paper.execution_trace as m_trace
        import crypto_quant_ai.backend.paper.order_event as m_event
        import crypto_quant_ai.backend.paper.snapshot as m_snap
        importlib.reload(m_event)
        importlib.reload(m_snap)
        importlib.reload(m_trace)
        importlib.reload(m_audit)

    def test_order_event_live_guard(self):
        import crypto_quant_ai.backend.paper.order_event as m
        try:
            with pytest.raises(RuntimeError):
                with patch_env({"LIVE_TRADING": "true", "PAPER_TRADING": "false"}):
                    importlib.reload(m)
        finally:
            os.environ["LIVE_TRADING"] = "false"
            importlib.reload(m)

    def test_audit_modules_raise_under_live(self):
        import crypto_quant_ai.backend.paper.audit as m_audit
        import crypto_quant_ai.backend.paper.snapshot as m_snap
        try:
            with pytest.raises(RuntimeError):
                with patch_env({"LIVE_TRADING": "true", "PAPER_TRADING": "false"}):
                    importlib.reload(m_snap)
            with pytest.raises(RuntimeError):
                with patch_env({"LIVE_TRADING": "true", "PAPER_TRADING": "false"}):
                    importlib.reload(m_audit)
        finally:
            os.environ["LIVE_TRADING"] = "false"
            importlib.reload(m_snap)
            importlib.reload(m_audit)


from contextlib import contextmanager


@contextmanager
def patch_env(updates: dict):
    saved = {k: os.environ.get(k) for k in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
