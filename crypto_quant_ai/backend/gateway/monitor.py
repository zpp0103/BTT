"""Stage 7 (Plan A) - Monitoring and in-memory alerts (no external delivery)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Alert:
    level: str
    message: str
    timestamp: datetime


class Monitor:
    """Collects run metrics and alerts. No network, no external sink."""

    def __init__(self) -> None:
        self._alerts: List[Alert] = []
        self._submitted = 0
        self._executed = 0
        self._rejected = 0
        self._skipped = 0

    def record_submission(self, decision) -> None:
        self._submitted += 1

    def record_result(self, result, decision) -> None:
        if result.executed:
            self._executed += 1
            return
        if result.veto_blocked:
            self._skipped += 1
            self.emit(AlertLevel.WARN.value, f"Veto blocked: {result.reason}")
            return
        if "Risk gate rejected" in result.reason:
            self._rejected += 1
            self.emit(AlertLevel.WARN.value, f"Risk gate rejected: {result.reason}")
            return
        if result.no_trade:
            self._skipped += 1
            return
        self._rejected += 1

    def emit(self, level: str, message: str) -> Alert:
        alert = Alert(
            level=level, message=message, timestamp=datetime.now(timezone.utc)
        )
        self._alerts.append(alert)
        return alert

    def alerts(self) -> List[Alert]:
        return list(self._alerts)

    def summary(self) -> dict:
        return {
            "submitted": self._submitted,
            "executed": self._executed,
            "rejected": self._rejected,
            "skipped": self._skipped,
            "alerts": len(self._alerts),
        }
