from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ava_devicekit.ota.version import scan_firmware, select_update
from ava_devicekit.runtime.settings import RuntimeSettings


def build_ota_response(
    *,
    settings: RuntimeSettings,
    headers: dict[str, str],
    body: dict[str, Any] | None = None,
    host_hint: str = "127.0.0.1",
) -> dict[str, Any]:
    """Build the xiaozhi-compatible OTA response used by existing firmware.

    The shape follows the legacy OTA contract, but the implementation is owned
    by DeviceKit and only emits the runtime config Ava Box needs.
    """

    body = body or {}
    device_model = _first_header(headers, "device-model", "device_model", "model") or _body_model(body) or "default"
    current_version = _first_header(headers, "device-version", "device_version", "firmware-version", "app-version", "application-version") or _body_version(body) or "0.0.0"
    response = {
        "server_time": {
            "timestamp": int(round(time.time() * 1000)),
            "timezone_offset": settings.timezone_offset_hours * 60,
        },
        "firmware": {
            "version": current_version,
            "url": "",
        },
        "websocket": {
            "url": settings.websocket_endpoint(host_hint),
            "token": "",
        },
    }
    candidates = scan_firmware(settings.firmware_bin_dir).get(device_model, [])
    update = select_update(candidates, current_version)
    if update:
        response["firmware"] = {
            "version": update.version,
            "url": f"{settings.ota_base_url(host_hint)}/xiaozhi/ota/download/{update.filename}",
        }
    return response


def resolve_firmware_download(settings: RuntimeSettings, filename: str) -> Path | None:
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.endswith(".bin"):
        return None
    path = Path(settings.firmware_bin_dir) / safe_name
    try:
        root = Path(settings.firmware_bin_dir).resolve()
        resolved = path.resolve()
        if root not in resolved.parents and resolved != root:
            return None
    except OSError:
        return None
    return path if path.is_file() else None


def _first_header(headers: dict[str, str], *names: str) -> str:
    lower = {str(k).lower(): str(v) for k, v in headers.items()}
    for name in names:
        value = lower.get(name.lower(), "").strip()
        if value:
            return value
    return ""


def _body_model(body: dict[str, Any]) -> str:
    board = body.get("board") if isinstance(body.get("board"), dict) else {}
    return str(board.get("type") or body.get("model") or "").strip()


def _body_version(body: dict[str, Any]) -> str:
    app = body.get("application") if isinstance(body.get("application"), dict) else {}
    return str(app.get("version") or body.get("version") or "").strip()
