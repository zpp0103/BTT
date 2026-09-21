"""Stage 8 - Local Parameter Optimization & Walk-Forward Validation.

Paper-only research layer. No external venue connection, no orders, no network.
Reuses Stage 4 BacktestSimulator, Stage 5 ReplayConfig, Stage 6 shapes.
"""
from .types import (
    ParamSpec,
    ParamSpace,
    SearchConfig,
    WalkForwardConfig,
    CandidateResult,
    WindowResult,
    RobustnessReport,
    OptimizationResult,
)
from .search import run_optimization, optimize
from .report import build_result
from .formatters import render_markdown, render_json, render_csv, export_report

__all__ = [
    "ParamSpec",
    "ParamSpace",
    "SearchConfig",
    "WalkForwardConfig",
    "CandidateResult",
    "WindowResult",
    "RobustnessReport",
    "OptimizationResult",
    "run_optimization",
    "optimize",
    "build_result",
    "render_markdown",
    "render_json",
    "render_csv",
    "export_report",
]
