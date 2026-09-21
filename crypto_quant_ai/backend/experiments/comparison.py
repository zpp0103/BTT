"""Stage 6 — Comparison engine: deterministic ranking and baseline analysis."""

from __future__ import annotations

import math
from typing import Any, Optional

from .types import (
    ComparisonRow,
    ExperimentRun,
    RunStatus,
)


class ComparisonEngine:
    """Rank completed strategies and compare them against a baseline."""

    @staticmethod
    def _completed(runs: list[ExperimentRun]) -> list[ExperimentRun]:
        return [r for r in runs if r.status == RunStatus.COMPLETED]

    def rank(self, runs: list[ExperimentRun]) -> list[ComparisonRow]:
        """Rank completed runs.

        Sort key (descending priority): sharpe_ratio desc, total_return_pct desc,
        max_drawdown_pct asc, strategy_id asc (stable tie-break).
        """
        completed = self._completed(runs)
        ordered = sorted(
            completed,
            key=lambda r: (
                -float(r.sharpe_ratio),
                -float(r.total_return_pct),
                float(r.max_drawdown_pct),
                str(r.strategy_id),
            ),
        )
        rows: list[ComparisonRow] = []
        for rank, r in enumerate(ordered, start=1):
            rows.append(
                ComparisonRow(
                    strategy_id=r.strategy_id,
                    rank=rank,
                    final_equity=float(r.final_equity),
                    total_return_pct=float(r.total_return_pct),
                    max_drawdown_pct=float(r.max_drawdown_pct),
                    sharpe_ratio=float(r.sharpe_ratio),
                    sortino_ratio=float(r.sortino_ratio),
                    win_rate_pct=float(r.win_rate_pct),
                    total_trades=int(r.total_trades),
                    rejected_orders=int(r.rejected_orders),
                    vs_baseline_return_pct=0.0,
                )
            )
        return rows

    def baseline_compare(
        self, runs: list[ExperimentRun], baseline_id: Optional[str]
    ) -> dict:
        """Compare each completed run against the baseline strategy."""
        completed = {r.strategy_id: r for r in self._completed(runs)}
        if baseline_id is None or baseline_id not in completed:
            return {
                "available": False,
                "baseline_id": baseline_id,
                "reason": "baseline strategy not available or not completed",
                "rows": {},
            }
        base = completed[baseline_id]
        rows: dict = {}
        for sid, r in completed.items():
            if math.isfinite(r.total_return_pct) and math.isfinite(
                base.total_return_pct
            ):
                diff = float(r.total_return_pct) - float(base.total_return_pct)
            else:
                diff = 0.0
            rows[sid] = {
                "vs_baseline_return_pct": diff,
                "vs_baseline_final_equity": float(r.final_equity)
                - float(base.final_equity),
                "is_baseline": sid == baseline_id,
            }
        return {
            "available": True,
            "baseline_id": baseline_id,
            "rows": rows,
        }

    def compare(
        self, runs: list[ExperimentRun], baseline_id: Optional[str]
    ) -> tuple:
        """Return (ranked_rows, baseline_comparison)."""
        rows = self.rank(runs)
        baseline = self.baseline_compare(runs, baseline_id)
        if baseline.get("available"):
            diff_map = {
                sid: row["vs_baseline_return_pct"]
                for sid, row in baseline["rows"].items()
            }
            for row in rows:
                row.vs_baseline_return_pct = diff_map.get(row.strategy_id, 0.0)
        return rows, baseline
