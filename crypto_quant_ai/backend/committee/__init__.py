"""Stage 11 - Model Committee & Policy Layer.

Local, paper-only aggregation of multiple brain / model analyses into a single
policy verdict. No network, no external venue, no order submission. Importing
this package trips a LIVE_TRADING guard.
"""
from __future__ import annotations

import os

if os.environ.get("LIVE_TRADING", "false").lower() == "true":
    raise RuntimeError(
        "LIVE_TRADING enabled; paper-only safety guard tripped in committee package."
    )

from .committee import ModelCommittee
from .formatters import render_committee_report
from .router import route_models
from .types import (
    CommitteeVerdict,
    FusionStrategy,
    ModelCommitteeConfig,
    ModelContribution,
)

__all__ = [
    "ModelCommittee",
    "CommitteeVerdict",
    "FusionStrategy",
    "ModelCommitteeConfig",
    "ModelContribution",
    "render_committee_report",
    "route_models",
]
