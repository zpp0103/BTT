"""Stage 7 (Plan A) - External venue adapter (gated stub) + simulated ledger.

The adapter is a STUB. It never opens a network connection, never reads
credentials, and never submits an order to an external venue. Under LIVE_TRADING=true it refuses
to operate (RuntimeError). In paper mode it mirrors fills into a local
simulated ledger for post-trade reconciliation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from crypto_quant_ai.backend.paper.account import PaperOrder


LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() in ("true", "1")
if LIVE_TRADING:
    raise RuntimeError(
        "External venue adapter requires paper mode. "
        "Disable LIVE_TRADING to continue."
    )


@dataclass(frozen=True)
class VenueFill:
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    timestamp: datetime
    venue: str = "simulated"


class SimulatedVenueLedger:
    """Local, in-memory mirror of venue fills (no network, no credentials)."""

    def __init__(self) -> None:
        self._fills: Dict[str, VenueFill] = {}

    def record(self, fill: VenueFill) -> VenueFill:
        self._fills[fill.order_id] = fill
        return fill

    def get(self, order_id: str) -> Optional[VenueFill]:
        return self._fills.get(order_id)

    def all(self) -> list[VenueFill]:
        return list(self._fills.values())

    def clear(self) -> None:
        self._fills = {}


class ExternalVenueAdapter:
    """Gated stub adapter. No external venue connection; mirrors to a simulated ledger."""

    def __init__(self, ledger: SimulatedVenueLedger | None = None) -> None:
        self._ledger = ledger or SimulatedVenueLedger()

    @property
    def ledger(self) -> SimulatedVenueLedger:
        return self._ledger

    def submit(self, order_id: str, order: PaperOrder) -> VenueFill:
        # Safety boundary: refuse to operate if live trading is enabled. The
        # stub never performs a network call; this check is the guard.
        live = os.environ.get("LIVE_TRADING", "false").lower() in ("true", "1")
        if live:
            raise RuntimeError(
                "Refusing to submit to an external venue in live mode. "
                "This adapter is a stub and must not perform external routing."
            )
        fill = VenueFill(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.price,
            timestamp=order.timestamp,
            venue="simulated",
        )
        self._ledger.record(fill)
        return fill
