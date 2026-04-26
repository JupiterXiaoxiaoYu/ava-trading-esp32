from __future__ import annotations

from pathlib import Path
from typing import Any

from ava_devicekit.adapters.registry import default_adapter_registry, normalize_adapter_name
from ava_devicekit.apps.registry import create_hardware_app, load_manifest
from ava_devicekit.gateway.session import DeviceSession


def create_device_session(
    *,
    app_id: str = "ava_box",
    manifest_path: str | Path | None = None,
    adapter: str = "auto",
    mock: bool = False,
    skill_store_path: str | None = None,
    adapter_options: dict[str, Any] | None = None,
) -> DeviceSession:
    manifest = load_manifest(app_id=app_id, manifest_path=manifest_path)
    adapter_name = _resolve_adapter_name(manifest.adapters.get("chain", "solana"), adapter=adapter, mock=mock)
    chain_adapter = default_adapter_registry().create(adapter_name, **(adapter_options or {}))
    app = create_hardware_app(
        app_id=app_id,
        manifest_path=manifest_path,
        chain_adapter=chain_adapter,
        skill_store_path=skill_store_path,
    )
    return DeviceSession(app)


def _resolve_adapter_name(manifest_adapter: str, *, adapter: str, mock: bool) -> str:
    if mock:
        return "mock_solana"
    requested = normalize_adapter_name(adapter)
    if requested and requested != "auto":
        return requested
    return normalize_adapter_name(manifest_adapter or "solana")
