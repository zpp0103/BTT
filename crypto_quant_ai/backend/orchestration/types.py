from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto_quant_ai.backend.committee.types import CommitteeVerdict, ModelCommitteeConfig
from crypto_quant_ai.backend.core.models import FinalDecision
from crypto_quant_ai.backend.data.ohlcv import OHLCVBar
from crypto_quant_ai.backend.evidence.types import EvidenceSet, VerificationResult
from crypto_quant_ai.backend.gateway import GatewayConfig, GatewayExecutionResult, GatewayReport
from crypto_quant_ai.backend.intelligence import IntelligenceReport

_DYNAMIC_HASH_KEYS = {
    "generated_at",
    "collected_at",
    "started_at",
    "stopped_at",
    "timestamp",
}


def default_stage13_committee_config() -> ModelCommitteeConfig:
    return ModelCommitteeConfig(
        allow_active_decisions=True,
        require_stop_loss_for_active=False,
        routing=True,
        fail_closed=True,
    )


@dataclass
class Stage13Request:
    candles: list[OHLCVBar]
    symbol: str = "BTC/USDT"
    timeframe: str = "15m"
    timeframes: tuple[int, ...] = (20, 50, 100)
    committee_config: ModelCommitteeConfig = field(
        default_factory=default_stage13_committee_config
    )
    gateway_config: GatewayConfig = field(default_factory=GatewayConfig)
    space: Any | None = None
    search: Any | None = None
    wf: Any | None = None
    replay_config: Any | None = None


@dataclass(frozen=True)
class Stage13RequestSummary:
    symbol: str
    timeframe: str
    candles_count: int
    timeframes: list[int]
    committee_fusion: str
    gateway_hash: str


@dataclass(frozen=True)
class Stage13MarketContext:
    symbol: str
    timeframe: str
    candles_count: int
    first_timestamp: str
    last_timestamp: str
    last_close: float


@dataclass(frozen=True)
class Stage13ExecutionResult:
    verification_passed: bool
    gateway_allowed: bool
    executed: bool
    blocked: bool
    block_reason: str
    final_decision: FinalDecision
    gateway_result: GatewayExecutionResult | None = None


@dataclass
class Stage13Report:
    request: Stage13RequestSummary
    market_context: Stage13MarketContext
    intelligence: IntelligenceReport
    committee_verdict: CommitteeVerdict
    evidence: EvidenceSet
    verification: VerificationResult
    contradictions: list[str]
    result: Stage13ExecutionResult
    gateway_report: GatewayReport | None = None
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    report_hash: str = ""


class Stage13ApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candles: list[OHLCVBar]
    symbol: str = Field(default="BTC/USDT", min_length=1)
    timeframe: str = Field(default="15m", min_length=1)
    timeframes: list[int] = Field(default_factory=lambda: [20, 50, 100])

    @field_validator("symbol", "timeframe")
    @classmethod
    def _strip_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be blank")
        return value

    @field_validator("timeframes")
    @classmethod
    def _validate_timeframes(cls, value: list[int]) -> list[int]:
        out = [int(v) for v in value if int(v) >= 2]
        if not out:
            raise ValueError("timeframes must contain at least one value >= 2")
        return out

    def to_request(self) -> Stage13Request:
        gateway_config = GatewayConfig(
            symbol=self.symbol,
            timeframe=self.timeframe,
        )
        return Stage13Request(
            candles=list(self.candles),
            symbol=self.symbol,
            timeframe=self.timeframe,
            timeframes=tuple(self.timeframes),
            gateway_config=gateway_config,
        )



def _canonicalize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _canonicalize(value.model_dump())
    if hasattr(value, "value") and not isinstance(value, str):
        return getattr(value, "value")
    if hasattr(value, "isoformat") and callable(value.isoformat):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {
            key: _canonicalize(val)
            for key, val in value.__dict__.items()
            if key not in _DYNAMIC_HASH_KEYS
        }
    if isinstance(value, dict):
        return {
            key: _canonicalize(val)
            for key, val in sorted(value.items())
            if key not in _DYNAMIC_HASH_KEYS
        }
    if isinstance(value, list):
        return [_canonicalize(v) for v in value]
    if isinstance(value, tuple):
        return [_canonicalize(v) for v in value]
    return value



def stage13_hash(payload: dict[str, Any]) -> str:
    canonical = _canonicalize(payload)
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
