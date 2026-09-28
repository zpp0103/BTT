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

## Authentication

System Settings exchanges API credentials for Freqtrade JWTs. Credentials are
never stored; access and refresh tokens live in `sessionStorage`, expired access
tokens are refreshed automatically, and **Disconnect current session** clears
the saved tokens immediately.
