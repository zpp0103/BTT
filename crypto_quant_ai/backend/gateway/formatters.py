"""Stage 7 (Plan A) - Report formatters (markdown / json / csv)."""
from __future__ import annotations

import csv
import io
import json
from typing import Optional

from crypto_quant_ai.backend.gateway.report import GatewayReport


def to_markdown(report: GatewayReport) -> str:
    lines = [
        "# Stage 7 Paper Gateway Report",
        "",
        f"- Symbol: {report.config.symbol}",
        f"- Timeframe: {report.config.timeframe}",
        f"- Strategy: {report.config.strategy_id}",
        f"- Status: {report.status.value}",
        f"- Gateway hash: {report.gateway_hash}",
        f"- Submitted: {report.total_submitted}",
        f"- Executed: {report.total_executed}",
        f"- Rejected: {report.total_rejected}",
        f"- Skipped: {report.total_skipped}",
        f"- Circuit breaker tripped: {report.circuit_breaker_tripped}",
        f"- Reconciliation OK: {report.reconciliation_ok} "
        f"(mismatches: {report.reconciliation_mismatches})",
        "",
        "## Alerts",
    ]
    if report.alerts:
        for a in report.alerts:
            lines.append(f"- [{a.level}] {a.message}")
    else:
        lines.append("- (none)")
    return "\n".join(lines) + "\n"


def to_json(report: GatewayReport) -> str:
    return json.dumps(report.to_json(), indent=2, default=str)


def to_csv(report: GatewayReport) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["field", "value"])
    for key, value in report.to_json().items():
        writer.writerow([key, json.dumps(value, default=str)])
    return buf.getvalue()


def export_report(
    report: GatewayReport, fmt: str = "markdown", path: Optional[str] = None
) -> str:
    fmt = (fmt or "markdown").lower()
    if fmt == "json":
        content = to_json(report)
    elif fmt == "csv":
        content = to_csv(report)
    else:
        content = to_markdown(report)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    return content
