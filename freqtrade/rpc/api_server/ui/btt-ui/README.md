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
execution state. No external news or model adapter is bundled, so LIVE mode
honestly renders providers as unconfigured until server-side adapters are
installed. DEMO events and opinions are local, simulated, and visibly labelled.

## Authentication

System Settings exchanges API credentials for Freqtrade JWTs. Credentials are
never stored; access and refresh tokens live in `sessionStorage`, expired access
tokens are refreshed automatically, and **Disconnect current session** clears
the saved tokens immediately.

AI output is advisory only. Every proposal is evaluated by an independent,
deterministic risk gate, stale data is vetoed, and the first release keeps the
executor in `observe_only` mode. Exchange credentials are never exposed to AI
providers.
