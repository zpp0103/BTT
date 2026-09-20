from __future__ import annotations

from pydantic import BaseModel, Field


class MarketData(BaseModel):
    symbol: str = Field(..., min_length=1)
    timestamp: str = Field(..., min_length=1)
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    volume: float = Field(..., ge=0)
    timeframe: str = Field(default="15m")


class BrainAnalysis(BaseModel):
    brain_name: str = Field(..., min_length=1)
    decision: str = Field(default="NO_TRADE")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str = Field(default="")
    warnings: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    risk_level: str = Field(default="LOW")
    position_size: float = Field(default=0.0, ge=0.0)
    stop_loss: float = Field(default=0.0, ge=0.0)
    take_profit: float = Field(default=0.0, ge=0.0)
    risk_reward: float = Field(default=0.0)
    max_loss: float = Field(default=0.0, ge=0.0)
    veto: bool = Field(default=False)
    veto_reason: str = Field(default="")


class FinalDecision(BaseModel):
    symbol: str = Field(..., min_length=1)
    timeframe: str = Field(default="15m")
    decision: str = Field(default="NO_TRADE")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    entry: float | None = Field(default=None)
    stop_loss: float | None = Field(default=None)
    take_profit: float | None = Field(default=None)
    position_size: float = Field(default=0.0, ge=0.0)
    risk_reward: float = Field(default=0.0)
    veto: bool = Field(default=False)
    reasoning: str = Field(default="")
    timestamp: str = Field(..., min_length=1)
