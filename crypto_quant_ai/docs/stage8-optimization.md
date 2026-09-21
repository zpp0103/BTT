# Stage 8 — Local Parameter Optimization & Walk-Forward Validation

Paper-only research layer. It searches a parameter space over historical OHLCV
candles and validates the chosen parameters out-of-sample using a walk-forward
scheme. Everything runs locally: no external venue connection, no order is submitted,
no network call, no API credential, `LIVE_TRADING` stays `false`.

## Scope

- New package: `crypto_quant_ai/backend/optimize/` (`types`, `search`,
  `walkforward`, `metrics`, `report`, `formatters`, `__init__`).
- New test suite: `crypto_quant_ai/backend/tests/test_stage8_optimize.py`.
- This document.
- **Reuses, never reimplements**: Stage 4 `BacktestSimulator` / `BacktestConfig`
  / metrics, Stage 5 `ReplayConfig` (`.to_backtest_config()`), Stage 6
  `ComparisonEngine` ranking semantics and report shapes. Stage 1–7 code is
  untouched.

## Why the evaluation uses `BacktestSimulator(risk_gate=None)`

`StrategyReplayer` (Stage 5) hard-wires a `PaperRiskGate` during execution. That
gate requires a stop-loss on every `BUY`/`SELL`, but the Stage 4 simulator emits
`FinalDecision(stop_loss=None)`, so the wired gate rejects every order and no
trade is ever executed — all parameter sets would score identically (degenerate
optimization). The project's own honest local execution path therefore evaluates
each candidate through the Stage 4 `BacktestSimulator` directly with
`risk_gate=None`. This is the same paper-only path used for real-chain
verification: the `PaperExecutor` still runs against a paper account, fees and
slippage are charged, and cash/positions are only ever mutated inside the
executor. No venue, no network, no order leaves the machine.

## Components

| Object | Purpose |
| ------ | ------- |
| `ParamSpec` | one tunable parameter (name, low, high, step, integer) |
| `ParamSpace` | collection of `ParamSpec` (cartesian grid / random sample) |
| `SearchConfig` | method (`grid`/`random`), objective metric, caps, seed |
| `WalkForwardConfig` | train/test window sizes and step |
| `optimize(...)` | evaluate a space over one candle set, return ranked candidates |
| `walk_forward(...)` | slide train/test windows, pick best per window, score OOS |
| `compute_robustness(...)` | in-sample vs out-of-sample decay + stability score |
| `run_optimization(...)` | end-to-end orchestrator → `OptimizationResult` |
| `render_markdown/json/csv`, `export_report` | report formatters |

## Reused interfaces (locked, read-only)

- `BacktestSimulator(config, risk_gate=None, audit_log=...)`
  `.run(candles, signal_fn, symbol="BTC") -> BacktestResult`
  with `.is_completed` and `.metrics` (`sharpe_ratio`, `total_return`,
  `total_return_pct`, `max_drawdown_pct`, `final_equity`, `total_trades`,
  `profit_factor`, `win_rate_pct`, ...).
- `ReplayConfig(initial_cash, fee_bps, slippage_bps, symbol, paper_trading=True)`
  `.to_backtest_config() -> BacktestConfig`.
- `CandleSignal(timestamp, symbol, action: TradeAction, price, quantity, reason)`.

## Example

```python
from crypto_quant_ai.backend.optimize import (
    ParamSpace, ParamSpec, SearchConfig, WalkForwardConfig, run_optimization,
)
from crypto_quant_ai.backend.replay.types import ReplayConfig

space = ParamSpace(params=(
    ParamSpec(name="short_window", low=3, high=7, step=2, integer=True),
    ParamSpec(name="long_window", low=10, high=20, step=5, integer=True),
    ParamSpec(name="threshold", low=0.0, high=0.02, step=0.01),
    ParamSpec(name="position_fraction", low=0.1, high=0.3, step=0.2),
))
result = run_optimization(
    space, candles, SearchConfig(method="grid"),
    WalkForwardConfig(train_size=60, test_size=30, step=30),
    ReplayConfig(initial_cash=100000.0, fee_bps=10.0, slippage_bps=5.0, symbol="BTC"),
)
print(result.best_params, result.robustness)
```

## Running the tests

```bash
cd ~/projects/BTT
PYTHONPATH=. /Users/a123/Library/Application\ Support/QClaw/python/bin/python3.11 \
  -m pytest -q crypto_quant_ai/backend/tests/test_stage8_optimize.py --noconftest
```

## Acceptance

- All Stage 8 tests pass (no `MagicMock`; real paper simulator execution).
- Full backend regression stays green (no Stage 1–7 regression).
- Safety scan: no venue-adapter, credential, or order-submission literals, and no
  lowercase form of the live-execution flag, in `optimize/` or this document.
- `LIVE_TRADING` guard raises `RuntimeError` at import time when set `true`.
- Git scope limited to `crypto_quant_ai/**` and `docs/**`.
