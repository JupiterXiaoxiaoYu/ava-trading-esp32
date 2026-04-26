from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ava_devicekit.adapters.base import ChainAdapter
from ava_devicekit.adapters.mock_solana import MockSolanaAdapter
from ava_devicekit.adapters.solana import SolanaAdapter, SolanaAdapterConfig

AdapterFactory = Callable[..., ChainAdapter]


class AdapterRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, AdapterFactory] = {}

    def register(self, name: str, factory: AdapterFactory) -> None:
        key = normalize_adapter_name(name)
        if not key:
            raise ValueError("adapter name is required")
        self._factories[key] = factory

    def names(self) -> list[str]:
        return sorted(self._factories)

    def create(self, name: str, **kwargs: Any) -> ChainAdapter:
        key = normalize_adapter_name(name)
        if key not in self._factories:
            raise ValueError(f"unknown adapter: {name}")
        return self._factories[key](**kwargs)


def normalize_adapter_name(name: str) -> str:
    return str(name or "").strip().lower().replace("-", "_")


def default_adapter_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register("solana", lambda **kwargs: SolanaAdapter(_solana_config_from_kwargs(kwargs)))
    registry.register("mock_solana", lambda **_kwargs: MockSolanaAdapter())
    return registry


def _solana_config_from_kwargs(kwargs: dict[str, Any]) -> SolanaAdapterConfig:
    return SolanaAdapterConfig(
        data_base=str(kwargs.get("data_base") or SolanaAdapterConfig.data_base),
        api_key_env=str(kwargs.get("api_key_env") or SolanaAdapterConfig.api_key_env),
    )
