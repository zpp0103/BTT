"""
Stage 4 — Backtest Engine: Equity Tracker

Tracks equity curve and computes drawdown metrics over a backtest run.
Pure local computation, no network calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence


@dataclass
class EquityPoint:
    """A single point on the equity curve."""
    timestamp: datetime
    equity: float
    cash: float
    position_value: float

    def __post_init__(self) -> None:
        if self.equity < 0:
            raise ValueError("equity must be non-negative")
        if self.cash < 0:
            raise ValueError("cash must be non-negative")
        if self.position_value < 0:
            raise ValueError("position_value must be non-negative")


@dataclass
class EquityTracker:
    """
    Tracks the equity curve over a backtest run.

    Records equity points and computes:
    - Maximum drawdown (absolute and percentage)
    - Peak equity
    - Trough equity
    """
    _points: list[EquityPoint] = field(default_factory=list)
    _peak: float = 0.0
    _peak_ts: datetime | None = None
    _trough: float = 0.0
    _trough_ts: datetime | None = None
    _max_drawdown: float = 0.0
    _max_drawdown_pct: float = 0.0

    def record(self, timestamp: datetime, cash: float, position_value: float) -> None:
        """Record a new equity point and update drawdown tracking."""
        equity = cash + position_value
        if equity < 0:
            raise ValueError("equity must be non-negative")

        point = EquityPoint(
            timestamp=timestamp,
            equity=equity,
            cash=cash,
            position_value=position_value,
        )
        self._points.append(point)

        # Update peak
        if equity > self._peak:
            self._peak = equity
            self._peak_ts = timestamp
            # Reset trough when new peak is set
            self._trough = equity
            self._trough_ts = timestamp

        # Update trough (only after a peak is set)
        if self._peak > 0 and equity < self._trough:
            self._trough = equity
            self._trough_ts = timestamp

        # Calculate drawdown from peak
        if self._peak > 0:
            dd = self._peak - equity
            dd_pct = dd / self._peak
            if dd > self._max_drawdown:
                self._max_drawdown = dd
                self._max_drawdown_pct = dd_pct

    @property
    def points(self) -> Sequence[EquityPoint]:
        """Return all recorded equity points (read-only)."""
        return tuple(self._points)

    @property
    def peak_equity(self) -> float:
        """Maximum equity reached."""
        return self._peak

    @property
    def trough_equity(self) -> float:
        """Minimum equity after peak."""
        return self._trough

    @property
    def max_drawdown(self) -> float:
        """Maximum drawdown in absolute terms."""
        return self._max_drawdown

    @property
    def max_drawdown_pct(self) -> float:
        """Maximum drawdown as a fraction of peak (e.g. 0.15 = 15%)."""
        return self._max_drawdown_pct

    @property
    def final_equity(self) -> float:
        """Last recorded equity, or 0 if no points."""
        if not self._points:
            return 0.0
        return self._points[-1].equity

    @property
    def initial_equity(self) -> float:
        """First recorded equity, or 0 if no points."""
        if not self._points:
            return 0.0
        return self._points[0].equity

    def equity_series(self) -> list[tuple[datetime, float]]:
        """Return list of (timestamp, equity) pairs for charting."""
        return [(p.timestamp, p.equity) for p in self._points]

    def reset(self) -> None:
        """Clear all recorded data."""
        self._points.clear()
        self._peak = 0.0
        self._peak_ts = None
        self._trough = 0.0
        self._trough_ts = None
        self._max_drawdown = 0.0
        self._max_drawdown_pct = 0.0
