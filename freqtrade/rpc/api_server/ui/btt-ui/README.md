# BTT Quant Terminal

Vue 3 + TypeScript SPA for the BTT desktop quant terminal.

## Commands

```bash
npm install
npm run dev
npm test
npm run build
```

`npm run build` type-checks the app and writes the deployable bundle to the
adjacent `../installed` directory used by `web_ui.py`.

## API mapping

The dashboard reads the existing Freqtrade API only:

| UI data | Endpoint |
| --- | --- |
| API status | `GET /api/v1/ping` |
| Bot, strategy, exchange, mode | `GET /api/v1/show_config` |
| Net asset value | `GET /api/v1/balance` |
| Equity curve | `GET /api/v1/historic_balance` |
| Return and risk metrics | `GET /api/v1/profit` |
| Open positions | `GET /api/v1/status` |
| Recent closed trades | `GET /api/v1/trades` |
| Bot heartbeat | `GET /api/v1/health` |
| CPU and memory | `GET /api/v1/sysinfo` |

Requests are isolated so one failing endpoint does not hide other live data.
Demo data is opt-in and always marked `DEMO`.

`GET /api/v1/market_intelligence` supplies the normalized news snapshot,
provider health, AI roundtable result, deterministic risk decision, and
execution state. LIVE mode uses the bundled public RSS/Atom adapter and reports
each source failure. AI supports local Ollama or an OpenAI-compatible endpoint;
it remains visibly unavailable unless a model actually returns valid,
evidence-linked JSON. DEMO events and opinions are local, simulated, and visibly
labelled.

## Authentication

System Settings exchanges API credentials for Freqtrade JWTs. Credentials are
never stored; access and refresh tokens live in `sessionStorage`, expired access
tokens are refreshed automatically, and **Disconnect current session** clears
the saved tokens immediately.

AI output is advisory only. Every proposal is evaluated by an independent,
deterministic risk gate, stale data is vetoed, and the first release keeps the
executor in `observe_only` mode. Exchange credentials are never exposed to AI
providers.

## Institutional read-only surfaces

The dashboard also consumes authenticated, trading-mode API 2.55 contracts:

- `/effective_risk` and `/decision_journal` expose bounded persisted risk and
  decision evidence. Missing limits remain `unconfigured`; missing facts remain
  `null`/`unavailable`, not zero.
- `/market_observer` reads cached analyzed OHLCV across bounded pairs,
  timeframes, and candles. It is `observe_only`, reports freshness and coverage,
  does not download exchange data, and is not consumed by live strategies.
- `/execution_quality` derives bounded fee, lifecycle, latency, and price
  deviation coverage from persisted trades/orders. It is `read_only`.
- `/strategy_governance` fingerprints the active strategy and reads only the
  bounded latest backtest artifact. `promotion_allowed` is always `false`; no
  strategy is approved, published, or switched.
- `/system_observability` reports aggregate runtime/database/resource health and
  log-level counts. Raw log messages, stack traces, configuration, and source
  paths are deliberately excluded.

All five surfaces declare `affects_trading: false` (or the equivalent risk
capability boundary), add no database migration or trading-path write, and use
the existing Basic/JWT plus trading-mode guards. The client distinguishes
server-native facts from client-derived compatibility fallbacks.
