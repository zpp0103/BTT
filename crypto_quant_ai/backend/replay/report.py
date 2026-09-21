from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .types import StrategyReport


def render_markdown(report: StrategyReport) -> str:
    lines = []
    lines.append(f"# {report.title}")
    lines.append("")
    lines.append(f"- Generated at: {report.generated_at.isoformat()}")
    lines.append(f"- Input hash: {report.input_hash}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Total return: {report.summary.total_return}")
    lines.append(f"- Total return %: {report.summary.total_return_pct}")
    lines.append(f"- Max drawdown %: {report.summary.max_drawdown_pct}")
    lines.append(f"- Sharpe: {report.summary.sharpe_ratio}")
    lines.append(f"- Sortino: {report.summary.sortino_ratio}")
    lines.append(f"- Win rate %: {report.summary.win_rate_pct}")
    lines.append(f"- Profit factor: {report.summary.profit_factor}")
    lines.append(f"- Final equity: {report.summary.final_equity}")
    lines.append("")
    lines.append("## Audit")
    lines.append(f"- Total orders: {report.audit.total_orders}")
    lines.append(f"- Executed: {report.audit.executed}")
    lines.append(f"- Rejected: {report.audit.rejected}")
    lines.append(f"- Skipped: {report.audit.skipped}")
    return "\n".join(lines)


def render_json(report: StrategyReport) -> str:
    return report.to_json()


def render_csv(report: StrategyReport) -> str:
    rows = []
    rows.append("timestamp,action,price,quantity,fee,slippage_cost")
    for trade in report.trades:
        rows.append(
            ",".join(
                [
                    str(trade.get("timestamp", "")),
                    str(trade.get("action", "")),
                    str(trade.get("price", "")),
                    str(trade.get("quantity", "")),
                    str(trade.get("fee", "")),
                    str(trade.get("slippage_cost", "")),
                ]
            )
        )
    return "\n".join(rows)


def export_report(report: StrategyReport, output_dir: str = "output") -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(exist_ok=True, parents=True)
    md = out / "strategy_report.md"
    js = out / "strategy_report.json"
    csv = out / "strategy_report.csv"

    md.write_text(render_markdown(report), encoding="utf-8")
    js.write_text(render_json(report), encoding="utf-8")
    csv.write_text(render_csv(report), encoding="utf-8")

    return {
        "markdown": str(md),
        "json": str(js),
        "csv": str(csv),
    }
