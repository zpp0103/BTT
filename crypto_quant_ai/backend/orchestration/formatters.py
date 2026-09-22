from __future__ import annotations

import csv
import io
import json
import os
from typing import Any

from crypto_quant_ai.backend.llm.safety import assert_paper_only

from .types import Stage13Report

_REDACTED = "***REDACTED***"
_SENSITIVE_MARKERS = (
    "secret",
    "token",
    "password",
    "credential",
    "api_key",
    "api_secret",
)


def _serialize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _serialize(value.model_dump())
    if hasattr(value, "value") and not isinstance(value, str):
        return getattr(value, "value")
    if hasattr(value, "isoformat") and callable(value.isoformat):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {k: _serialize(v) for k, v in value.__dict__.items()}
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


def _looks_sensitive_value(value: str) -> bool:
    lower = value.lower()
    if not any(marker in lower for marker in _SENSITIVE_MARKERS):
        return False
    if len(value) < 8:
        return False
    return any(ch in value for ch in ("-", "_", "=", ":", "/", "."))


def _redact(value: Any, parent_key: str = "") -> Any:
    key_l = parent_key.lower()
    if any(marker in key_l for marker in _SENSITIVE_MARKERS):
        return _REDACTED
    if isinstance(value, dict):
        return {key: _redact(sub, parent_key=key) for key, sub in value.items()}
    if isinstance(value, list):
        return [_redact(v, parent_key=parent_key) for v in value]
    if isinstance(value, str) and _looks_sensitive_value(value):
        return _REDACTED
    return value


def report_to_dict(report: Stage13Report) -> dict[str, Any]:
    return _redact(_serialize(report))


def render_markdown(report: Stage13Report) -> str:
    assert_paper_only()
    lines = [
        "# Stage 13 Execution Report",
        "",
        f"- symbol: **{report.market_context.symbol}**",
        f"- timeframe: {report.market_context.timeframe}",
        f"- candles: {report.market_context.candles_count}",
        f"- report_hash: `{report.report_hash}`",
        f"- verification_passed: {report.result.verification_passed}",
        f"- gateway_allowed: {report.result.gateway_allowed}",
        f"- executed: {report.result.executed}",
        f"- blocked: {report.result.blocked}",
        f"- block_reason: {report.result.block_reason or 'none'}",
        "",
        "## Intelligence",
        f"- market_regime: **{report.intelligence.market_state.regime.value}**",
        f"- intelligence_action: **{report.intelligence.decision.action}** (conf={report.intelligence.decision.confidence:.2f})",
        f"- recommendation: {_redact(report.intelligence.recommendation)}",
        f"- risk_notes: {_redact(report.intelligence.risk_notes)}",
        "",
        "## Committee",
        f"- final_decision: **{report.committee_verdict.final_decision}**",
        f"- confidence: {report.committee_verdict.confidence:.2f}",
        f"- conflict: {report.committee_verdict.conflict}",
        f"- quorum_met: {report.committee_verdict.quorum_met}",
        f"- reasoning: {_redact(report.committee_verdict.reasoning)}",
        "",
        "## Evidence Verification",
        f"- decision: **{report.verification.decision}**",
        f"- approved: {report.verification.approved}",
        f"- evidence_hash: `{report.verification.evidence_hash}`",
        f"- contradictions: {len(report.contradictions)}",
        f"- reasons: {_redact(report.verification.reasons)}",
        "",
        "## Final Decision",
        f"- decision: **{report.result.final_decision.decision}**",
        f"- confidence: {report.result.final_decision.confidence:.2f}",
        f"- entry: {report.result.final_decision.entry}",
        f"- stop_loss: {report.result.final_decision.stop_loss}",
        f"- take_profit: {report.result.final_decision.take_profit}",
        f"- position_size: {report.result.final_decision.position_size}",
        f"- reasoning: {_redact(report.result.final_decision.reasoning)}",
        "",
        "## Gateway",
    ]
    if report.result.gateway_result is None:
        lines.append("- gateway_result: not submitted")
    else:
        lines.append(f"- executed: {report.result.gateway_result.executed}")
        lines.append(f"- reason: {_redact(report.result.gateway_result.reason)}")
    if report.gateway_report is not None:
        lines.append(f"- total_submitted: {report.gateway_report.total_submitted}")
        lines.append(f"- total_executed: {report.gateway_report.total_executed}")
        lines.append(f"- total_rejected: {report.gateway_report.total_rejected}")
        lines.append(f"- total_skipped: {report.gateway_report.total_skipped}")
    return "\n".join(lines)


def render_json(report: Stage13Report) -> str:
    assert_paper_only()
    return json.dumps(report_to_dict(report), ensure_ascii=False, sort_keys=True)


def render_csv(report: Stage13Report) -> str:
    assert_paper_only()
    rows = [
        ["symbol", report.market_context.symbol],
        ["timeframe", report.market_context.timeframe],
        ["candles_count", str(report.market_context.candles_count)],
        ["verification_passed", str(report.result.verification_passed)],
        ["gateway_allowed", str(report.result.gateway_allowed)],
        ["executed", str(report.result.executed)],
        ["blocked", str(report.result.blocked)],
        ["block_reason", str(_redact(report.result.block_reason))],
        ["committee_decision", report.committee_verdict.final_decision],
        ["verification_decision", report.verification.decision],
        ["final_decision", report.result.final_decision.decision],
        ["report_hash", report.report_hash],
    ]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["field", "value"])
    writer.writerows(rows)
    return buf.getvalue()


def export_report(report: Stage13Report, output_dir: str = "output") -> dict[str, str]:
    assert_paper_only()
    os.makedirs(output_dir, exist_ok=True)
    paths: dict[str, str] = {}
    md = os.path.join(output_dir, "stage13_execution_report.md")
    js = os.path.join(output_dir, "stage13_execution_report.json")
    cv = os.path.join(output_dir, "stage13_execution_report.csv")
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
