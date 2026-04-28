from __future__ import annotations

import hashlib
import secrets
import time
from pathlib import Path
from typing import Any

from ava_devicekit.storage.json_store import JsonStore

DEFAULT_DEVICE_CONFIG: dict[str, Any] = {
    "language": "zh",
    "ai_name": "Ava",
    "wake_phrases": ["hey ava", "hi ava", "hello ava", "你好ava"],
    "tts_voice": "",
    "volume": 100,
    "app_id": "ava_box",
    "firmware_channel": "stable",
    "wallet_mode": "proxy",
    "risk_mode": "confirm_all",
}

DEFAULT_SERVICE_PLANS: list[dict[str, Any]] = [
    {
        "plan_id": "plan_internal",
        "name": "Internal",
        "status": "active",
        "price_label": "internal",
        "limits": {"asr_seconds": 0, "llm_tokens": 0, "tts_chars": 0, "api_calls": 0},
        "features": ["unlimited_lab_use"],
    },
    {
        "plan_id": "plan_starter",
        "name": "Starter",
        "status": "active",
        "price_label": "manual",
        "limits": {"asr_seconds": 3600, "llm_tokens": 200000, "tts_chars": 200000, "api_calls": 10000},
        "features": ["voice", "ota", "basic_support"],
    },
]


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
            "customers": [dict(item) for item in data.get("customers", [])],
            "projects": [dict(item) for item in data.get("projects", [])],
            "devices": [dict(item) for item in data.get("devices", [])],
            "runtime_config": _redact(dict(data.get("runtime_config") or {})),
            "default_device_config": dict(data.get("default_device_config") or DEFAULT_DEVICE_CONFIG),
            "service_plans": [dict(item) for item in data.get("service_plans", [])],
            "usage_summary": self._usage_summary_unlocked(data),
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
                "customers": len(items["customers"]),
                "projects": len(items["projects"]),
                "active_devices": len([d for d in items["devices"] if d.get("status") in {"active", "online_seen"}]),
                "registered_devices": len([d for d in items["devices"] if d.get("registered_at")]),
                "provisioned_devices": len(items["devices"]),
                "service_plans": len(items["service_plans"]),
            },
        }

    def runtime_config(self) -> dict[str, Any]:
        data = self.bootstrap()
        return dict(data.get("runtime_config") or {})

    def update_runtime_config(self, body: dict[str, Any]) -> dict[str, Any]:
        updated: dict[str, Any] = {}

        def mutate(data: dict[str, Any]) -> None:
            nonlocal updated
            _ensure_shape(data)
            current = data.get("runtime_config")
            if not isinstance(current, dict):
                current = {}
                data["runtime_config"] = current
            _deep_merge(current, _sanitize_runtime_config(body))
            updated = dict(current)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "runtime_config": updated}

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
                "app_id": str(body.get("app_id") or "ava_box"),
                "description": description,
                "device_config": body.get("device_config") if isinstance(body.get("device_config"), dict) else {},
                "created_at": now,
            }
            state["projects"].append(created)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "project": created}

    def create_customer(self, body: dict[str, Any]) -> dict[str, Any]:
        email = str(body.get("email") or "").strip().lower()
        display_name = str(body.get("display_name") or body.get("name") or email or "customer")
        wallet = str(body.get("wallet") or body.get("wallet_address") or "")
        now = _now()
        created: dict[str, Any] = {}

        def mutate(data: dict[str, Any]) -> None:
            nonlocal created
            _ensure_shape(data)
            if email and any(item.get("email") == email for item in data["customers"]):
                raise ValueError("customer_exists")
            created = {
                "customer_id": _id("cus"),
                "email": email,
                "display_name": display_name,
                "wallet": wallet,
                "status": str(body.get("status") or "active"),
                "created_at": now,
                "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            }
            data["customers"].append(created)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "customer": created}

    def create_service_plan(self, body: dict[str, Any]) -> dict[str, Any]:
        plan_id = str(body.get("plan_id") or _slug(str(body.get("name") or _id("plan")))).replace("-", "_")
        if not plan_id.startswith("plan_"):
            plan_id = f"plan_{plan_id}"
        limits = body.get("limits") if isinstance(body.get("limits"), dict) else {}
        created: dict[str, Any] = {}
        now = _now()

        def mutate(data: dict[str, Any]) -> None:
            nonlocal created
            _ensure_shape(data)
            if any(item.get("plan_id") == plan_id for item in data["service_plans"]):
                raise ValueError("service_plan_exists")
            created = {
                "plan_id": plan_id,
                "name": str(body.get("name") or plan_id),
                "status": str(body.get("status") or "active"),
                "price_label": str(body.get("price_label") or "manual"),
                "limits": _usage_limits(limits),
                "features": body.get("features") if isinstance(body.get("features"), list) else [],
                "created_at": now,
            }
            data["service_plans"].append(created)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "service_plan": created}

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
                "customer_id": str(body.get("customer_id") or ""),
                "activation_code_hash": _hash_token(_activation_code(device_id)),
                "created_at": now,
                "registered_at": None,
                "activated_at": None,
                "last_seen": None,
                "firmware_version": str(body.get("firmware_version") or ""),
                "config": _device_config(body),
                "entitlement": _entitlement(body),
                "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
                "provisioning_token_hash": _hash_token(token),
                "device_token_hash": "",
            }
            state["devices"].append(created)

        self.store.update(_default_state(), mutate)
        safe = _safe_device(created)
        return {"ok": True, "device": safe, "provisioning_token": token, "activation_code": _activation_code(device_id)}

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

    def activate_device(self, body: dict[str, Any]) -> dict[str, Any]:
        code = str(body.get("activation_code") or "")
        if not code:
            raise ValueError("activation_code_required")
        customer_id = str(body.get("customer_id") or "")
        customer_body = body.get("customer") if isinstance(body.get("customer"), dict) else {}
        activated: dict[str, Any] = {}
        customer: dict[str, Any] = {}
        now = _now()

        def mutate(state: dict[str, Any]) -> None:
            nonlocal activated, customer, customer_id
            _ensure_shape(state)
            device = None
            code_hash = _hash_token(code)
            for item in state["devices"]:
                if item.get("activation_code_hash") == code_hash:
                    device = item
                    break
            if not device:
                raise ValueError("invalid_activation_code")
            if not customer_id:
                email = str(customer_body.get("email") or "").strip().lower()
                existing = next((item for item in state["customers"] if email and item.get("email") == email), None)
                if existing:
                    customer = existing
                    customer_id = str(existing["customer_id"])
                else:
                    customer = {
                        "customer_id": _id("cus"),
                        "email": email,
                        "display_name": str(customer_body.get("display_name") or customer_body.get("name") or email or "customer"),
                        "wallet": str(customer_body.get("wallet") or customer_body.get("wallet_address") or ""),
                        "status": "active",
                        "created_at": now,
                        "metadata": {},
                    }
                    state["customers"].append(customer)
                    customer_id = str(customer["customer_id"])
            elif not any(item.get("customer_id") == customer_id for item in state["customers"]):
                raise ValueError("customer_not_found")
            device["customer_id"] = customer_id
            device["status"] = "active"
            device["activated_at"] = now
            activated = dict(device)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "device": _safe_device(activated), "customer_id": customer_id}

    def update_device_status(self, device_id: str, status: str) -> dict[str, Any]:
        if status not in {"provisioned", "registered", "active", "suspended", "revoked"}:
            raise ValueError("invalid_status")
        updated: dict[str, Any] = {}

        def mutate(state: dict[str, Any]) -> None:
            nonlocal updated
            _ensure_shape(state)
            device = _find_device(state, device_id)
            if not device:
                raise ValueError("device_not_found")
            device["status"] = status
            if status == "revoked":
                device["device_token_hash"] = ""
                device["provisioning_token_hash"] = ""
            updated = dict(device)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "device": _safe_device(updated)}

    def set_device_entitlement(self, device_id: str, body: dict[str, Any]) -> dict[str, Any]:
        updated: dict[str, Any] = {}

        def mutate(state: dict[str, Any]) -> None:
            nonlocal updated
            _ensure_shape(state)
            device = _find_device(state, device_id)
            if not device:
                raise ValueError("device_not_found")
            entitlement = _entitlement(body)
            if entitlement.get("plan_id") and not any(item.get("plan_id") == entitlement["plan_id"] for item in state["service_plans"]):
                raise ValueError("service_plan_not_found")
            device["entitlement"] = entitlement
            updated = dict(device)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "device": _safe_device(updated), "entitlement": updated.get("entitlement") or {}}

    def update_device_config(self, device_id: str, body: dict[str, Any]) -> dict[str, Any]:
        updated: dict[str, Any] = {}

        def mutate(state: dict[str, Any]) -> None:
            nonlocal updated
            _ensure_shape(state)
            device = _find_device(state, device_id)
            if not device:
                raise ValueError("device_not_found")
            config = device.get("config")
            if not isinstance(config, dict):
                config = {}
                device["config"] = config
            _deep_merge(config, _device_config(body))
            updated = dict(device)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "device": _safe_device(updated), "config": self.device_config(device_id)}

    def device_config(self, device_id: str) -> dict[str, Any]:
        data = self.bootstrap()
        device = _find_device(data, device_id)
        if not device:
            raise ValueError("device_not_found")
        merged = dict(data.get("default_device_config") or DEFAULT_DEVICE_CONFIG)
        project = next((item for item in data.get("projects", []) if item.get("project_id") == device.get("project_id")), {})
        if isinstance(project.get("device_config"), dict):
            _deep_merge(merged, project["device_config"])
        if isinstance(device.get("config"), dict):
            _deep_merge(merged, device["config"])
        return merged

    def record_usage(self, body: dict[str, Any]) -> dict[str, Any]:
        metric = str(body.get("metric") or "").strip()
        if metric not in {"asr_seconds", "llm_tokens", "tts_chars", "api_calls"}:
            raise ValueError("invalid_usage_metric")
        amount = float(body.get("amount") or 0)
        if amount < 0:
            raise ValueError("invalid_usage_amount")
        device_id = normalize_control_device_id(str(body.get("device_id") or ""))
        if not device_id:
            raise ValueError("device_id_required")
        period = str(body.get("period") or _usage_period())
        recorded: dict[str, Any] = {}

        def mutate(state: dict[str, Any]) -> None:
            nonlocal recorded
            _ensure_shape(state)
            device = _find_device(state, device_id)
            if not device:
                raise ValueError("device_not_found")
            counters = state["usage_counters"].setdefault(period, {}).setdefault(device["device_id"], {})
            counters[metric] = float(counters.get(metric) or 0) + amount
            event = {
                "ts": _now(),
                "period": period,
                "device_id": device["device_id"],
                "customer_id": str(device.get("customer_id") or body.get("customer_id") or ""),
                "metric": metric,
                "amount": amount,
                "source": str(body.get("source") or "manual"),
                "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            }
            state["usage_events"].append(event)
            state["usage_events"] = state["usage_events"][-1000:]
            recorded = {"event": event, "counters": dict(counters), "entitlement": dict(device.get("entitlement") or {})}

        self.store.update(_default_state(), mutate)
        recorded["limit_status"] = self._limit_status(device_id, period)
        return {"ok": True, **recorded}

    def usage_report(self, *, device_id: str = "", period: str = "") -> dict[str, Any]:
        data = self.bootstrap()
        period = period or _usage_period()
        counters_by_device = data.get("usage_counters", {}).get(period, {})
        devices = data.get("devices", [])
        rows: list[dict[str, Any]] = []
        for device in devices:
            if device_id and normalize_control_device_id(device_id) != normalize_control_device_id(str(device.get("device_id") or "")):
                continue
            counters = dict(counters_by_device.get(device.get("device_id"), {}))
            row = {
                "device_id": device.get("device_id"),
                "customer_id": device.get("customer_id", ""),
                "status": device.get("status", ""),
                "entitlement": dict(device.get("entitlement") or {}),
                "usage": _usage_limits(counters),
                "limit_status": self._limit_status(str(device.get("device_id") or ""), period),
            }
            rows.append(row)
        return {
            "ok": True,
            "period": period,
            "items": rows,
            "count": len(rows),
            "events": [dict(item) for item in data.get("usage_events", []) if (not device_id or normalize_control_device_id(device_id) == normalize_control_device_id(str(item.get("device_id") or "")))][-100:],
        }

    def validate_device_token(self, device_id: str, token: str) -> bool:
        if not device_id or not token:
            return False
        data = self.bootstrap()
        device = _find_device(data, device_id)
        if (device or {}).get("status") in {"revoked", "suspended"}:
            return False
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

    def _usage_summary_unlocked(self, data: dict[str, Any]) -> dict[str, Any]:
        period = _usage_period()
        totals = {"asr_seconds": 0.0, "llm_tokens": 0.0, "tts_chars": 0.0, "api_calls": 0.0}
        for counters in data.get("usage_counters", {}).get(period, {}).values():
            for key in totals:
                totals[key] += float(counters.get(key) or 0)
        return {"period": period, "totals": totals, "events_count": len(data.get("usage_events", []))}

    def _limit_status(self, device_id: str, period: str) -> dict[str, Any]:
        data = self.bootstrap()
        device = _find_device(data, device_id)
        if not device:
            return {"ok": False, "reason": "device_not_found"}
        entitlement = dict(device.get("entitlement") or {})
        if entitlement.get("status") in {"suspended", "expired"}:
            return {"ok": False, "reason": str(entitlement.get("status"))}
        expires_at = int(entitlement.get("expires_at") or 0)
        if expires_at and expires_at < _now():
            return {"ok": False, "reason": "expired"}
        plan = next((item for item in data.get("service_plans", []) if item.get("plan_id") == entitlement.get("plan_id")), None)
        if not plan:
            return {"ok": True, "reason": "no_plan"}
        limits = _usage_limits(plan.get("limits") if isinstance(plan.get("limits"), dict) else {})
        usage = _usage_limits(data.get("usage_counters", {}).get(period, {}).get(device.get("device_id"), {}))
        exceeded = [key for key, limit in limits.items() if limit > 0 and usage.get(key, 0) > limit]
        return {"ok": not exceeded, "reason": "limit_exceeded" if exceeded else "ok", "exceeded": exceeded, "limits": limits, "usage": usage}


def _default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "users": [],
        "customers": [],
        "projects": [],
        "devices": [],
        "runtime_config": {},
        "default_device_config": dict(DEFAULT_DEVICE_CONFIG),
        "service_plans": [dict(item) for item in DEFAULT_SERVICE_PLANS],
        "usage_counters": {},
        "usage_events": [],
    }


