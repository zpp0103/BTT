from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto_quant_ai.backend.data.ohlcv import OHLCVBar
from crypto_quant_ai.backend.gateway import (
    CircuitBreakerConfig,
    GatewayConfig,
    RiskManagerConfig,
)
from crypto_quant_ai.backend.paper.account import PaperAccount


@dataclass(frozen=True)
class Stage14AuditSummary:
    total_orders: int
    executed_count: int
    rejected_count: int
    skipped_count: int
    total_events: int


@dataclass(frozen=True)
class Stage14ReconciliationSnapshot:
    ok: bool
    matched: int
    mismatches: int


@dataclass(frozen=True)
class Stage14RunRecord:
    run_id: str
    created_at: str
    report_hash: str
    verification_passed: bool
    executed: bool
    blocked: bool
    final_decision: str
    block_reason: str
    reconciliation_ok: bool
    reconciliation_mismatches: int


@dataclass
class Stage14SessionState:
    session_id: str
    gateway_hash: str
    gateway_config: GatewayConfig
    account: PaperAccount
    audit_summary: Stage14AuditSummary
    reconciliation: Stage14ReconciliationSnapshot
    latest_report_hash: str = ""
    latest_report_generated_at: str = ""
    latest_result: dict[str, Any] = field(default_factory=dict)
    history: list[Stage14RunRecord] = field(default_factory=list)
    breaker_state: dict[str, Any] = field(default_factory=dict)
    order_seq: int = 0
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    venue_fills: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class Stage14SessionView:
    session_id: str
    gateway_hash: str
    gateway_config: GatewayConfig
    account: PaperAccount
    audit_summary: Stage14AuditSummary
    reconciliation: Stage14ReconciliationSnapshot
    latest_report_hash: str
    latest_report_generated_at: str
    latest_result: dict[str, Any]
    history_length: int
    updated_at: str


class Stage14SessionOpenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: str = Field(default="local", min_length=1)
    account_id: str = Field(default="paper-001", min_length=1)
    symbol: str = Field(default="BTC/USDT", min_length=1)
    timeframe: str = Field(default="15m", min_length=1)
    strategy_id: str = Field(default="single-strategy", min_length=1)
    initial_cash: float = Field(default=100000.0, gt=0)
    risk_manager: RiskManagerConfig = Field(default_factory=RiskManagerConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)

    @field_validator("user", "account_id", "symbol", "timeframe", "strategy_id")
    @classmethod
    def _strip_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be blank")
        return value

    def to_gateway_config(self) -> GatewayConfig:
        return GatewayConfig(
            user=self.user,
            account_id=self.account_id,
            symbol=self.symbol,
            timeframe=self.timeframe,
            strategy_id=self.strategy_id,
            initial_cash=self.initial_cash,
            risk_manager=self.risk_manager,
            circuit_breaker=self.circuit_breaker,
        )


class Stage14SessionRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candles: list[OHLCVBar]
    timeframes: list[int] = Field(default_factory=lambda: [20, 50, 100])

    @field_validator("timeframes")
    @classmethod
    def _validate_timeframes(cls, value: list[int]) -> list[int]:
        out = [int(v) for v in value if int(v) >= 2]
        if not out:
            raise ValueError("timeframes must contain at least one value >= 2")
        return out
