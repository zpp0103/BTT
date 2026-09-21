"""Stage 10 - LLM adapters (pluggable, gated).

Local stub adapter is fully functional and deterministic (no network). The
online adapter is a gated stub: it exists to show the plug point but refuses
to perform any network call in this paper-only environment.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from .types import LLMResponse


class LLMAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def complete(self, prompt: str, timeout_s: float = 5.0) -> str:
        raise NotImplementedError


class LocalStubAdapter(LLMAdapter):
    name = "local_stub"

    def __init__(self, model: str | None = None) -> None:
        self.model = model

    def complete(self, prompt: str, timeout_s: float = 5.0) -> str:
        # Deterministic, conservative response. No network, no venue, no credentials.
        return json.dumps({
            "decision": "NO_TRADE",
            "confidence": 0.0,
            "reasoning": "local stub adapter: paper-only mode, no external model consulted",
        })


class OpenAIStyleAdapter(LLMAdapter):
    """Gated stub for an online OpenAI-style backend.

    This adapter intentionally does NOT perform any network call. In the
    paper-only environment network access is forbidden, so any attempt to use
    it raises. It documents where a real implementation would plug in.
    """

    name = "openai_style"

    def __init__(self, model: str = "gpt-4o-mini", allow_network: bool = False) -> None:
        self.model = model
        self._allow_network = allow_network

    def complete(self, prompt: str, timeout_s: float = 5.0) -> str:
        if not self._allow_network:
            raise RuntimeError(
                "online LLM adapter is disabled: paper-only mode forbids network calls"
            )
        # A real implementation would call the model API here. Disabled by design.
        raise RuntimeError("network LLM calls are not permitted in this environment")
