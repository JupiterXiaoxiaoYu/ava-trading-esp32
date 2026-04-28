from __future__ import annotations

import hashlib
import secrets
import time
from pathlib import Path
from typing import Any

from ava_devicekit.storage.json_store import JsonStore

DEFAULT_STATE: dict[str, Any] = {"version": 1, "users": [], "projects": [], "devices": []}


class ControlPlaneStore:
    """Local control-plane store for self-hosted DeviceKit deployments."""

    def __init__(self, path: str | Path):
        self.store = JsonStore(path)

    def bootstrap(self) -> dict[str, Any]:
        def mutate(data: dict[str, Any]) -> None:
            _ensure_shape(data)
            now = _now()
            if not data["users"]:
                data["users"].append(
                    {
                        "user_id": "usr_default_admin",
                        "username": "admin",
                        "display_name": "Default Admin",
                        "role": "admin",
                        "created_at": now,
                    }
                )
            if not data["projects"]:
                data["projects"].append(
                    {
                        "project_id": "prj_default_solana",
                        "name": "Default Solana Project",
                        "slug": "default-solana",
                        "owner_user_id": data["users"][0]["user_id"],
                        "chain": "solana",
                        "description": "Default project for local ESP32 Solana hardware apps.",
                        "created_at": now,
                    }
                )

        return self.store.update(_default_state(), mutate)

    def snapshot(self, *, include_secrets: bool = False) -> dict[str, Any]:
        data = self.bootstrap()
        items = {
            "version": data.get("version", 1),
            "users": [dict(item) for item in data.get("users", [])],
            "projects": [dict(item) for item in data.get("projects", [])],
            "devices": [dict(item) for item in data.get("devices", [])],
        }
        if not include_secrets:
            for device in items["devices"]:
                device.pop("device_token_hash", None)
                device.pop("provisioning_token_hash", None)
        return {
            "ok": True,
            **items,
            "counts": {
                "users": len(items["users"]),
                "projects": len(items["projects"]),
                "registered_devices": len([d for d in items["devices"] if d.get("registered_at")]),
                "provisioned_devices": len(items["devices"]),
            },
        }

    def create_user(self, body: dict[str, Any]) -> dict[str, Any]:
        username = _slug(str(body.get("username") or body.get("email") or "user"))
        display_name = str(body.get("display_name") or body.get("name") or username)
        role = str(body.get("role") or "developer")
        if role not in {"admin", "developer", "operator", "viewer"}:
            raise ValueError("invalid_role")
        now = _now()
        created: dict[str, Any] = {}

        def mutate(data: dict[str, Any]) -> None:
            nonlocal created
            _ensure_shape(data)
            if any(item.get("username") == username for item in data["users"]):
                raise ValueError("user_exists")
            created = {
                "user_id": _id("usr"),
                "username": username,
                "display_name": display_name,
                "role": role,
                "created_at": now,
            }
            data["users"].append(created)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "user": created}

    def create_project(self, body: dict[str, Any]) -> dict[str, Any]:
        data = self.bootstrap()
        default_owner = data["users"][0]["user_id"]
        owner = str(body.get("owner_user_id") or default_owner)
        name = str(body.get("name") or "Solana Hardware App")
        slug = _slug(str(body.get("slug") or name))
        chain = str(body.get("chain") or "solana")
        description = str(body.get("description") or "")
        now = _now()
        created: dict[str, Any] = {}

        def mutate(state: dict[str, Any]) -> None:
            nonlocal created
            _ensure_shape(state)
            if not any(item.get("user_id") == owner for item in state["users"]):
                raise ValueError("owner_not_found")
            if any(item.get("slug") == slug for item in state["projects"]):
                raise ValueError("project_exists")
            created = {
                "project_id": _id("prj"),
                "name": name,
                "slug": slug,
                "owner_user_id": owner,
                "chain": chain,
                "description": description,
                "created_at": now,
            }
            state["projects"].append(created)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "project": created}

    def provision_device(self, body: dict[str, Any]) -> dict[str, Any]:
        data = self.bootstrap()
        project_id = str(body.get("project_id") or data["projects"][0]["project_id"])
        owner_user_id = str(body.get("owner_user_id") or _project_owner(data, project_id) or data["users"][0]["user_id"])
        device_id = _slug(str(body.get("device_id") or _id("dev"))).replace("-", "_")
        now = _now()
        token = _token("avaprov")
        created: dict[str, Any] = {}

        def mutate(state: dict[str, Any]) -> None:
            nonlocal created
            _ensure_shape(state)
            if not any(item.get("project_id") == project_id for item in state["projects"]):
                raise ValueError("project_not_found")
            if not any(item.get("user_id") == owner_user_id for item in state["users"]):
                raise ValueError("owner_not_found")
            if any(item.get("device_id") == device_id for item in state["devices"]):
                raise ValueError("device_exists")
            created = {
                "device_id": device_id,
                "project_id": project_id,
                "owner_user_id": owner_user_id,
                "name": str(body.get("name") or device_id),
                "board_model": str(body.get("board_model") or body.get("model") or "esp32"),
                "app_id": str(body.get("app_id") or "ava_box"),
                "status": "provisioned",
                "created_at": now,
                "registered_at": None,
                "last_seen": None,
                "firmware_version": str(body.get("firmware_version") or ""),
                "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
                "provisioning_token_hash": _hash_token(token),
                "device_token_hash": "",
            }
            state["devices"].append(created)

        self.store.update(_default_state(), mutate)
        safe = _safe_device(created)
        return {"ok": True, "device": safe, "provisioning_token": token}

    def rotate_provisioning_token(self, device_id: str) -> dict[str, Any]:
        token = _token("avaprov")
        updated: dict[str, Any] = {}

        def mutate(state: dict[str, Any]) -> None:
            nonlocal updated
            _ensure_shape(state)
            device = _find_device(state, device_id)
            if not device:
                raise ValueError("device_not_found")
            device["provisioning_token_hash"] = _hash_token(token)
            device["status"] = "provisioned"
            updated = dict(device)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "device": _safe_device(updated), "provisioning_token": token}

    def register_device(self, body: dict[str, Any]) -> dict[str, Any]:
        supplied = str(body.get("provisioning_token") or "")
        if not supplied:
            raise ValueError("provisioning_token_required")
        requested_id = str(body.get("device_id") or "")
        token = _token("avadev")
        registered: dict[str, Any] = {}
        now = _now()

        def mutate(state: dict[str, Any]) -> None:
            nonlocal registered
            _ensure_shape(state)
            device = None
            supplied_hash = _hash_token(supplied)
            for item in state["devices"]:
                if item.get("provisioning_token_hash") == supplied_hash:
                    if requested_id and item.get("device_id") not in {requested_id, _slug(requested_id).replace("-", "_")}:
                        raise ValueError("device_id_mismatch")
                    device = item
                    break
            if not device:
                raise ValueError("invalid_provisioning_token")
            device["device_token_hash"] = _hash_token(token)
            device["provisioning_token_hash"] = ""
            device["status"] = "registered"
            device["registered_at"] = now
            device["last_seen"] = now
            if body.get("board_model") or body.get("model"):
                device["board_model"] = str(body.get("board_model") or body.get("model"))
            if body.get("app_id"):
                device["app_id"] = str(body.get("app_id"))
            if body.get("firmware_version"):
                device["firmware_version"] = str(body.get("firmware_version"))
            registered = dict(device)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "device": _safe_device(registered), "device_token": token}

    def validate_device_token(self, device_id: str, token: str) -> bool:
        if not device_id or not token:
            return False
        data = self.bootstrap()
        device = _find_device(data, device_id)
        expected = str((device or {}).get("device_token_hash") or "")
        return bool(expected and secrets.compare_digest(expected, _hash_token(token)))

    def mark_device_seen(self, device_id: str, *, firmware_version: str = "") -> None:
        data = self.store.read(_default_state())
        _ensure_shape(data)
        if not _find_device(data, device_id):
            return
        now = _now()

        def mutate(state: dict[str, Any]) -> None:
            _ensure_shape(state)
            device = _find_device(state, device_id)
            if not device:
                return
            device["last_seen"] = now
            if device.get("registered_at"):
                device["status"] = "online_seen"
            if firmware_version:
                device["firmware_version"] = firmware_version

        self.store.update(_default_state(), mutate)


