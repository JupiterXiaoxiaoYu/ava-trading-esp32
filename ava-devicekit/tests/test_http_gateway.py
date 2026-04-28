from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.gateway.http_server import make_handler
from ava_devicekit.gateway.session import DeviceSession
from ava_devicekit.runtime.settings import RuntimeSettings

def _post(base_url: str, path: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(
        base_url + path,
        data=json.dumps(payload or {}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _get(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(base_url + path, timeout=10) as resp:
        return json.loads(resp.read().decode())


def test_http_gateway_mock_flow():
    def factory() -> DeviceSession:
        return create_device_session(mock=True)

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(factory))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert _get(base_url, "/health")["ok"] is True
        assert _get(base_url, "/manifest")["app_id"] == "ava_box"
        assert _get(base_url, "/device/state")["screen"] == "boot"
        assert _post(base_url, "/device/boot")["screen"] == "feed"
        assert _get(base_url, "/device/state")["screen"] == "feed"
        assert _post(base_url, "/device/message", {"type": "key_action", "action": "watch"})["screen"] == "spotlight"
        draft = _post(base_url, "/device/message", {"type": "key_action", "action": "buy"})
        assert draft["screen"] == "confirm"
        assert draft["action_draft"]["requires_confirmation"] is True
        assert _post(base_url, "/device/message", {"type": "confirm"})["screen"] == "result"
        assert _get(base_url, "/device/outbox")["count"] >= 4
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_gateway_admin_endpoints():
    def factory() -> DeviceSession:
        return create_device_session(mock=True)

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(factory))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert "core_capabilities" in _get(base_url, "/admin/capabilities")
        assert "providers" in _get(base_url, "/admin/runtime")
        assert _get(base_url, "/admin/providers/health")["count"] >= 3
        assert _get(base_url, "/admin/developer/services")["count"] == 0
        assert "items" in _get(base_url, "/admin/ota/firmware")
        assert _get(base_url, "/admin/tasks")["count"] == 0
        assert _get(base_url, "/admin/apps")["active"]["app_id"] == "ava_box"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_gateway_reports_developer_services(monkeypatch):
    monkeypatch.setenv("MY_PROXY_KEY", "secret")
    settings = RuntimeSettings.from_dict(
        {
            "services": [
                {
                    "id": "proxy_wallet",
                    "kind": "custodial_wallet",
                    "base_url": "https://wallet.example.com",
                    "api_key_env": "MY_PROXY_KEY",
                    "capabilities": ["wallet.balance", "trade.submit"],
                }
            ]
        }
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        body = _get(base_url, "/admin/developer/services")
        assert body["ok"] is True
        assert body["items"][0]["id"] == "proxy_wallet"
        assert body["items"][0]["status"] == "configured"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _get_status(base_url: str, path: str, headers: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(base_url + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_http_gateway_admin_auth_and_multi_device(monkeypatch):
    monkeypatch.setenv("AVA_DEVICEKIT_ADMIN_TOKEN", "admin-secret")

    def factory() -> DeviceSession:
        return create_device_session(mock=True)

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(factory))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, body = _get_status(base_url, "/admin/runtime")
        assert status == 401
        assert body["error"] == "unauthorized"
        status, body = _get_status(base_url, "/admin/runtime", {"Authorization": "Bearer admin-secret"})
        assert status == 200
        assert body["admin_token_env"] == "AVA_DEVICEKIT_ADMIN_TOKEN"
        assert _post(base_url, "/device/boot", {})["screen"] == "feed"
        req = urllib.request.Request(base_url + "/device/boot", data=b"{}", headers={"X-Ava-Device-Id": "device-b", "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert json.loads(resp.read().decode())["screen"] == "feed"
        status, body = _get_status(base_url, "/admin/devices", {"Authorization": "Bearer admin-secret"})
        assert status == 200
        assert body["count"] == 2
    finally:
        server.shutdown()
        thread.join(timeout=5)
