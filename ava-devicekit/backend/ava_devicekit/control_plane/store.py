from __future__ import annotations

import hashlib
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from ava_devicekit.storage.json_store import JsonStore
from ava_devicekit.wallet import build_login_message, verify_solana_signature

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
            "customers": [_safe_customer(item) for item in data.get("customers", [])],
            "projects": [dict(item) for item in data.get("projects", [])],
            "devices": [dict(item) for item in data.get("devices", [])],
            "purchases": [_safe_purchase(item) for item in data.get("purchases", [])],
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
                "purchases": len(items["purchases"]),
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
        app_id = str(body.get("app_id") or "").strip()
        project_id = str(body.get("project_id") or "").strip()
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
                "app_ids": [app_id] if app_id else [],
                "project_ids": [project_id] if project_id else [],
                "created_at": now,
                "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            }
            data["customers"].append(created)

        self.store.update(_default_state(), mutate)
        return {"ok": True, "customer": _safe_customer(created)}

    def register_customer(self, body: dict[str, Any]) -> dict[str, Any]:
        """Self-service C-end customer registration with optional device binding."""

        email = str(body.get("email") or "").strip().lower()
        if not email:
            raise ValueError("email_required")
        display_name = str(body.get("display_name") or body.get("name") or email)
        wallet = str(body.get("wallet") or body.get("wallet_address") or "")
        app_id = str(body.get("app_id") or "").strip()
        project_id = str(body.get("project_id") or "").strip()
        customer: dict[str, Any] = {}
        now = _now()

        def mutate(data: dict[str, Any]) -> None:
            nonlocal customer
            _ensure_shape(data)
            existing = next((item for item in data["customers"] if item.get("email") == email), None)
            if existing:
                if display_name and existing.get("display_name") in {"", existing.get("email"), "customer"}:
                    existing["display_name"] = display_name
                if wallet:
                    existing["wallet"] = wallet
                _ensure_customer_app_link(existing, app_id=app_id, project_id=project_id)
                customer = _safe_customer(existing)
                return
            customer = {
                "customer_id": _id("cus"),
                "email": email,
                "display_name": display_name,
                "wallet": wallet,
                "status": "active",
                "app_ids": [app_id] if app_id else [],
                "project_ids": [project_id] if project_id else [],
                "created_at": now,
                "registered_at": now,
                "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            }
            data["customers"].append(customer)
            customer = _safe_customer(customer)

        self.store.update(_default_state(), mutate)
        result: dict[str, Any] = {"ok": True, "customer": customer, "created": bool(customer.get("registered_at") == now)}
        activation_code = str(body.get("activation_code") or "").strip()
        if activation_code:
            activation = self.activate_device(
                {
                    "activation_code": activation_code,
                    "customer_id": customer["customer_id"],
                    "customer": {"email": email, "display_name": display_name, "wallet": wallet},
                }
            )
            result["activation"] = activation
            result["device"] = activation["device"]
            result["customer"] = self.customer(customer["customer_id"])["customer"]
        return result

    def customer(self, customer_id: str) -> dict[str, Any]:
        data = self.bootstrap()
        customer = _find_customer(data, customer_id)
        if not customer:
            raise ValueError("customer_not_found")
        devices = [_safe_device(item) for item in data.get("devices", []) if item.get("customer_id") == customer.get("customer_id")]
        return {"ok": True, "customer": _safe_customer(customer), "devices": devices, "device_count": len(devices)}

    def login_customer(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create or reuse a C-end account and issue a customer session token."""

        email = str(body.get("email") or "").strip().lower()
        if not email:
            raise ValueError("email_required")
        display_name = str(body.get("display_name") or body.get("name") or email)
        wallet = str(body.get("wallet") or body.get("wallet_address") or "")
        app_id = str(body.get("app_id") or "ava_box").strip()
        project_id = str(body.get("project_id") or "").strip()
        token = _token("avacus")
        now = _now()
        customer_id = ""

        def mutate(data: dict[str, Any]) -> None:
            nonlocal customer_id
            _ensure_shape(data)
            customer = next((item for item in data["customers"] if item.get("email") == email), None)
            if not customer:
                customer = {
                    "customer_id": _id("cus"),
                    "email": email,
                    "display_name": display_name,
                    "wallet": wallet,
                    "status": "active",
                    "app_ids": [],
                    "project_ids": [],
                    "created_at": now,
                    "registered_at": now,
                    "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
                }
                data["customers"].append(customer)
            else:
                if display_name and customer.get("display_name") in {"", customer.get("email"), "customer"}:
                    customer["display_name"] = display_name
                if wallet:
                    customer["wallet"] = wallet
            _ensure_customer_app_link(customer, app_id=app_id, project_id=project_id)
            customer["customer_token_hash"] = _hash_token(token)
            customer["last_login_at"] = now
            customer_id = str(customer["customer_id"])

        self.store.update(_default_state(), mutate)
        profile = self.customer(customer_id)
        return {"ok": True, "customer": profile["customer"], "devices": profile["devices"], "device_count": profile["device_count"], "customer_token": token}

    def create_wallet_challenge(self, body: dict[str, Any]) -> dict[str, Any]:
        wallet = str(body.get("wallet") or body.get("wallet_address") or "").strip()
        if not wallet:
            raise ValueError("wallet_required")
        app_id = str(body.get("app_id") or "ava_box").strip()
        now = _now()
        nonce = secrets.token_urlsafe(24)
        message = build_login_message(wallet=wallet, nonce=nonce, app_id=app_id, issued_at=now)
        challenge = {
            "challenge_id": _id("wch"),
            "wallet": wallet,
            "app_id": app_id,
            "nonce": nonce,
            "message": message,
            "created_at": now,
            "expires_at": now + 300,
            "used_at": 0,
        }

        def mutate(data: dict[str, Any]) -> None:
            _ensure_shape(data)
            data["auth_challenges"] = [
                item
                for item in data.get("auth_challenges", [])
                if int(item.get("expires_at") or 0) > now and not int(item.get("used_at") or 0)
            ][-50:]
            data["auth_challenges"].append(challenge)

        self.store.update(_default_state(), mutate)
        return {"ok": True, **challenge}

    def login_customer_with_wallet(self, body: dict[str, Any]) -> dict[str, Any]:
        wallet = str(body.get("wallet") or body.get("wallet_address") or "").strip()
        nonce = str(body.get("nonce") or "").strip()
        signature = str(body.get("signature") or "").strip()
        if not wallet:
            raise ValueError("wallet_required")
        if not nonce:
            raise ValueError("nonce_required")
        if not signature:
            raise ValueError("signature_required")
        email = str(body.get("email") or "").strip().lower()
        display_name = str(body.get("display_name") or body.get("name") or _short_wallet(wallet))
        app_id = str(body.get("app_id") or "ava_box").strip()
        project_id = str(body.get("project_id") or "").strip()
        token = _token("avacus")
        now = _now()
        customer_id = ""

        def mutate(data: dict[str, Any]) -> None:
            nonlocal customer_id
            _ensure_shape(data)
            challenge = next(
                (
                    item
                    for item in data.get("auth_challenges", [])
                    if item.get("nonce") == nonce and item.get("wallet") == wallet and not int(item.get("used_at") or 0)
                ),
                None,
            )
            if not challenge:
                raise ValueError("wallet_challenge_not_found")
            if int(challenge.get("expires_at") or 0) < now:
                raise ValueError("wallet_challenge_expired")
            if not verify_solana_signature(wallet=wallet, message=str(challenge.get("message") or ""), signature=signature):
                raise ValueError("invalid_wallet_signature")
            challenge["used_at"] = now

            customer = next((item for item in data["customers"] if item.get("wallet") == wallet), None)
            if not customer and email:
                customer = next((item for item in data["customers"] if item.get("email") == email), None)
            if not customer:
                customer = {
                    "customer_id": _id("cus"),
                    "email": email,
                    "display_name": display_name,
                    "wallet": wallet,
                    "status": "active",
                    "auth_method": "wallet_signature",
                    "app_ids": [],
                    "project_ids": [],
                    "created_at": now,
                    "registered_at": now,
                    "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
                }
                data["customers"].append(customer)
            else:
                customer["wallet"] = wallet
                customer["auth_method"] = "wallet_signature"
                if email and not customer.get("email"):
                    customer["email"] = email
                if display_name and customer.get("display_name") in {"", customer.get("email"), "customer", _short_wallet(wallet)}:
                    customer["display_name"] = display_name
            _ensure_customer_app_link(customer, app_id=app_id, project_id=project_id)
            customer["customer_token_hash"] = _hash_token(token)
            customer["last_login_at"] = now
            customer_id = str(customer["customer_id"])

        self.store.update(_default_state(), mutate)
        profile = self.customer(customer_id)
        return {
            "ok": True,
            "auth_method": "wallet_signature",
            "customer": profile["customer"],
            "devices": profile["devices"],
            "device_count": profile["device_count"],
            "customer_token": token,
        }

    def customer_session(self, token: str) -> dict[str, Any]:
        token = str(token or "").strip()
        if not token:
            raise ValueError("customer_token_required")
        token_hash = _hash_token(token)
        data = self.bootstrap()
        for customer in data.get("customers", []):
            expected = str(customer.get("customer_token_hash") or "")
            if expected and secrets.compare_digest(expected, token_hash):
                devices = [_safe_device(item) for item in data.get("devices", []) if item.get("customer_id") == customer.get("customer_id")]
                return {"ok": True, "customer": _safe_customer(customer), "devices": devices, "device_count": len(devices)}
        raise ValueError("invalid_customer_token")

    def activate_customer_device(self, customer_id: str, body: dict[str, Any]) -> dict[str, Any]:
        activation = self.activate_device({**body, "customer_id": customer_id})
        profile = self.customer(customer_id)
        return {"ok": True, "activation": activation, "device": activation["device"], "customer": profile["customer"], "devices": profile["devices"], "device_count": profile["device_count"]}

    def app_customers(self, app_id: str) -> dict[str, Any]:
        data = self.bootstrap()
        app_id = str(app_id or "").strip()
        devices = [item for item in data.get("devices", []) if not app_id or item.get("app_id") == app_id]
        customer_ids = {str(item.get("customer_id") or "") for item in devices if item.get("customer_id")}
        rows: list[dict[str, Any]] = []
        for customer in data.get("customers", []):
            if app_id and app_id not in set(customer.get("app_ids") or []) and customer.get("customer_id") not in customer_ids:
                continue
            linked_devices = [_safe_device(item) for item in devices if item.get("customer_id") == customer.get("customer_id")]
            rows.append({**_safe_customer(customer), "devices": linked_devices, "device_count": len(linked_devices)})
        return {"ok": True, "app_id": app_id, "items": rows, "count": len(rows)}

    def app_devices(self, app_id: str) -> dict[str, Any]:
        data = self.bootstrap()
        app_id = str(app_id or "").strip()
        rows = [_safe_device(item) for item in data.get("devices", []) if not app_id or item.get("app_id") == app_id]
        return {"ok": True, "app_id": app_id, "items": rows, "count": len(rows)}

    def purchases(self, app_id: str = "") -> dict[str, Any]:
        data = self.bootstrap()
        app_id = str(app_id or "").strip()
        rows = [_safe_purchase(item) for item in data.get("purchases", []) if not app_id or item.get("app_id") == app_id]
        return {"ok": True, "app_id": app_id, "items": rows, "count": len(rows)}

    def create_purchase(self, body: dict[str, Any], *, public_base_url: str = "") -> dict[str, Any]:
        data = self.bootstrap()
        requested_device_id = str(body.get("device_id") or body.get("serial") or _id("device"))
        device_id = normalize_control_device_id(requested_device_id)
        app_id = str(body.get("app_id") or "ava_box").strip()
        project_id = str(body.get("project_id") or data["projects"][0]["project_id"])
        plan_id = str(body.get("plan_id") or "")
        if plan_id and not any(item.get("plan_id") == plan_id for item in data["service_plans"]):
            raise ValueError("service_plan_not_found")
        device = _find_device(data, device_id)
        provisioning_token = ""
        if not device:
            provisioned = self.provision_device(
                {
                    "device_id": device_id,
                    "project_id": project_id,
                    "app_id": app_id,
                    "name": str(body.get("device_name") or body.get("name") or device_id),
                    "board_model": str(body.get("board_model") or body.get("model") or "esp32"),
                    "plan_id": plan_id,
                    "entitlement_status": str(body.get("entitlement_status") or "pending_activation"),
                }
            )
            provisioning_token = provisioned["provisioning_token"]
            data = self.bootstrap()
            device = _find_device(data, device_id)
        if not device:
            raise ValueError("device_not_found")
        activation_code = _activation_code(str(device["device_id"]))
        now = _now()
        purchase: dict[str, Any] = {}

        def mutate(state: dict[str, Any]) -> None:
            nonlocal purchase
            _ensure_shape(state)
            current_device = _find_device(state, str(device["device_id"]))
            if not current_device:
                raise ValueError("device_not_found")
            current_device["app_id"] = app_id or str(current_device.get("app_id") or "ava_box")
            if plan_id:
                current_device["entitlement"] = _entitlement({"plan_id": plan_id, "status": str(body.get("entitlement_status") or "pending_activation"), "expires_at": body.get("expires_at") or 0})
            purchase = {
                "purchase_id": _id("pur"),
                "order_ref": str(body.get("order_ref") or body.get("order_id") or ""),
                "status": str(body.get("status") or "paid"),
                "app_id": app_id or str(current_device.get("app_id") or "ava_box"),
                "project_id": str(current_device.get("project_id") or project_id),
                "device_id": str(current_device["device_id"]),
                "activation_code": activation_code,
                "activation_url": _activation_url(public_base_url, activation_code, app_id),
                "customer_email": str(body.get("customer_email") or body.get("email") or "").strip().lower(),
                "customer_wallet": str(body.get("customer_wallet") or body.get("wallet") or body.get("wallet_address") or "").strip(),
                "customer_id": str(body.get("customer_id") or current_device.get("customer_id") or ""),
                "plan_id": plan_id,
                "amount_label": str(body.get("amount_label") or body.get("price_label") or ""),
                "created_at": now,
                "activated_at": 0,
                "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            }
            state["purchases"].append(purchase)

        self.store.update(_default_state(), mutate)
        result = {"ok": True, "purchase": _safe_purchase(purchase), "activation_card": _activation_card(purchase), "activation_code": activation_code}
        if provisioning_token:
            result["provisioning_token"] = provisioning_token
        return result

    def activation_card(self, purchase_id: str, *, public_base_url: str = "") -> dict[str, Any]:
        data = self.bootstrap()
        purchase = _find_purchase(data, purchase_id)
        if not purchase:
            device = _find_device(data, purchase_id)
            if not device:
                raise ValueError("purchase_not_found")
            activation_code = _activation_code(str(device["device_id"]))
            purchase = {
                "purchase_id": "",
                "order_ref": "",
                "status": "device_card",
                "app_id": str(device.get("app_id") or "ava_box"),
                "project_id": str(device.get("project_id") or ""),
                "device_id": str(device["device_id"]),
                "activation_code": activation_code,
                "activation_url": _activation_url(public_base_url, activation_code, str(device.get("app_id") or "ava_box")),
                "customer_email": "",
                "customer_wallet": "",
                "customer_id": str(device.get("customer_id") or ""),
                "plan_id": str((device.get("entitlement") or {}).get("plan_id") or ""),
                "amount_label": "",
                "created_at": int(device.get("created_at") or 0),
                "activated_at": int(device.get("activated_at") or 0),
                "metadata": {},
            }
        elif public_base_url:
            purchase = dict(purchase)
            purchase["activation_url"] = _activation_url(public_base_url, str(purchase.get("activation_code") or ""), str(purchase.get("app_id") or "ava_box"))
        return {"ok": True, "purchase": _safe_purchase(purchase), "activation_card": _activation_card(purchase)}

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
                        "app_ids": [],
                        "project_ids": [],
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
            linked_customer = _find_customer(state, customer_id)
            if linked_customer:
                _ensure_customer_app_link(linked_customer, app_id=str(device.get("app_id") or ""), project_id=str(device.get("project_id") or ""))
            for purchase in state.get("purchases", []):
                if purchase.get("device_id") != device.get("device_id") and purchase.get("activation_code") != code:
                    continue
                expected_wallet = str(purchase.get("customer_wallet") or "")
                actual_wallet = str((linked_customer or {}).get("wallet") or "")
                if expected_wallet and actual_wallet != expected_wallet:
                    raise ValueError("wallet_does_not_match_purchase")
            for purchase in state.get("purchases", []):
                if purchase.get("device_id") != device.get("device_id") and purchase.get("activation_code") != code:
                    continue
                purchase["status"] = "activated"
                purchase["customer_id"] = customer_id
                purchase["activated_at"] = now
                if linked_customer:
                    purchase["customer_email"] = str(linked_customer.get("email") or purchase.get("customer_email") or "")
                    purchase["customer_wallet"] = str(linked_customer.get("wallet") or purchase.get("customer_wallet") or "")
                plan_id = str(purchase.get("plan_id") or "")
                if plan_id:
                    device["entitlement"] = _entitlement({"plan_id": plan_id, "status": "active", "expires_at": (device.get("entitlement") or {}).get("expires_at") or 0})
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
        "purchases": [],
        "auth_challenges": [],
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
    if not isinstance(data.get("purchases"), list):
        data["purchases"] = []
    if not isinstance(data.get("auth_challenges"), list):
        data["auth_challenges"] = []
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
    for customer in data["customers"]:
        if not isinstance(customer, dict):
            continue
        if not isinstance(customer.get("app_ids"), list):
            customer["app_ids"] = [str(customer["app_id"])] if customer.get("app_id") else []
        if not isinstance(customer.get("project_ids"), list):
            customer["project_ids"] = [str(customer["project_id"])] if customer.get("project_id") else []
    data["version"] = int(data.get("version") or 1)


def _safe_device(device: dict[str, Any]) -> dict[str, Any]:
    safe = dict(device)
    safe.pop("provisioning_token_hash", None)
    safe.pop("device_token_hash", None)
    safe.pop("activation_code_hash", None)
    return safe


def _safe_customer(customer: dict[str, Any]) -> dict[str, Any]:
    safe = dict(customer)
    safe.pop("customer_token_hash", None)
    return safe


def _safe_purchase(purchase: dict[str, Any]) -> dict[str, Any]:
    return dict(purchase)


def _find_device(data: dict[str, Any], device_id: str) -> dict[str, Any] | None:
    normalized = normalize_control_device_id(device_id)
    for item in data.get("devices", []):
        if normalize_control_device_id(str(item.get("device_id") or "")) == normalized:
            return item
    return None


def _find_customer(data: dict[str, Any], customer_id: str) -> dict[str, Any] | None:
    needle = str(customer_id or "")
    for item in data.get("customers", []):
        if str(item.get("customer_id") or "") == needle:
            return item
    return None


def _find_purchase(data: dict[str, Any], purchase_id: str) -> dict[str, Any] | None:
    needle = str(purchase_id or "")
    for item in data.get("purchases", []):
        if str(item.get("purchase_id") or "") == needle or str(item.get("device_id") or "") == normalize_control_device_id(needle):
            return item
    return None


def _ensure_customer_app_link(customer: dict[str, Any], *, app_id: str = "", project_id: str = "") -> None:
    app_id = str(app_id or "").strip()
    project_id = str(project_id or "").strip()
    app_ids = customer.get("app_ids") if isinstance(customer.get("app_ids"), list) else []
    project_ids = customer.get("project_ids") if isinstance(customer.get("project_ids"), list) else []
    if app_id and app_id not in app_ids:
        app_ids.append(app_id)
    if project_id and project_id not in project_ids:
        project_ids.append(project_id)
    customer["app_ids"] = app_ids
    customer["project_ids"] = project_ids


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


def _activation_url(public_base_url: str, activation_code: str, app_id: str) -> str:
    base = str(public_base_url or "").strip().rstrip("/")
    if not base:
        base = "http://127.0.0.1:8788"
    return f"{base}/customer?{urlencode({'activation_code': activation_code, 'app_id': app_id or 'ava_box'})}"


def _activation_card(purchase: dict[str, Any]) -> dict[str, Any]:
    activation_url = str(purchase.get("activation_url") or _activation_url("", str(purchase.get("activation_code") or ""), str(purchase.get("app_id") or "ava_box")))
    return {
        "title": "Activate your Ava device",
        "device_id": str(purchase.get("device_id") or ""),
        "app_id": str(purchase.get("app_id") or "ava_box"),
        "activation_code": str(purchase.get("activation_code") or ""),
        "activation_url": activation_url,
        "qr_payload": activation_url,
        "qr_svg": _qr_placeholder_svg(activation_url),
        "instructions": [
            "Open the activation URL or scan the QR code.",
            "Connect your Solana wallet and sign the login message.",
            "Confirm the activation code to bind this hardware to your account.",
        ],
    }


def _qr_placeholder_svg(payload: str) -> str:
    try:
        import qrcode
        import qrcode.image.svg

        image = qrcode.make(payload, image_factory=qrcode.image.svg.SvgPathImage)
        return image.to_string(encoding="unicode")
    except Exception:
        pass
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    cells = 17
    size = 170
    cell = size // cells
    rects = [f'<rect width="{size}" height="{size}" fill="#fff9ea"/>']
    for y in range(cells):
        for x in range(cells):
            idx = (x + y * cells) % len(digest)
            finder = (x < 5 and y < 5) or (x >= cells - 5 and y < 5) or (x < 5 and y >= cells - 5)
            if finder or ((digest[idx] >> ((x + y) % 8)) & 1):
                rects.append(f'<rect x="{x * cell}" y="{y * cell}" width="{cell}" height="{cell}" fill="#253021"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" role="img" aria-label="Activation code visual marker">' + "".join(rects) + "</svg>"


def _short_wallet(wallet: str) -> str:
    wallet = str(wallet or "")
    if len(wallet) <= 12:
        return wallet or "wallet user"
    return f"{wallet[:4]}...{wallet[-4:]}"


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
