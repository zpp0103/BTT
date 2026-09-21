"""Stage 9 - formatters: markdown / json / csv + export."""
from __future__ import annotations

import csv
import io
import json
import os
from typing import Any

from .report import IntelligenceReport


def render_markdown(report: IntelligenceReport) -> str:
    r = report
    lines = ["# Stage 9 Intelligence Report", ""]
    lines.append(f"- Symbol: **{r.symbol}**")
    lines.append(f"- Generated: {r.generated_at.isoformat()}")
    lines.append("")
    lines.append("## Market State")
    lines.append(f"- Regime: **{r.market_state.regime.value}** (confidence {r.market_state.confidence:.2f})")
    lines.append(f"- {r.market_state.summary}")
    lines.append("")
    lines.append("## Decision Brief")
    lines.append(f"- Action: **{r.decision.action}** (confidence {r.decision.confidence:.2f})")
    lines.append(f"- Supporters: {', '.join(r.decision.supporters) or 'none'}")
    lines.append(f"- Opponents: {', '.join(r.decision.opponents) or 'none'}")
    lines.append(f"- Rationale: {r.decision.rationale}")
    if r.decision.failure_conditions:
        lines.append("- Failure conditions:")
        for fc in r.decision.failure_conditions:
            lines.append(f"  - {fc}")
    lines.append("")
    lines.append("## Research")
    lines.append(f"- Objective: {r.research.objective}")
    lines.append(f"- Candidates: {r.research.candidates_count} (completed {r.research.completed_count})")
    lines.append(f"- Best params: `{r.research.best_params}`")
    lines.append(f"- Best metrics: `{r.research.best_metrics}`")
    lines.append(f"- Stability score: {r.research.stability_score:.3f}")
    if r.research.overfit_flags:
        lines.append("- Overfit flags:")
        for of in r.research.overfit_flags:
            lines.append(f"  - {of}")
    lines.append("")
    lines.append("## Recommendation")
    lines.append(r.recommendation)
    if r.risk_notes:
        lines.append("")
        lines.append("## Risk Notes")
        for rn in r.risk_notes:
            lines.append(f"- {rn}")
    return "\n".join(lines)


def _serialize(o: Any) -> Any:
    if hasattr(o, "value"):  # Enum
        return o.value
    if hasattr(o, "__dataclass_fields__"):
        return {k: _serialize(v) for k, v in o.__dict__.items()}
    if isinstance(o, dict):
        return {k: _serialize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_serialize(v) for v in o]
    return o


def render_json(report: IntelligenceReport) -> str:
    return json.dumps(_serialize(report), indent=2, ensure_ascii=False, default=str)


def render_csv(report: IntelligenceReport) -> str:
    rows = [
        ["symbol", report.symbol],
        ["regime", report.market_state.regime.value],
        ["market_confidence", f"{report.market_state.confidence:.4f}"],
        ["action", report.decision.action],
        ["decision_confidence", f"{report.decision.confidence:.4f}"],
        ["objective", report.research.objective],
        ["candidates", str(report.research.candidates_count)],
        ["completed", str(report.research.completed_count)],
        ["stability_score", f"{report.research.stability_score:.4f}"],
        ["overfit_flags", str(len(report.research.overfit_flags))],
        ["recommendation", report.recommendation],
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["field", "value"])
    for k, v in rows:
        w.writerow([k, v])
    return buf.getvalue()


def export_report(report: IntelligenceReport, output_dir: str = "output") -> dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    paths: dict[str, str] = {}
    md = os.path.join(output_dir, "intelligence_report.md")
    js = os.path.join(output_dir, "intelligence_report.json")
    cv = os.path.join(output_dir, "intelligence_report.csv")
    with open(md, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))
    paths["markdown"] = md
    with open(js, "w", encoding="utf-8") as f:
        f.write(render_json(report))
    paths["json"] = js
    with open(cv, "w", encoding="utf-8", newline="") as f:
        f.write(render_csv(report))
    paths["csv"] = cv
    return paths
