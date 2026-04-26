from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer

from ava_devicekit.adapters.mock_solana import MockSolanaAdapter
from ava_devicekit.apps.ava_box import AvaBoxApp
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.gateway.http_server import make_handler
from ava_devicekit.gateway.session import DeviceSession

ROOT = Path(__file__).resolve().parents[1]


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
    manifest = HardwareAppManifest.load(ROOT / "apps" / "ava_box" / "manifest.json")

    def factory() -> DeviceSession:
        return DeviceSession(AvaBoxApp(manifest=manifest, chain_adapter=MockSolanaAdapter()))

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(factory))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert _get(base_url, "/health")["ok"] is True
        assert _get(base_url, "/manifest")["app_id"] == "ava_box"
        assert _post(base_url, "/device/boot")["screen"] == "feed"
        assert _post(base_url, "/device/message", {"type": "key_action", "action": "watch"})["screen"] == "spotlight"
        draft = _post(base_url, "/device/message", {"type": "key_action", "action": "buy"})
        assert draft["screen"] == "confirm"
        assert draft["action_draft"]["requires_confirmation"] is True
        assert _post(base_url, "/device/message", {"type": "confirm"})["screen"] == "result"
    finally:
        server.shutdown()
        thread.join(timeout=5)
