"""Stage 10 - LLMBrain: an optional BrainBase plugin.

Safe by default: when disabled it returns NO_TRADE with zero confidence. When
enabled it consults a configured adapter, but still only forwards an active
decision (BUY/SELL) if the config explicitly allows it. Any failure (adapter
error, parse error, timeout, missing stop-loss) degrades safely to NO_TRADE.
"""
from __future__ import annotations

import json
from typing import Any

from crypto_quant_ai.backend.brains.base import BrainAnalysis, BrainBase
from crypto_quant_ai.backend.core.models import MarketData

from .prompt import build_prompt
from .registry import build_adapter
from .types import LLMConfig, LLMResponse, _live_guard


_ALLOWED_DECISIONS = ("BUY", "SELL", "NO_TRADE")


class LLMBrain(BrainBase):
    name = "llm"

    def __init__(self, config: LLMConfig | None = None, adapter: Any | None = None) -> None:
        _live_guard()
        self._config = config or LLMConfig()
        if adapter is not None:
            self._adapter = adapter
        else:
            self._adapter = build_adapter(
                self._config.adapter_name, model=self._config.model
            ) if self._config.enabled else None

    @property
    def config(self) -> LLMConfig:
        return self._config

    def analyze(self, market_data: MarketData) -> BrainAnalysis:
        cfg = self._config
        if not cfg.enabled or self._adapter is None:
            return BrainAnalysis(
                brain_name=self.name,
                decision="NO_TRADE",
                confidence=0.0,
                reasoning="LLM brain disabled; safe fallback NO_TRADE",
                warnings=["llm disabled"],
            )
        try:
            prompt = build_prompt(market_data, cfg.prompt_template)
            raw = self._adapter.complete(prompt, timeout_s=cfg.timeout_s)
            resp = self._parse(raw, source=cfg.adapter_name)
        except Exception as exc:  # pragma: no cover - defensive safety net
            return BrainAnalysis(
                brain_name=self.name,
                decision="NO_TRADE",
                confidence=0.0,
                reasoning=f"LLM call failed; safe fallback NO_TRADE ({exc})",
                warnings=[f"llm error: {exc}"],
            )

        if resp.decision not in _ALLOWED_DECISIONS:
            return self._fallback(f"invalid decision {resp.decision!r}")
        if resp.decision in ("BUY", "SELL") and not cfg.allow_active_decisions:
            return self._fallback("active decision blocked by config")
        if (
            resp.decision in ("BUY", "SELL")
            and cfg.require_stop_loss_for_active
            and not getattr(market_data, "stop_loss", None)
        ):
            return self._fallback("active decision requires stop_loss on market data")

        return BrainAnalysis(
            brain_name=self.name,
            decision=resp.decision,
            confidence=resp.confidence,
            reasoning=resp.reasoning or "LLM analysis",
            warnings=[],
        )

    def _fallback(self, reason: str) -> BrainAnalysis:
        return BrainAnalysis(
            brain_name=self.name,
            decision=self._config.fallback_decision,
            confidence=0.0,
            reasoning=f"LLM suggestion not adopted: {reason}",
            warnings=[reason],
        )

    @staticmethod
    def _parse(raw: str, source: str) -> LLMResponse:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Treat non-JSON as a neutral NO_TRADE suggestion.
            return LLMResponse(
                raw=raw, decision="NO_TRADE", confidence=0.0,
                reasoning="unparsable LLM output", source=source,
            )
        decision = str(data.get("decision", "NO_TRADE")).upper()
        try:
            conf = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        if conf < 0.0 or conf > 1.0:
            conf = 0.0
        return LLMResponse(
            raw=raw,
            decision=decision,
            confidence=conf,
            reasoning=str(data.get("reasoning", ""))[:500],
            source=source,
        )
