from __future__ import annotations

import argparse
import json
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from ava_devicekit.control_plane import ControlPlaneStore
from ava_devicekit.gateway.admin_page import ADMIN_PAGE
from ava_devicekit.gateway.customer_page import CUSTOMER_PAGE
from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.gateway.runtime_manager import RuntimeManager, normalize_device_id, runtime_manager_for_settings
from ava_devicekit.gateway.session import DeviceSession
from ava_devicekit.ota.firmware import build_ota_response, resolve_firmware_download
from ava_devicekit.ota.publish import firmware_catalog, publish_firmware
from ava_devicekit.providers.health import provider_health_report
from ava_devicekit.runtime.settings import RuntimeSettings
from ava_devicekit.runtime.tasks import BackgroundTaskManager
from ava_devicekit.services.client import invoke_developer_service
from ava_devicekit.services.registry import developer_service_report

SessionFactory = Callable[[], DeviceSession]


def make_handler(
    session_factory: SessionFactory | None = None,
    runtime_settings: RuntimeSettings | None = None,
    manager: RuntimeManager | None = None,
    task_manager: BackgroundTaskManager | None = None,
    provider_health: Callable[[], dict[str, Any]] | None = None,
):
    settings = runtime_settings or RuntimeSettings.load()
    session_factory = session_factory or (lambda: create_device_session(mock=True))
    manager = manager or RuntimeManager(lambda device_id: session_factory())
    control_plane = ControlPlaneStore(settings.control_plane_store_path)
    _apply_runtime_config(settings, control_plane.runtime_config())

    class DeviceKitHandler(BaseHTTPRequestHandler):
        server_version = "AvaDeviceKitHTTP/0.1"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/health":
                self._send_json({"ok": True, "service": "ava-devicekit"})
                return
            if path == "/manifest":
                self._send_json(self._session().app.manifest.to_dict())
                return
            if path == "/device/state":
                if not self._authorized_device():
                    return
                self._send_json(manager.state(self._device_id()))
                return
            if path == "/device/outbox":
                if not self._authorized_device():
                    return
                self._send_json(manager.outbox(self._device_id()))
                return
            if path == "/device/config":
                if not self._authorized_device():
                    return
                try:
                    self._send_json({"ok": True, "device_id": self._device_id(), "config": control_plane.device_config(self._device_id())})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            if path == "/admin/usage":
                if not self._authorized_admin():
                    return
                self._send_json(control_plane.usage_report(device_id=_query_value(query, "device_id"), period=_query_value(query, "period")))
                return
            if path == "/admin/service-plans":
                if not self._authorized_admin():
                    return
                snapshot = control_plane.snapshot()
                self._send_json({"ok": True, "items": snapshot["service_plans"], "count": len(snapshot["service_plans"])})
                return
            if path == "/admin/capabilities":
                if not self._authorized_admin():
                    return
                self._send_json(_load_capabilities())
                return
            if path == "/admin":
                if not self._authorized_admin():
                    return
                self._send_bytes(_admin_page().encode("utf-8"), "text/html; charset=utf-8")
                return
            if path in {"/customer", "/customer/"}:
                self._send_bytes(_customer_page().encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/customer/me":
                session = self._customer_session()
                if not session:
                    return
                self._send_json(session)
                return
            if path == "/admin/runtime":
                if not self._authorized_admin():
                    return
                self._send_json(settings.sanitized_dict())
                return
            if path == "/admin/runtime/config":
                if not self._authorized_admin():
                    return
                self._send_json({"ok": True, "runtime_config": control_plane.runtime_config(), "effective": settings.sanitized_dict()})
                return
            if path == "/admin/apps":
                if not self._authorized_admin():
                    return
                active = self._session().app.manifest.to_dict()
                self._send_json(control_plane.apps_overview(active_manifest=active))
                return
            if path.startswith("/admin/apps/") and path.endswith("/customers"):
                if not self._authorized_admin():
                    return
                app_id = path.split("/")[3]
                self._send_json(control_plane.app_customers(app_id))
                return
            if path.startswith("/admin/apps/") and path.endswith("/devices"):
                if not self._authorized_admin():
                    return
                app_id = path.split("/")[3]
                self._send_json(control_plane.app_devices(app_id))
                return
            if path == "/admin/devices":
                if not self._authorized_admin():
                    return
                self._send_json({"items": manager.list_devices(), "count": len(manager.sessions)})
                return
            if path == "/admin/control-plane":
                if not self._authorized_admin():
                    return
                self._send_json(control_plane.snapshot())
                return
            if path == "/admin/users":
                if not self._authorized_admin():
                    return
                snapshot = control_plane.snapshot()
                self._send_json({"ok": True, "items": snapshot["users"], "count": len(snapshot["users"])})
                return
            if path == "/admin/customers":
                if not self._authorized_admin():
                    return
                snapshot = control_plane.snapshot()
                self._send_json({"ok": True, "items": snapshot["customers"], "count": len(snapshot["customers"])})
                return
            if path == "/admin/projects":
                if not self._authorized_admin():
                    return
                snapshot = control_plane.snapshot()
                self._send_json({"ok": True, "items": snapshot["projects"], "count": len(snapshot["projects"])})
                return
            if path == "/admin/purchases":
                if not self._authorized_admin():
                    return
                self._send_json(control_plane.purchases(app_id=_query_value(query, "app_id")))
                return
            if path.startswith("/admin/purchases/") and path.endswith("/activation-card"):
                if not self._authorized_admin():
                    return
                purchase_id = path.split("/")[3]
                try:
                    self._send_json(control_plane.activation_card(purchase_id, public_base_url=self._public_base_url()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            if path == "/admin/registered-devices":
                if not self._authorized_admin():
                    return
                snapshot = control_plane.snapshot()
                self._send_json({"ok": True, "items": snapshot["devices"], "count": len(snapshot["devices"])})
                return
            if path == "/admin/events":
                if not self._authorized_admin():
                    return
                self._send_json(
                    manager.event_log(
                        device_id=_query_value(query, "device_id"),
                        event=_query_value(query, "event"),
                        limit=int(_query_value(query, "limit") or 200),
                    )
                )
                return
            if path == "/admin/providers/health":
                if not self._authorized_admin():
                    return
                self._send_json(provider_health() if provider_health else provider_health_report(settings))
                return
            if path == "/admin/developer/services":
                if not self._authorized_admin():
                    return
                self._send_json(developer_service_report(settings.developer_services))
                return
            if path == "/admin/ota/firmware":
                if not self._authorized_admin():
                    return
                self._send_json(firmware_catalog(settings))
                return
            if path == "/admin/tasks":
                if not self._authorized_admin():
                    return
                self._send_json(task_manager.snapshot() if task_manager else {"items": [], "count": 0, "running_count": 0})
                return
            if path.startswith("/admin/devices/") and path.endswith("/state"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                self._send_json(manager.state(device_id))
                return
            if path.startswith("/admin/devices/") and path.endswith("/config"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                try:
                    self._send_json({"ok": True, "device_id": device_id, "config": control_plane.device_config(device_id)})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            if path.startswith("/admin/devices/") and path.endswith("/diagnostics"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                snapshot = control_plane.snapshot()
                device = next((item for item in snapshot["devices"] if item.get("device_id") == device_id), {})
                payload = {
                    "ok": True,
                    "device": device,
                    "runtime_state": manager.state(device_id),
                    "connection": manager.connection_state(device_id),
                    "events": manager.event_log(device_id=device_id, limit=100),
                }
                try:
                    payload["config"] = control_plane.device_config(device_id)
                except Exception:
                    payload["config"] = {}
                payload["usage"] = control_plane.usage_report(device_id=device_id)
                self._send_json(payload)
                return
            if path.startswith("/admin/devices/") and path.endswith("/connection"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                self._send_json(manager.connection_state(device_id))
                return
            if path.startswith("/admin/devices/") and path.endswith("/outbox"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                self._send_json(manager.outbox(device_id))
                return
            if path == "/admin/dashboard.json":
                if not self._authorized_admin():
                    return
                self._send_json(_dashboard_payload(settings, manager, task_manager, provider_health))
                return
            if path == "/admin/onboarding":
                if not self._authorized_admin():
                    return
                self._send_json(_onboarding_payload(settings, manager, provider_health))
                return
            if path == "/ava/ota/":
                host_hint = self.headers.get("Host", "127.0.0.1").split(":")[0]
                message = f"OTA OK. WebSocket: {settings.websocket_endpoint(host_hint)}"
                self._send_bytes(message.encode("utf-8"), "text/plain; charset=utf-8")
                return
            if path.startswith("/ava/ota/download/"):
                filename = path.rsplit("/", 1)[-1]
                file_path = resolve_firmware_download(settings, filename)
                if not file_path:
                    self._send_json({"ok": False, "error": "file_not_found"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_file(file_path)
                return
            self._send_json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlparse(self.path).path
            if path == "/device/register":
                try:
                    self._send_json(control_plane.register_device(self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/device/activate":
                try:
                    self._send_json(control_plane.activate_device(self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/customer/register":
                try:
                    self._send_json(control_plane.register_customer(self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/customer/wallet/challenge":
                try:
                    self._send_json(control_plane.create_wallet_challenge(self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/customer/wallet/login":
                try:
                    self._send_json(control_plane.login_customer_with_wallet(self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/customer/demo-purchase":
                if settings.production_mode and os.environ.get("AVA_DEVICEKIT_ENABLE_DEMO_CHECKOUT") != "1":
                    self._send_json({"ok": False, "error": "demo_checkout_disabled"}, HTTPStatus.FORBIDDEN)
                    return
                try:
                    result = control_plane.create_purchase(_demo_purchase_body(self._read_json()), public_base_url=self._public_base_url())
                    result.pop("provisioning_token", None)
                    result["factory_note"] = "Device provisioning token is kept on the fulfillment/device side; customers only receive the activation card."
                    self._send_json(result)
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/customer/login":
                try:
                    self._send_json(control_plane.login_customer(self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/customer/activate":
                session = self._customer_session()
                if not session:
                    return
                try:
                    self._send_json(control_plane.activate_customer_device(session["customer"]["customer_id"], self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/device/boot":
                if not self._authorized_device():
                    return
                control_plane.mark_device_seen(self._device_id())
                self._send_json(manager.boot(self._device_id()))
                return
            if path == "/device/message":
                if not self._authorized_device():
                    return
                try:
                    body = self._read_json()
                    control_plane.mark_device_seen(self._device_id(), firmware_version=str(body.get("firmware_version") or ""))
                    self._send_json(manager.handle(self._device_id(), body))
                except Exception as exc:  # pragma: no cover - defensive server boundary
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/device/usage":
                if not self._authorized_device():
                    return
                try:
                    body = self._read_json()
                    body["device_id"] = self._device_id()
                    body.setdefault("source", "device")
                    self._send_json(control_plane.record_usage(body))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/admin/users":
                if not self._authorized_admin():
                    return
                try:
                    self._send_json(control_plane.create_user(self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/admin/customers":
                if not self._authorized_admin():
                    return
                try:
                    self._send_json(control_plane.create_customer(self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/admin/service-plans":
                if not self._authorized_admin():
                    return
                try:
                    self._send_json(control_plane.create_service_plan(self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/admin/usage":
                if not self._authorized_admin():
                    return
                try:
                    body = self._read_json()
                    body.setdefault("source", "admin")
                    self._send_json(control_plane.record_usage(body))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/admin/projects":
                if not self._authorized_admin():
                    return
                try:
                    self._send_json(control_plane.create_project(self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/admin/purchases":
                if not self._authorized_admin():
                    return
                try:
                    self._send_json(control_plane.create_purchase(self._read_json(), public_base_url=self._public_base_url()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/admin/runtime/config":
                if not self._authorized_admin():
                    return
                try:
                    body = self._read_json()
                    result = control_plane.update_runtime_config(body)
                    _apply_runtime_config(settings, result["runtime_config"])
                    self._send_json({"ok": True, "runtime_config": result["runtime_config"], "effective": settings.sanitized_dict()})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/admin/runtime/providers":
                if not self._authorized_admin():
                    return
                try:
                    body = self._read_json()
                    result = control_plane.update_runtime_config(_runtime_provider_patch(body))
                    _apply_runtime_config(settings, result["runtime_config"])
                    self._send_json({"ok": True, "runtime_config": result["runtime_config"], "providers": provider_health_report(settings)})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/admin/devices/register":
                if not self._authorized_admin():
                    return
                try:
                    self._send_json(control_plane.provision_device(self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path.startswith("/admin/devices/") and path.endswith("/provision-token"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                try:
                    self._send_json(control_plane.rotate_provisioning_token(device_id))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path.startswith("/admin/devices/") and path.endswith("/config"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                try:
                    self._send_json(control_plane.update_device_config(device_id, self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path.startswith("/admin/devices/") and path.endswith("/status"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                try:
                    self._send_json(control_plane.update_device_status(device_id, str(self._read_json().get("status") or "")))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path.startswith("/admin/devices/") and path.endswith("/delete"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                try:
                    self._send_json(control_plane.delete_device(device_id))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path.startswith("/admin/devices/") and path.endswith("/entitlement"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                try:
                    self._send_json(control_plane.set_device_entitlement(device_id, self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path.startswith("/admin/devices/") and path.endswith("/boot"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                self._send_json(manager.boot(device_id))
                return
            if path.startswith("/admin/devices/") and path.endswith("/message"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                try:
                    self._send_json(manager.handle(device_id, self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/ava/ota/":
                try:
                    body = self._read_json()
                    host_hint = self.headers.get("Host", "127.0.0.1").split(":")[0]
                    self._send_json(
                        build_ota_response(
                            settings=settings,
                            headers=dict(self.headers.items()),
                            body=body,
                            host_hint=host_hint,
                        )
                    )
                except Exception as exc:  # pragma: no cover - defensive server boundary
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path == "/admin/ota/firmware":
                if not self._authorized_admin():
                    return
                try:
                    body = self._read_json()
                    self._send_json(
                        publish_firmware(
                            settings,
                            model=str(body.get("model") or ""),
                            version=str(body.get("version") or ""),
                            source_path=body.get("source_path"),
                            content_base64=str(body.get("content_base64") or ""),
                        )
                    )
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path.startswith("/admin/devices/") and path.endswith("/ota-check"):
                if not self._authorized_admin():
                    return
                device_id = path.split("/")[3]
                try:
                    self._send_json(manager.queue_ota_check(device_id))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if path.startswith("/admin/developer/services/") and path.endswith("/invoke"):
                if not self._authorized_admin():
                    return
                service_id = path.split("/")[4]
                try:
                    self._send_json(invoke_developer_service(settings.developer_services, service_id, self._read_json()))
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)

        def log_message(self, fmt: str, *args) -> None:
            print(f"[ava-devicekit] {self.address_string()} - {fmt % args}")

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _session(self) -> DeviceSession:
            return manager.get(self._device_id())

        def _device_id(self) -> str:
            return normalize_device_id(self.headers.get("X-Ava-Device-Id") or "default")

        def _public_base_url(self) -> str:
            host = self.headers.get("Host", "127.0.0.1:8788")
            scheme = "https" if self.headers.get("X-Forwarded-Proto") == "https" else "http"
            return f"{scheme}://{host}"

        def _authorized_admin(self) -> bool:
            return self._authorized(settings.admin_token_env)

        def _authorized_device(self) -> bool:
            expected = os.environ.get(settings.device_token_env, "")
            supplied = self.headers.get("Authorization", "")
            token = supplied.removeprefix("Bearer ").strip()
            if expected and token == expected:
                return True
            if control_plane.validate_device_token(self._device_id(), token):
                return True
            if not expected and not settings.production_mode:
                return True
            if expected:
                self._send_json({"ok": False, "error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            else:
                self._send_json({"ok": False, "error": "token_required", "token_env": settings.device_token_env}, HTTPStatus.UNAUTHORIZED)
            return False

        def _customer_session(self) -> dict[str, Any] | None:
            supplied = self.headers.get("Authorization", "")
            token = supplied.removeprefix("Bearer ").strip()
            try:
                return control_plane.customer_session(token)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.UNAUTHORIZED)
                return None

        def _authorized(self, token_env: str) -> bool:
            expected = os.environ.get(token_env, "")
            if not expected:
                if settings.production_mode:
                    self._send_json({"ok": False, "error": "token_required", "token_env": token_env}, HTTPStatus.UNAUTHORIZED)
                    return False
                return True
            supplied = self.headers.get("Authorization", "")
            token = supplied.removeprefix("Bearer ").strip()
            if token == expected:
                return True
            self._send_json({"ok": False, "error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return False

        def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(data, "application/json; charset=utf-8", status)

        def _send_bytes(self, data: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(int(status))
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def _send_file(self, file_path: Path) -> None:
            data = file_path.read_bytes()
            self._send_bytes(data, "application/octet-stream")

    return DeviceKitHandler


def _load_capabilities() -> dict:
    path = Path(__file__).resolve().parents[3] / "userland" / "capabilities.json"
    if not path.exists():
        return {"capabilities": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _query_value(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return str(values[0]) if values else ""


def _runtime_provider_patch(body: dict[str, Any]) -> dict[str, Any]:
    kind = str(body.get("kind") or "").strip().lower()
    if kind not in {"asr", "llm", "tts", "chain", "execution"}:
        raise ValueError("invalid_provider_kind")
    payload = {k: v for k, v in body.items() if k not in {"kind"} and v is not None}
    if "options_json" in payload:
        text = str(payload.pop("options_json") or "").strip()
        payload["options"] = json.loads(text) if text else {}
    if kind == "chain":
        return {"adapters": {"chain": payload}}
    if kind == "execution":
        return {"execution": payload}
    return {"providers": {kind: payload}}


def _apply_runtime_config(settings: RuntimeSettings, config: dict[str, Any]) -> None:
    if not config:
        return
    providers = config.get("providers") if isinstance(config.get("providers"), dict) else {}
    _apply_provider(settings, "asr", providers.get("asr") if isinstance(providers.get("asr"), dict) else {})
    _apply_provider(settings, "llm", providers.get("llm") if isinstance(providers.get("llm"), dict) else {})
    _apply_provider(settings, "tts", providers.get("tts") if isinstance(providers.get("tts"), dict) else {})
    adapters = config.get("adapters") if isinstance(config.get("adapters"), dict) else {}
    chain = adapters.get("chain") if isinstance(adapters.get("chain"), dict) else {}
    if chain:
        settings.chain_adapter = str(chain.get("provider") or chain.get("name") or settings.chain_adapter)
        settings.chain_adapter_class = str(chain.get("class") or chain.get("class_path") or settings.chain_adapter_class)
        if isinstance(chain.get("options"), dict):
            settings.chain_adapter_options = dict(chain["options"])
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    if execution:
        settings.execution_mode = str(execution.get("mode") or execution.get("provider") or settings.execution_mode)
        settings.execution_base_url = str(execution.get("base_url") or settings.execution_base_url)
        settings.execution_api_key_env = str(execution.get("api_key_env") or settings.execution_api_key_env)
        settings.execution_secret_key_env = str(execution.get("secret_key_env") or settings.execution_secret_key_env)
        settings.proxy_wallet_id_env = str(execution.get("proxy_wallet_id_env") or settings.proxy_wallet_id_env)
        settings.proxy_default_gas = str(execution.get("proxy_default_gas") or settings.proxy_default_gas)
        settings.execution_provider_class = str(execution.get("class") or execution.get("class_path") or settings.execution_provider_class)
        if isinstance(execution.get("options"), dict):
            settings.execution_options = dict(execution["options"])
    if isinstance(config.get("services"), list):
        settings.developer_services = [dict(item) for item in config["services"] if isinstance(item, dict)]


def _apply_provider(settings: RuntimeSettings, kind: str, data: dict[str, Any]) -> None:
    if not data:
        return
    prefix = f"{kind}_"
    mapping = {
        "provider": "provider",
        "base_url": "base_url",
        "model": "model",
        "api_key_env": "api_key_env",
        "class": "class",
        "class_path": "class",
        "voice": "voice",
        "format": "format",
        "language": "language",
        "sample_rate": "sample_rate",
        "timeout_sec": "timeout_sec",
    }
    for key, suffix in mapping.items():
        if key not in data:
            continue
        attr = prefix + suffix
        if hasattr(settings, attr):
            current = getattr(settings, attr)
            value = data[key]
            if isinstance(current, int):
                value = int(value)
            setattr(settings, attr, value)
    if isinstance(data.get("options"), dict):
        setattr(settings, prefix + "options", dict(data["options"]))


def _dashboard_payload(
    settings: RuntimeSettings,
    manager: RuntimeManager,
    task_manager: BackgroundTaskManager | None,
    provider_health: Callable[[], dict[str, Any]] | None,
) -> dict[str, Any]:
    providers = provider_health() if provider_health else provider_health_report(settings)
    control_plane = ControlPlaneStore(settings.control_plane_store_path).snapshot()
    active_manifest = manager.get("default").app.manifest.to_dict()
    apps = ControlPlaneStore(settings.control_plane_store_path).apps_overview(active_manifest=active_manifest)
    firmware = firmware_catalog(settings)
    developer_services = developer_service_report(settings.developer_services)
    return {
        "ok": True,
        "runtime": settings.sanitized_dict(),
        "control_plane": control_plane,
        "apps": apps,
        "providers": providers,
        "developer_services": developer_services,
        "firmware": firmware,
        "devices": {"items": manager.list_devices(), "count": len(manager.list_devices())},
        "tasks": task_manager.snapshot() if task_manager else {"items": [], "count": 0, "running_count": 0},
        "events": manager.event_log(limit=50),
        "onboarding": _onboarding_from_parts(settings, manager, control_plane, providers, developer_services, firmware),
    }


def _onboarding_payload(
    settings: RuntimeSettings,
    manager: RuntimeManager,
    provider_health: Callable[[], dict[str, Any]] | None,
) -> dict[str, Any]:
    providers = provider_health() if provider_health else provider_health_report(settings)
    control_plane = ControlPlaneStore(settings.control_plane_store_path).snapshot()
    firmware = firmware_catalog(settings)
    developer_services = developer_service_report(settings.developer_services)
    return _onboarding_from_parts(settings, manager, control_plane, providers, developer_services, firmware)


def _onboarding_from_parts(
    settings: RuntimeSettings,
    manager: RuntimeManager,
    control_plane: dict[str, Any],
    providers: dict[str, Any],
    developer_services: dict[str, Any],
    firmware: dict[str, Any],
) -> dict[str, Any]:
    projects = control_plane.get("projects") if isinstance(control_plane.get("projects"), list) else []
    customers = control_plane.get("customers") if isinstance(control_plane.get("customers"), list) else []
    devices = control_plane.get("devices") if isinstance(control_plane.get("devices"), list) else []
    purchases = control_plane.get("purchases") if isinstance(control_plane.get("purchases"), list) else []
    plans = control_plane.get("service_plans") if isinstance(control_plane.get("service_plans"), list) else []
    registered = [item for item in devices if item.get("registered_at")]
    active = [item for item in devices if item.get("status") in {"active", "online_seen"}]
    linked = [item for item in devices if item.get("customer_id")]
    online = [item for item in manager.list_devices() if (item.get("connection") or {}).get("connected")]
    steps = [
        _step("app_project", "Create an app/project", bool(projects), "Apps", "POST /admin/projects", "Create the product app record that devices and users attach to.", entry="/admin -> Apps -> Create app/project record"),
        _step("providers", "Configure providers", bool(providers.get("ok")), "Providers", "POST /admin/runtime/providers", "Set ASR, LLM, TTS, chain, and execution providers by env-key references.", entry="/admin -> Providers -> Edit provider config"),
        _step("service_plan", "Create service plan", bool(plans), "Usage", "POST /admin/service-plans", "Define the usage and entitlement model for C-end hardware users.", entry="/admin -> Usage -> Create service plan"),
        _step("device_provisioned", "Provision hardware", bool(devices), "Fleet Setup", "POST /admin/devices/register", "Create a device record and get its provisioning token plus activation code.", entry="/admin -> Fleet Setup -> Provision device"),
        _step("purchase_recorded", "Create purchase activation card", bool(purchases), "Fleet Setup", "POST /admin/purchases", "Record the hardware purchase, assign a plan, and generate the customer activation URL/card.", entry="/admin -> Fleet Setup -> Create purchase and activation card"),
        _step("device_registered", "Register device token", bool(registered), "Device firmware", "POST /device/register", "Device exchanges the one-time provisioning token for a per-device bearer token.", entry="Device firmware or mock device client"),
        _step("customer_registered", "Register one C-end user", bool(customers), "Customer Portal", "GET /customer then POST /customer/wallet/login", "Create or reuse a customer account after Solana wallet signature verification.", entry="/customer -> Connect wallet"),
        _step("user_device_bound", "Bind user to device", bool(linked), "Customer Portal", "POST /customer/activate", "Activation code links the purchased device to the logged-in user and app.", entry="/customer -> Activation code"),
        _step("device_active", "Activate device", bool(active), "Customer Portal", "POST /customer/activate", "Device is active or has been seen online after activation.", entry="/customer -> Activate device"),
        _step("live_session", "Verify live session", bool(online), "Device Detail", "POST /device/boot or WebSocket hello", "Confirm that at least one hardware unit is connected to this backend.", required=False, entry="/admin -> Device Detail or connected hardware"),
        _step("developer_services", "Configure backend services", bool((developer_services.get("items") or [])), "Services", "runtime services[]", "Register Solana RPC, payment, oracle, reward, data anchor, wallet, or custom APIs.", required=False, entry="/admin -> Services"),
        _step("firmware", "Publish firmware", bool((firmware.get("items") or [])), "Firmware", "POST /admin/ota/firmware", "Publish at least one OTA binary for pull-based updates.", required=False, entry="/admin -> Firmware -> Publish firmware"),
    ]
    required = [item for item in steps if item["required"]]
    complete_required = [item for item in required if item["done"]]
    next_required = next((item for item in required if not item["done"]), None)
    next_optional = next((item for item in steps if not item["done"]), None)
    return {
        "ok": True,
        "complete": len(complete_required) == len(required),
        "percent": int(round((len(complete_required) / max(len(required), 1)) * 100)),
        "required_done": len(complete_required),
        "required_total": len(required),
        "steps": steps,
        "next_action": next_required or next_optional or {"id": "complete", "title": "Operational loop complete", "tab": "Dashboard", "api": "", "description": "The core app/user/device loop is in place."},
        "quickstart": [
            "Create app/project in Apps",
            "Configure Providers with env var names",
            "Provision device in Fleet Setup",
            "Create purchase activation card in Fleet Setup",
            "Register device with provisioning token",
            "Open /customer, sign with wallet, and bind activation_code",
            "Inspect app users, device diagnostics, usage, events, and OTA",
        ],
    }


def _step(step_id: str, title: str, done: bool, tab: str, api: str, description: str, *, required: bool = True, entry: str = "") -> dict[str, Any]:
    return {
        "id": step_id,
        "title": title,
        "done": bool(done),
        "required": required,
        "tab": tab,
        "api": api,
        "entry": entry,
        "description": description,
    }


def _admin_page() -> str:
    return ADMIN_PAGE


def _customer_page() -> str:
    return CUSTOMER_PAGE


def _demo_purchase_body(body: dict[str, Any]) -> dict[str, Any]:
    now = int(time.time())
    app_id = str(body.get("app_id") or "ava_box").strip() or "ava_box"
    board_model = str(body.get("board_model") or body.get("model") or "esp32s3").strip() or "esp32s3"
    payload: dict[str, Any] = {
        "device_id": str(body.get("device_id") or f"{app_id}-demo-{now}"),
        "device_name": str(body.get("device_name") or f"{app_id} demo unit"),
        "board_model": board_model,
        "app_id": app_id,
        "plan_id": str(body.get("plan_id") or "plan_starter"),
        "order_ref": str(body.get("order_ref") or f"DEMO-{now}"),
        "amount_label": str(body.get("amount_label") or "Demo hardware bundle"),
        "metadata": {
            "source": "customer_demo_checkout",
            "shipping_status": "demo_not_shipped",
            "fulfillment_note": "In production, payment or fulfillment webhook should call the purchase/provision endpoint after checkout.",
        },
    }
    customer_wallet = str(body.get("customer_wallet") or "").strip()
    if customer_wallet:
        payload["customer_wallet"] = customer_wallet
    return payload

def run_http_gateway(
    host: str = "127.0.0.1",
    port: int = 8788,
    session_factory: SessionFactory | None = None,
    app_id: str = "ava_box",
    manifest_path: str | Path | None = None,
    adapter: str = "auto",
    mock: bool = False,
    skill_store_path: str | None = None,
    runtime_settings: RuntimeSettings | None = None,
) -> None:
    runtime_settings = runtime_settings or RuntimeSettings.load()
    manager = runtime_manager_for_settings(
        runtime_settings,
        app_id=app_id,
        manifest_path=manifest_path,
        adapter=adapter,
        mock=mock,
        skill_store_path=skill_store_path,
        queue_outbound=True,
    )
    factory = session_factory or (lambda: manager.get("default"))
    server = ThreadingHTTPServer((host, port), make_handler(factory, runtime_settings, manager=manager))
    print(f"Ava DeviceKit HTTP gateway listening on http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Ava DeviceKit development HTTP gateway.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--app-id", default="ava_box")
    parser.add_argument("--manifest", default=None, help="Path to a hardware app manifest JSON.")
    parser.add_argument("--adapter", default="auto", help="Chain adapter name, or 'auto' to use the manifest.")
    parser.add_argument("--skill-store", default=None, help="Path for app-layer persistent skill state.")
    parser.add_argument("--config", default=None, help="Path to DeviceKit runtime JSON config.")
    parser.add_argument("--mock", action="store_true", help="Use offline mock Solana data for local demos.")
    args = parser.parse_args()
    runtime_settings = RuntimeSettings.load(args.config)
    run_http_gateway(
        args.host,
        args.port,
        app_id=args.app_id,
        manifest_path=args.manifest,
        adapter=args.adapter,
        mock=args.mock,
        skill_store_path=args.skill_store,
        runtime_settings=runtime_settings,
    )


if __name__ == "__main__":
    main()
