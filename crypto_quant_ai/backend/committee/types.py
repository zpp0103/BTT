"""Stage 11 - Model Committee & Policy Layer: types and configuration.

Local, paper-only aggregation of multiple brain / model analyses into a single
policy verdict. No network, no external venue, no order submission. Reuses the
Stage 9 decision board, Stage 10 LLM adapter, and Stage 3 safety gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FusionStrategy(str, Enum):
    WEIGHTED_MAJORITY = "weighted_majority"
    SIMPLE_MAJORITY = "simple_majority"
    UNANIMOUS = "unanimous"
    CONSENSUS_QUORUM = "consensus_quorum"


@dataclass
class ModelContribution:
    model_name: str
    decision: str
    confidence: float
    reasoning: str = ""
    warnings: list[str] = field(default_factory=list)
    latency_ms: float | None = None


@dataclass
class CommitteeVerdict:
    final_decision: str
    confidence: float
    contributions: list[ModelContribution]
    conflict: bool
    quorum_met: bool
    routing: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "final_decision": self.final_decision,
            "confidence": self.confidence,
            "conflict": self.conflict,
            "quorum_met": self.quorum_met,
            "reasoning": self.reasoning,
            "routing": self.routing,
            "contributions": [
                {
                    "model_name": c.model_name,
                    "decision": c.decision,
                    "confidence": c.confidence,
                    "reasoning": c.reasoning,
                    "warnings": list(c.warnings),
                    "latency_ms": c.latency_ms,
                }
                for c in self.contributions
            ],
        }


@dataclass
class ModelCommitteeConfig:
    fusion: FusionStrategy = FusionStrategy.WEIGHTED_MAJORITY
    weights: dict[str, float] = field(default_factory=dict)
    quorum: int = 2
    allow_active_decisions: bool = False
    require_stop_loss_for_active: bool = False
    routing: bool = False
    fail_closed: bool = True
