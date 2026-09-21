# Stage 5 — Local Strategy Replay & Performance Report

## Goal
Build a local strategy replay pipeline that composes Stage 1–4 modules into a deterministic, auditable, paper-only report engine.

## Safety
- LIVE_TRADING=false
- No live trading
- No real orders
- No exchange connections
- No API key or secret
- No network requests
- No BTT/Freqtrade core changes

## Modules
- `crypto_quant_ai/backend/replay/types.py`
- `crypto_quant_ai/backend/replay/config.py`
- `crypto_quant_ai/backend/replay/registry.py`
- `crypto_quant_ai/backend/replay/strategy.py`
- `crypto_quant_ai/backend/replay/engine.py`
- `crypto_quant_ai/backend/replay/report.py`
- `crypto_quant_ai/backend/replay/__init__.py`

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
