# Stage 5 — Local Strategy Replay & Performance Report

## Goal
Build a local strategy replay pipeline that composes Stage 1–4 modules into a deterministic, auditable, paper-only report engine.

## Safety
- LIVE_TRADING=false
- No live trading
- No real orders
- No exchange connections
- No API key or secret
- No network calls
- No BTT/Freqtrade core changes

## Modules
- `crypto_quant_ai/backend/replay/types.py`
- `crypto_quant_ai/backend/replay/config.py`
- `crypto_quant_ai/backend/replay/registry.py`
- `crypto_quant_ai/backend/replay/strategy.py`
- `crypto_quant_ai/backend/replay/engine.py`
- `crypto_quant_ai/backend/replay/report.py`
- `crypto_quant_ai/backend/replay/__init__.py`

## Real Execution Chain (wired, not reimplemented)
The replayer is a thin orchestration layer. It does NOT reimplement trading, risk,
audit, or metrics. It wires the existing Stage 2.2 / 3.2 / 3.3 / 3.4 / 4
components and reports on the results they produce:

```
signal_fn(candle, account)            # built from MultiBrainOrchestrator (Stage 2.2)
  -> BacktestSimulator.run            # Stage 4 candle loop
  -> simulator builds OrchestratorReport
  -> PaperExecutor.execute(report)    # Stage 3.2
       -> report.final_decision
       -> PaperRiskGate.check(decision)   # Stage 3.3 (wired into the executor)
       -> AuditLog events                  # Stage 3.4
```

Every order routes through the real PaperExecutor; cash and positions are never
mutated outside it. All activity is paper-only (LIVE_TRADING=false).

### Risk gate hidden in the execution chain
The engine wires a real PaperRiskGate (configured from the strategy's
RiskGateSpec) into the executor. The gate is genuinely enforced during
execution: a BUY or SELL whose policy fails (missing stop-loss, exceeded size,
etc.) is rejected and leaves cash/positions unchanged
(`created -> validated -> rejected`). The Stage 4 simulator emits
`FinalDecision.stop_loss=None`, so the gate rejects every BUY/SELL by default
(no stop-loss policy) — the safe default. A real strategy's brains supply the
stop-loss to permit a trade.

## Flow
1. Read OHLCV bars (local, non-live)
2. Match strategy definition to brains
3. Invoke MultiBrainOrchestrator (Stage 2.2)
4. Convert decision to CandleSignal
5. Backtest via Stage 4 simulator (with PaperRiskGate + AuditLog: Stage 3.3 + 3.4)
6. Build report and export JSON / Markdown / CSV

## Reused capabilities (no reimplementation)
- `MultiBrainOrchestrator` / `OrchestratorReport` (Stage 2.2)
- `PaperExecutor` (Stage 3.2)
- `PaperRiskGate` (Stage 3.3)
- `AuditLog` (Stage 3.4)
- `BacktestSimulator` / `BacktestConfig` / `compute_metrics` / `EquityTracker` / `TradeLedger` (Stage 4)

## Validation
- Stage 5 tests pass
- Full backend tests pass
- Safety scan clean
- LIVE_TRADING=false

## Final Decision
Stage 5 is a local replay and report engine only. It does not implement live orders, exchange APIs, or real-world trading.
