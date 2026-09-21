"""Stage 3.4 — Per-order execution trace (append-only, local).

An ``ExecutionTrace`` records the full lifecycle of a single paper order:

    created -> validated -> accepted -> executed -> closed
                              -> rejected
                              -> skipped

Each state transition is an :class:`OrderEvent`.  The trace is append-only
and fully local; it never performs orders, contacts an exchange, or reaches
the network.  ``snapshot_before`` / ``snapshot_after`` capture local
portfolio state around execution.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple

from crypto_quant_ai.backend.paper.order_event import OrderEvent
from crypto_quant_ai.backend.paper.snapshot import PortfolioSnapshot

# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() in ("true", "1")
if LIVE_TRADING:
    raise RuntimeError(
        "Paper execution traces require LIVE_TRADING to be disabled."
        " Disable it to continue."
    )

# Legal state transitions. ``None`` value means terminal.
_LEGAL_NEXT = {
    "created": {"validated"},
    "validated": {"accepted", "rejected", "skipped"},
    "accepted": {"executed", "rejected", "skipped"},
    "executed": {"closed"},
    "closed": set(),
    "rejected": set(),
    "skipped": set(),
}

_TERMINAL = {"closed", "rejected", "skipped"}

# Stable ordering for deterministic event sorting across exports.
_LIFECYCLE_INDEX = {
    "created": 0,
    "validated": 1,
    "accepted": 2,
    "executed": 3,
    "closed": 4,
    "rejected": 5,
    "skipped": 6,
}


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------


@dataclass
class ExecutionTrace:
    """Append-only record of one order's lifecycle."""

    order_id: str
    symbol: str
    side: str = ""
    events: Tuple[OrderEvent, ...] = ()
    snapshot_before: Optional[PortfolioSnapshot] = None
    snapshot_after: Optional[PortfolioSnapshot] = None
    final_status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # -- construction ------------------------------------------------------

    @classmethod
    def new_trace(cls, order_id: str, symbol: str, side: str = "") -> "ExecutionTrace":
        if not order_id or not order_id.strip():
            raise ValueError("order_id must not be blank")
        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be blank")
        return cls(order_id=order_id, symbol=symbol.upper(), side=side)

    @classmethod
    def from_events(cls, events) -> "ExecutionTrace":
        """Build a trace from an arbitrary ordered list of events for one order.

        Used by the audit ledger to materialise a trace from stored events.
        Does not enforce a strict transition sequence (the ledger records the
        order produced by the executor), but it extracts snapshots and status.
        """
        if not events:
            raise ValueError("cannot build a trace from zero events")
        order_ids = {e.order_id for e in events}
        if len(order_ids) != 1:
            raise ValueError("events must all belong to a single order_id")
        sorted_events = sorted(
            events,
            key=lambda e: (
                e.timestamp,
                _LIFECYCLE_INDEX.get(e.event_type, 99),
                e.event_id,
            ),
        )
        e0 = sorted_events[0]
        before = next((e.snapshot for e in sorted_events if e.snapshot is not None), None)
        after = None
        for e in reversed(sorted_events):
            if e.snapshot is not None:
                after = e.snapshot
                break
        return cls(
            order_id=e0.order_id,
            symbol=e0.symbol,
            side=e0.side,
            events=tuple(sorted_events),
            snapshot_before=before,
            snapshot_after=after,
            final_status=sorted_events[-1].event_type,
            created_at=sorted_events[0].timestamp,
            updated_at=sorted_events[-1].timestamp,
        )

    # -- mutation (append-only) -------------------------------------------

    def append(self, event: OrderEvent) -> "ExecutionTrace":
        """Return a new trace with ``event`` appended (strict state machine)."""
        if event.order_id != self.order_id:
            raise ValueError("event order_id does not match trace order_id")
        current = self.final_status or ("created" if not self.events else self.events[-1].event_type)
        allowed = _LEGAL_NEXT.get(current, set())
        if event.event_type not in allowed:
            raise ValueError(
                f"illegal transition: {current!r} -> {event.event_type!r}"
            )
        new_events = list(self.events) + [event]
        before = self.snapshot_before or next(
            (e.snapshot for e in new_events if e.snapshot is not None), None
        )
        after = self.snapshot_after
        for e in reversed(new_events):
            if e.snapshot is not None:
                after = e.snapshot
                break
        return ExecutionTrace(
            order_id=self.order_id,
            symbol=self.symbol,
            side=self.side,
            events=tuple(new_events),
            snapshot_before=before,
            snapshot_after=after,
            final_status=event.event_type,
            created_at=self.created_at or event.timestamp,
            updated_at=event.timestamp,
        )

    # -- queries ----------------------------------------------------------

    @property
    def is_created(self) -> bool:
        return self.final_status in ("created", None) and not self.events

    @property
    def is_validated(self) -> bool:
        return self.final_status == "validated" or self._has("validated")

    @property
    def is_accepted(self) -> bool:
        return self._has("accepted")

    @property
    def is_executed(self) -> bool:
        # Once the order has reached EXECUTED it stays executed even if it later
        # moves to CLOSED.
        return self._has("executed")

    @property
    def is_rejected(self) -> bool:
        return self.final_status == "rejected" or self._has("rejected")

    @property
    def is_skipped(self) -> bool:
        return self.final_status == "skipped" or self._has("skipped")

    @property
    def is_closed(self) -> bool:
        return self.final_status == "closed"

    @property
    def is_terminal(self) -> bool:
        return self.final_status in _TERMINAL

    def _has(self, event_type: str) -> bool:
        return any(e.event_type == event_type for e in self.events)


def trace_from_execution(
    order_id: str,
    symbol: str,
    side: str,
    created_snapshot: Optional[PortfolioSnapshot] = None,
) -> ExecutionTrace:
    """Build a fresh ``ExecutionTrace`` for a newly created order."""
    return ExecutionTrace.new_trace(order_id, symbol, side)._with_snapshot(
        created_snapshot
    )


def _with_snapshot(self, snapshot):
    if snapshot is None:
        return self
    return ExecutionTrace(
        order_id=self.order_id,
        symbol=self.symbol,
        side=self.side,
        events=self.events,
        snapshot_before=snapshot,
        snapshot_after=self.snapshot_after,
        final_status=self.final_status,
        created_at=self.created_at,
        updated_at=self.updated_at,
    )


ExecutionTrace._with_snapshot = _with_snapshot  # type: ignore[attr-defined]


def new_trace(order_id: str, symbol: str, side: str = "") -> ExecutionTrace:
    """Module-level helper that creates a fresh ``ExecutionTrace``."""
    return ExecutionTrace.new_trace(order_id, symbol, side)
