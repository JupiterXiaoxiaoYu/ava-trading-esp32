from __future__ import annotations

import importlib
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
        if key in {"custom", "class", "python"} or kwargs.get("class") or kwargs.get("class_path"):
            return _load_custom_adapter(str(kwargs.get("class") or kwargs.get("class_path") or ""), _adapter_options(kwargs))
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


def _load_custom_adapter(class_path: str, options: dict[str, Any]) -> ChainAdapter:
    if not class_path:
        raise ValueError("custom chain adapter requires `class` or `class_path`")
    module_name, sep, attr = class_path.replace(":", ".").rpartition(".")
    if not sep or not module_name or not attr:
        raise ValueError(f"invalid adapter class path: {class_path}")
    cls = getattr(importlib.import_module(module_name), attr)
    try:
        return cls(**options)
    except TypeError:
        return cls(options)


def _adapter_options(kwargs: dict[str, Any]) -> dict[str, Any]:
    options = kwargs.get("options") if isinstance(kwargs.get("options"), dict) else {}
    inline = {k: v for k, v in kwargs.items() if k not in {"class", "class_path", "options"}}
    return {**inline, **options}


def _solana_config_from_kwargs(kwargs: dict[str, Any]) -> SolanaAdapterConfig:
    defaults = SolanaAdapterConfig()
    return SolanaAdapterConfig(
        data_base=str(kwargs.get("data_base") or defaults.data_base),
        api_key_env=str(kwargs.get("api_key_env") or defaults.api_key_env),
    )
