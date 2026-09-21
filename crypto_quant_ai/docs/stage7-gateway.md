# Stage 7 — Safe Paper Trading Gateway (Plan A)

> Plan A (safe-constructible version). No external venue connection, no external orders,
> no credentials. `LIVE_TRADING` stays `false`. Reuses Stage 3.1–3.4 modules
> unchanged.

## Scope

Stage 7 adds a single-user, single-account, single-symbol, single-timeframe,
single-strategy paper trading gateway. It is the integration layer that wires
decisions through a circuit breaker, the Stage 3.3 risk gate, the Stage 3.2
executor, the Stage 3.1 account, and the Stage 3.4 audit log, then mirrors the
result into a simulated venue ledger for reconciliation.

This version is deliberately **not** a live trading bridge. The external venue
adapter is a gated stub: it never opens a network socket, never reads
credentials, and never submits an order to an external venue.

## Architecture

```
decision (FinalDecision)
   -> CircuitBreaker.pre_trade        (Stage 7, fixed params)
   -> PaperRiskGate.check             (Stage 3.3, reused)
   -> PaperExecutor.execute           (Stage 3.2, gate-then-execute, reused)
   -> PaperAccount mutation           (Stage 3.1, reused)
   -> AuditLog                        (Stage 3.4, reused)
   -> SimulatedVenueLedger            (gated stub, no network)
   -> Monitor / Alert
   -> PostTradeReconciliation         (local audit vs simulated ledger)
```

## Package layout

`crypto_quant_ai/backend/gateway/`

| File | Responsibility |
|------|----------------|
| `types.py` | Frozen + finite configuration (`GatewayConfig`, `RiskManagerConfig`, `CircuitBreakerConfig`, `GatewayStatus`) |
| `hashing.py` | Deterministic `compute_gateway_hash` (excludes runtime state) |
| `venue.py` | `ExternalVenueAdapter` (gated stub) + `SimulatedVenueLedger` + `VenueFill` |
| `risk.py` | `CircuitBreaker` (hard stops) + `RiskManager` (wraps `PaperRiskGate`) |
| `monitor.py` | `Monitor` + in-memory `Alert` (no external sink) |
| `reconcile.py` | `PostTradeReconciliation` (local audit vs simulated ledger) |
| `session.py` | `LiveTradingSession` (explicit start/stop, single strategy) + `GatewayExecutionResult` |
| `report.py` | `GatewayReport` + `GatewayReportGenerator` |
| `formatters.py` | markdown / json / csv exporters |
| `__init__.py` | Public exports |

## Safety guarantees

1. **Three-layer `LIVE_TRADING` guard** — module import, `start()`, and
   `ExternalVenueAdapter.submit()` each refuse when live trading is enabled.
2. **No network** — the venue adapter is a stub; it performs no socket, HTTP,
   or credential operations.
3. **Reused risk path** — every decision still passes `PaperRiskGate` and is
   recorded in the local `AuditLog`.
4. **Fixed parameters** — configuration is frozen; no automatic tuning while a
   session runs.
5. **Explicit lifecycle** — a session is started and stopped by direct calls;
   there is no daemon and no background automation.

## Circuit breaker

The breaker is the Stage 7 addition on top of the Stage 3.3 gate:

- `max_order_notional` — per-order notional ceiling (pre-trade).
- `price_anomaly_pct` — entry vs reference price deviation ceiling (pre-trade).
- `daily_loss_limit` — realized intra-day loss ceiling (post-trade).
- `max_drawdown_pct` — peak-to-current equity drawdown ceiling (post-trade).

Once tripped, the breaker blocks all further submissions until the session is
recreated (stop + new session).

## Reconciliation

`PostTradeReconciliation` compares the local `AuditLog` (source of truth from
the executor) against the simulated venue ledger. It reports matched fills and
any mismatch in side / quantity / price. Because both are fed from the same
executed order, a healthy run reports `ok = true`.

## Determinism

`compute_gateway_hash` returns the SHA-256 of the frozen configuration. It never
includes `started_at`, `stopped_at`, the current time, or any random value, so
identical configuration always yields the same hash.

## Usage

```python
from crypto_quant_ai.backend.gateway import (
    GatewayConfig, LiveTradingSession, compute_gateway_hash,
)

config = GatewayConfig(initial_cash=100000.0)
session = LiveTradingSession(config)
session.start()
result = session.submit_decision(decision)  # a FinalDecision
session.stop()
report = session.reconcile()
```

## Test matrix

Run from the repository root:

```bash
PYTHONPATH=. python -m pytest -q \
  crypto_quant_ai/backend/tests/test_stage7_gateway.py --noconftest
```

The suite covers: configuration freezing/finite validation, the full paper order
lifecycle, gate rejection (missing stop loss / low confidence), veto and
no-trade skips, circuit-breaker guards (notional / anomaly / daily loss /
persistence), venue stub live-guard, monitor alerts, reconciliation (ok and
mismatch), report generation, and a self-contained forbidden-token scan.
