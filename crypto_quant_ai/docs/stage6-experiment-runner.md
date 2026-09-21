# Stage 6 — Local Experiment Runner & Comparative Strategy Analysis

Local-only layer that executes multiple `StrategySpec` definitions over the same
local OHLCV bars, each in full isolation, then compares and ranks results and
exports a report. Built on top of Stage 5 (`StrategyReplayer` / `ReplayConfig`
/ `StrategySpec`) and Stage 4 (`BacktestSimulator` / metrics / audit).

**Safety posture:** No network access. No exchange integration. No real orders.
No credentials. Paper trading only. `LIVE_TRADING=false`. The runner raises
`RuntimeError` if `LIVE_TRADING=true`.

## Files

- `crypto_quant_ai/backend/experiments/__init__.py` — public exports
- `crypto_quant_ai/backend/experiments/types.py` — `ExperimentConfig`, `ExperimentRun`, `ExperimentReport`, `ComparisonRow`, `RunStatus`, experiment hashing
- `crypto_quant_ai/backend/experiments/runner.py` — `ExperimentRunner`, `ExperimentResult`
- `crypto_quant_ai/backend/experiments/comparison.py` — `ComparisonEngine`
- `crypto_quant_ai/backend/experiments/report.py` — `build_report`
- `crypto_quant_ai/backend/experiments/formatters.py` — `render_markdown` / `render_json` / `render_csv` / `export_report`
- `crypto_quant_ai/backend/tests/test_stage6_experiments.py` — 46 tests
- `crypto_quant_ai/docs/stage6-experiment-runner.md` — this document

## ExperimentConfig (frozen)

| field | meaning |
| --- | --- |
| `experiment_id` | non-empty id |
| `name` | human name |
| `description` | text |
| `strategies` | tuple of `StrategySpec` (order preserved, ids unique, >=1) |
| `replay_config` | `ReplayConfig` (must have `paper_trading=True`) |
| `baseline_strategy_id` | optional, must match a strategy id |
| `fail_fast` | if True, stop and mark rest SKIPPED after first failure |

Validation (in `__post_init__`): rejects empty id, empty name, empty strategy
list, duplicate strategy ids, unknown baseline, and any replay config that is not
paper-only. Nested `ReplayConfig` / `RiskGateSpec` already enforce finite,
positive, paper-only numeric constraints, so no fabricated NaN/Inf slips through.

## Execution model (real components)

`ExperimentRunner.run(candles, config)`:

1. Guards `LIVE_TRADING` (raises if true).
2. Computes a deterministic `experiment_hash` from config + candles.
3. For each strategy (in declared order):
   - Builds a **fresh** `StrategyReplayer` = own `ReplayConfig` instance, own
     `PaperAccount`, own `AuditLog`, own `BacktestSimulator`, `EquityTracker`,
     `TradeLedger`. Account and audit are fully isolated per strategy.
   - Calls `replayer.run(candles)`.
   - A `FAILED` replay (empty candles → `ValueError`; non-chronological candles →
     `FAILED` result) is recorded as `RunStatus.FAILED` with the real error
     message. Never faked as `COMPLETED`.
   - With `fail_fast=True`, once a strategy fails the remaining strategies are
     recorded as `SKIPPED`.
4. Assembles `ExperimentResult` (runs, comparison rows, `ExperimentReport`).

The caller's candle sequence is copied; it is never mutated.

## Real execution chain (no mocks)

- Each strategy runs through the genuine `MultiBrainOrchestrator` (Stage 2.2) and
  `StrategyReplayer` (Stage 5), which wire a real `PaperRiskGate` and
  `PaperExecutor` into the `BacktestSimulator` (Stage 4).
- The Stage 4 simulator builds `FinalDecision(stop_loss=None)`. Because the wired
  `PaperRiskGate` requires a stop loss for BUY/SELL, a plain replay over the stub
  NO_TRADE brains completes with **zero executed trades** (safe default) and the
  risk gate would reject any injected BUY/SELL lacking a stop loss — cash and
  positions remain unchanged and a `rejected` audit event is recorded. This is the
  honest, real rejection path (created → validated → rejected), not a simulation.
- Fee accounting is demonstrated on the reused Stage 4 engine with the gate
  disabled: a BUY `signal_fn` fills and the simulator deducts the fee from the
  account, so `final_equity(fee_bps=0) > final_equity(fee_bps=10)`.

## Comparison engine

`ComparisonEngine.rank(runs)` ranks **only completed** runs by the key:

1. `sharpe_ratio` desc
2. `total_return_pct` desc
3. `max_drawdown_pct` asc
4. `strategy_id` asc (stable)

`ComparisonEngine.baseline_compare(runs, baseline_id)` returns per-strategy
`vs_baseline_return_pct = run.total_return_pct - baseline.total_return_pct`. If the
baseline is missing or failed, it reports `available=False` with no fabricated
values.

## Reports

`ExperimentReport` serializes via `to_dict()` and three formatters:

- `render_markdown(report)` — human-readable summary (config, ranking, baseline, failures, safety).
- `render_json(report)` — JSON, `datetime` -> ISO string, sort-keys.
- `render_csv(report)` — one row per strategy, stable header, equal-width rows.
- `export_report(report, output_dir)` — writes the three files locally (no network).

## Experiment hash (canonical, deterministic)

`compute_experiment_hash(config, candles)` hashes a canonical JSON payload built
by `experiment_payload`: `experiment_id`, `name`, `description`, `fail_fast`,
`baseline_strategy_id`, `replay_config` (asdict), every `StrategySpec` (asdict,
including its `RiskGateSpec`), and the raw candle series
(`timestamp/open/high/low/close/volume`) in original order. `generated_at` is
explicitly excluded, so identical inputs always produce the same hash; changing any
strategy, config, baseline, or candle changes the hash.

## Tests (46)

Coverage groups: configuration validation (empty/duplicate/invalid-baseline/empty-id/
NaN-Inf/non-paper), execution (single/multi, account & audit isolation, input hashes,
empty/descending candles fail, fail_fast behaviour, no-fabrication, candles unmodified,
independent replay), comparison (sharpe priority, return secondary, drawdown tertiary,
id tie-break, determinism, baseline diff, baseline failure, rank excludes failed/skipped,
real rejection statistics, fee reaches equity, finite metrics), report (markdown/json/csv,
column consistency, hash presence, input hashes, failure reason, hash independent of time,
no sensitive fields), and safety (LIVE_TRADING blocks run, no forbidden tokens in source,
no exchange dependency, no real orders, Stage 1–5 components importable).

## Real multi-strategy run

`test_real_multi_strategy_run` builds two `StrategySpec` (each with >=2 brains), runs
them through `ExperimentRunner` over local bars, and asserts both complete, accounts and
audits are isolated, input + experiment hashes are present, ranking has both rows, the
report serializes, and the safety statement is present.
