"""Stage 7 (Plan A) - Deterministic gateway hash (excludes runtime state)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from crypto_quant_ai.backend.gateway.types import GatewayConfig


def _default(o: Any) -> Any:
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if isinstance(o, (str, int, float, bool)) or o is None:
        return o
    return str(o)


def compute_gateway_hash(config: GatewayConfig) -> str:
    """SHA-256 of the fixed configuration.

    Excludes started_at / stopped_at / now / any non-deterministic runtime
    state, so identical configuration always yields the same hash.
    """
    payload = {
        "user": config.user,
        "account_id": config.account_id,
        "symbol": config.symbol,
        "timeframe": config.timeframe,
        "strategy_id": config.strategy_id,
        "initial_cash": config.initial_cash,
        "risk_manager": config.risk_manager.model_dump(),
        "circuit_breaker": config.circuit_breaker.model_dump(),
    }
    canonical = json.dumps(payload, sort_keys=True, default=_default)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
