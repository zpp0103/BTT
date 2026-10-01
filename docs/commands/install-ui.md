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
`GET /api/v1/market_intelligence` contract. The bundled `rss` provider reads
public RSS/Atom feeds with an explicit timeout and User-Agent, normalizes event
timestamps and sources, removes duplicate headlines, and tolerates individual
feed failures. External content is untrusted data and is never treated as
instructions.

The configuration points are:

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
    "timeout_seconds": 90
  }
}
```

Custom RSS sources can be configured as `{id, label, url}` objects in
`btt_market_intelligence.sources`. Use only feeds whose terms permit automated
subscription. The default sources are the Ethereum Foundation Blog, CoinDesk
RSS, and Cointelegraph RSS; each source reports its own connected/error state.

AI adapters support local Ollama and OpenAI-compatible chat-completions:

- `ollama` defaults to `http://127.0.0.1:11434` and requires a local model.
- `openai_compatible` accepts `base_url`, `model`, and `api_key_env`. The key is
  read only from the named server-side environment variable (default
  `BTT_AI_API_KEY`); it is never returned by the API or sent to the browser.

Both adapters submit the same immutable, timestamped snapshot to all four roles.
News fields are length/quantity limited, prompts declare them untrusted, and
responses must pass strict Pydantic validation, contain all four required roles,
and cite only supplied event IDs. Timeout, HTTP, JSON, schema, or citation errors
make AI explicitly unavailable; there is no synthetic fallback.

The first version is always **observe only**:

1. News and market providers create a timestamped normalized snapshot.
2. AI roles may propose an action and a coordinator records consensus and
   disagreements.
3. A deterministic risk gate independently checks data freshness, maximum
   position, maximum drawdown, daily loss, and circuit-breaker state.
4. The executor remains disabled. AI services never receive exchange keys and
   cannot bypass a risk veto.

DEMO mode uses clearly labelled local events and simulated opinions only.
Additional live providers must preserve these contracts and safety boundaries;
connecting a model must not directly enable order execution.

### Local ports and startup

All defaults bind only to loopback:

| Service | Address | Purpose |
| --- | --- | --- |
| Freqtrade + BTT UI | `127.0.0.1:8080` | Same-origin production API and UI |
| Vite | `127.0.0.1:5173` | Frontend development server |
| Ollama | `127.0.0.1:11434` | Local OpenAI-free model runtime |

Set up a project-local Python 3.11 environment, install dependencies, and run
the diagnostics:

``` bash
uv python install 3.11
uv venv --python 3.11
uv pip install --python .venv/bin/python -e '.[develop]'
.venv/bin/python scripts/btt-local.py check
```

Copy `.env.example` values into your shell or an untracked `.env` if ports or
model settings need to change. Generate a random local API password and JWT
secret, then start webserver mode:

``` bash
.venv/bin/python scripts/btt-local.py generate-config
.venv/bin/python scripts/btt-local.py start
```

The generated config and credentials are under ignored `user_data/`, mode 0600.
The script refuses to replace an occupied port and never kills another process.
For frontend development use:

``` bash
cd freqtrade/rpc/api_server/ui/btt-ui
npm run dev -- --host 127.0.0.1 --port 5173
```
