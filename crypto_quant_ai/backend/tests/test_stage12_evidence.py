from __future__ import annotations

import csv
import io
import math
import os

import pytest

from crypto_quant_ai.backend.committee.types import CommitteeVerdict, ModelContribution
from crypto_quant_ai.backend.evidence.collector import EvidenceCollector
from crypto_quant_ai.backend.evidence.contradiction import ContradictionDetector
from crypto_quant_ai.backend.evidence.report import EvidenceReporter
from crypto_quant_ai.backend.evidence.types import (
    EvidenceItem,
    EvidenceReport,
    EvidenceSet,
    evidence_hash,
)
from crypto_quant_ai.backend.evidence.verifier import EvidenceVerifier


def test_evidence_item_rejects_nan_and_inf():
    with pytest.raises(ValueError):
        EvidenceItem("research", "risk", False, math.nan, "bad")
    with pytest.raises(ValueError):
        EvidenceItem("research", "risk", False, 0.5, "bad", {"stability": math.inf})


def test_collector_adds_research_opposition_for_low_stability_and_overfit():
    collector = EvidenceCollector(stability_threshold=0.7)
    ev = collector.collect(
        intelligence_report={
            "decision": "BUY",
            "stability": 0.2,
            "overfit_flags": ["sharpe_decay"],
        }
    )
    risk = [i for i in ev.items if i.source == "research" and not i.supports_trade]
    assert len(risk) == 1
    assert risk[0].strength >= 0.5
    assert risk[0].details["stability_threshold"] == 0.7


def test_collector_adds_replay_opposition_with_threshold_details():
    collector = EvidenceCollector(stability_threshold=0.65)
    ev = collector.collect(replay_metrics={"stability": 0.4, "pnl": -1.2, "drawdown": 0.3})
    replay_risk = [i for i in ev.items if i.source == "replay" and not i.supports_trade]
    assert len(replay_risk) == 1
    assert replay_risk[0].details["stability_threshold"] == 0.65
    assert replay_risk[0].strength >= 0.5


def test_contradiction_uses_evidence_threshold_and_detects_active_unstable_combo():
    evidence = EvidenceSet(
        items=[
            EvidenceItem("committee", "committee", True, 0.6, "committee BUY", {"decision": "BUY"}),
            EvidenceItem(
                "research",
                "risk",
                False,
                0.6,
                "unstable",
                {"stability": 0.4, "stability_threshold": 0.7, "overfit_flags": ["x"]},
            ),
        ]
    )
    contradictions = ContradictionDetector().detect(evidence)
    assert any("active committee conflicts" in c for c in contradictions)
    assert all("threshold=0.50" not in c for c in contradictions)


def test_verifier_fail_closed_conditions():
    verifier = EvidenceVerifier(min_items=2)
    insufficient = EvidenceSet(items=[EvidenceItem("committee", "committee", True, 0.9, "only one")])
    result = verifier.verify(insufficient)
    assert result.decision == "NO_TRADE"

    contradictory = EvidenceSet(
        items=[
            EvidenceItem("committee", "committee", True, 0.9, "committee BUY"),
            EvidenceItem(
                "replay",
                "risk",
                False,
                0.9,
                "unstable replay",
                {"stability": 0.2, "stability_threshold": 0.7},
            ),
        ]
    )
    result2 = verifier.verify(contradictory)
    assert result2.decision == "NO_TRADE"
    assert any("contradictions" in r for r in result2.reasons)


def test_verifier_passes_only_when_sufficient_and_consistent():
    verifier = EvidenceVerifier(min_items=2)
    evidence = EvidenceSet(
        items=[
            EvidenceItem("committee", "committee", True, 0.9, "committee BUY"),
            EvidenceItem(
                "replay",
                "replay",
                True,
                0.8,
                "stable replay",
                {"stability": 0.9, "stability_threshold": 0.6},
            ),
            EvidenceItem(
                "research",
                "research",
                True,
                0.8,
                "stable research",
                {"stability": 0.9, "stability_threshold": 0.6, "overfit_flags": []},
            ),
        ]
    )
    result = verifier.verify(evidence)
    assert result.approved is True
    assert result.decision == "PAPER_TRADE"


