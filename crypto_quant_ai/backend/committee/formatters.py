"""Stage 11 - Markdown rendering of a CommitteeVerdict."""
from __future__ import annotations

from .types import CommitteeVerdict


def render_committee_report(verdict: CommitteeVerdict) -> str:
    lines = [
        "# Model Committee Verdict",
        "",
        f"- final_decision: **{verdict.final_decision}**",
        f"- confidence: {verdict.confidence:.2f}",
        f"- conflict: {verdict.conflict}",
        f"- quorum_met: {verdict.quorum_met}",
        f"- reasoning: {verdict.reasoning}",
        "",
        "## Contributions",
        "",
    ]
    for c in verdict.contributions:
        lines.append(f"- {c.model_name}: {c.decision} (conf={c.confidence:.2f})")
        if c.reasoning:
            lines.append(f"    - {c.reasoning}")
        for w in c.warnings:
            lines.append(f"    - warning: {w}")
    if verdict.routing.get("enabled"):
        lines.append("")
        lines.append(f"## Routing (regime={verdict.routing.get('regime')})")
        lines.append(f"- kept: {verdict.routing.get('kept')}")
    return "\n".join(lines)
