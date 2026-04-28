from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ava_devicekit.services.client import invoke_developer_service
from ava_devicekit.services.registry import DeveloperService, developer_service_report, normalize_service_kind, service_kind_catalog


def test_developer_service_reports_configured_env(monkeypatch):
    monkeypatch.setenv("WALLET_KEY", "secret")
    service = DeveloperService.from_dict(
        {
            "id": "proxy_wallet",
            "kind": "custodial_wallet",
            "base_url": "https://wallet.example.com",
            "api_key_env": "WALLET_KEY",
            "capabilities": ["trade.market"],
            "options": {"api_secret": "hidden", "timeout": 5},
        }
    )

    health = service.health()

    assert health["status"] == "configured"
    assert health["options"]["api_secret"] == "<redacted>"
    assert health["options"]["timeout"] == 5


def test_developer_service_report_flags_missing_env(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)

    report = developer_service_report([{"id": "data", "kind": "market_data", "api_key_env": "MISSING_KEY"}])

    assert report["ok"] is False
    assert report["items"][0]["kind"] == "market_data_api"
    assert report["items"][0]["status"] == "missing_env"
    assert report["items"][0]["env"]["missing"] == ["MISSING_KEY"]
    assert any(item["kind"] == "device_ingest" for item in report["kind_catalog"])


def test_developer_service_kind_catalog_standardizes_solana_depin_services():
    kinds = {item["kind"] for item in service_kind_catalog()}

    assert {"solana_rpc", "solana_pay", "oracle", "reward_distributor", "data_anchor", "gasless_tx", "device_ingest"}.issubset(kinds)
    assert normalize_service_kind("solana-pay") == "solana_pay"
    assert normalize_service_kind("proxy_wallet") == "custodial_wallet"

    service = DeveloperService.from_dict({"id": "ingest", "kind": "device_ingest"})
    health = service.health()
    assert health["configured"] is True
    assert "device_ingest.heartbeat" in health["capabilities"]


def test_developer_service_invocation_requires_allowlist(tmp_path):
    service = {
        "id": "quote",
        "kind": "api",
        "base_url": "https://example.com",
        "options": {"invocable": True, "allowed_paths": ["/quote"]},
    }

    with pytest.raises(PermissionError):
        invoke_developer_service([service], "quote", {"path": "/not-allowed"})


def test_developer_service_invocation_calls_backend_allowlisted_api():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = json.loads(self.rfile.read(length).decode())
            payload = json.dumps({"seen": body, "path": self.path}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        service = {
            "id": "quote",
            "kind": "api",
            "base_url": f"http://127.0.0.1:{server.server_port}",
            "options": {"invocable": True, "allowed_paths": ["/quote"]},
        }
        result = invoke_developer_service([service], "quote", {"path": "/quote", "body": {"amount": "1"}})
        assert result["ok"] is True
        assert result["body"]["seen"]["amount"] == "1"
    finally:
        server.shutdown()
        thread.join(timeout=5)
