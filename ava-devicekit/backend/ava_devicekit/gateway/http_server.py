from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from ava_devicekit.control_plane import ControlPlaneStore
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
                self._send_json({"active": active, "items": [active]})
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
            if path == "/admin/projects":
                if not self._authorized_admin():
                    return
                try:
                    self._send_json(control_plane.create_project(self._read_json()))
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
    return {
        "ok": True,
        "runtime": settings.sanitized_dict(),
        "control_plane": control_plane,
        "providers": providers,
        "developer_services": developer_service_report(settings.developer_services),
        "firmware": firmware_catalog(settings),
        "devices": {"items": manager.list_devices(), "count": len(manager.list_devices())},
        "tasks": task_manager.snapshot() if task_manager else {"items": [], "count": 0, "running_count": 0},
        "events": manager.event_log(limit=50),
    }


def _admin_page() -> str:
    return """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ava DeviceKit Cloud</title>
<style>
:root{
  --ink:#1f241b;--muted:#68715f;--paper:#f3ead7;--panel:#fff9eb;--line:#d6c7aa;
  --coal:#263022;--moss:#587247;--amber:#c97923;--red:#b84a33;--blue:#386f86;
  --shadow:0 22px 70px rgba(63,49,25,.14);--radius:22px;
}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:var(--ink);background:
  radial-gradient(circle at 18% 8%,rgba(201,121,35,.20),transparent 28rem),
  linear-gradient(115deg,#f7efd8 0%,#efe1c2 42%,#e7d2aa 100%);
  font-family:"Aptos","IBM Plex Sans","Segoe UI",sans-serif;min-height:100vh}
body:before{content:"";position:fixed;inset:0;pointer-events:none;background-image:linear-gradient(rgba(38,48,34,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(38,48,34,.035) 1px,transparent 1px);background-size:32px 32px;mask-image:linear-gradient(to bottom,#000,transparent 88%)}
button,input,textarea,select{font:inherit}button{cursor:pointer}.shell{width:min(1440px,calc(100% - 32px));margin:0 auto;padding:28px 0 56px}.hero{display:grid;grid-template-columns:1.15fr .85fr;gap:22px;align-items:stretch;margin-bottom:22px}.title{background:var(--coal);color:#fbf1d7;border-radius:32px;padding:32px;box-shadow:var(--shadow);position:relative;overflow:hidden}.title:after{content:"";position:absolute;right:-70px;top:-100px;width:260px;height:260px;border:42px solid rgba(201,121,35,.34);border-radius:50%}.eyebrow{letter-spacing:.14em;text-transform:uppercase;color:#e6b15f;font-size:12px;font-weight:800}.title h1{font-family:Georgia,"Times New Roman",serif;font-size:clamp(38px,6vw,86px);line-height:.88;margin:12px 0 18px;max-width:780px;font-weight:900}.title p{font-size:clamp(15px,1.7vw,20px);color:#e3d7b8;max-width:720px;margin:0}.status-strip{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.metric{background:rgba(255,249,235,.82);border:1px solid rgba(90,71,34,.20);border-radius:26px;padding:20px;box-shadow:var(--shadow);backdrop-filter:blur(10px)}.metric b{display:block;font-size:clamp(30px,4vw,54px);line-height:1;font-family:Georgia,"Times New Roman",serif}.metric span{display:block;color:var(--muted);margin-top:8px;font-weight:700}.toolbar{position:sticky;top:0;z-index:10;display:flex;gap:10px;align-items:center;padding:12px;margin:0 -8px 18px;background:rgba(239,225,194,.82);backdrop-filter:blur(16px);border-bottom:1px solid rgba(90,71,34,.18)}.tab{border:1px solid var(--line);background:var(--panel);color:var(--coal);border-radius:999px;padding:10px 14px;font-weight:800}.tab.active{background:var(--coal);color:#fbf1d7}.spacer{flex:1}.token{min-width:220px;border:1px solid var(--line);border-radius:999px;padding:10px 14px;background:#fff7e4}.btn{border:0;border-radius:999px;padding:11px 15px;background:var(--coal);color:#fff3d8;font-weight:900}.btn.alt{background:transparent;color:var(--coal);border:1px solid var(--line)}.btn.warn{background:var(--amber);color:#1d160b}.btn.danger{background:var(--red);color:#fff}.panel{display:none;animation:rise .32s cubic-bezier(.19,1,.22,1)}.panel.active{display:block}@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}.card{grid-column:span 6;background:var(--panel);border:1px solid rgba(90,71,34,.20);border-radius:var(--radius);box-shadow:var(--shadow);padding:20px}.card.wide{grid-column:span 12}.card.third{grid-column:span 4}.card h2,.card h3{margin:0 0 14px;font-family:Georgia,"Times New Roman",serif}.card h2{font-size:30px}.card h3{font-size:22px}.sub{color:var(--muted);font-weight:700}table{width:100%;border-collapse:collapse}th{text-align:left;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid var(--line);padding:9px 8px}td{border-bottom:1px solid rgba(90,71,34,.14);padding:11px 8px;vertical-align:top}tr:hover td{background:rgba(201,121,35,.07)}.pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:5px 9px;font-size:12px;font-weight:900;background:#eadfc4;color:var(--coal)}.pill.ok{background:#d9e8c8;color:#31501f}.pill.bad{background:#f0c7b8;color:#7d2818}.pill.info{background:#cce1e8;color:#214d5d}.mono{font-family:"Cascadia Mono","SFMono-Regular",monospace;font-size:12px}.stack{display:flex;flex-wrap:wrap;gap:8px}.form{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;align-items:end}.field label{display:block;color:var(--muted);font-size:12px;text-transform:uppercase;font-weight:900;margin:0 0 6px}.field input,.field textarea,.field select{width:100%;border:1px solid var(--line);border-radius:14px;padding:11px;background:#fffaf0;color:var(--ink)}textarea{min-height:110px;resize:vertical}.log{max-height:520px;overflow:auto;background:#1f241b;color:#f6e9c9;border-radius:20px;padding:16px}.event{display:grid;grid-template-columns:150px 170px 1fr;gap:12px;padding:10px;border-bottom:1px solid rgba(246,233,201,.14)}.raw{white-space:pre-wrap;overflow:auto;max-height:560px;background:#1f241b;color:#f6e9c9;border-radius:20px;padding:18px}.empty{border:1px dashed var(--line);border-radius:18px;padding:22px;color:var(--muted);background:rgba(255,249,235,.58)}.toast{position:fixed;right:20px;bottom:20px;z-index:30;background:var(--coal);color:#fff1d4;border-radius:18px;padding:14px 16px;box-shadow:var(--shadow);max-width:420px;display:none}.toast.show{display:block;animation:rise .2s ease-out}@media(max-width:900px){.hero{grid-template-columns:1fr}.status-strip{grid-template-columns:repeat(2,1fr)}.toolbar{overflow:auto}.card,.card.third{grid-column:span 12}.form{grid-template-columns:1fr}.event{grid-template-columns:1fr}.token{min-width:180px}.title{border-radius:24px;padding:24px}}
</style>
<main class="shell">
  <section class="hero">
    <div class="title">
      <div class="eyebrow">Ava DeviceKit Cloud Control Plane</div>
      <h1>AI hardware fleet command.</h1>
      <p>Manage ESP32 AI devices, model providers, OTA firmware, backend services, and runtime events from one lightweight gateway.</p>
    </div>
    <div class="status-strip">
      <div class="metric"><b id="m-devices">-</b><span>devices</span></div>
      <div class="metric"><b id="m-online">-</b><span>online</span></div>
      <div class="metric"><b id="m-firmware">-</b><span>firmware builds</span></div>
      <div class="metric"><b id="m-providers">-</b><span>providers ok</span></div>
    </div>
  </section>
  <nav class="toolbar" aria-label="Admin sections">
    <button class="tab active" data-tab="overview">Overview</button><button class="tab" data-tab="control">Control Plane</button><button class="tab" data-tab="customers">Customers</button><button class="tab" data-tab="devices">Runtime Devices</button><button class="tab" data-tab="firmware">Firmware</button><button class="tab" data-tab="providers">Providers</button><button class="tab" data-tab="services">Services</button><button class="tab" data-tab="events">Events</button><button class="tab" data-tab="raw">Raw</button>
    <span class="spacer"></span><input id="admin-token" class="token" placeholder="Admin bearer token"><button class="btn alt" id="save-token">Save token</button><button class="btn" id="refresh">Refresh</button>
  </nav>
  <section id="overview" class="panel active"><div class="grid"><div class="card wide"><h2>Runtime posture</h2><div id="overview-body" class="stack"></div></div><div class="card"><h3>Recent events</h3><div id="overview-events" class="log"></div></div><div class="card"><h3>Quick actions</h3><div class="stack"><a class="btn alt" href="/admin/runtime">Runtime JSON</a><a class="btn alt" href="/admin/capabilities">Capabilities</a><a class="btn alt" href="/manifest">Manifest</a></div><p class="sub">Use the tabs for device OTA checks, firmware publishing, service invoke tests, and event filtering.</p></div></div></section>
  <section id="control" class="panel"><div class="grid"><div class="card wide"><h2>Users, projects, provisioned devices</h2><p class="sub">Self-hosted registry for operators, projects, customers, per-device credentials, and C-end device configuration.</p><div id="control-summary" class="stack"></div></div><div class="card"><h3>Create user</h3><form id="user-form" class="form"><div class="field"><label>Username</label><input name="username" placeholder="alice" required></div><div class="field"><label>Display name</label><input name="display_name" placeholder="Alice"></div><div class="field"><label>Role</label><select name="role"><option>developer</option><option>operator</option><option>viewer</option><option>admin</option></select></div><button class="btn" type="submit">Create</button></form></div><div class="card"><h3>Create project</h3><form id="project-form" class="form"><div class="field"><label>Name</label><input name="name" placeholder="Solana device app" required></div><div class="field"><label>Chain</label><input name="chain" value="solana"></div><div class="field"><label>Owner user id</label><input name="owner_user_id" placeholder="usr_default_admin"></div><button class="btn" type="submit">Create</button></form></div><div class="card wide"><h3>Provision device</h3><form id="device-form" class="form"><div class="field"><label>Device id</label><input name="device_id" placeholder="ava-box-001" required></div><div class="field"><label>Name</label><input name="name" placeholder="Ava Box 001"></div><div class="field"><label>Project id</label><input name="project_id" placeholder="prj_default_solana"></div><div class="field"><label>Board model</label><input name="board_model" placeholder="esp32s3"></div><div class="field"><label>App id</label><input name="app_id" value="ava_box"></div><button class="btn warn" type="submit">Provision</button></form><pre id="provision-result" class="raw">Provisioning and activation codes are shown once here.</pre></div><div class="card wide"><h3>Device config</h3><form id="device-config-form" class="form"><div class="field"><label>Device id</label><input name="device_id" placeholder="ava_box_001" required></div><div class="field"><label>AI name</label><input name="ai_name" placeholder="Ava"></div><div class="field"><label>Language</label><input name="language" placeholder="zh"></div><div class="field"><label>Wake phrases</label><input name="wake_phrases" placeholder="hey ava,hi ava,你好ava"></div><div class="field"><label>Voice</label><input name="tts_voice" placeholder="longanyang"></div><div class="field"><label>Volume</label><input name="volume" type="number" min="0" max="100" placeholder="100"></div><div class="field"><label>App id</label><input name="app_id" placeholder="ava_box"></div><div class="field"><label>Firmware channel</label><input name="firmware_channel" placeholder="stable"></div><div class="field"><label>Wallet mode</label><select name="wallet_mode"><option value="">keep</option><option>proxy</option><option>external</option><option>paper</option></select></div><div class="field"><label>Risk mode</label><select name="risk_mode"><option value="">keep</option><option>confirm_all</option><option>confirm_risky</option><option>read_only</option></select></div><button class="btn" type="submit">Save config</button><button class="btn alt" type="button" id="load-device-config">Load config</button></form><pre id="device-config-result" class="raw">Device config appears here.</pre></div><div class="card wide"><h3>Registered devices</h3><div id="registered-devices-table"></div></div></div></section>
  <section id="customers" class="panel"><div class="grid"><div class="card"><h2>Create customer</h2><form id="customer-form" class="form"><div class="field"><label>Email</label><input name="email" placeholder="user@example.com"></div><div class="field"><label>Name</label><input name="display_name" placeholder="Ava user"></div><div class="field"><label>Wallet</label><input name="wallet" placeholder="optional Solana wallet"></div><button class="btn" type="submit">Create</button></form></div><div class="card"><h2>Activate device</h2><form id="activation-form" class="form"><div class="field"><label>Activation code</label><input name="activation_code" placeholder="AVA-XXXX-XXXX" required></div><div class="field"><label>Customer id</label><input name="customer_id" placeholder="optional existing customer"></div><div class="field"><label>Email</label><input name="email" placeholder="new customer email"></div><button class="btn warn" type="submit">Activate</button></form><pre id="activation-result" class="raw">Activation result appears here.</pre></div><div class="card wide"><h2>Customers</h2><div id="customers-table"></div></div></div></section>
  <section id="devices" class="panel"><div class="card wide"><h2>Devices</h2><div id="devices-table"></div></div></section>
  <section id="firmware" class="panel"><div class="grid"><div class="card"><h2>Publish firmware</h2><form id="firmware-form" class="form"><div class="field"><label>Model</label><input name="model" placeholder="scratch-arcade" required></div><div class="field"><label>Version</label><input name="version" placeholder="1.4.0" required></div><div class="field" style="grid-column:span 2"><label>Server source path</label><input name="source_path" placeholder="/path/to/build.bin" required></div><button class="btn warn" type="submit">Publish</button></form><p class="sub">This copies an existing server-side .bin into the configured OTA directory.</p></div><div class="card"><h2>Firmware catalog</h2><div id="firmware-table"></div></div></div></section>
  <section id="providers" class="panel"><div class="grid"><div class="card wide"><h2>AI and chain providers</h2><div id="providers-table"></div></div><div class="card wide"><h3>Edit provider config</h3><form id="provider-form" class="form"><div class="field"><label>Kind</label><select name="kind"><option>asr</option><option>llm</option><option>tts</option><option>chain</option><option>execution</option></select></div><div class="field"><label>Provider / mode</label><input name="provider" placeholder="qwen / openai-compatible / solana / custodial"></div><div class="field"><label>Model</label><input name="model" placeholder="qwen3.5-flash"></div><div class="field"><label>Base URL</label><input name="base_url" placeholder="https://..."></div><div class="field"><label>API key env</label><input name="api_key_env" placeholder="DASHSCOPE_API_KEY"></div><div class="field"><label>Secret env</label><input name="secret_key_env" placeholder="AVE_SECRET_KEY"></div><div class="field"><label>Class path</label><input name="class" placeholder="my_pkg.Provider"></div><div class="field"><label>Voice</label><input name="voice" placeholder="longanyang"></div><div class="field"><label>Language</label><input name="language" placeholder="zh"></div><div class="field"><label>Format</label><input name="format" placeholder="opus"></div><div class="field" style="grid-column:span 4"><label>Options JSON</label><textarea name="options_json" placeholder='{\"temperature\":0.7}'></textarea></div><button class="btn warn" type="submit">Save provider</button><button class="btn alt" type="button" id="load-provider">Load selected</button></form><pre id="provider-result" class="raw">Provider config changes apply immediately to this running gateway and persist in the control-plane store.</pre></div></div></section>
  <section id="services" class="panel"><div class="grid"><div class="card wide"><h2>Developer services</h2><div id="services-table"></div></div><div class="card wide"><h3>Allowlisted invoke test</h3><form id="invoke-form" class="form"><div class="field"><label>Service id</label><input name="service_id" placeholder="quote_api" required></div><div class="field"><label>Path</label><input name="path" placeholder="/quote" required></div><div class="field"><label>Method</label><select name="method"><option>POST</option><option>GET</option></select></div><div class="field"><label>Body JSON</label><textarea name="body" placeholder='{"symbol":"SOL"}'></textarea></div><button class="btn" type="submit">Invoke</button></form><pre id="invoke-result" class="raw">No invocation yet.</pre></div></div></section>
  <section id="events" class="panel"><div class="card wide"><h2>Events</h2><form id="events-form" class="form"><div class="field"><label>Device id</label><input name="device_id" placeholder="default"></div><div class="field"><label>Event type</label><input name="event" placeholder="runtime.error"></div><div class="field"><label>Limit</label><input name="limit" value="100"></div><button class="btn" type="submit">Filter</button></form><div id="events-log" class="log"></div></div></section>
  <section id="raw" class="panel"><div class="card wide"><h2>Dashboard payload</h2><pre id="raw-json" class="raw">loading...</pre></div></section>
</main><div id="toast" class="toast"></div>
<script>
const state={dashboard:null};
const $=(s,r=document)=>r.querySelector(s); const $$=(s,r=document)=>Array.from(r.querySelectorAll(s));
function token(){return localStorage.getItem('ava_admin_token')||''} function headers(extra={}){const h={...extra}; if(token()) h.Authorization='Bearer '+token(); return h}
function toast(msg){const el=$('#toast'); el.textContent=msg; el.classList.add('show'); setTimeout(()=>el.classList.remove('show'),3600)}
async function api(path, opts={}){const res=await fetch(path,{...opts,headers:headers(opts.headers||{})}); const text=await res.text(); let body; try{body=JSON.parse(text)}catch{body={ok:false,error:text||res.statusText}} if(!res.ok) throw new Error(body.error||res.statusText); return body}
function pill(ok,text){return `<span class="pill ${ok?'ok':'bad'}">${escapeHtml(text)}</span>`} function info(text){return `<span class="pill info">${escapeHtml(text)}</span>`}
function escapeHtml(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function table(cols, rows, empty='No data yet.'){if(!rows||!rows.length)return `<div class="empty">${empty}</div>`;return `<table><thead><tr>${cols.map(c=>`<th>${escapeHtml(c.label)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${cols.map(c=>`<td>${c.render?c.render(row):escapeHtml(row[c.key])}</td>`).join('')}</tr>`).join('')}</tbody></table>`}
function render(){const d=state.dashboard;if(!d)return; const devices=d.devices?.items||[], fw=d.firmware?.items||[], providers=d.providers?.items||[], services=d.developer_services?.items||[], events=d.events?.items||[], cp=d.control_plane||{}, customers=cp.customers||[]; const online=devices.filter(x=>x.connection&&x.connection.connected).length; $('#m-devices').textContent=cp.counts?.provisioned_devices??devices.length; $('#m-online').textContent=online; $('#m-firmware').textContent=fw.length; $('#m-providers').textContent=d.providers?.ok?'yes':'check'; $('#raw-json').textContent=JSON.stringify(d,null,2);
 $('#overview-body').innerHTML=[pill(d.providers?.ok,'providers '+(d.providers?.ok?'healthy':'need config')),pill(d.developer_services?.ok,'services '+(d.developer_services?.ok?'ready':'need env')),info('customers '+(cp.counts?.customers??0)),info('users '+(cp.counts?.users??0)),info('projects '+(cp.counts?.projects??0)),info('runtime '+(d.runtime?.production_mode?'production':'development')),info('ws '+(d.runtime?.websocket_port||'-')),info('http '+(d.runtime?.http_port||'-'))].join(' ');
 $('#control-summary').innerHTML=[info('users '+(cp.counts?.users??0)),info('customers '+(cp.counts?.customers??0)),info('projects '+(cp.counts?.projects??0)),info('provisioned '+(cp.counts?.provisioned_devices??0)),info('registered '+(cp.counts?.registered_devices??0)),info('active '+(cp.counts?.active_devices??0))].join(' ');
 $('#overview-events').innerHTML=renderEvents(events.slice(-8)); $('#events-log').innerHTML=renderEvents(events);
 $('#customers-table').innerHTML=table([{label:'Customer',render:r=>`<span class="mono">${escapeHtml(r.customer_id)}</span>`},{label:'Name',key:'display_name'},{label:'Email',key:'email'},{label:'Wallet',render:r=>`<span class="mono">${escapeHtml(r.wallet||'-')}</span>`},{label:'Status',render:r=>info(r.status||'-')}],customers,'No customers yet.');
 $('#registered-devices-table').innerHTML=table([{label:'Device',render:r=>`<span class="mono">${escapeHtml(r.device_id)}</span>`},{label:'Customer',render:r=>`<span class="mono">${escapeHtml(r.customer_id||'-')}</span>`},{label:'Project',render:r=>`<span class="mono">${escapeHtml(r.project_id)}</span>`},{label:'Board',key:'board_model'},{label:'App',key:'app_id'},{label:'Status',render:r=>info(r.status||'-')},{label:'Action',render:r=>`<button class="btn alt" onclick="rotateProvision('${escapeHtml(r.device_id)}')">New token</button> <button class="btn alt" onclick="loadDeviceConfig('${escapeHtml(r.device_id)}')">Config</button> <button class="btn alt" onclick="diagnoseDevice('${escapeHtml(r.device_id)}')">Diagnose</button> <button class="btn danger" onclick="setDeviceStatus('${escapeHtml(r.device_id)}','revoked')">Revoke</button>`}],cp.devices||[],'No provisioned devices yet.');
 $('#devices-table').innerHTML=table([{label:'Device',render:r=>`<span class="mono">${escapeHtml(r.device_id)}</span>`},{label:'Status',render:r=>pill(!!(r.connection&&r.connection.connected),r.connection&&r.connection.connected?'online':'offline')},{label:'App',render:r=>escapeHtml(r.app_name||r.app_id||'-')},{label:'Screen',render:r=>info(r.screen||'-')},{label:'Last seen',render:r=>escapeHtml(r.connection?.last_seen?new Date(r.connection.last_seen*1000).toLocaleString():'-')},{label:'Action',render:r=>`<button class="btn warn" onclick="otaCheck('${escapeHtml(r.device_id)}')">OTA check</button> <button class="btn alt" onclick="viewDevice('${escapeHtml(r.device_id)}')">State</button>`}],devices,'No devices have connected yet.');
 $('#firmware-table').innerHTML=table([{label:'Model',key:'model'},{label:'Version',render:r=>info(r.version)},{label:'File',render:r=>`<span class="mono">${escapeHtml(r.filename)}</span>`},{label:'Size',render:r=>escapeHtml(r.size||0)}],fw,'No firmware binaries published.');
 $('#providers-table').innerHTML=table([{label:'Kind',key:'kind'},{label:'Provider',key:'provider'},{label:'Status',render:r=>pill(r.configured,r.status)},{label:'Model',key:'model'},{label:'Env',render:r=>`<span class="mono">${escapeHtml(r.api_key_env||'-')}</span>`}],providers,'No providers reported.');
 $('#services-table').innerHTML=table([{label:'Service',key:'id'},{label:'Kind',key:'kind'},{label:'Status',render:r=>pill(r.configured,r.status)},{label:'Base URL',render:r=>`<span class="mono">${escapeHtml(r.base_url||'-')}</span>`},{label:'Capabilities',render:r=>(r.capabilities||[]).map(info).join(' ')}],services,'No developer services configured.');}
function renderEvents(events){if(!events||!events.length)return '<div class="empty">No events yet.</div>';return events.map(e=>`<div class="event"><div>${new Date((e.ts||0)*1000).toLocaleTimeString()}</div><div><span class="mono">${escapeHtml(e.event)}</span><br><span class="sub">${escapeHtml(e.device_id)}</span></div><div class="mono">${escapeHtml(JSON.stringify(e.payload||{}))}</div></div>`).join('')}
async function refresh(){try{state.dashboard=await api('/admin/dashboard.json'); render(); toast('Dashboard refreshed')}catch(e){toast('Refresh failed: '+e.message)}}
async function otaCheck(id){try{await api(`/admin/devices/${encodeURIComponent(id)}/ota-check`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}); toast('OTA check queued for '+id); await refresh()}catch(e){toast('OTA check failed: '+e.message)}}
async function rotateProvision(id){try{const result=await api(`/admin/devices/${encodeURIComponent(id)}/provision-token`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});$('#provision-result').textContent=JSON.stringify(result,null,2);toast('Provisioning token rotated');await refresh()}catch(e){toast('Token rotation failed: '+e.message)}}
async function viewDevice(id){try{const body=await api(`/admin/devices/${encodeURIComponent(id)}/state`); $('#raw-json').textContent=JSON.stringify(body,null,2); activate('raw')}catch(e){toast('State failed: '+e.message)}}
async function diagnoseDevice(id){try{const body=await api(`/admin/devices/${encodeURIComponent(id)}/diagnostics`); $('#raw-json').textContent=JSON.stringify(body,null,2); activate('raw')}catch(e){toast('Diagnostics failed: '+e.message)}}
async function setDeviceStatus(id,status){try{await api(`/admin/devices/${encodeURIComponent(id)}/status`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})}); toast('Device '+id+' set to '+status); await refresh()}catch(e){toast('Status update failed: '+e.message)}}
async function loadDeviceConfig(id){try{const body=await api(`/admin/devices/${encodeURIComponent(id)}/config`); const form=$('#device-config-form'); form.device_id.value=id; Object.entries(body.config||{}).forEach(([k,v])=>{if(form[k]) form[k].value=Array.isArray(v)?v.join(','):v}); $('#device-config-result').textContent=JSON.stringify(body,null,2); activate('control')}catch(e){toast('Load config failed: '+e.message)}}
function activate(id){$$('.tab').forEach(x=>x.classList.toggle('active',x.dataset.tab===id)); $$('.panel').forEach(x=>x.classList.toggle('active',x.id===id))}
$$('.tab').forEach(btn=>btn.addEventListener('click',()=>activate(btn.dataset.tab))); $('#refresh').addEventListener('click',refresh); $('#admin-token').value=token(); $('#save-token').addEventListener('click',()=>{localStorage.setItem('ava_admin_token',$('#admin-token').value.trim());toast('Token saved locally');refresh()});
$('#firmware-form').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);try{await api('/admin/ota/firmware',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(fd))});toast('Firmware published');e.target.reset();await refresh()}catch(err){toast('Publish failed: '+err.message)}});
$('#user-form').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);try{await api('/admin/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(fd))});toast('User created');e.target.reset();await refresh()}catch(err){toast('Create user failed: '+err.message)}});
$('#customer-form').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);try{await api('/admin/customers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(fd))});toast('Customer created');e.target.reset();await refresh()}catch(err){toast('Create customer failed: '+err.message)}});
$('#activation-form').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);const body={activation_code:fd.get('activation_code'),customer_id:fd.get('customer_id')||'',customer:{email:fd.get('email')||''}};try{const result=await api('/device/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});$('#activation-result').textContent=JSON.stringify(result,null,2);toast('Device activated');e.target.reset();await refresh()}catch(err){toast('Activation failed: '+err.message)}});
$('#project-form').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);try{await api('/admin/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(fd))});toast('Project created');e.target.reset();await refresh()}catch(err){toast('Create project failed: '+err.message)}});
$('#device-form').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);const body=Object.fromEntries(fd);Object.keys(body).forEach(k=>{if(body[k]==='')delete body[k]});try{const result=await api('/admin/devices/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});$('#provision-result').textContent=JSON.stringify(result,null,2);toast('Device provisioned');await refresh()}catch(err){toast('Provision failed: '+err.message)}});
$('#device-config-form').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);const id=fd.get('device_id');const body=Object.fromEntries(fd);delete body.device_id;Object.keys(body).forEach(k=>{if(body[k]==='')delete body[k]});try{const result=await api(`/admin/devices/${encodeURIComponent(id)}/config`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});$('#device-config-result').textContent=JSON.stringify(result,null,2);toast('Device config saved');await refresh()}catch(err){toast('Config save failed: '+err.message)}});
$('#load-device-config').addEventListener('click',()=>{const id=$('#device-config-form').device_id.value.trim(); if(id) loadDeviceConfig(id)});
$('#provider-form').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);const body=Object.fromEntries(fd);Object.keys(body).forEach(k=>{if(body[k]==='')delete body[k]});try{const result=await api('/admin/runtime/providers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});$('#provider-result').textContent=JSON.stringify(result,null,2);toast('Provider saved and applied');await refresh()}catch(err){toast('Provider save failed: '+err.message)}});
$('#load-provider').addEventListener('click',()=>{const form=$('#provider-form'), el=n=>form.elements.namedItem(n);const kind=el('kind').value;const runtime=state.dashboard?.runtime||{};let block={}; if(kind==='chain') block=runtime.adapters?.chain||{}; else if(kind==='execution') block=runtime.execution||{}; else block=runtime.providers?.[kind]||{}; el('provider').value=block.provider||block.mode||''; el('model').value=block.model||''; el('base_url').value=block.base_url||''; el('api_key_env').value=block.api_key_env||''; el('secret_key_env').value=block.secret_key_env||''; el('class').value=block.class||''; el('voice').value=block.voice||''; el('language').value=block.language||''; el('format').value=block.format||''; el('options_json').value=JSON.stringify(block.options||{},null,2);});
$('#invoke-form').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);let body={};try{body=fd.get('body')?JSON.parse(fd.get('body')):{}}catch(err){toast('Body JSON invalid');return}try{const result=await api(`/admin/developer/services/${encodeURIComponent(fd.get('service_id'))}/invoke`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:fd.get('path'),method:fd.get('method'),body})});$('#invoke-result').textContent=JSON.stringify(result,null,2);toast('Service invoked')}catch(err){$('#invoke-result').textContent=err.message;toast('Invoke failed: '+err.message)}});
$('#events-form').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);const qs=new URLSearchParams();['device_id','event','limit'].forEach(k=>{if(fd.get(k))qs.set(k,fd.get(k))});try{$('#events-log').innerHTML=renderEvents((await api('/admin/events?'+qs)).items||[])}catch(err){toast('Event filter failed: '+err.message)}});
refresh();
</script>
"""


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
