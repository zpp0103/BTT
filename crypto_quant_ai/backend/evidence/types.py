from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_DYNAMIC_HASH_KEYS = {"generated_at", "started_at", "stopped_at", "collected_at"}


def _validate_finite(value: Any, path: str) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"non-finite numeric value at {path}")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            _validate_finite(v, f"{path}.{k}")
        return
    if isinstance(value, (list, tuple)):
        for idx, v in enumerate(value):
            _validate_finite(v, f"{path}[{idx}]")


@dataclass
class EvidenceItem:
    source: str
    category: str
    supports_trade: bool
    strength: float
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_finite(self.strength, "strength")
        if not (0.0 <= float(self.strength) <= 1.0):
            raise ValueError("strength must be in [0, 1]")
        _validate_finite(self.details, "details")


@dataclass
class EvidenceSet:
    items: list[EvidenceItem] = field(default_factory=list)
    collected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add(self, item: EvidenceItem) -> None:
        self.items.append(item)

    def to_dict(self) -> dict[str, Any]:
        return {
            "collected_at": self.collected_at,
            "items": [
                {
                    "source": i.source,
                    "category": i.category,
                    "supports_trade": i.supports_trade,
                    "strength": i.strength,
                    "summary": i.summary,
                    "details": i.details,
                }
                for i in self.items
            ],
        }


@dataclass
class VerificationResult:
    decision: str
    approved: bool
    reasons: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    evidence_hash: str = ""


@dataclass
class EvidenceReport:
    evidence: EvidenceSet
    verification: VerificationResult
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            if key in _DYNAMIC_HASH_KEYS:
                continue
            normalized[key] = _canonicalize(value[key])
        return normalized
    if isinstance(value, list):
        return [_canonicalize(v) for v in value]
    return value


def evidence_hash(payload: dict[str, Any]) -> str:
    canonical = _canonicalize(payload)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
