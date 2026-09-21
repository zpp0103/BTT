from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod

from .types import LLMResponse, ParsedSuggestion


_STUB_PAYLOAD = {
    "decision": "NO_TRADE",
    "confidence": 0.0,
    "reasoning": "local stub: conservative hold, no external signal",
    "stop_loss": None,
}


class LLMProvider(ABC):
    """Pluggable completion backend. Implementations MUST NOT perform any
    network call in this paper-only environment."""
    name: str = "base"

    @abstractmethod
    def complete(self, prompt: str, timeout_s: float = 5.0) -> LLMResponse:
        raise NotImplementedError


class LocalStubProvider(LLMProvider):
    """Deterministic, offline provider. Returns a conservative hold."""
    name = "local_stub"

    def __init__(self, model: str = "local-stub") -> None:
        self.model = model

    def complete(self, prompt: str, timeout_s: float = 5.0) -> LLMResponse:
        t0 = time.perf_counter()
        text = json.dumps(_STUB_PAYLOAD, ensure_ascii=False)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            latency_s=time.perf_counter() - t0,
        )


class OpenAIGatedProvider(LLMProvider):
    """Gated stand-in for an online provider. It performs NO network call and
    refuses to operate unless explicitly permitted; even when permitted it only
    returns a safe stub and never contacts any external service."""
    name = "openai_gated"

    def __init__(self, model: str = "gpt-stub", allow_network: bool = False) -> None:
        self.model = model
        self.allow_network = allow_network

    def complete(self, prompt: str, timeout_s: float = 5.0) -> LLMResponse:
        if self.allow_network:
            return LLMResponse(
                text=json.dumps(
                    {**_STUB_PAYLOAD, "reasoning": "network path disabled in paper-only layer"}
                ),
                provider=self.name,
                model=self.model,
                error="online completion disabled in paper-only layer",
            )
        raise RuntimeError(
            "OpenAIGatedProvider refuses network access; paper-only layer only."
        )


def parse_suggestion(text: str) -> ParsedSuggestion | None:
    """Parse a provider JSON payload into a structured suggestion.

    Returns None on any parse failure so callers can fall back safely.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    decision = str(data.get("decision", "NO_TRADE"))
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    reasoning = str(data.get("reasoning", ""))
    stop_loss = data.get("stop_loss", None)
    if stop_loss is not None:
        try:
            stop_loss = float(stop_loss)
        except (TypeError, ValueError):
            stop_loss = None
    return ParsedSuggestion(
        decision=decision,
        confidence=confidence,
        reasoning=reasoning,
        stop_loss=stop_loss,
    )


def build_provider(name: str, **kwargs: Any) -> LLMProvider:
    from .registry import get_provider_registry

    cls = get_provider_registry().get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name}")
    return cls(**kwargs)
