"""Stage 3.4 — Local portfolio snapshot model.

A ``PortfolioSnapshot`` is a point-in-time, local view of the paper account.
It never contacts an exchange or a price feed.  Valuation, when requested,
uses only explicitly-supplied local prices (order price or a caller-provided
mapping); it never fetches live market data over the network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from crypto_quant_ai.backend.paper.account import PaperAccount

# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() in ("true", "1")
if LIVE_TRADING:
    raise RuntimeError(
        "Paper snapshots require LIVE_TRADING to be disabled."
        " Disable it to continue."
    )


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


@dataclass
class PortfolioSnapshot:
    """Local, network-free view of paper account state.

    Fields
    ------
    timestamp : capture time.
    cash : free cash (quote currency).
    positions : symbol -> quantity held.
    total_equity : cash + valued exposure (0 valued exposure when no prices).
    total_exposure : valued exposure (0 when no prices supplied).
    exposure_pct : total_exposure / total_equity (0 when equity is 0).
    source : producer of the snapshot ("paper_executor" / "audit_log" / ...).
    """

    timestamp: datetime
    cash: float
    positions: Dict[str, float] = field(default_factory=dict)
    total_equity: float = 0.0
    total_exposure: float = 0.0
    exposure_pct: float = 0.0
    source: str = ""


def snapshot_from_account(
    account: PaperAccount,
    source: str,
    *,
    timestamp: Optional[datetime] = None,
    prices: Optional[Dict[str, float]] = None,
) -> PortfolioSnapshot:
    """Build a ``PortfolioSnapshot`` from a ``PaperAccount``.

    Valuation uses only ``prices`` (a caller-supplied, local mapping of
    symbol -> price).  When no prices are supplied the exposure fields are
    left at 0; this is conservative and never contacts the network.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    positions = {
        sym: float(pos.quantity) for sym, pos in account.positions.items()
    }

    cash = float(account.cash)

    total_exposure = 0.0
    if prices:
        for sym, qty in positions.items():
            price = prices.get(sym)
            if price is not None:
                total_exposure += qty * float(price)

    total_equity = cash + total_exposure
    exposure_pct = (total_exposure / total_equity) if total_equity > 0 else 0.0

    return PortfolioSnapshot(
        timestamp=timestamp,
        cash=cash,
        positions=positions,
        total_equity=total_equity,
        total_exposure=total_exposure,
        exposure_pct=exposure_pct,
        source=source,
    )
