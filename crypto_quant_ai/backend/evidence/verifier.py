from __future__ import annotations

import math
from dataclasses import dataclass

from crypto_quant_ai.backend.llm.safety import assert_paper_only

from .contradiction import ContradictionDetector
from .types import EvidenceSet, VerificationResult, evidence_hash


@dataclass
class EvidenceVerifier:
    min_items: int = 2
    default_stability_threshold: float = 0.6

    def __post_init__(self) -> None:
        assert_paper_only()
        self.detector = ContradictionDetector(self.default_stability_threshold)

    def verify(self, evidence: EvidenceSet) -> VerificationResult:
        assert_paper_only()
        reasons: list[str] = []

        if len(evidence.items) < self.min_items:
            reasons.append("insufficient evidence")

        non_finite = self._has_non_finite(evidence)
        if non_finite:
            reasons.append("non-finite evidence value")

        contradictions = self.detector.detect(evidence)
        if contradictions:
            reasons.append("contradictions detected")

        stability_risk = any(self._has_stability_risk(item) for item in evidence.items)
        if stability_risk:
            reasons.append("low stability or overfit risk")

        has_support = any(i.supports_trade for i in evidence.items)
        if not has_support:
            reasons.append("no supporting trade evidence")

        approved = len(reasons) == 0
        decision = "PAPER_TRADE" if approved else "NO_TRADE"
        return VerificationResult(
            decision=decision,
            approved=approved,
            reasons=reasons,
            contradictions=contradictions,
            evidence_hash=evidence_hash(evidence.to_dict()),
        )

    def _has_stability_risk(self, item) -> bool:
        if item.source not in ("research", "replay"):
            return False
        details = item.details if isinstance(item.details, dict) else {}
        threshold = details.get("stability_threshold", self.default_stability_threshold)
        stability = details.get("stability")
        if isinstance(stability, (int, float)) and isinstance(threshold, (int, float)):
            if float(stability) < float(threshold):
                return True
        return bool(details.get("overfit_flags"))

    def _has_non_finite(self, evidence: EvidenceSet) -> bool:
        for item in evidence.items:
            if not math.isfinite(float(item.strength)):
                return True
            if self._non_finite_nested(item.details):
                return True
        return False

    def _non_finite_nested(self, value) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return not math.isfinite(float(value))
        if isinstance(value, dict):
            return any(self._non_finite_nested(v) for v in value.values())
        if isinstance(value, (list, tuple)):
            return any(self._non_finite_nested(v) for v in value)
        return False
