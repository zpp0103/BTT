"""Stage 10 - LLM adapter registry (BrainRegistry).

Independent of the Stage 1-8 brain decision registry. By default only the local
stub adapter is registered. Online adapters must be registered explicitly.
"""
from __future__ import annotations

from typing import Any

from .adapters import LocalStubAdapter


class BrainRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, type] = {}
        self.register("local_stub", LocalStubAdapter)

    def register(self, name: str, adapter_cls: type) -> None:
        self._adapters[name] = adapter_cls

    def get(self, name: str) -> Any:
        if name not in self._adapters:
            raise KeyError(f"unknown LLM adapter: {name}")
        return self._adapters[name]

    def list_adapters(self) -> list[str]:
        return sorted(self._adapters.keys())


_REGISTRY = BrainRegistry()


def get_registry() -> BrainRegistry:
    return _REGISTRY


def register_adapter(name: str, adapter_cls: type) -> None:
    get_registry().register(name, adapter_cls)


def build_adapter(name: str, **kwargs: Any) -> Any:
    cls = get_registry().get(name)
    return cls(**kwargs)
