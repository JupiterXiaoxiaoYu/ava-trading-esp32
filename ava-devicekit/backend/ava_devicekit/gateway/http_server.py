from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.gateway.session import DeviceSession
from ava_devicekit.ota.firmware import build_ota_response, resolve_firmware_download
from ava_devicekit.runtime.settings import RuntimeSettings

SessionFactory = Callable[[], DeviceSession]


def make_handler(session_factory: SessionFactory, runtime_settings: RuntimeSettings | None = None):
    session = session_factory()
    settings = runtime_settings or RuntimeSettings.load()

    class DeviceKitHandler(BaseHTTPRequestHandler):
        server_version = "AvaDeviceKitHTTP/0.1"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlparse(self.path).path
            if path == "/health":
                self._send_json({"ok": True, "service": "ava-devicekit"})
                return
            if path == "/manifest":
                self._send_json(session.app.manifest.to_dict())
                return
            if path == "/device/state":
                self._send_json(session.snapshot())
                return
            if path == "/device/outbox":
                self._send_json({"items": session.outbox, "count": len(session.outbox)})
                return
            if path == "/admin/capabilities":
                self._send_json(_load_capabilities())
                return
            if path == "/admin":
                self._send_bytes(_admin_page().encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/admin/runtime":
                self._send_json(settings.sanitized_dict())
                return
            if path == "/admin/apps":
                self._send_json({"active": session.app.manifest.to_dict(), "items": [session.app.manifest.to_dict()]})
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
            if path == "/device/boot":
                self._send_json(session.boot())
                return
            if path == "/device/message":
                try:
                    body = self._read_json()
                    self._send_json(session.handle(body))
                except Exception as exc:  # pragma: no cover - defensive server boundary
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
            self._send_json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)

        def log_message(self, fmt: str, *args) -> None:
            print(f"[ava-devicekit] {self.address_string()} - {fmt % args}")

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

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


def _admin_page() -> str:
    return """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ava DeviceKit Admin</title>
<style>
body{margin:0;background:#101418;color:#edf2f7;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
main{max-width:960px;margin:0 auto;padding:32px}
h1{font-size:28px;margin:0 0 8px}
p{color:#a8b3c2}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:24px 0}
a{display:block;padding:18px;border:1px solid #2d3748;border-radius:14px;color:#edf2f7;text-decoration:none;background:#151c24}
a:hover{border-color:#64d2ff}
code{color:#64d2ff}
</style>
<main>
<h1>Ava DeviceKit Admin</h1>
<p>Deployment inspection surface. Secret values are never returned by these endpoints.</p>
<div class="grid">
<a href="/admin/capabilities">Capabilities<br><code>/admin/capabilities</code></a>
<a href="/admin/runtime">Runtime<br><code>/admin/runtime</code></a>
<a href="/admin/apps">Apps<br><code>/admin/apps</code></a>
<a href="/device/state">Device State<br><code>/device/state</code></a>
</div>
</main>
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
    factory = session_factory or (
        lambda: create_device_session(
            app_id=app_id,
            manifest_path=manifest_path,
            adapter=adapter,
            mock=mock,
            skill_store_path=skill_store_path,
        )
    )
    server = ThreadingHTTPServer((host, port), make_handler(factory, runtime_settings))
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
