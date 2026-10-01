``` output
usage: freqtrade install-ui [-h] [--erase] [--prerelease]
                            [--ui-version UI_VERSION]

options:
  -h, --help            show this help message and exit
  --erase               Clean UI folder, don't download new version.
  --prerelease          Install the latest pre-release version of FreqUI. This
                        is not recommended for production use.
  --ui-version UI_VERSION
                        Specify a specific version of FreqUI to install. Not
                        specifying this installs the latest version.

```

## BTT terminal UI development

This source tree also contains the first-party BTT quant terminal in
`freqtrade/rpc/api_server/ui/btt-ui`. It is a Vue 3 and TypeScript single-page
application that uses the existing `/api/v1` endpoints.

``` bash
cd freqtrade/rpc/api_server/ui/btt-ui
npm install
npm run dev
```

The development server proxies API requests to `http://127.0.0.1:8080`. To
create the files served by Freqtrade, run:

``` bash
npm run build
```

The build is written directly to `freqtrade/rpc/api_server/ui/installed`.
Freqtrade's existing catch-all route serves static assets and falls back to
`index.html` for client-side routes such as `/positions` and `/risk`.

The terminal starts in **LIVE** mode and reports individual API failures. The
explicit **DEMO** switch uses labelled local sample data for UI evaluation; it
does not silently replace failed API responses. API credentials entered in
System Settings are exchanged for a JWT and are only retained in the browser
session.

### Market intelligence and AI roundtable

The **Market intelligence** page reads the authenticated
`GET /api/v1/market_intelligence` contract. The bundled backend intentionally
ships without an external news feed or AI model adapter. In LIVE mode the API
therefore returns `unconfigured` provider states, no events, and a rejected
risk decision instead of presenting demo content as real data.

The configuration points are:

``` json
{
  "btt_market_intelligence": {
    "provider": "your-news-adapter",
    "max_age_seconds": 300
  },
  "btt_ai": {
    "provider": "your-model-adapter"
  }
}
```

Provider names alone do not enable a connection. An adapter implementing the
`IntelligenceProvider` protocol must normalize source events into the API
contract, preserve source and publication timestamps, and report connection
errors explicitly. Model adapters must produce role opinions from one immutable
snapshot and include evidence references, confidence, and validity time.
Provider credentials belong in server-side secrets or environment-backed
configuration and must never be sent to the browser or an LLM prompt.

The first version is always **observe only**:

1. News and market providers create a timestamped normalized snapshot.
2. AI roles may propose an action and a coordinator records consensus and
   disagreements.
3. A deterministic risk gate independently checks data freshness, maximum
   position, maximum drawdown, daily loss, and circuit-breaker state.
4. The executor remains disabled. AI services never receive exchange keys and
   cannot bypass a risk veto.

DEMO mode uses clearly labelled local events and simulated opinions only. A
future live integration must add provider adapters and tests without changing
these safety boundaries; connecting a model must not directly enable order
execution.
