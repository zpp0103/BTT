"""Stage 6 — Report assembly from experiment runs."""

from __future__ import annotations

import dataclasses
from datetime import datetime

from .types import (
    ExperimentConfig,
    ExperimentReport,
    ExperimentRun,
    RunStatus,
)


def build_report(
    config: ExperimentConfig,
    runs: list,
    rows: list,
    baseline_comparison: dict,
    experiment_hash: str,
) -> ExperimentReport:
    """Assemble an ExperimentReport from runs and comparison output."""
    completed = sum(1 for r in runs if r.status == RunStatus.COMPLETED)
    failed = sum(1 for r in runs if r.status == RunStatus.FAILED)
    skipped = sum(1 for r in runs if r.status == RunStatus.SKIPPED)

    input_hashes = {r.strategy_id: r.input_hash for r in runs}
    error_messages = {
        r.strategy_id: r.error_message for r in runs if r.error_message
    }

    config_dict = {
        "experiment_id": config.experiment_id,
        "name": config.name,
        "description": config.description,
        "fail_fast": config.fail_fast,
        "baseline_strategy_id": config.baseline_strategy_id,
        "replay_config": dataclasses.asdict(config.replay_config),
        "strategy_ids": [s.id for s in config.strategies],
    }

    safety_summary = (
        "Local-only experiment runner. No network access. No exchange integration. "
        "No real orders. No credentials. Paper trading only. "
        "LIVE_TRADING=false."
    )

    return ExperimentReport(
        experiment_id=config.experiment_id,
        generated_at=datetime.utcnow(),
        experiment_hash=experiment_hash,
        config=config_dict,
        strategy_ids=[s.id for s in config.strategies],
        completed=completed,
        failed=failed,
        skipped=skipped,
        runs=list(runs),
        comparison=list(rows),
        baseline_strategy_id=config.baseline_strategy_id,
        baseline_comparison=baseline_comparison,
        input_hashes=input_hashes,
        error_messages=error_messages,
        safety_summary=safety_summary,
    )