def _ensure_shape(data: dict[str, Any]) -> None:
    if not isinstance(data.get("users"), list):
        data["users"] = []
    if not isinstance(data.get("customers"), list):
        data["customers"] = []
    if not isinstance(data.get("projects"), list):
        data["projects"] = []
    if not isinstance(data.get("devices"), list):
        data["devices"] = []
    if not isinstance(data.get("runtime_config"), dict):
        data["runtime_config"] = {}
    if not isinstance(data.get("default_device_config"), dict):
        data["default_device_config"] = dict(DEFAULT_DEVICE_CONFIG)
    if not isinstance(data.get("service_plans"), list):
        data["service_plans"] = [dict(item) for item in DEFAULT_SERVICE_PLANS]
    if not data["service_plans"]:
        data["service_plans"] = [dict(item) for item in DEFAULT_SERVICE_PLANS]
    if not isinstance(data.get("usage_counters"), dict):
        data["usage_counters"] = {}
    if not isinstance(data.get("usage_events"), list):
        data["usage_events"] = []
    data["version"] = int(data.get("version") or 1)


def _safe_device(device: dict[str, Any]) -> dict[str, Any]:
    safe = dict(device)
    safe.pop("provisioning_token_hash", None)
    safe.pop("device_token_hash", None)
    safe.pop("activation_code_hash", None)
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


