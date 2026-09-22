"""Stage 11 - Regime-aware model routing (optional).

Routes which models participate per market regime, reusing Stage 9 market_state.
When routing is disabled, all models participate. Safety: never drop below 2
models (falls back to all models).
"""
from __future__ import annotations

from typing import Any, Sequence

from crypto_quant_ai.backend.intelligence.market_state import MarketState, Regime

_ROUTING_TABLE: dict[Regime, set[str]] = {
    Regime.TREND: {"quant", "market_structure", "llm_stub"},
    Regime.RANGE: {"quant", "risk", "llm_stub"},
    Regime.HIGH_VOL: {"risk", "devil_advocate", "llm_stub"},
    Regime.LOW_VOL: {"quant", "market_structure", "llm_stub"},
    Regime.UNKNOWN: set(),
}


def route_models(
    models: Sequence[Any], state: MarketState, config: Any
) -> tuple[list, dict]:
    if not getattr(config, "routing", False):
        return list(models), {"enabled": False, "regime": state.regime.value}
    keep = _ROUTING_TABLE.get(state.regime, set())
    if not keep:
        return list(models), {
            "enabled": True, "regime": state.regime.value, "kept": "all(unknown)"
        }
    filtered = [m for m in models if getattr(m, "name", "") in keep]
    if len(filtered) < 2:
        return list(models), {
            "enabled": True, "regime": state.regime.value, "kept": "all(safety)"
        }
    return filtered, {
        "enabled": True,
        "regime": state.regime.value,
        "kept": [m.name for m in filtered],
    }
