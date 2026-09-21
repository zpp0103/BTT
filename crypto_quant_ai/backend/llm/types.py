from __future__ import annotations

import os
from dataclasses import dataclass, field

from typing import Any


def _live_guard() -> None:
    """Refuse to operate when real trading is enabled (paper-only layer)."""
    if os.environ.get("LIVE_TRADING", "false").lower() == "true":
        raise RuntimeError(
            "LIVE_TRADING is enabled; the LLM adapter layer is paper-only and "
            "refuses to initialize or run."
        )


@dataclass
class LLMConfig:
    """Configuration for an LLM-backed brain. Safe by default."""
    enabled: bool = False
    provider_name: str = "local_stub"
    model: str = "local-stub"
    fallback_decision: str = "NO_TRADE"
    allow_active_decisions: bool = False
    require_stop_loss_for_active: bool = True
    timeout_s: float = 5.0
    temperature: float = 0.0
    extra_prompt: str = ""


@dataclass
class LLMResponse:
    """Raw output returned by a provider; no execution side effects."""
    text: str
    provider: str
    model: str
    latency_s: float = 0.0
    error: str | None = None


@dataclass
class ParsedSuggestion:
    """Structured suggestion extracted from a provider response."""
    decision: str
    confidence: float
    reasoning: str
    stop_loss: float | None = None
    warnings: list[str] = field(default_factory=list)
