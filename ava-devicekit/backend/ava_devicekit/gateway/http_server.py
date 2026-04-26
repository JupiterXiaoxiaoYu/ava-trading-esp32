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

SessionFactory = Callable[[], DeviceSession]


def make_handler(session_factory: SessionFactory):
    session = session_factory()

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
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return DeviceKitHandler


def run_http_gateway(
    host: str = "127.0.0.1",
    port: int = 8788,
    session_factory: SessionFactory | None = None,
    app_id: str = "ava_box",
    manifest_path: str | Path | None = None,
    adapter: str = "auto",
    mock: bool = False,
    skill_store_path: str | None = None,
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
    server = ThreadingHTTPServer((host, port), make_handler(factory))
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
    parser.add_argument("--mock", action="store_true", help="Use offline mock Solana data for local demos.")
    args = parser.parse_args()
    run_http_gateway(
        args.host,
        args.port,
        app_id=args.app_id,
        manifest_path=args.manifest,
        adapter=args.adapter,
        mock=args.mock,
        skill_store_path=args.skill_store,
    )


if __name__ == "__main__":
    main()