def _activation_code(device_id: str) -> str:
    digest = hashlib.sha1(device_id.encode("utf-8")).hexdigest()[:8].upper()
    return f"AVA-{digest[:4]}-{digest[4:]}"


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def _slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "item"


def _now() -> int:
    return int(time.time())


def _usage_period(ts: int | None = None) -> str:
    return time.strftime("%Y-%m", time.gmtime(ts or _now()))


def _usage_limits(data: dict[str, Any]) -> dict[str, float]:
    return {
        "asr_seconds": float(data.get("asr_seconds") or 0),
        "llm_tokens": float(data.get("llm_tokens") or 0),
        "tts_chars": float(data.get("tts_chars") or 0),
        "api_calls": float(data.get("api_calls") or 0),
    }


def _entitlement(body: dict[str, Any]) -> dict[str, Any]:
    source = body.get("entitlement") if isinstance(body.get("entitlement"), dict) else body
    return {
        "plan_id": str(source.get("plan_id") or "plan_internal"),
        "status": str(source.get("entitlement_status") or source.get("status") or "active"),
        "started_at": int(source.get("started_at") or _now()),
        "expires_at": int(source.get("expires_at") or 0),
        "notes": str(source.get("notes") or ""),
    }


def _device_config(body: dict[str, Any]) -> dict[str, Any]:
    config = body.get("config") if isinstance(body.get("config"), dict) else {}
    allowed = {
        "language",
        "ai_name",
        "wake_phrases",
        "tts_voice",
        "volume",
        "app_id",
        "firmware_channel",
        "wallet_mode",
        "risk_mode",
    }
    inline = {key: body[key] for key in allowed if key in body}
    merged = {**config, **inline}
    if "wake_phrases" in merged and isinstance(merged["wake_phrases"], str):
        merged["wake_phrases"] = [item.strip() for item in merged["wake_phrases"].split(",") if item.strip()]
    if "volume" in merged:
        merged["volume"] = max(0, min(100, int(merged["volume"] or 0)))
    return {k: v for k, v in merged.items() if k in allowed}


def _sanitize_runtime_config(body: dict[str, Any]) -> dict[str, Any]:
    allowed_top = {"providers", "adapters", "execution", "services"}
    result: dict[str, Any] = {}
    for key in allowed_top:
        if isinstance(body.get(key), dict):
            result[key] = body[key]
        elif key == "services" and isinstance(body.get(key), list):
            result[key] = body[key]
    return result


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lower = str(key).lower()
            if not lower.endswith("_env") and any(word in lower for word in ("key", "secret", "token", "password")):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
