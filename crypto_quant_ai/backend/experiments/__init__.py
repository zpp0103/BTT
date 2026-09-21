"""Stage 6 — Local Experiment Runner & Comparative Strategy Analysis.

Pure local experiment layer built on top of Stage 5 (StrategyReplayer) and
Stage 4 (BacktestSimulator / metrics / audit). No network, no exchange, no
real orders, no automatic trading. Paper trading only.
"""

from .types import (
    ExperimentConfig,
    ExperimentRun,
    ExperimentReport,
    ComparisonRow,
    RunStatus,
    compute_experiment_hash,
    experiment_payload,
)
from .runner import ExperimentRunner, ExperimentResult
from .comparison import ComparisonEngine
from .report import build_report
from .formatters import (
    render_markdown,
    render_json,
    render_csv,
    export_report,
)

__all__ = [
    "ExperimentConfig",
    "ExperimentRun",
    "ExperimentReport",
    "ComparisonRow",
    "RunStatus",
    "compute_experiment_hash",
    "experiment_payload",
    "ExperimentRunner",
    "ExperimentResult",
    "ComparisonEngine",
    "build_report",
    "render_markdown",
    "render_json",
    "render_csv",
    "export_report",
]
