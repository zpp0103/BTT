# BTT terminal

The first-party BTT quant terminal is a Vue 3 and TypeScript single-page
application in `freqtrade/rpc/api_server/ui/btt-ui`. It uses authenticated
`/api/v1` contracts and writes its production bundle to
`freqtrade/rpc/api_server/ui/installed`.

## Frontend development

``` bash
cd freqtrade/rpc/api_server/ui/btt-ui
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

The development server proxies API requests to `http://127.0.0.1:8080`.
Run `npm run build` to type-check and build the files served by Freqtrade.
The existing catch-all route serves static assets and falls back to
`index.html` for client-side routes.

The terminal starts in **LIVE** mode and reports individual API failures.
The explicit **DEMO** switch uses labelled local sample data and never silently
replaces a failed live response. Credentials entered in System Settings are
exchanged for a JWT and retained only in the browser session.

## Market intelligence and AI roundtable

The **Market intelligence** page reads the authenticated
`GET /api/v1/market_intelligence` contract. The bundled `rss` provider reads
public RSS/Atom feeds with an explicit timeout and User-Agent, normalizes
timestamps and sources, removes duplicate headlines, and tolerates individual
feed failures. External content is untrusted data and is never treated as
instructions.

``` json
{
  "btt_market_intelligence": {
    "provider": "rss",
    "timeout_seconds": 8,
    "max_events": 30,
    "max_age_seconds": 300
  },
  "btt_ai": {
    "provider": "ollama",
    "base_url": "http://127.0.0.1:11434",
    "model": "qwen2.5:1.5b",
    "timeout_seconds": 300
  }
}
```

Custom feeds are configured as `{id, label, url}` objects in
`btt_market_intelligence.sources`. Use only sources whose terms permit
automated subscription. The defaults are the Ethereum Foundation Blog,
CoinDesk RSS, and Cointelegraph RSS; each source reports its own connection
state.

AI adapters support local Ollama and OpenAI-compatible chat completions:

- `ollama` defaults to `http://127.0.0.1:11434` and requires a local model.
- `openai_compatible` accepts `base_url`, `model`, and `api_key_env`. The key is
  read only from the named server-side environment variable, which defaults to
  `BTT_AI_API_KEY`; it is never returned by the API or sent to the browser.

Both adapters submit the same immutable, timestamped snapshot to all four
roles. News fields are bounded, prompts declare them untrusted, and responses
must contain all four roles, pass strict validation, and cite only supplied
event IDs. Timeout, HTTP, JSON, schema, or citation errors make AI explicitly
unavailable; there is no synthetic fallback.

The first version is always **observe only**:

1. Providers create a timestamped normalized snapshot.
2. AI roles may propose an action and record consensus and disagreements.
3. A deterministic risk gate checks data freshness, maximum position, maximum
   drawdown, daily loss, and circuit-breaker state.
4. The executor remains disabled. AI never receives exchange keys and cannot
   bypass a risk veto.

DEMO mode uses clearly labelled local events and simulated opinions only.

## Institutional read-only APIs

API 2.55 adds authenticated, trading-mode contracts:

- `/effective_risk` and `/decision_journal` expose bounded persisted risk and
  decision evidence. Missing limits remain `unconfigured`; missing facts remain
  `null` or `unavailable`, not zero.
- `/market_observer` reads cached analyzed OHLCV across bounded pairs,
  timeframes, and candles. It is `observe_only`, performs no exchange download,
  and is not consumed by live strategies.
- `/execution_quality` derives bounded fee, lifecycle, latency, and price
  deviation coverage from persisted trades and orders.
- `/strategy_governance` fingerprints the active strategy and reads only the
  bounded latest backtest artifact. `promotion_allowed` is always `false`.
- `/system_observability` reports aggregate runtime, database, resource, and
  log-level health without raw messages, stack traces, configuration, or paths.

These surfaces are read-only, declare `affects_trading: false`, add no database
migration or trading-path write, and use the existing Basic/JWT plus
trading-mode guards.

## Local ports and startup

All defaults bind only to loopback:

| Service | Address |
| --- | --- |
| Freqtrade API and BTT UI | `127.0.0.1:8080` |
| Vite development server | `127.0.0.1:5173` |
| Ollama | `127.0.0.1:11434` |

``` bash
uv python install 3.11
uv venv --python 3.11
uv pip install --python .venv/bin/python -e '.[develop]'
.venv/bin/python scripts/btt-local.py check
```

Copy `.env.example` values into the shell or an untracked `.env` when ports or
model settings need to change. Generate random local credentials and start
webserver mode:

``` bash
OLLAMA_HOST=127.0.0.1:11434 ollama serve
OLLAMA_HOST=127.0.0.1:11434 ollama pull qwen2.5:1.5b
.venv/bin/python scripts/btt-local.py generate-config
.venv/bin/python scripts/btt-local.py start
```

Generated configuration and credentials are stored under ignored `user_data/`
with mode 0600. The helper refuses to replace an occupied port and never kills
another process.
