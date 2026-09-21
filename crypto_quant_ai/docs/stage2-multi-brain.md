# Stage 2.2: Multi-Brain Decision Orchestration

## Objective

Run multiple brains in parallel on the same market snapshot and aggregate their votes into a single, deterministic `FinalDecision`.

## Architecture

### New Modules

| File | Role |
|------|------|
| `backend/decision/brain_orchestrator.py` | Core `MultiBrainOrchestrator` + `BrainResult` + `OrchestratorReport` |
| `backend/decision/router.py` | Re-exports orchestrator + existing `DecisionEngine` |
| `backend/decision/__init__.py` | Package entry point |

### Core Design

**`MultiBrainOrchestrator`**
- Accepts a list of `BrainBase` instances (injected at construction).
- `run(market_data)` executes all brains in parallel via `ThreadPoolExecutor`.
- Returns an `OrchestratorReport` containing per-brain results, latency, vote summary, and a `FinalDecision`.

**`OrchestratorReport`** (dataclass, not Pydantic)
- `unanimous_buy` / `unanimous_sell` convenience properties.
- `vote_summary: dict[str, int]` — count per decision label.

### Voting Rules

| Condition | Final Decision |
|-----------|---------------|
| ≥ 2 brains vote BUY / LONG | BUY |
| ≥ 2 brains vote SELL / SHORT | SELL |
| Any brain returns veto=True | NO_TRADE |
| All other cases | NO_TRADE |

Confidence in the final decision = arithmetic mean of the voting brains' confidence values.

## Files Created (Stage 2.2 Scope)

- `crypto_quant_ai/backend/decision/brain_orchestrator.py`
- `crypto_quant_ai/backend/decision/router.py`
- `crypto_quant_ai/backend/decision/__init__.py` (updated)
- `crypto_quant_ai/backend/tests/test_stage2_multi_brain.py`
- `crypto_quant_ai/docs/stage2-multi-brain.md`

## Safety Constraints (Enforced)

- `LIVE_TRADING=false` — no real exchange connectivity
- No API keys or secrets in scope files
- No changes to BTT/Freqtrade core files
- Orchestrator does not call `ExecutionService` — it only returns a `FinalDecision`

## Stage 2.2 Tests

```bash
cd ~/projects/BTT
PYTHONPATH=. python -m pytest -q crypto_quant_ai/backend/tests/test_stage2_multi_brain.py
```

Expected: 10 passed.
