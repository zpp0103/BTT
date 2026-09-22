"""Stage 7 (Plan A) - Circuit breaker and fixed risk parameters."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from crypto_quant_ai.backend.core.models import FinalDecision
from crypto_quant_ai.backend.gateway.types import (
    CircuitBreakerConfig,
    RiskManagerConfig,
)
from crypto_quant_ai.backend.paper.account import PaperAccount
from crypto_quant_ai.backend.paper.risk_gate import PaperRiskGate


@dataclass
class _BreakerState:
    triggered: bool = False
    reason: str = ""
    day_start_equity: float = 0.0
    peak_equity: float = 0.0
    day_realized_loss: float = 0.0

    def reset(self, equity: float) -> None:
        self.triggered = False
        self.reason = ""
        self.day_start_equity = equity
        self.peak_equity = equity
        self.day_realized_loss = 0.0


class CircuitBreaker:
    """Hard-stop guards. Parameters are fixed at construction (no auto-tune)."""

    def __init__(self, config: CircuitBreakerConfig) -> None:
        self._config = config
        self._state = _BreakerState()

    @property
    def config(self) -> CircuitBreakerConfig:
        return self._config

    @property
    def triggered(self) -> bool:
        return self._state.triggered

    @property
    def reason(self) -> str:
        return self._state.reason

    def arm(self, equity: float) -> None:
        self._state.reset(equity)

    def export_state(self) -> dict[str, float | bool | str]:
        return {
            "triggered": self._state.triggered,
            "reason": self._state.reason,
            "day_start_equity": self._state.day_start_equity,
            "peak_equity": self._state.peak_equity,
            "day_realized_loss": self._state.day_realized_loss,
        }

    def restore_state(self, state: dict) -> None:
        if not isinstance(state, dict):
            raise ValueError("circuit breaker state must be a dict")
        triggered = bool(state.get("triggered", False))
        reason = str(state.get("reason", ""))
        day_start_equity = float(state.get("day_start_equity", 0.0))
        peak_equity = float(state.get("peak_equity", 0.0))
        day_realized_loss = float(state.get("day_realized_loss", 0.0))
        for name, value in (
            ("day_start_equity", day_start_equity),
            ("peak_equity", peak_equity),
            ("day_realized_loss", day_realized_loss),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        self._state.triggered = triggered
        self._state.reason = reason
        self._state.day_start_equity = day_start_equity
        self._state.peak_equity = peak_equity
        self._state.day_realized_loss = day_realized_loss

    def pre_trade(
        self,
        decision: FinalDecision,
        account: PaperAccount,
        reference_price: Optional[float] = None,
    ) -> tuple[bool, str]:
        """Return (blocked, reason). Once tripped, always blocks."""
        if self._state.triggered:
            return True, self._state.reason
        notional = (
            float(decision.position_size)
            if (decision.position_size and decision.position_size > 0)
            else 0.0
        )
        if notional > self._config.max_order_notional:
            self._trip(
                f"per-order notional {notional:.2f} exceeds limit "
                f"{self._config.max_order_notional:.2f}"
            )
            return True, self._state.reason
        if (
            reference_price
            and decision.entry
            and decision.entry > 0
            and reference_price > 0
        ):
            move = abs(decision.entry - reference_price) / reference_price
            if move > self._config.price_anomaly_pct:
                self._trip(
                    f"price move {move:.2%} exceeds anomaly band "
                    f"{self._config.price_anomaly_pct:.2%}"
                )
                return True, self._state.reason
        return False, ""

    def post_trade(self, equity: float) -> None:
        if self._state.triggered:
            return
        self._state.peak_equity = max(self._state.peak_equity, equity)
        if equity < self._state.day_start_equity:
            self._state.day_realized_loss = self._state.day_start_equity - equity
        if self._state.day_realized_loss > self._config.daily_loss_limit:
            self._trip(
                f"daily loss {self._state.day_realized_loss:.2f} exceeds limit "
                f"{self._config.daily_loss_limit:.2f}"
            )
            return
        if self._state.peak_equity > 0:
            dd = (self._state.peak_equity - equity) / self._state.peak_equity
            if dd > self._config.max_drawdown_pct:
                self._trip(
                    f"drawdown {dd:.2%} exceeds limit "
                    f"{self._config.max_drawdown_pct:.2%}"
                )
                return

    def _trip(self, reason: str) -> None:
        self._state.triggered = True
        self._state.reason = reason


class RiskManager:
    """Builds and wraps a Stage 3.3 PaperRiskGate from fixed parameters."""

    def __init__(self, config: RiskManagerConfig, account: PaperAccount) -> None:
        self._config = config
        self._gate = PaperRiskGate(
            account,
            None,
            min_confidence=config.min_confidence,
            max_position_fraction=config.max_position_fraction,
            min_risk_reward=config.min_risk_reward,
            min_stop_loss_pct=config.min_stop_loss_pct,
        )

    @property
    def gate(self) -> PaperRiskGate:
        return self._gate

    @property
    def config(self) -> RiskManagerConfig:
        return self._config

    def check(self, decision: FinalDecision):
        return self._gate.check(decision)
