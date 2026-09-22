from __future__ import annotations

import os

if os.environ.get("LIVE_TRADING", "false").lower() == "true":
    raise RuntimeError(
        "LIVE_TRADING enabled; paper-only safety guard tripped in evidence package."
    )

from .collector import EvidenceCollector
from .contradiction import ContradictionDetector
from .report import EvidenceReporter
from .types import EvidenceItem, EvidenceReport, EvidenceSet, VerificationResult, evidence_hash
from .verifier import EvidenceVerifier

__all__ = [
    "EvidenceItem",
    "EvidenceSet",
    "VerificationResult",
    "EvidenceReport",
    "EvidenceCollector",
    "ContradictionDetector",
    "EvidenceVerifier",
    "EvidenceReporter",
    "evidence_hash",
]
