"""Stage 3.4 — Local audit log for paper orders.

The ``AuditLog`` is the single source of truth for every order event.  It is:

* **local only** — no exchange calls, no network, no credentials;
* **append-only** — events are added once and never mutated;
* **queryable** — by order id, by recency, or all events in deterministic order.

``PaperAuditLedger`` is kept as a backward-compatible alias of ``AuditLog``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Dict, List, Optional

from crypto_quant_ai.backend.paper.execution_trace import (
    ExecutionTrace,
    _LIFECYCLE_INDEX,
)
from crypto_quant_ai.backend.paper.order_event import OrderEvent

# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() in ("true", "1")
if LIVE_TRADING:
    raise RuntimeError(
        "Paper audit log requires LIVE_TRADING to be disabled."
        " Disable it to continue."
    )


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class AuditLog:
    """Append-only local audit log of paper order events."""

    def __init__(self) -> None:
        self._events: List[OrderEvent] = []
        self._traces: Dict[str, ExecutionTrace] = {}

    # -- ingestion --------------------------------------------------------

    def append(self, event: OrderEvent) -> "AuditLog":
        """Append a single order event and route it to its trace."""
        if not isinstance(event, OrderEvent):
            raise TypeError("append expects an OrderEvent")
        self._events.append(event)
        order_id = event.order_id
        existing = self._traces.get(order_id)
        if existing is None:
            self._traces[order_id] = ExecutionTrace.from_events([event])
        else:
            self._traces[order_id] = ExecutionTrace.from_events(
                list(existing.events) + [event]
            )
        return self

    def append_trace(self, trace: ExecutionTrace) -> "AuditLog":
        """Append every event from a trace to the log."""
        for event in trace.events:
            self.append(event)
        return self

    def add_trace(self, trace: ExecutionTrace) -> "AuditLog":
        """Backward-compatible alias for :meth:`append_trace`."""
        return self.append_trace(trace)

    def extend(self, traces) -> "AuditLog":
        """Append several traces."""
        for trace in traces:
            self.append_trace(trace)
        return self

    # -- queries ----------------------------------------------------------

    @staticmethod
    def _sort_key(event: OrderEvent):
        return (
            event.timestamp,
            _LIFECYCLE_INDEX.get(event.event_type, 99),
            event.event_id,
        )

    def query_by_order(self, order_id: str) -> List[OrderEvent]:
        """Return all events for ``order_id`` in deterministic order."""
        trace = self._traces.get(order_id)
        if trace is None:
            return []
        return sorted(trace.events, key=self._sort_key)

    def query_recent(self, limit: int) -> List[OrderEvent]:
        """Return the most recent ``limit`` events across all orders."""
        ordered = sorted(self._events, key=self._sort_key)
        if limit is not None and limit >= 0:
            ordered = ordered[-limit:]
        return ordered

    def all_events(self) -> List[OrderEvent]:
        """Return every event in deterministic order."""
        return sorted(self._events, key=self._sort_key)

    def events(self) -> List[OrderEvent]:
        """Backward-compatible alias for :meth:`all_events`."""
        return self.all_events()

    def get_trace(self, order_id: str) -> Optional[ExecutionTrace]:
        """Return the trace for ``order_id`` (or ``None``)."""
        return self._traces.get(order_id)

    def clear(self) -> None:
        """Remove every event and trace."""
        self._events = []
        self._traces = {}

    # -- aggregated views -------------------------------------------------

    @property
    def total_orders(self) -> int:
        return len(self._traces)

    @property
    def executed_count(self) -> int:
        return sum(1 for t in self._traces.values() if t.is_executed)

    @property
    def rejected_count(self) -> int:
        return sum(1 for t in self._traces.values() if t.is_rejected)

    @property
    def skipped_count(self) -> int:
        return sum(1 for t in self._traces.values() if t.is_skipped)

    @property
    def terminal_count(self) -> int:
        return sum(1 for t in self._traces.values() if t.is_terminal)

    @property
    def traces_by_symbol(self) -> Dict[str, List[ExecutionTrace]]:
        out: Dict[str, List[ExecutionTrace]] = {}
        for trace in self._traces.values():
            out.setdefault(trace.symbol, []).append(trace)
        return out

    @property
    def traces_by_state(self) -> Dict[str, List[ExecutionTrace]]:
        out: Dict[str, List[ExecutionTrace]] = {}
        for trace in self._traces.values():
            state = trace.final_status or "created"
            out.setdefault(state, []).append(trace)
        return out

    # -- export -----------------------------------------------------------

    def to_csv(self, path: Optional[str] = None) -> str:
        """Export all events to CSV (string or file)."""
        header = [
            "event_id",
            "order_id",
            "event_type",
            "symbol",
            "side",
            "timestamp",
            "quantity",
            "price",
            "status",
            "source",
            "reasons",
        ]
        rows = [",".join(header)]
        for e in self.all_events():
            rows.append(
                ",".join(
                    [
                        e.event_id,
                        e.order_id,
                        e.event_type,
                        e.symbol,
                        e.side,
                        e.timestamp.isoformat(),
                        str(e.quantity),
                        str(e.price),
                        e.status,
                        e.source,
                        ";".join(e.reasons).replace(",", ";"),
                    ]
                )
            )
        content = "\n".join(rows) + "\n"
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        return content

    def to_json(self, path: Optional[str] = None) -> str:
        """Export all events to JSON (string or file)."""
        payload = [
            {
                "event_id": e.event_id,
                "order_id": e.order_id,
                "event_type": e.event_type,
                "symbol": e.symbol,
                "side": e.side,
                "timestamp": e.timestamp.isoformat(),
                "quantity": e.quantity,
                "price": e.price,
                "status": e.status,
                "source": e.source,
                "reasons": list(e.reasons),
                "has_snapshot": e.snapshot is not None,
            }
            for e in self.all_events()
        ]
        content = json.dumps(payload, indent=2, default=str)
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        return content

    # -- dunder -----------------------------------------------------------

    def __len__(self) -> int:
        return len(self._events)

    def __repr__(self) -> str:
        return f"AuditLog(events={len(self._events)}, orders={len(self._traces)})"


# Backward-compatible alias.
PaperAuditLedger = AuditLog
