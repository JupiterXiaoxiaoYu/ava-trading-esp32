from __future__ import annotations

from pathlib import Path

from ava_devicekit.adapters.base import ChainAdapter
from ava_devicekit.apps.base import HardwareApp
from ava_devicekit.apps.ava_box import AvaBoxApp, DEFAULT_MANIFEST
from ava_devicekit.apps.ava_box_skills import AvaBoxSkillConfig, AvaBoxSkillService
from ava_devicekit.core.manifest import HardwareAppManifest


def load_manifest(app_id: str = "ava_box", manifest_path: str | Path | None = None) -> HardwareAppManifest:
    if manifest_path:
        return HardwareAppManifest.load(manifest_path)
    if app_id == "ava_box":
        return HardwareAppManifest.load(DEFAULT_MANIFEST)
    raise ValueError(f"unknown app: {app_id}")


def create_hardware_app(
    *,
    app_id: str = "ava_box",
    manifest_path: str | Path | None = None,
    chain_adapter: ChainAdapter,
    skill_store_path: str | None = None,
    skill_config: AvaBoxSkillConfig | None = None,
) -> HardwareApp:
    manifest = load_manifest(app_id=app_id, manifest_path=manifest_path)
    if manifest.app_id != "ava_box":
        raise ValueError(f"unsupported app manifest: {manifest.app_id}")
    config = skill_config or (AvaBoxSkillConfig(store_path=skill_store_path) if skill_store_path else AvaBoxSkillConfig())
    return AvaBoxApp(
        manifest=manifest,
        chain_adapter=chain_adapter,
        skills=AvaBoxSkillService(config),
    )
