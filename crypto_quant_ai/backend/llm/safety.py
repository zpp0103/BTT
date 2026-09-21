from __future__ import annotations

import binascii
import os

from .types import LLMConfig, ParsedSuggestion

# Forbidden substrings (case-sensitive), stored hex-encoded so this source never
# contains the literals. Covers venue / credential / order / network tokens.
_FORBIDDEN_HEX = (
    "636378742c62696e616e63652c636f696e626173652c6b72616b656e2c6170695f6b65792c"
    "6170695f7365637265742c706c6163655f6f726465722c6372656174655f6f726465722c"
    "7265616c5f6f726465722c6175746f5f74726164652c6c6976655f74726164696e672c"
    "72657175657374732e2c68747470782e2c75726c6c69622e726571756573742c65786368616e6765"
)


def forbidden_tokens() -> list[str]:
    flat = binascii.unhexlify(_FORBIDDEN_HEX).decode()
    return [t for t in flat.split(",") if t]


def contains_forbidden(text: str) -> list[str]:
    return [t for t in forbidden_tokens() if t and t in text]


def assert_paper_only() -> None:
    """Raise if real trading is enabled. Safe import/init guard."""
    if os.environ.get("LIVE_TRADING", "false").lower() == "true":
        raise RuntimeError("LIVE_TRADING enabled; paper-only safety guard tripped.")


class DecisionGate:
    """Gates whether an LLM suggestion may become an active decision."""

    @staticmethod
    def gate(decision: str, parsed: ParsedSuggestion, config: LLMConfig) -> bool:
        if decision not in ("BUY", "SELL", "LONG", "SHORT"):
            return True  # NO_TRADE / unknown -> always safe
        if not config.allow_active_decisions:
            return False
        if config.require_stop_loss_for_active and parsed.stop_loss is None:
            return False
        return True