def _default_state() -> dict[str, Any]:
    return {"version": 1, "users": [], "projects": [], "devices": []}


def _ensure_shape(data: dict[str, Any]) -> None:
    if not isinstance(data.get("users"), list):
        data["users"] = []
    if not isinstance(data.get("projects"), list):
        data["projects"] = []
    if not isinstance(data.get("devices"), list):
        data["devices"] = []
    data["version"] = int(data.get("version") or 1)


def _safe_device(device: dict[str, Any]) -> dict[str, Any]:
    safe = dict(device)
    safe.pop("provisioning_token_hash", None)
    safe.pop("device_token_hash", None)
    return safe


def _find_device(data: dict[str, Any], device_id: str) -> dict[str, Any] | None:
    normalized = normalize_control_device_id(device_id)
    for item in data.get("devices", []):
        if normalize_control_device_id(str(item.get("device_id") or "")) == normalized:
            return item
    return None


def normalize_control_device_id(device_id: str) -> str:
    return _slug(device_id or "default").replace("-", "_")


def _project_owner(data: dict[str, Any], project_id: str) -> str:
    for item in data.get("projects", []):
        if item.get("project_id") == project_id:
            return str(item.get("owner_user_id") or "")
    return ""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(24)}"


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def _slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "item"


def _now() -> int:
    return int(time.time())
