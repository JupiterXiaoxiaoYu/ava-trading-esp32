from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.gateway.http_server import make_handler
from ava_devicekit.ota.firmware import build_ota_response
from ava_devicekit.ota.publish import firmware_catalog, publish_firmware
from ava_devicekit.ota.version import is_higher_version, scan_firmware
from ava_devicekit.runtime.settings import RuntimeSettings


def test_version_compare_and_scan_firmware(tmp_path):
    (tmp_path / "scratch-arcade_1.0.2.bin").write_bytes(b"old")
    (tmp_path / "scratch-arcade_1.2.0.bin").write_bytes(b"new")
    (tmp_path / "ignored.bin").write_bytes(b"bad")
    assert is_higher_version("1.2.0", "1.0.9") is True
    assert is_higher_version("1.0.0", "1.0.0") is False
    files = scan_firmware(tmp_path)
    assert [item.version for item in files["scratch-arcade"]] == ["1.2.0", "1.0.2"]


def test_ava_ota_response_includes_websocket_and_update(tmp_path):
    (tmp_path / "scratch-arcade_1.2.0.bin").write_bytes(b"bin")
    settings = RuntimeSettings(
        http_port=9003,
        websocket_port=9000,
        firmware_bin_dir=str(tmp_path),
        public_base_url="https://ava.example.com",
        websocket_url="wss://ava.example.com/ava/v1/",
    )
    payload = build_ota_response(
        settings=settings,
        headers={"device-model": "scratch-arcade", "device-version": "1.0.0"},
        body={},
        host_hint="127.0.0.1",
    )
    assert payload["websocket"]["url"] == "wss://ava.example.com/ava/v1/"
    assert payload["firmware"]["version"] == "1.2.0"
    assert payload["firmware"]["url"] == "https://ava.example.com/ava/ota/download/scratch-arcade_1.2.0.bin"


def test_http_gateway_serves_ava_ota_contract(tmp_path):
    (tmp_path / "scratch-arcade_1.2.0.bin").write_bytes(b"bin")
    settings = RuntimeSettings(firmware_bin_dir=str(tmp_path), websocket_url="ws://unit.test/ava/v1/")

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        req = urllib.request.Request(
            base_url + "/ava/ota/",
            data=json.dumps({"application": {"version": "1.0.0"}}).encode(),
            headers={"Content-Type": "application/json", "device-model": "scratch-arcade"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode())
        assert payload["websocket"]["url"] == "ws://unit.test/ava/v1/"
        assert payload["firmware"]["version"] == "1.2.0"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_publish_firmware_and_catalog(tmp_path):
    source = tmp_path / "build.bin"
    source.write_bytes(b"new-bin")
    settings = RuntimeSettings(firmware_bin_dir=str(tmp_path / "bin"))

    published = publish_firmware(settings, model="scratch arcade", version="1.3.0", source_path=source)
    catalog = firmware_catalog(settings)

    assert published["ok"] is True
    assert published["firmware"]["filename"] == "scratch-arcade_1.3.0.bin"
    assert catalog["count"] == 1
    assert catalog["items"][0]["version"] == "1.3.0"


def test_http_gateway_admin_ota_firmware_endpoints(tmp_path):
    source = tmp_path / "firmware.bin"
    source.write_bytes(b"bin")
    settings = RuntimeSettings(firmware_bin_dir=str(tmp_path / "bin"))

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        req = urllib.request.Request(
            base_url + "/admin/ota/firmware",
            data=json.dumps({"model": "scratch-arcade", "version": "1.4.0", "source_path": str(source)}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert json.loads(resp.read().decode())["firmware"]["filename"] == "scratch-arcade_1.4.0.bin"
        with urllib.request.urlopen(base_url + "/admin/ota/firmware", timeout=10) as resp:
            assert json.loads(resp.read().decode())["count"] == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)
