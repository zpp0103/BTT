from __future__ import annotations

from crypto_quant_ai.backend.brains.base import BrainBase
from crypto_quant_ai.backend.core.models import BrainAnalysis, MarketData
from crypto_quant_ai.backend.llm.providers import build_provider, parse_suggestion
from crypto_quant_ai.backend.llm.safety import DecisionGate
from crypto_quant_ai.backend.llm.types import LLMConfig, _live_guard as _llm_live_guard

_PROMPT_TMPL = (
    "You are a conservative market analyst operating in a paper-only "
    "simulation. Given the snapshot, output JSON with keys: "
    "decision (one of NO_TRADE/BUY/SELL), confidence (0..1), reasoning, "
    "stop_loss (number or null). Analysis only; this is a paper-only sim.\n"
    "symbol={symbol} timeframe={timeframe} o={open} h={high} l={low} "
    "c={close} v={volume}\n{extra}"
)


class LLMBrain(BrainBase):
    """LLM-backed analysis brain. Safe by default; active decisions gated."""
    name = "llm"

    def __init__(self, config: LLMConfig | None = None, provider=None) -> None:
        _llm_live_guard()
        self._config = config or LLMConfig()
        if provider is None:
            provider = build_provider(self._config.provider_name, model=self._config.model)
        self._provider = provider

    def analyze(self, market_data: MarketData) -> BrainAnalysis:
        if not self._config.enabled:
            return BrainAnalysis(
                brain_name=self.name,
                decision="NO_TRADE",
                confidence=0.0,
                reasoning="llm brain disabled by config",
                warnings=["llm disabled"],
            )
        prompt = _PROMPT_TMPL.format(
            symbol=market_data.symbol,
            timeframe=market_data.timeframe,
            open=market_data.open,
            high=market_data.high,
            low=market_data.low,
            close=market_data.close,
            volume=market_data.volume,
            extra=self._config.extra_prompt,
        )
        try:
            resp = self._provider.complete(prompt, timeout_s=self._config.timeout_s)
        except Exception as exc:  # provider failure -> safe fallback
            return self._fallback(f"provider error: {exc}")
        if resp.error:
            return self._fallback(f"provider error: {resp.error}")
        parsed = parse_suggestion(resp.text)
        if parsed is None:
            return self._fallback("unparsable provider output")
        decision = parsed.decision
        if not DecisionGate.gate(decision, parsed, self._config):
            return self._fallback("active decision blocked by safety gate")
        confidence = max(0.0, min(1.0, float(parsed.confidence)))
        return BrainAnalysis(
            brain_name=self.name,
            decision=decision,
            confidence=confidence,
            reasoning=parsed.reasoning,
            warnings=list(parsed.warnings),
        )

    def _fallback(self, reason: str) -> BrainAnalysis:
        return BrainAnalysis(
            brain_name=self.name,
            decision=self._config.fallback_decision,
            confidence=0.0,
            reasoning=f"llm fallback: {reason}",
            warnings=[f"fallback: {reason}"],
        )


def build_llm_brain(config: LLMConfig | None = None) -> LLMBrain:
    return LLMBrain(config=config)
