from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.gateway.http_server import make_handler
from ava_devicekit.gateway.session import DeviceSession

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
        assert _get(base_url, "/admin/apps")["active"]["app_id"] == "ava_box"
    finally:
        server.shutdown()
        thread.join(timeout=5)
