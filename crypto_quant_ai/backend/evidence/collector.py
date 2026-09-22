from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_quant_ai.backend.llm.safety import assert_paper_only

from .types import EvidenceItem, EvidenceSet


@dataclass
class EvidenceCollector:
    stability_threshold: float = 0.6

    def __post_init__(self) -> None:
        assert_paper_only()

    def collect(
        self,
        *,
        intelligence_report: dict[str, Any] | None = None,
        committee_verdict: Any | None = None,
        model_contributions: list[Any] | None = None,
        replay_metrics: dict[str, Any] | None = None,
    ) -> EvidenceSet:
        assert_paper_only()
        evidence = EvidenceSet()
        self._collect_committee(evidence, committee_verdict)
        self._collect_models(evidence, model_contributions or [])
        self._collect_research(evidence, intelligence_report or {})
        self._collect_replay(evidence, replay_metrics or {})
        return evidence

    def _collect_committee(self, evidence: EvidenceSet, verdict: Any | None) -> None:
        if verdict is None:
            return
        decision = self._read_verdict_field(verdict, "final_decision")
        confidence = self._read_verdict_field(verdict, "confidence", 0.0)
        quorum = self._read_verdict_field(verdict, "quorum_met", False)
        conflict = self._read_verdict_field(verdict, "conflict", False)

        if decision in ("BUY", "SELL") and quorum and not conflict:
            evidence.add(
                EvidenceItem(
                    source="committee",
                    category="committee",
                    supports_trade=True,
                    strength=max(0.0, min(1.0, float(confidence))),
                    summary="committee active decision supports paper trade",
                    details={
                        "decision": decision,
                        "quorum_met": bool(quorum),
                        "conflict": bool(conflict),
                    },
                )
            )

    def _read_verdict_field(self, verdict: Any, field: str, default: Any = None) -> Any:
        value = getattr(verdict, field, None)
        if value is not None:
            return value
        if isinstance(verdict, dict):
            return verdict.get(field, default)
        return default

    def _collect_models(self, evidence: EvidenceSet, contributions: list[Any]) -> None:
        for c in contributions:
            decision = getattr(c, "decision", None)
            if decision is None and isinstance(c, dict):
                decision = c.get("decision")
            if decision not in ("BUY", "SELL"):
                continue
            name = getattr(c, "model_name", None)
            if name is None and isinstance(c, dict):
                name = c.get("model_name", "unknown")
            confidence = getattr(c, "confidence", None)
            if confidence is None and isinstance(c, dict):
                confidence = c.get("confidence", 0.0)
            evidence.add(
                EvidenceItem(
                    source="model",
                    category="model",
                    supports_trade=True,
                    strength=max(0.0, min(1.0, float(confidence or 0.0))),
                    summary="model contribution supports active trade",
                    details={"model_name": name or "unknown", "decision": decision},
                )
            )

    def _collect_research(self, evidence: EvidenceSet, report: dict[str, Any]) -> None:
        if not report:
            return
        stability = float(report.get("stability", 1.0))
        overfit_flags = list(report.get("overfit_flags") or [])
        decision = report.get("decision", "NO_TRADE")
        details = {
            "stability": stability,
            "stability_threshold": self.stability_threshold,
            "overfit_flags": overfit_flags,
        }

        if decision in ("BUY", "SELL") and stability >= self.stability_threshold and not overfit_flags:
            evidence.add(
                EvidenceItem(
                    source="research",
                    category="research",
                    supports_trade=True,
                    strength=max(0.5, min(1.0, stability)),
                    summary="research indicates stable active setup",
                    details=details,
                )
            )

        if stability < self.stability_threshold or overfit_flags:
            penalty = (self.stability_threshold - stability) if stability < self.stability_threshold else 0.0
            opposition = max(0.5, 1.0 - stability + penalty)
            if overfit_flags:
                opposition = min(1.0, opposition + 0.2 * min(2, len(overfit_flags)))
            evidence.add(
                EvidenceItem(
                    source="research",
                    category="risk",
                    supports_trade=False,
                    strength=min(1.0, opposition),
                    summary="research stability/overfit risk opposes active trade",
                    details=details,
                )
            )

    def _collect_replay(self, evidence: EvidenceSet, metrics: dict[str, Any]) -> None:
        if not metrics:
            return
        stability = float(metrics.get("stability", 1.0))
        details = {
            "stability": stability,
            "stability_threshold": self.stability_threshold,
            "drawdown": metrics.get("drawdown"),
            "pnl": metrics.get("pnl"),
        }
        if stability < self.stability_threshold:
            penalty = self.stability_threshold - stability
            opposition = max(0.5, 1.0 - stability + penalty)
            evidence.add(
                EvidenceItem(
                    source="replay",
                    category="risk",
                    supports_trade=False,
                    strength=min(1.0, opposition),
                    summary="replay stability below threshold opposes active trade",
                    details=details,
                )
            )
        elif metrics.get("pnl", 0.0) > 0:
            evidence.add(
                EvidenceItem(
                    source="replay",
                    category="replay",
                    supports_trade=True,
                    strength=max(0.5, min(1.0, stability)),
                    summary="replay metrics support active trade under paper-only mode",
                    details=details,
                )
            )
