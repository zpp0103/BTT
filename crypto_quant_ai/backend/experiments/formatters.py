"""Stage 6 — Report formatters: Markdown / JSON / CSV / file export."""

from __future__ import annotations

import csv
import io
import json
import os
from typing import Any

from .types import ExperimentReport


def render_json(report: ExperimentReport) -> str:
    """Serialize the report to JSON. Datetimes become ISO strings."""
    return json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str)


def render_csv(report: ExperimentReport) -> str:
    """Serialize the report to CSV with a stable header and equal-width rows."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    header = [
        "strategy_id",
        "status",
        "rank",
        "final_equity",
        "total_return_pct",
        "max_drawdown_pct",
        "sharpe_ratio",
        "sortino_ratio",
        "win_rate_pct",
        "total_trades",
        "rejected_orders",
        "vs_baseline_return_pct",
        "input_hash",
        "error_message",
    ]
    writer.writerow(header)

    rank_map = {row.strategy_id: row.rank for row in report.comparison}
    base_rows = report.baseline_comparison.get("rows", {})

    for run in report.runs:
        vs_base = ""
        if run.strategy_id in base_rows:
            vs_base = base_rows[run.strategy_id].get("vs_baseline_return_pct", "")
        writer.writerow(
            [
                run.strategy_id,
                run.status.value,
                rank_map.get(run.strategy_id, ""),
                run.final_equity,
                run.total_return_pct,
                run.max_drawdown_pct,
                run.sharpe_ratio,
                run.sortino_ratio,
                run.win_rate_pct,
                run.total_trades,
                run.rejected_orders,
                vs_base,
                run.input_hash,
                run.error_message,
            ]
        )
    return buf.getvalue()


def render_markdown(report: ExperimentReport) -> str:
    """Render a human-readable Markdown experiment report."""
    lines: list[str] = []
    lines.append(f"# Experiment Report: {report.experiment_id}")
    lines.append("")
    lines.append(f"- **experiment_hash**: `{report.experiment_hash}`")
    lines.append(f"- **generated_at**: {report.generated_at.isoformat()}")
    lines.append(
        f"- **runs**: {report.completed} completed, "
        f"{report.failed} failed, {report.skipped} skipped"
    )
    lines.append("")

    lines.append("## Replay Config")
    lines.append("")
    rc = report.config.get("replay_config", {})
    lines.append(f"- symbol: {rc.get('symbol')}")
    lines.append(f"- initial_cash: {rc.get('initial_cash')}")
    lines.append(f"- fee_bps: {rc.get('fee_bps')}")
    lines.append(f"- slippage_bps: {rc.get('slippage_bps')}")
    lines.append(f"- paper_trading: {rc.get('paper_trading')}")
    lines.append("")

    lines.append("## Strategies")
    lines.append("")
    for sid in report.strategy_ids:
        status = "?"
        for run in report.runs:
            if run.strategy_id == sid:
                status = run.status.value
                break
        inp = report.input_hashes.get(sid, "")
        lines.append(f"- `{sid}` — {status} — input_hash `{inp}`")
    lines.append("")

    lines.append("## Ranking")
    lines.append("")
    if report.comparison:
        lines.append(
            "| rank | strategy | final_equity | return% | "
            "max_dd% | sharpe | sortino | win% | trades | rejected | vs_base% |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for row in report.comparison:
            lines.append(
                f"| {row.rank} | `{row.strategy_id}` | {row.final_equity:.2f} | "
                f"{row.total_return_pct:.2f} | {row.max_drawdown_pct:.2f} | "
                f"{row.sharpe_ratio:.4f} | {row.sortino_ratio:.4f} | "
                f"{row.win_rate_pct:.2f} | {row.total_trades} | "
                f"{row.rejected_orders} | {row.vs_baseline_return_pct:.2f} |"
            )
    else:
        lines.append("_No completed strategies to rank._")
    lines.append("")

    lines.append("## Baseline")
    lines.append("")
    if report.baseline_comparison.get("available"):
        lines.append(
            f"Baseline strategy: `{report.baseline_comparison.get('baseline_id')}`"
        )
        for sid, row in report.baseline_comparison.get("rows", {}).items():
            lines.append(
                f"- `{sid}`: vs_baseline_return_pct = "
                f"{row.get('vs_baseline_return_pct')}"
            )
    else:
        reason = report.baseline_comparison.get("reason", "unavailable")
        lines.append(f"Baseline unavailable: {reason}")
    lines.append("")

    lines.append("## Failures")
    lines.append("")
    if report.error_messages:
        for sid, msg in report.error_messages.items():
            lines.append(f"- `{sid}`: {msg}")
    else:
        lines.append("_No failures._")
    lines.append("")

    lines.append("## Safety")
    lines.append("")
    lines.append(report.safety_summary)
    lines.append("")

    return "\n".join(lines)


def export_report(report: ExperimentReport, output_dir: str) -> dict:
    """Write Markdown, JSON and CSV files to ``output_dir`` (local only)."""
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.join(output_dir, f"experiment_{report.experiment_id}")
    paths = {
        "markdown": f"{base}.md",
        "json": f"{base}.json",
        "csv": f"{base}.csv",
    }
    with open(paths["markdown"], "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report))
    with open(paths["json"], "w", encoding="utf-8") as fh:
        fh.write(render_json(report))
    with open(paths["csv"], "w", encoding="utf-8") as fh:
        fh.write(render_csv(report))
    return paths
