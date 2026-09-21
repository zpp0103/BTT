from __future__ import annotations

import os
from datetime import datetime

from .types import ReplayConfig


def _live_guard() -> None:
    if os.environ.get("LIVE_TRADING", "false").lower() == "true":
        raise RuntimeError("LIVE_TRADING must be false for replay")


def build_replay_config(**kwargs) -> ReplayConfig:
    _live_guard()
    return ReplayConfig(**kwargs)


def safe_report_formats(formats: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if not formats:
        return ("markdown", "json")
    out = tuple(str(x).lower() for x in formats)
    allowed = {"markdown", "json", "csv"}
    bad = [x for x in out if x not in allowed]
    if bad:
        raise ValueError(f"unsupported report format(s): {bad}")
    return out
