from __future__ import annotations

from dataclasses import dataclass

from .types import EvidenceItem, EvidenceSet


@dataclass
class ContradictionDetector:
    default_strength_threshold: float = 0.6

    def detect(self, evidence: EvidenceSet) -> list[str]:
        contradictions: list[str] = []
        threshold = self._threshold_from_evidence(evidence.items)

        support = [i for i in evidence.items if i.supports_trade and i.strength >= threshold]
        oppose = [i for i in evidence.items if (not i.supports_trade) and i.strength >= threshold]
        if support and oppose:
            contradictions.append(
                f"strong support/opposition coexist (threshold={threshold:.2f})"
            )

        committee_active = any(
            i.source == "committee" and i.supports_trade for i in evidence.items
        )
        unstable_risk = any(self._is_unstable_risk(i) for i in evidence.items)
        if committee_active and unstable_risk:
            contradictions.append(
                "active committee conflicts with unstable research/replay or overfit risk"
            )

        return contradictions

    def _threshold_from_evidence(self, items: list[EvidenceItem]) -> float:
        thresholds: list[float] = []
        for item in items:
            if isinstance(item.details, dict) and "stability_threshold" in item.details:
                val = item.details.get("stability_threshold")
                if isinstance(val, (int, float)):
                    thresholds.append(float(val))
        if thresholds:
            return max(0.0, min(1.0, max(thresholds)))
        return self.default_strength_threshold

    def _is_unstable_risk(self, item: EvidenceItem) -> bool:
        if item.source not in ("research", "replay"):
            return False
        if item.supports_trade:
            return False
        stability = item.details.get("stability") if isinstance(item.details, dict) else None
        threshold = item.details.get("stability_threshold") if isinstance(item.details, dict) else None
        overfit_flags = item.details.get("overfit_flags") if isinstance(item.details, dict) else None
        unstable = (
            isinstance(stability, (int, float))
            and isinstance(threshold, (int, float))
            and float(stability) < float(threshold)
        )
        return unstable or bool(overfit_flags)
