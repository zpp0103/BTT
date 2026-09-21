# Stage 9 — Intelligence Orchestration Layer

Local, paper-only, explainable research layer that composes Stage 1–8 capabilities
into one decision-support loop. It never submits orders, never contacts an external
venue, and never relaxes any existing risk boundary. `LIVE_TRADING` must remain `false`.

## Scope

- **New package only:** `crypto_quant_ai/backend/intelligence/`
- Does **not** modify Stage 1–8 code, `requirements.txt`, or `pyproject.toml`.
- Reuses (does not rewrite) the real paper-chain and reporting APIs from earlier stages.

## Architecture (4 sub-layers)

```
                  ┌──────────────────────────────────────────┐
   candles  ───▶  │     IntelligenceOrchestrator.analyze()     │
                  └──────────────────────────────────────────┘
                                   │
        ┌──────────────┬───────────┴───────────┬───────────────┐
        ▼              ▼                       ▼               ▼
  [L1] Market      [L2] Decision           [L3] Research    [L4] Synthesis
   State            Board                    (optimize/        → IntelligenceReport
                    (brains)                 walk-forward)     → markdown/json/csv
```

### L1 — Market State (`market_state.py`)
Classifies regime (trend / range / high-vol / low-vol) from OHLCV using finite-safe
volatility and trend-strength features. `consensus_regime()` votes across multiple
windows.

### L2 — Decision Board (`decision_board.py`)
Wraps `MultiBrainOrchestrator.run(market_data)` into a structured `DecisionBrief`:
action, confidence, supporters, opponents, failure conditions, alternatives. Adds
explainability on top of the existing brain committee — no execution.

### L3 — Research (`research.py`)
Reuses Stage 8 `run_optimization(space, candles, search, wf, replay_config)`.
Adds, by pure post-processing (no rewrite):
- **Sensitivity map** — mean objective per parameter value, derived from the candidate grid.
- **Overfitting flags** — from walk-forward in-sample vs out-of-sample gaps and the
  robustness `stability_score`.

### L4 — Orchestrator + Report (`orchestrator.py`, `report.py`, `formatters.py`)
`IntelligenceOrchestrator.analyze()` ties L1–L3 together and returns a frozen
`IntelligenceReport` (market state + decision brief + research + recommendation +
risk notes + explainable text). `render_markdown/json/csv` and `export_report` mirror
the Stage 5/6 output conventions.

## Reused real APIs (verified)

| Capability | Source |
|---|---|
| `BacktestSimulator(config, risk_gate=None, audit_log)` / `.run(candles, signal_fn, symbol)` | Stage 4 |
| `ReplayConfig(...).to_backtest_config()`, `StrategyReplayer` | Stage 5 |
| `ExperimentRunner`, `ComparisonEngine` (rank) | Stage 6 |
| `ParamSpace`, `SearchConfig`, `WalkForwardConfig`, `run_optimization`, `compute_robustness` | Stage 8 |
| `MultiBrainOrchestrator`, `build_brains`, `OrchestratorReport`, `FinalDecision`, `BrainAnalysis` | Stage 1 / 3.1 |
| `MarketData`, `OHLCVBar` | core models / data |

## Safety

- `LIVE_TRADING=true` raises `RuntimeError` at import and at `analyze()`.
- All metrics use `math.isfinite` guards; no network, no venue, no order submission.
- Paper-only path is identical to the Stage 4/8 verification path (`risk_gate=None`).

## Usage

```python
from crypto_quant_ai.backend.intelligence import IntelligenceOrchestrator, render_markdown
from crypto_quant_ai.backend.optimize.types import ParamSpace, ParamSpec, SearchConfig, WalkForwardConfig
from crypto_quant_ai.backend.replay.types import ReplayConfig

candles = [...]  # list[OHLCVBar]
orch = IntelligenceOrchestrator()
report = orch.analyze(
    candles,
    symbol="BTC",
    space=ParamSpace((ParamSpec("short_window", 3, 20, 1, integer=True),
                     ParamSpec("long_window", 10, 60, 5, integer=True),
                     ParamSpec("position_fraction", 0.05, 0.3, 0.05),
                     ParamSpec("threshold", 0.0, 0.05, 0.01))),
    search=SearchConfig(method="grid", metric="sharpe_ratio"),
    wf=WalkForwardConfig(train_size=60, test_size=30, step=30),
)
print(render_markdown(report))
```

## Outputs

- `IntelligenceReport` (programmatic) with `explainable_text`.
- `intelligence_report.{md,json,csv}` via `export_report(output_dir=...)`.

## Acceptance

- New package adds only the `intelligence/` module and its tests/docs; no other source changes.
- Stage 9 test suite passes; full backend regression passes with no regressions.
- Safety scan reports no forbidden literals; `LIVE_TRADING=false` holds.
- `git diff --check` clean; changes stay within the allowed directories.
