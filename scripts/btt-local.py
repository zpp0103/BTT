#!/usr/bin/env python3
import argparse
import base64
import json
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = ROOT / "user_data" / "btt-local-config.json"
LOCAL_INFO = ROOT / "user_data" / "btt-local-credentials.txt"
HOST = os.environ.get("BTT_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("BTT_API_PORT", "8080"))
VITE_PORT = int(os.environ.get("BTT_VITE_PORT", "5173"))
OLLAMA_PORT = int(os.environ.get("BTT_OLLAMA_PORT", "11434"))


def require_python() -> None:
    if sys.version_info[:2] != (3, 11):
        raise SystemExit(
            f"Python 3.11 is required; current interpreter is {sys.version.split()[0]}. "
            "Run with .venv/bin/python scripts/btt-local.py."
        )


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((HOST, port)) == 0


def http_status(url: str, headers: dict[str, str] | None = None) -> tuple[bool, str]:
    try:
        request = Request(url, headers=headers or {"User-Agent": "BTT-Local-Diagnostics/0.1"})
        with urlopen(request, timeout=3) as response:
            return True, f"HTTP {response.status}"
    except (URLError, TimeoutError, OSError) as exc:
        return False, type(exc).__name__


def provider_status(username: str, password: str) -> str:
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    try:
        login = Request(
            f"http://{HOST}:{API_PORT}/api/v1/token/login",
            method="POST",
            headers={"Authorization": f"Basic {credentials}", "Content-Length": "0"},
        )
        with urlopen(login, timeout=5) as response:
            access_token = json.load(response)["access_token"]
        request = Request(
            f"http://{HOST}:{API_PORT}/api/v1/market_intelligence",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urlopen(request, timeout=120) as response:
            payload = json.load(response)
        statuses = ", ".join(
            f"{provider['provider_id']}={provider['status']}"
            for provider in payload["providers"]
        )
        return f"source={payload['source_mode']} events={len(payload['events'])} {statuses}"
    except (URLError, TimeoutError, OSError, KeyError, ValueError) as exc:
        return f"unavailable ({type(exc).__name__})"


def generate_config() -> tuple[str, str]:
    LOCAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if LOCAL_CONFIG.exists():
        payload = json.loads(LOCAL_CONFIG.read_text())
        return payload["api_server"]["username"], payload["api_server"]["password"]
    username = "btt-local"
    password = secrets.token_urlsafe(18)
    payload = {
        "dry_run": True,
        "exchange": {
            "name": "binance",
            "key": "",
            "secret": "",
            "pair_whitelist": ["BTC/USDT"],
            "pair_blacklist": [],
        },
        "dataformat_ohlcv": "feather",
        "dataformat_trades": "feather",
        "api_server": {
            "enabled": True,
            "listen_ip_address": HOST,
            "listen_port": API_PORT,
            "verbosity": "error",
            "CORS_origins": [f"http://{HOST}:{VITE_PORT}"],
            "username": username,
            "password": password,
            "jwt_secret_key": secrets.token_hex(32),
        },
        "btt_market_intelligence": {
            "provider": "rss",
            "timeout_seconds": 8,
            "max_events": 30,
            "max_age_seconds": 300,
        },
        "btt_ai": {
            "provider": os.environ.get("BTT_AI_PROVIDER", "ollama"),
            "base_url": os.environ.get(
                "BTT_AI_BASE_URL", f"http://{HOST}:{OLLAMA_PORT}"
            ),
            "model": os.environ.get("BTT_AI_MODEL", "qwen2.5:1.5b"),
            "api_key_env": "BTT_AI_API_KEY",
            "timeout_seconds": 90,
        },
    }
    LOCAL_CONFIG.write_text(json.dumps(payload, indent=2) + "\n")
    LOCAL_INFO.write_text(
        f"BTT_API_USERNAME={username}\nBTT_API_PASSWORD={password}\n"
    )
    LOCAL_CONFIG.chmod(0o600)
    LOCAL_INFO.chmod(0o600)
    return username, password


def check() -> int:
    require_python()
    username, password = generate_config()
    checks = [
        ("Freqtrade/BTT API", API_PORT, f"http://{HOST}:{API_PORT}/api/v1/ping"),
        ("Vite dev server", VITE_PORT, f"http://{HOST}:{VITE_PORT}"),
        ("Ollama", OLLAMA_PORT, f"http://{HOST}:{OLLAMA_PORT}/api/tags"),
    ]
    print(f"Python: {sys.executable} ({sys.version.split()[0]})")
    print(f"Local config: {LOCAL_CONFIG} (mode 0600, user {username})")
    for label, port, url in checks:
        listening = port_open(port)
        healthy, detail = http_status(url) if listening else (False, "not listening")
        print(f"{label}: {HOST}:{port} listening={listening} health={healthy} ({detail})")
    if port_open(API_PORT):
        print(f"Market providers: {provider_status(username, password)}")
    return 0


def start() -> int:
    require_python()
    generate_config()
    if port_open(API_PORT):
        raise SystemExit(
            f"{HOST}:{API_PORT} is already occupied; refusing to kill or replace its process."
        )
    command = [
        str(ROOT / ".venv" / "bin" / "freqtrade"),
        "webserver",
        "-c",
        str(LOCAL_CONFIG),
    ]
    print("Starting:", " ".join(command))
    return subprocess.call(command, cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="BTT local runtime helper")
    parser.add_argument("command", choices=["check", "start", "generate-config"])
    args = parser.parse_args()
    if args.command == "check":
        return check()
    if args.command == "generate-config":
        require_python()
        generate_config()
        print(LOCAL_CONFIG)
        return 0
    return start()


if __name__ == "__main__":
    raise SystemExit(main())
