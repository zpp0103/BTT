from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass
from typing import Any

from crypto_quant_ai.backend.llm.safety import assert_paper_only

from .types import EvidenceReport

_REDACTED = "***REDACTED***"
_SENSITIVE_MARKERS = ("secret", "token", "password", "credential", "api_key", "api_secret")


@dataclass
class EvidenceReporter:
    def __post_init__(self) -> None:
        assert_paper_only()

    def export_markdown(self, report: EvidenceReport) -> str:
        assert_paper_only()
        lines = [
            "# Stage 12 Evidence Report",
            "",
            f"- decision: **{report.verification.decision}**",
            f"- approved: {report.verification.approved}",
            f"- evidence_hash: `{report.verification.evidence_hash}`",
            f"- contradictions: {len(report.verification.contradictions)}",
            "",
            "## Evidence Items",
            "",
        ]
        for item in report.evidence.items:
            lines.append(
                f"- [{item.source}/{item.category}] supports_trade={item.supports_trade} strength={item.strength:.2f}"
            )
            lines.append(f"  - summary: {item.summary}")
            lines.append(f"  - details: {self._redact(item.details)}")
        return "\n".join(lines)

    def export_json(self, report: EvidenceReport) -> str:
        assert_paper_only()
        payload = asdict(report)
        payload["evidence"]["items"] = [
            {**item, "details": self._redact(item.get("details", {}))}
            for item in payload["evidence"]["items"]
        ]
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def export_csv(self, report: EvidenceReport) -> str:
        assert_paper_only()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["source", "category", "supports_trade", "strength", "summary", "details"])
        for item in report.evidence.items:
            writer.writerow(
                [
                    item.source,
                    item.category,
                    str(item.supports_trade),
                    f"{item.strength:.6f}",
                    item.summary,
                    json.dumps(self._redact(item.details), ensure_ascii=False, sort_keys=True),
                ]
            )
        return buf.getvalue()

    def _redact(self, value: Any, parent_key: str = "") -> Any:
        if isinstance(value, dict):
            out = {}
            for key, sub in value.items():
                out[key] = self._redact(sub, parent_key=key)
            return out
        if isinstance(value, list):
            return [self._redact(v, parent_key=parent_key) for v in value]
        key_l = parent_key.lower()
        if any(marker in key_l for marker in _SENSITIVE_MARKERS):
            return _REDACTED
        if isinstance(value, str):
            value_l = value.lower()
            if any(marker in value_l for marker in _SENSITIVE_MARKERS):
                return _REDACTED
        return value
