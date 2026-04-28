from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ava_devicekit.runtime.settings import RuntimeSettings


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    name: str
    kind: str
    provider: str
    status: str
    configured: bool
    model: str = ""
    api_key_env: str = ""
    class_path: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "provider": self.provider,
            "status": self.status,
            "configured": self.configured,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "class": self.class_path,
            "details": dict(self.details),
        }


def provider_health_report(settings: RuntimeSettings) -> dict[str, Any]:
    items = [
        _provider("asr", settings.asr_provider, settings.asr_model, settings.asr_api_key_env, settings.asr_class),
        _provider("llm", settings.llm_provider, settings.llm_model, settings.llm_api_key_env, settings.llm_class),
        _provider("tts", settings.tts_provider, settings.tts_model, settings.tts_api_key_env, settings.tts_class, mock_names={"", "mock", "none", "disabled"}),
        _provider("chain", settings.chain_adapter or "auto", "", "", settings.chain_adapter_class, mock_names={"mock", "mock_solana"}),
        _provider("execution", settings.execution_mode, "", settings.execution_api_key_env, settings.execution_provider_class, mock_names={"", "paper", "mock"}),
    ]
    payloads = [item.to_dict() for item in items]
    return {
        "ok": all(item["status"] not in {"missing_env", "invalid"} for item in payloads),
        "items": payloads,
        "count": len(payloads),
    }


def _provider(
    kind: str,
    provider: str,
    model: str,
    api_key_env: str,
    class_path: str,
    *,
    mock_names: set[str] | None = None,
) -> ProviderHealth:
    name = str(provider or "").strip()
    normalized = name.lower()
    mock_names = mock_names or {"", "none", "disabled"}
    if normalized in mock_names:
        status = "disabled" if normalized in {"", "none", "disabled"} else "ok"
        return ProviderHealth(kind=kind, name=kind, provider=name or "disabled", model=model, api_key_env=api_key_env, class_path=class_path, configured=True, status=status)
    if class_path:
        return ProviderHealth(kind=kind, name=kind, provider=name or "custom", model=model, api_key_env=api_key_env, class_path=class_path, configured=True, status="configured")
    if api_key_env and not os.environ.get(api_key_env):
        return ProviderHealth(kind=kind, name=kind, provider=name, model=model, api_key_env=api_key_env, class_path=class_path, configured=False, status="missing_env")
    return ProviderHealth(kind=kind, name=kind, provider=name, model=model, api_key_env=api_key_env, class_path=class_path, configured=True, status="configured")


__all__ = ["ProviderHealth", "provider_health_report"]
