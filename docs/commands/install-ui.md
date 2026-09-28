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
