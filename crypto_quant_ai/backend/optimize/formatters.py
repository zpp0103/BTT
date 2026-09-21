"""Stage 8 - report formatters (markdown / json / csv)."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from .types import OptimizationResult


def render_json(result: OptimizationResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str)


def render_markdown(result: OptimizationResult) -> str:
    lines: list[str] = []
    lines.append("# Stage 8 Optimization Report")
    lines.append("")
    lines.append(f"- Objective: {result.objective}")
    lines.append(f"- Search method: {result.search.get('method')}")
    lines.append(f"- Candidates evaluated: {len(result.candidates)}")
    lines.append(f"- Best params: {result.best_params}")
    lines.append(f"- Best in-sample metrics: {result.best_metrics}")
    lines.append("")
    lines.append("## Walk-forward windows")
    for w in result.windows:
        lines.append(
            f"- W{w.index}: train[{w.train_start}:{w.train_end}] "
            f"test[{w.test_start}:{w.test_end}] "
            f"OOS sharpe={w.out_of_sample.get('sharpe_ratio', 0.0):.4f}"
        )
    lines.append("")
    lines.append("## Robustness")
    lines.append(json.dumps(result.robustness, indent=2, default=str))
    return "\n".join(lines)


def render_csv(result: OptimizationResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "param_set", "params", "sharpe_ratio", "total_return_pct",
        "max_drawdown_pct", "final_equity", "is_completed",
    ])
    for i, c in enumerate(result.candidates):
        writer.writerow([
            i,
            json.dumps(c.params, default=str),
            c.metrics.get("sharpe_ratio", 0.0),
            c.metrics.get("total_return_pct", 0.0),
            c.metrics.get("max_drawdown_pct", 0.0),
            c.metrics.get("final_equity", 0.0),
            c.is_completed,
        ])
    return buf.getvalue()


def export_report(result: OptimizationResult, output_dir: str = "output") -> dict[str, str]:
    from pathlib import Path
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = {
        "markdown": str(out / "stage8_report.md"),
        "json": str(out / "stage8_report.json"),
        "csv": str(out / "stage8_report.csv"),
    }
    out.joinpath("stage8_report.md").write_text(render_markdown(result), encoding="utf-8")
    out.joinpath("stage8_report.json").write_text(render_json(result), encoding="utf-8")
    out.joinpath("stage8_report.csv").write_text(render_csv(result), encoding="utf-8")
    return written
