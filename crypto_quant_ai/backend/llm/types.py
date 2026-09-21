"""Stage 10 - LLM Adapter Layer: configuration + response types.

Paper-only, local-first. The online (networked) adapter is a gated stub that
refuses to perform any network call in this environment (no network, no venue,
no credentials). All network code paths are opt-in and disabled by default.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


def _live_guard() -> None:
    if os.environ.get("LIVE_TRADING", "false").lower() == "true":
        raise RuntimeError("Stage 10 LLM layer requires LIVE_TRADING=false (paper only).")


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool = False
    adapter_name: str = "local_stub"
    model: str = "local-stub"
    prompt_template: str = (
        "You are a conservative crypto analyst. Given the market snapshot, "
        "respond ONLY with JSON: {\"decision\": \"NO_TRADE\", \"confidence\": 0.0, "
        "\"reasoning\": \"...\"} where decision is one of BUY/SELL/NO_TRADE."
    )
    timeout_s: float = 5.0
    max_retries: int = 1
    allow_active_decisions: bool = False
    require_stop_loss_for_active: bool = True
    fallback_decision: str = "NO_TRADE"


@dataclass(frozen=True)
class LLMResponse:
    raw: str
    decision: str
    confidence: float
    reasoning: str
    source: str
    error: str = ""
