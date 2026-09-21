from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crypto_quant_ai.backend.decision.brain_orchestrator import OrchestratorReport


def render_llm_contribution(report: "OrchestratorReport") -> str:
    """Explain the LLM brain's contribution to an orchestrator report."""
    llm = None
    for r in report.brain_results:
        if r.brain_name == "llm":
            llm = r
            break
    if llm is None:
        return "## LLM contribution\n\nNo LLM brain was present in this report."
    a = llm.analysis
    adopted = "yes" if report.final_decision.decision == a.decision else "no"
    lines = [
        "## LLM contribution",
        "",
        "- Brain: `llm`",
        f"- Decision: `{a.decision}` (confidence {a.confidence:.2f})",
        f"- Adopted into final: {adopted}",
        f"- Reasoning: {a.reasoning or '(none)'}",
    ]
    if a.warnings:
        lines.append("- Warnings:")
        for w in a.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)