def test_evidence_hash_stable_and_ignores_dynamic_fields():
    payload1 = {
        "generated_at": "2026-01-01T00:00:00Z",
        "started_at": "2026-01-01T00:00:01Z",
        "items": [{"source": "committee", "strength": 0.8}],
    }
    payload2 = {
        "generated_at": "2027-01-01T00:00:00Z",
        "started_at": "2027-01-01T00:00:01Z",
        "items": [{"source": "committee", "strength": 0.8}],
    }
    assert evidence_hash(payload1) == evidence_hash(payload2)

    payload3 = {
        "generated_at": "2027-01-01T00:00:00Z",
        "items": [{"source": "committee", "strength": 0.7}],
    }
    assert evidence_hash(payload1) != evidence_hash(payload3)


def test_report_markdown_json_csv_and_redaction():
    evidence = EvidenceSet(
        items=[
            EvidenceItem(
                "committee",
                "committee",
                True,
                0.9,
                "committee BUY",
                {"decision": "BUY"},
            ),
            EvidenceItem(
                "research",
                "risk",
                False,
                0.8,
                "risk",
                {"api_key": "should_not_leak", "stability": 0.4, "stability_threshold": 0.7},
            ),
            EvidenceItem(
                "replay",
                "risk",
                False,
                0.7,
                "risk replay",
                {"token_value": "token-secret"},
            ),
        ]
    )
    verification = EvidenceVerifier(min_items=2).verify(evidence)
    report = EvidenceReport(evidence=evidence, verification=verification)

    reporter = EvidenceReporter()
    md = reporter.export_markdown(report)
    js = reporter.export_json(report)
    csv_text = reporter.export_csv(report)

    assert "Stage 12 Evidence Report" in md
    assert "***REDACTED***" in md
    assert "***REDACTED***" in js

    rows = list(csv.reader(io.StringIO(csv_text)))
    assert rows[0] == ["source", "category", "supports_trade", "strength", "summary", "details"]
    sources = {row[0] for row in rows[1:]}
    assert {"committee", "research", "replay"}.issubset(sources)


def test_stage12_offline_smoke_committee_to_report():
    verdict = CommitteeVerdict(
        final_decision="BUY",
        confidence=0.9,
        contributions=[
            ModelContribution("quant", "BUY", 0.8),
            ModelContribution("llm_stub", "BUY", 0.7),
        ],
        conflict=False,
        quorum_met=True,
        routing={"enabled": False, "regime": "unknown"},
        reasoning="committee support",
    )
    collector = EvidenceCollector(stability_threshold=0.7)
    evidence = collector.collect(
        committee_verdict=verdict,
        intelligence_report={
            "decision": "BUY",
            "stability": 0.2,
            "overfit_flags": ["fit"],
        },
        replay_metrics={"stability": 0.3, "pnl": -0.5, "drawdown": 0.2},
    )
    contradictions = ContradictionDetector().detect(evidence)
    verification = EvidenceVerifier(min_items=2).verify(evidence)
    report = EvidenceReporter().export_markdown(EvidenceReport(evidence=evidence, verification=verification))

    assert any(i.source == "committee" and i.supports_trade for i in evidence.items)
    assert any(i.source == "research" and not i.supports_trade for i in evidence.items)
    assert any(i.source == "replay" and not i.supports_trade for i in evidence.items)
    assert contradictions
    assert verification.decision == "NO_TRADE"
    assert "Evidence Report" in report


def test_live_trading_guard_in_evidence_components():
    os.environ["LIVE_TRADING"] = "true"
    try:
        with pytest.raises(RuntimeError):
            EvidenceCollector()
        with pytest.raises(RuntimeError):
            EvidenceVerifier()
        with pytest.raises(RuntimeError):
            EvidenceReporter()
    finally:
        os.environ.pop("LIVE_TRADING", None)
