"""Stage 10 - formatters: LLM contribution report (explainability)."""
from __future__ import annotations

from typing import Any


def render_llm_contribution(report: Any) -> str:
    """Render the LLM brain's contribution within an OrchestratorReport.

    Shows which brains voted, what the LLM suggested, whether it was adopted,
    and the fallback reason. Always safe and read-only.
    """
    lines = ["## LLM Contribution", ""]
    llm = None
    others = []
    for r in getattr(report, "brain_results", []) or []:
        if r.brain_name == "llm":
            llm = r
        else:
            others.append(r.brain_name)
    lines.append(f"- Other brains: {', '.join(others) or 'none'}")
    if llm is None:
        lines.append("- LLM brain: not injected (disabled by default).")
        return "\n".join(lines)
    a = llm.analysis
    lines.append(f"- LLM decision: **{a.decision}** (confidence {a.confidence:.2f})")
    lines.append(f"- LLM reasoning: {a.reasoning}")
    if a.warnings:
        lines.append(f"- LLM warnings: {', '.join(a.warnings)}")
    return "\n".join(lines)


def explain_llm_decision(report: Any) -> str:
    return render_llm_contribution(report)
