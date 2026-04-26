from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from ava_devicekit.adapters.mock_solana import MockSolanaAdapter
from ava_devicekit.apps.ava_box import AvaBoxApp
from ava_devicekit.gateway.session import DeviceSession

SessionFactory = Callable[[], DeviceSession]


def make_handler(session_factory: SessionFactory):
    session = session_factory()

    class DeviceKitHandler(BaseHTTPRequestHandler):
        server_version = "AvaDeviceKitHTTP/0.1"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path == "/health":
                self._send_json({"ok": True, "service": "ava-devicekit"})
                return
            if self.path == "/manifest":
                self._send_json(session.app.manifest.to_dict())
                return
            self._send_json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path == "/device/boot":
                self._send_json(session.boot())
                return
            if self.path == "/device/message":
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
    mock: bool = False,
) -> None:
    factory = session_factory or (
        lambda: DeviceSession(AvaBoxApp.create(chain_adapter=MockSolanaAdapter()))
        if mock
        else lambda: DeviceSession(AvaBoxApp.create())
    )
    server = ThreadingHTTPServer((host, port), make_handler(factory))
    print(f"Ava DeviceKit HTTP gateway listening on http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Ava DeviceKit development HTTP gateway.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--mock", action="store_true", help="Use offline mock Solana data for local demos.")
    args = parser.parse_args()
    run_http_gateway(args.host, args.port, mock=args.mock)


if __name__ == "__main__":
    main()
