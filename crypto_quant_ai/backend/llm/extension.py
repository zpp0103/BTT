"""Stage 10 - optional integration with the Stage 9 intelligence layer.

This module does NOT modify Stage 9 code. It provides a helper that builds an
LLMBrain (when enabled) and appends it to an existing brain list, plus a thin
wrapper that runs the Stage 9 orchestrator with the LLM brain injected.
"""
from __future__ import annotations

from typing import Any, Sequence

from crypto_quant_ai.backend.brains.base import BrainBase
from crypto_quant_ai.backend.data.ohlcv import OHLCVBar
from .brain import LLMBrain
from .types import LLMConfig, _live_guard


def build_llm_brain(config: LLMConfig | None) -> LLMBrain | None:
    if config is None or not config.enabled:
        return None
    return LLMBrain(config=config)


def with_llm_brain(brains: Sequence[BrainBase], config: LLMConfig | None) -> list[BrainBase]:
    llm_brain = build_llm_brain(config)
    if llm_brain is None:
        return list(brains)
    return list(brains) + [llm_brain]


class LLMIntelligenceExtension:
    """Runs the Stage 9 orchestrator, optionally injecting the LLM brain."""

    def __init__(self, llm_config: LLMConfig | None = None) -> None:
        _live_guard()
        self._llm_config = llm_config

    def analyze(self, candles: Sequence[OHLCVBar], **kwargs: Any):
        from crypto_quant_ai.backend.intelligence.orchestrator import IntelligenceOrchestrator
        from crypto_quant_ai.backend.replay.registry import build_brains

        llm_brain = build_llm_brain(self._llm_config)
        if llm_brain is not None:
            extra = dict(kwargs)
            extra_brains = kwargs.get("brains")
            if extra_brains is not None:
                extra["brains"] = list(extra_brains) + [llm_brain]
            else:
                # Stage 9 builds default brains internally; append via custom brains.
                from crypto_quant_ai.backend.replay.registry import build_brains
                extra["brains"] = list(build_brains(
                    ["quant", "market_structure", "risk", "devil_advocate"]
                )) + [llm_brain]
            kwargs = extra
        orch = IntelligenceOrchestrator()
        return orch.analyze(candles, **kwargs)
