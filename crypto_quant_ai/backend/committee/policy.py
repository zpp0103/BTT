"""Stage 11 - Policy gate for active decisions.

Reuses the Stage 10 safety gate (DecisionGate + LLMConfig + ParsedSuggestion)
so the committee's active-decision policy is identical to the LLM adapter's.
"""
from __future__ import annotations

from .fusions import _norm
from .types import ModelCommitteeConfig
from crypto_quant_ai.backend.llm.safety import DecisionGate
from crypto_quant_ai.backend.llm.types import LLMConfig, ParsedSuggestion


def gate_active(decision: str, config: ModelCommitteeConfig) -> bool:
    llm_cfg = LLMConfig(
        enabled=True,
        allow_active_decisions=config.allow_active_decisions,
        require_stop_loss_for_active=config.require_stop_loss_for_active,
    )
    parsed = ParsedSuggestion(
        decision=_norm(decision), confidence=0.0, reasoning="", stop_loss=None
    )
    return DecisionGate.gate(parsed.decision, parsed, llm_cfg)
