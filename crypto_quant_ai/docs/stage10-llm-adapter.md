# Stage 10 — LLM Adapter Layer (new structure)

Local-first, pluggable LLM analysis plugin for the brain committee. An **optional**
analysis source that can be injected into `MultiBrainOrchestrator` without modifying
the orchestrator. No network, no external venue, no order submission; `LIVE_TRADING`
stays `false`. This package adds only `llm/` and two brain modules under `brains/`.

## Architecture

```
LLMConfig (enabled=False by default)
      │
      ▼
 LLMBrain(BrainBase)            brains/llm_base.py
      │  uses
      ▼
 LLMProvider.complete(prompt)   llm/providers.py
      │
      ├─ LocalStubProvider       deterministic, no network (default)
      └─ OpenAIGatedProvider     gated stand-in, performs NO network call
      │
      ▼
 ParsedSuggestion → DecisionGate (llm/safety.py) → BrainAnalysis
      │  appended to orchestrator brain list
      ▼
 MultiBrainOrchestrator → OrchestratorReport
```

The standalone `LLMStubBrain` (brains/llm_stub.py) is a deterministic offline brain
that needs no provider, useful as a safe default or test double.

## Files
- `llm/types.py` — `LLMConfig` (default `enabled=False`), `LLMResponse`, `ParsedSuggestion`; `_live_guard()`.
- `llm/providers.py` — `LLMProvider` ABC, `LocalStubProvider` (offline), `OpenAIGatedProvider` (no network), `parse_suggestion`, `build_provider`.
- `llm/registry.py` — `ProviderRegistry` (default only `local_stub` registered), `get_provider_registry`.
- `llm/safety.py` — `assert_paper_only` (LIVE_TRADING guard), `DecisionGate`, forbidden-token scan.
- `llm/formatters.py` — `render_llm_contribution(report)`.
- `llm/__init__.py` — imports with a LIVE_TRADING guard; exports.
- `brains/llm_base.py` — `LLMBrain(BrainBase)` + `build_llm_brain`.
- `brains/llm_stub.py` — `LLMStubBrain(BrainBase)`.

## Safety properties
- `LIVE_TRADING=true` → `RuntimeError` at import and at `LLMBrain.__init__`.
- Disabled by default: `LLMBrain.analyze` returns `NO_TRADE` (confidence 0).
- Active decision (BUY/SELL) forwarded only if `allow_active_decisions=True` **and** the
  provider response carries a `stop_loss` (when `require_stop_loss_for_active=True`).
- Provider error / timeout / unparsable output → safe `NO_TRADE` fallback.
- `OpenAIGatedProvider` performs no network call and refuses to operate unless explicitly
  permitted; even then it returns a safe stub, never contacting any external service.
- The default provider registry contains only the offline `local_stub`.

## Usage
```python
from crypto_quant_ai.backend.llm import LLMConfig, build_llm_brain, render_llm_contribution
from crypto_quant_ai.backend.brains.llm_stub import LLMStubBrain
from crypto_quant_ai.backend.replay.registry import build_brains
from crypto_quant_ai.backend.decision.brain_orchestrator import MultiBrainOrchestrator
from crypto_quant_ai.backend.core.models import MarketData

cfg = LLMConfig(enabled=False)  # safe default
md = MarketData(symbol="BTC", timestamp="2024-01-01T00:00:00", open=1.0, high=2.0,
                low=0.5, close=1.5, volume=10.0, timeframe="15m")

brains = build_brains(["quant", "market_structure", "risk", "devil_advocate"])
brains += [build_llm_brain(cfg), LLMStubBrain()]
report = MultiBrainOrchestrator(brains).run(md)
print(render_llm_contribution(report))
```

## Acceptance
- Only the `llm/` package and two `brains/` modules are added; Stage 1–9,
  `requirements.txt`, and `pyproject.toml` are unchanged.
- Stage 10 test suite passes; full backend regression passes with no regressions.
- Safety self-scan reports no forbidden literals; `LIVE_TRADING=false` holds.
