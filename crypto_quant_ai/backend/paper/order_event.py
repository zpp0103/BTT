"""Stage 3.4 — Order lifecycle events for paper audit trail.

This module defines the event type that records every state change of a
paper order from creation to closure. Events are plain local Python
objects; they never touch the network, an exchange, or any credential.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

from crypto_quant_ai.backend.paper.snapshot import PortfolioSnapshot

# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() in ("true", "1")
if LIVE_TRADING:
    raise RuntimeError(
        "Paper audit requires LIVE_TRADING to be disabled."
        " Disable it to continue."
    )


# ---------------------------------------------------------------------------
# Event type definitions
# ---------------------------------------------------------------------------

# Allowed event types in the order lifecycle.
#   created -> validated -> accepted -> executed -> closed
#                              -> rejected
#                              -> skipped (no-trade / veto)
OrderEventType = Literal[
    "created",
    "validated",
    "accepted",
    "rejected",
    "executed",
    "closed",
    "skipped",
]

# Actors / sources that may originate an event.
OrderActor = Literal[
    "paper_executor",
    "risk_gate",
    "audit_log",
]

# Events that represent a terminal decision (no further state change).
_TERMINAL_EVENTS = {"rejected", "closed", "skipped"}


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class OrderEvent:
    """Immutable record of a single order state transition.

    Fields
    ------
    event_id : stable local identifier (auto-generated).
    order_id : groups all events belonging to one order.
    event_type : one of ``OrderEventType``.
    symbol : trading symbol (must be non-empty).
    side : "buy" or "sell".
    timestamp : event time (mandatory, must be a valid datetime).
    quantity : order quantity (finite, non-negative).
    price : order price (finite, non-negative).
    status : human-readable status (defaults to ``event_type``).
    reasons : list of human-readable reasons / notes.
    source : actor that produced the event (paper_executor / risk_gate / audit_log).
    snapshot : optional local portfolio snapshot captured with the event.
    """

    event_id: str
    order_id: str
    event_type: OrderEventType
    symbol: str
    side: str
    timestamp: datetime
    quantity: float = 0.0
    price: float = 0.0
    status: str = ""
    reasons: list[str] = field(default_factory=list)
    source: OrderActor = "audit_log"
    snapshot: Optional[PortfolioSnapshot] = None

    def __post_init__(self) -> None:
        # timestamp must be present and valid
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a valid datetime")
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)

        if not self.order_id or not self.order_id.strip():
            raise ValueError("order_id must not be blank")
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        if self.side not in ("buy", "sell", ""):
            raise ValueError("side must be 'buy' or 'sell' (or '' when undetermined)")
        if self.event_type not in (
            "created",
            "validated",
            "accepted",
            "rejected",
            "executed",
            "closed",
            "skipped",
        ):
            raise ValueError(f"invalid event_type: {self.event_type!r}")

        # quantity / price must be finite and non-negative
        for name, val in (("quantity", self.quantity), ("price", self.price)):
            if not isinstance(val, (int, float)) or val != val or abs(val) == float("inf"):
                raise ValueError(f"{name} must be finite")
            if val < 0:
                raise ValueError(f"{name} must be non-negative")

        # rejected events must carry an explicit reason
        if self.event_type == "rejected" and not self.reasons:
            raise ValueError("rejected event must include at least one reason")

        # default status mirrors the event type when not supplied
        if not self.status:
            self.status = self.event_type

    @property
    def is_terminal(self) -> bool:
        return self.event_type in _TERMINAL_EVENTS


def make_event_id() -> str:
    """Return a short unique event id."""
    return uuid.uuid4().hex[:12]