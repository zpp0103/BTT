"""Stage 10 - LLM Adapter Layer (paper-only, local-first, pluggable).

Imports require LIVE_TRADING=false. This package adds an optional LLM analysis
plugin and a pluggable adapter registry. It never submits orders, never contacts
an external venue, and never relaxes existing risk boundaries. The online
adapter is a gated stub that performs no network call in this environment.
"""
from __future__ import annotations

import os as _os

from .types import LLMConfig, LLMResponse, _live_guard
from .adapters import LLMAdapter, LocalStubAdapter, OpenAIStyleAdapter
from .registry import BrainRegistry, get_registry, register_adapter, build_adapter
from .prompt import build_prompt
from .brain import LLMBrain
from .extension import build_llm_brain, with_llm_brain, LLMIntelligenceExtension
from .formatters import render_llm_contribution, explain_llm_decision

if _os.environ.get("LIVE_TRADING", "false").lower() == "true":
    raise RuntimeError("Stage 10 LLM layer requires LIVE_TRADING=false (paper only).")

__all__ = [
    "LLMConfig", "LLMResponse",
    "LLMAdapter", "LocalStubAdapter", "OpenAIStyleAdapter",
    "BrainRegistry", "get_registry", "register_adapter", "build_adapter",
    "build_prompt",
    "LLMBrain",
    "build_llm_brain", "with_llm_brain", "LLMIntelligenceExtension",
    "render_llm_contribution", "explain_llm_decision",
]
