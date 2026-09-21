"""Stage 7 (Plan A) - Safe paper trading gateway: immutable configuration types.

All configuration is frozen at session start. Parameters cannot change while a
session is running, and no automatic optimization is performed.
"""
from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GatewayStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    TRIPPED = "tripped"


class RiskManagerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_position_fraction: float = Field(default=1.0, gt=0, le=1)
    min_confidence: float = Field(default=0.50, ge=0, le=1)
    min_risk_reward: float = Field(default=1.5, ge=0)
    min_stop_loss_pct: float = Field(default=0.005, ge=0, le=1)

    @field_validator(
        "max_position_fraction", "min_confidence",
        "min_risk_reward", "min_stop_loss_pct",
    )
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("value must be finite")
        return v


class CircuitBreakerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    price_anomaly_pct: float = Field(default=0.05, gt=0, le=1)
    daily_loss_limit: float = Field(default=1000.0, gt=0)
    max_order_notional: float = Field(default=50000.0, gt=0)
    max_drawdown_pct: float = Field(default=0.20, gt=0, le=1)

    @field_validator(
        "price_anomaly_pct", "daily_loss_limit",
        "max_order_notional", "max_drawdown_pct",
    )
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("value must be finite")
        return v


class GatewayConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    user: str = Field(default="local", min_length=1)
    account_id: str = Field(default="paper-001", min_length=1)
    symbol: str = Field(default="BTC/USDT", min_length=1)
    timeframe: str = Field(default="15m", min_length=1)
    strategy_id: str = Field(default="single-strategy", min_length=1)
    initial_cash: float = Field(default=100000.0, gt=0)
    risk_manager: RiskManagerConfig = Field(default_factory=RiskManagerConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)

    @field_validator("initial_cash")
    @classmethod
    def _finite_cash(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0:
            raise ValueError("initial_cash must be finite and positive")
        return v

    @field_validator("user", "account_id", "symbol", "timeframe", "strategy_id")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("field must not be blank")
        return v.strip()
