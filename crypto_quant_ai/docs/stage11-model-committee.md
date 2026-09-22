# Stage 11 — Model Committee & Policy Layer

Aggregates multiple brain / model analyses (deterministic brains + LLM-backed
brains) into a single, explainable policy verdict. Local, paper-only; reuses
Stage 9 (decision board / market state) and Stage 10 (LLM adapter + safety gate).
No network, no external venue, no order submission.

## Architecture
```
models: list[BrainBase]   (quant, market_structure, risk, devil_advocate, LLMStubBrain, LLMBrain, ...)
        │  each.analyze(market_data) -> BrainAnalysis (collected as ModelContribution)
        ▼
 ModelCommittee.evaluate(market_data, market_state?)
        │  route_models (optional, regime-aware)  ->  fusions.<strategy>  ->  policy.gate_active
        ▼
 CommitteeVerdict (final_decision, confidence, conflict, quorum_met, routing, contributions)
        │
        ▼
 to_final_decision(market_data, verdict) -> FinalDecision   (reuses core.models)
 render_committee_report(verdict)        -> markdown
```

## Files
- `committee/types.py` — `FusionStrategy`, `ModelContribution`, `CommitteeVerdict`, `ModelCommitteeConfig`.
- `committee/fusions.py` — `weighted_majority`, `simple_majority`, `unanimous`, `consensus_quorum` (pure).
- `committee/policy.py` — `gate_active` reuses Stage 10 `DecisionGate` + `LLMConfig`.
- `committee/router.py` — `route_models` reuses Stage 9 `market_state.Regime`.
- `committee/committee.py` — `ModelCommittee.evaluate` / `to_final_decision`.
- `committee/formatters.py` — `render_committee_report`.
- `committee/__init__.py` — LIVE_TRADING guard; exports.

## Fusion strategies
- `weighted_majority` (default): weighted by per-model confidence and optional `weights`.
- `simple_majority`: count of active votes (BUY/SELL).
- `unanimous`: all active models must agree, else NO_TRADE.
- `consensus_quorum`: at least `quorum` active models agree.

## Safety properties
- `LIVE_TRADING=true` → `RuntimeError` at import and on committee construction.
- Disabled by default: `allow_active_decisions=False` → any BUY/SELL routed through
  `gate_active` is downgraded to NO_TRADE (fail-closed).
- `fail_closed=True` (default): conflicting signals → NO_TRADE.
- Quorum not met → NO_TRADE.
- Any model error / exception → that model contributes a NO_TRADE fallback; it does
  not break the committee.

## Usage
```python
from crypto_quant_ai.backend.committee import ModelCommittee, ModelCommitteeConfig, render_committee_report
from crypto_quant_ai.backend.replay.registry import build_brains
from crypto_quant_ai.backend.brains.llm_stub import LLMStubBrain
from crypto_quant_ai.backend.core.models import MarketData

brains = build_brains(["quant", "market_structure", "risk", "devil_advocate"]) + [LLMStubBrain()]
md = MarketData(symbol="BTC", timestamp="2024-01-01T00:00:00", open=1.0, high=2.0,
                low=0.5, close=1.5, volume=10.0, timeframe="15m")
cfg = ModelCommitteeConfig(fusion="weighted_majority", quorum=2, allow_active_decisions=False)
verdict = ModelCommittee(brains, cfg).evaluate(md)
print(render_committee_report(verdict))
```

`fusion` 同时接受 `FusionStrategy` 枚举和字符串值（如 `"weighted_majority"`）；非法字符串会抛出 `ValueError`，避免静默回退。

## Acceptance
- Only `crypto_quant_ai/backend/committee/` is added; Stage 1–10, `requirements.txt`,
  and `pyproject.toml` are unchanged.
- Stage 11 test suite passes; full backend regression passes with no regressions.
- Safety self-scan reports no forbidden literals; `LIVE_TRADING=false` holds.
