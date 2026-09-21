"""Stage 6 — Local Experiment Runner.

Runs multiple StrategySpec locally, each in full isolation (own ReplayConfig
instance, StrategyReplayer, PaperAccount, AuditLog, BacktestSimulator,
EquityTracker, TradeLedger). No network, no exchange, no real orders.
"""

from __future__ import annotations

import os
from typing import Any, Optional, Sequence

from crypto_quant_ai.backend.backtest.types import BacktestStatus
from crypto_quant_ai.backend.replay.engine import StrategyReplayer

from .types import (
    ExperimentConfig,
    ExperimentRun,
    ExperimentReport,
    RunStatus,
    compute_experiment_hash,
)


class ExperimentResult:
    """Unified result of an experiment run."""

    def __init__(
        self,
        config: ExperimentConfig,
        experiment_hash: str,
        runs: list,
        comparison: list,
        report: ExperimentReport,
        replayers: Optional[list] = None,
    ) -> None:
        self.config = config
        self.experiment_hash = experiment_hash
        self.runs = runs
        self.comparison = comparison
        self.report = report
        self.replayers = replayers or []

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.config.experiment_id,
            "experiment_hash": self.experiment_hash,
            "runs": [r.strategy_id for r in self.runs],
            "report": self.report.to_dict(),
        }


class ExperimentRunner:
    """Run a multi-strategy experiment over local candles."""

    def __init__(self) -> None:
        self.replayers: list = []

    @staticmethod
    def _live_guard() -> None:
        if os.environ.get("LIVE_TRADING", "false").lower() == "true":
            raise RuntimeError(
                "ExperimentRunner requires paper mode; disable LIVE_TRADING to continue"
            )

    def run(self, candles: Sequence[Any], config: ExperimentConfig) -> ExperimentResult:
        """Run every strategy in ``config`` over ``candles``.

        Returns an ExperimentResult with runs, comparison rows and report.
        Each strategy gets a fresh StrategyReplayer (own account / audit / sim).
        A failing strategy is recorded as FAILED (never faked as COMPLETED);
        with fail_fast=True the remaining strategies are marked SKIPPED.
        """
        self._live_guard()
        self.replayers = []

        experiment_hash = compute_experiment_hash(config, candles)
        # Never mutate the caller's candle sequence.
        candles_copy = list(candles)

        runs: list = []
        strategy_list = list(config.strategies)
        failed = False

        for idx, strategy in enumerate(strategy_list):
            if config.fail_fast and failed:
                runs.append(
                    ExperimentRun(strategy_id=strategy.id, status=RunStatus.SKIPPED)
                )
                continue
            try:
                replayer = StrategyReplayer(config.replay_config, strategy)
                result_dict = replayer.run(candles_copy)
                result = result_dict["result"]
                if (not result.is_completed) or (result.metrics is None):
                    raise RuntimeError(result.error_message or "replay failed")
                report = result_dict["report"]
                metrics = result.metrics
                run = ExperimentRun(
                    strategy_id=strategy.id,
                    status=RunStatus.COMPLETED,
                    input_hash=result_dict.get("input_hash", ""),
                    final_equity=getattr(
                        report.summary, "final_equity", float(metrics.final_equity)
                    ),
                    total_return_pct=float(metrics.total_return_pct),
                    max_drawdown_pct=float(metrics.max_drawdown_pct),
                    sharpe_ratio=float(metrics.sharpe_ratio),
                    sortino_ratio=float(metrics.sortino_ratio),
                    win_rate_pct=float(metrics.win_rate_pct),
                    total_trades=int(metrics.total_trades),
                    executed_orders=int(getattr(report.audit, "executed", 0)),
                    rejected_orders=int(getattr(report.audit, "rejected", 0)),
                )
                self.replayers.append(replayer)
                runs.append(run)
            except Exception as exc:  # noqa: BLE001 - record, never swallow as success
                runs.append(
                    ExperimentRun(
                        strategy_id=strategy.id,
                        status=RunStatus.FAILED,
                        error_message=str(exc),
                    )
                )
                failed = True
                if config.fail_fast:
                    continue

        from .comparison import ComparisonEngine
        from .report import build_report

        engine = ComparisonEngine()
        rows, baseline_comparison = engine.compare(runs, config.baseline_strategy_id)
        report = build_report(
            config, runs, rows, baseline_comparison, experiment_hash
        )
        return ExperimentResult(
            config=config,
            experiment_hash=experiment_hash,
            runs=runs,
            comparison=rows,
            report=report,
            replayers=self.replayers,
        )
