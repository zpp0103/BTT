# Stage 10 — LLM Adapter Layer

Local-first, pluggable LLM analysis plugin for the brain committee. It is an
**optional** analysis source that can be injected into `MultiBrainOrchestrator`
without modifying the orchestrator. It never submits orders, never contacts an
external venue, and never relaxes any risk boundary. `LIVE_TRADING` must stay `false`.

## Scope

- **New package only:** `crypto_quant_ai/backend/llm/`
- Does **not** modify Stage 1–9 code, `requirements.txt`, or `pyproject.toml`.
- The online adapter is a gated stub: it exists to show the plug point but performs
  **no network call** in this paper-only environment.

## Architecture

```
 LLMConfig (enabled=False by default)
        │
        ▼
   LLMBrain(BrainBase)  ──▶  adapter.complete(prompt)
        │                        │
        │                 local_stub (default, deterministic, no network)
        │                        │
        │                 openai_style (gated stub; refuses network calls)
        ▼
 BrainAnalysis(decision, confidence, reasoning, warnings)
        │  appended to the orchestrator's brain list (no orchestrator change)
        ▼
 MultiBrainOrchestrator → OrchestratorReport (with llm contribution explainable)
```

### Files
- `types.py` — `LLMConfig` (default `enabled=False`), `LLMResponse`; import-time `LIVE_TRADING` guard.
- `adapters.py` — `LLMAdapter` ABC, `LocalStubAdapter` (functional, deterministic), `OpenAIStyleAdapter` (gated stub, no network).
- `registry.py` — `BrainRegistry` (adapter registry; default only `local_stub` registered). `register_adapter` / `build_adapter` / `get_registry`.
- `prompt.py` — `build_prompt(market_data, template)` — read-only snapshot, no credentials.
- `brain.py` — `LLMBrain(BrainBase)`: safe by default; active decisions gated by config; any failure → `NO_TRADE`.
- `extension.py` — `build_llm_brain` / `with_llm_brain` / `LLMIntelligenceExtension` (optional Stage 9 integration without editing Stage 9).
- `formatters.py` — `render_llm_contribution(report)` (explainability).
- `__init__.py` — exports + import-time `LIVE_TRADING` guard.

## Reused real APIs (verified)
| Capability | Source |
|---|---|
| `BrainBase.analyze(market_data) -> BrainAnalysis` | Stage 1 `brains/base.py` |
| `BrainAnalysis` schema | `brains/base.py` |
| `MultiBrainOrchestrator(brains)` / `.run(market_data)` | Stage 3.1 `decision/brain_orchestrator.py` |
| `build_brains([...])` | Stage 5 `replay/registry.py` (untouched) |
| `MarketData` | `core/models.py` |
| `IntelligenceOrchestrator.analyze(...)` | Stage 9 `intelligence/orchestrator.py` (untouched) |

## Safety properties
- `LIVE_TRADING=true` → `RuntimeError` at import and at `LLMBrain.__init__`.
- Disabled by default: `LLMBrain.analyze` returns `NO_TRADE` (confidence 0).
- Enabled + local stub: returns the stub's conservative `NO_TRADE`.
- Enabled + active decision (BUY/SELL): only forwarded if `allow_active_decisions=True`
  **and** (when `require_stop_loss_for_active=True`) the market data carries a stop-loss.
- Adapter error / timeout / unparsable output → safe `NO_TRADE` fallback.
- The online adapter refuses network calls; it is not in the default registry.

## Usage

```python
from crypto_quant_ai.backend.llm import (
    LLMConfig, LLMBrain, build_llm_brain, with_llm_brain,
    render_llm_contribution,
)
from crypto_quant_ai.backend.replay.registry import build_brains
from crypto_quant_ai.backend.decision.brain_orchestrator import MultiBrainOrchestrator
from crypto_quant_ai.backend.core.models import MarketData

# default: llm disabled -> safe NO_TRADE
cfg = LLMConfig(enabled=False)

md = MarketData(symbol="BTC", timestamp="2024-01-01T00:00:00", open=1.0, high=2.0,
                low=0.5, close=1.5, volume=10.0, timeframe="15m")

brains = build_brains(["quant", "market_structure", "risk", "devil_advocate"])
brains = with_llm_brain(brains, cfg)  # appends only if enabled
report = MultiBrainOrchestrator(brains).run(md)
print(render_llm_contribution(report))
```

## Outputs
- `BrainAnalysis` contribution inside the orchestrator report (decision, confidence, reasoning, warnings).
- `render_llm_contribution(report)` → markdown snippet explaining the LLM's suggestion and whether it was adopted.

## Acceptance
- New package adds only the `llm/` module, its tests, and this doc; no other source changes.
- Stage 10 test suite passes; full backend regression passes with no regressions.
- Safety scan reports no forbidden literals; `LIVE_TRADING=false` holds.
- `git diff --check` clean; changes stay within allowed directories.
