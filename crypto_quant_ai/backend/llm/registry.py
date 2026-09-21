from __future__ import annotations

from .providers import LocalStubProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, type] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        # Only the offline local stub is registered by default. The online
        # provider is a non-network gated stub and must be registered explicitly.
        self.register("local_stub", LocalStubProvider)

    def register(self, name: str, provider_cls: type) -> None:
        self._providers[name] = provider_cls

    def get(self, name: str) -> type | None:
        return self._providers.get(name)

    def names(self) -> list[str]:
        return list(self._providers.keys())


_REGISTRY = ProviderRegistry()


def get_provider_registry() -> ProviderRegistry:
    return _REGISTRY
