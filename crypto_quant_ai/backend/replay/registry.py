from __future__ import annotations

from typing import Any

# Real brain module locations (verified against the repo at Stage 5 implementation).
from crypto_quant_ai.backend.brains.quant import QuantBrain
from crypto_quant_ai.backend.brains.market_structure import MarketStructureBrain
from crypto_quant_ai.backend.brains.risk import RiskManagerBrain
from crypto_quant_ai.backend.brains.devil_advocate import DevilsAdvocateBrain


def get_brain_registry() -> dict[str, Any]:
    return {
        "quant": QuantBrain,
        "market_structure": MarketStructureBrain,
        "risk": RiskManagerBrain,
        "devil_advocate": DevilsAdvocateBrain,
    }


def build_brains(brain_names: list[str] | tuple[str, ...]) -> list[Any]:
    registry = get_brain_registry()
    instances = []
    for name in brain_names:
        if name not in registry:
            raise ValueError(f"Unknown brain: {name}")
        instances.append(registry[name]())
    return instances
