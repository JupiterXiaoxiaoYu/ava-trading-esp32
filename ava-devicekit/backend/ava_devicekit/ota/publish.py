from __future__ import annotations

import base64
import re
import shutil
from pathlib import Path
from typing import Any

from ava_devicekit.ota.version import FirmwareCandidate, scan_firmware
from ava_devicekit.runtime.settings import RuntimeSettings

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def firmware_catalog(settings: RuntimeSettings) -> dict[str, Any]:
    items = []
    by_model = scan_firmware(settings.firmware_bin_dir)
    for model, candidates in sorted(by_model.items()):
        for candidate in candidates:
            items.append(_candidate_to_dict(candidate))
    return {"items": items, "count": len(items), "models": sorted(by_model)}


def publish_firmware(
    settings: RuntimeSettings,
    *,
    model: str,
    version: str,
    source_path: str | Path | None = None,
    content_base64: str = "",
) -> dict[str, Any]:
    safe_model = _safe_component(model, "model")
    safe_version = _safe_component(version, "version")
    target_dir = Path(settings.firmware_bin_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{safe_model}_{safe_version}.bin"

    if source_path:
        source = Path(source_path).expanduser()
        if not source.is_file() or source.suffix != ".bin":
            raise ValueError(f"source firmware must be an existing .bin file: {source}")
        shutil.copy2(source, target)
    elif content_base64:
        target.write_bytes(base64.b64decode(content_base64, validate=True))
    else:
        raise ValueError("publish firmware requires source_path or content_base64")

    candidate = FirmwareCandidate(model=safe_model, version=safe_version, filename=target.name, path=target)
    return {"ok": True, "firmware": _candidate_to_dict(candidate)}


def _candidate_to_dict(candidate: FirmwareCandidate) -> dict[str, Any]:
    stat = candidate.path.stat() if candidate.path.exists() else None
    return {
        "model": candidate.model,
        "version": candidate.version,
        "filename": candidate.filename,
        "path": str(candidate.path),
        "size": stat.st_size if stat else 0,
        "mtime": stat.st_mtime if stat else 0,
    }


def _safe_component(value: str, field: str) -> str:
    text = _SAFE.sub("-", str(value or "").strip()).strip(".-_")
    if not text:
        raise ValueError(f"firmware {field} is required")
    return text


__all__ = ["firmware_catalog", "publish_firmware"]
