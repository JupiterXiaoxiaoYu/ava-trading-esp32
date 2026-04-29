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


def _post_status(base_url: str, path: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        base_url + path,
        data=json.dumps(payload or {}).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def _get(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(base_url + path, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _get_text(base_url: str, path: str) -> str:
    with urllib.request.urlopen(base_url + path, timeout=10) as resp:
        return resp.read().decode()


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


def test_http_gateway_admin_endpoints(tmp_path):
    def factory() -> DeviceSession:
        return create_device_session(mock=True)

    settings = RuntimeSettings(control_plane_store_path=str(tmp_path / "control.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(factory, settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert "core_capabilities" in _get(base_url, "/admin/capabilities")
        html = _get_text(base_url, "/admin")
        assert "Ava DeviceKit Cloud Control Plane" in html
        assert "id=\"firmware-form\"" in html
        assert "id=\"invoke-form\"" in html
        assert "id=\"onboarding-list\"" in html
        assert "data-tab=\"devices\"" in html
        assert "data-tab=\"control\"" in html
        assert "data-tab=\"apps\"" in html
        assert "data-tab=\"hardware\"" in html
        assert "data-tab=\"orders\"" in html
        assert "data-tab=\"usage\"" in html
        assert "Hardware Service Console" in html
        assert "id=\"app-map\"" in html
        assert "id=\"hardware-devices-table\"" in html
        assert "id=\"orders-purchases-table\"" in html
        assert "id=\"app-log-form\"" in html
        assert "id=\"customer-register-form\"" in html
        assert "id=\"purchase-form\"" in html
        assert "id=\"purchases-table\"" in html
        assert "id=\"app-users-table\"" in html
        assert "id=\"device-detail-form\"" in html
        assert "providers" in _get(base_url, "/admin/runtime")
        assert _get(base_url, "/admin/control-plane")["counts"]["projects"] >= 1
        assert _get(base_url, "/admin/users")["count"] >= 1
        assert _get(base_url, "/admin/projects")["count"] >= 1
        assert _get(base_url, "/admin/purchases")["count"] == 0
        assert "items" in _get(base_url, "/admin/registered-devices")
        assert _get(base_url, "/admin/providers/health")["count"] >= 3
        assert _get(base_url, "/admin/developer/services")["count"] == 0
        assert "items" in _get(base_url, "/admin/ota/firmware")
        assert _get(base_url, "/admin/tasks")["count"] == 0
        apps = _get(base_url, "/admin/apps")
        assert apps["active"]["app_id"] == "ava_box"
        assert apps["items"][0]["app_id"] == "ava_box"
        assert _get(base_url, "/admin/apps/ava_box/customers")["ok"] is True
        assert _get(base_url, "/admin/apps/ava_box/devices")["ok"] is True
        onboarding = _get(base_url, "/admin/onboarding")
        assert onboarding["ok"] is True
        assert onboarding["next_action"]["id"] == "device_provisioned"
        assert any(item["id"] == "customer_registered" for item in onboarding["steps"])
        device_step = next(item for item in onboarding["steps"] if item["id"] == "device_provisioned")
        purchase_step = next(item for item in onboarding["steps"] if item["id"] == "purchase_recorded")
        assert device_step["entry"] == "/admin -> Fleet Setup -> Provision device"
        assert device_step["api"] == "POST /admin/devices/register"
        assert purchase_step["entry"] == "/admin -> Fleet Setup -> Create purchase and activation card"
        assert purchase_step["api"] == "POST /admin/purchases"
        assert _get(base_url, "/admin/dashboard.json")["onboarding"]["required_total"] >= 1
        assert _get(base_url, "/admin/dashboard.json")["ok"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_gateway_provisions_device_by_app_id_without_project_id(tmp_path):
    settings = RuntimeSettings(control_plane_store_path=str(tmp_path / "control.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        provisioned = _post(base_url, "/admin/devices/register", {"device_id": "sensor-http-box", "app_id": "sensor_oracle"})

        assert provisioned["device"]["app_id"] == "sensor_oracle"
        assert provisioned["device"]["project_id"].startswith("prj_sensor_oracle")
        apps = _get(base_url, "/admin/apps")
        sensor = next(item for item in apps["items"] if item["app_id"] == "sensor_oracle")
        assert sensor["devices_count"] == 1
        assert sensor["project_id"] == provisioned["device"]["project_id"]
        devices = _get(base_url, "/admin/apps/sensor_oracle/devices")
        assert devices["items"][0]["device_id"] == "sensor_http_box"
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


def test_http_gateway_invokes_allowlisted_developer_service():
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            payload = json.dumps({"path": self.path}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt, *args):
            return

    service_server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    service_thread = threading.Thread(target=service_server.serve_forever, daemon=True)
    service_thread.start()
    settings = RuntimeSettings.from_dict(
        {
            "services": [
                {
                    "id": "quote",
                    "kind": "api",
                    "base_url": f"http://127.0.0.1:{service_server.server_port}",
                    "options": {"invocable": True, "allowed_paths": ["/quote"]},
                }
            ]
        }
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        body = _post(base_url, "/admin/developer/services/quote/invoke", {"path": "/quote", "body": {"symbol": "SOL"}})
        assert body["ok"] is True
        assert body["body"]["path"] == "/quote"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        service_server.shutdown()
        service_thread.join(timeout=5)


def test_http_gateway_admin_queues_ota_check(tmp_path):
    settings = RuntimeSettings(runtime_state_dir=str(tmp_path / "runtime-state"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        body = _post(base_url, "/admin/devices/device-a/ota-check", {})
        assert body["command"] == "ota_check"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_gateway_production_mode_requires_tokens(monkeypatch):
    monkeypatch.delenv("AVA_DEVICEKIT_ADMIN_TOKEN", raising=False)
    settings = RuntimeSettings(production_mode=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, body = _get_status(base_url, "/admin/runtime")
        assert status == 401
        assert body["error"] == "token_required"
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


def test_http_gateway_control_plane_registration_and_per_device_auth(tmp_path, monkeypatch):
    monkeypatch.delenv("AVA_DEVICEKIT_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("AVA_DEVICEKIT_DEVICE_TOKEN", raising=False)
    settings = RuntimeSettings(production_mode=True, control_plane_store_path=str(tmp_path / "control.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, body = _post_status(base_url, "/admin/devices/register", {"device_id": "ava-box-002", "app_id": "ava_box"})
        assert status == 401
        assert body["error"] == "token_required"

        # Production mode allows self-hosted admin access when the admin bearer env is configured.
        monkeypatch.setenv("AVA_DEVICEKIT_ADMIN_TOKEN", "admin-secret")
        status, body = _post_status(base_url, "/admin/devices/register", {"device_id": "ava-box-002", "app_id": "ava_box"}, {"Authorization": "Bearer admin-secret"})
        assert status == 200
        provisioning_token = body["provisioning_token"]

        registered = _post(base_url, "/device/register", {"provisioning_token": provisioning_token, "device_id": "ava-box-002"})
        assert registered["device_token"].startswith("avadev_")

        status, body = _get_status(base_url, "/device/state", {"X-Ava-Device-Id": "ava-box-002"})
        assert status == 401
        status, body = _get_status(base_url, "/device/state", {"X-Ava-Device-Id": "ava-box-002", "Authorization": "Bearer " + registered["device_token"]})
        assert status == 200
        assert body["screen"] == "boot"

        status, cp = _get_status(base_url, "/admin/control-plane", {"Authorization": "Bearer admin-secret"})
        assert status == 200
        assert cp["counts"]["registered_devices"] == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_gateway_runtime_provider_and_customer_device_config(tmp_path):
    settings = RuntimeSettings(control_plane_store_path=str(tmp_path / "control.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        provider = _post(base_url, "/admin/runtime/providers", {"kind": "llm", "provider": "openai-compatible", "model": "qwen-test", "base_url": "https://example.test/v1", "api_key_env": "DASHSCOPE_API_KEY"})
        assert provider["providers"]["items"][1]["model"] == "qwen-test"
        _post(
            base_url,
            "/admin/runtime/providers",
            {
                "kind": "asr",
                "provider": "qwen",
                "model": "qwen3-asr-flash-realtime",
                "base_url": "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
                "api_key_env": "DASHSCOPE_API_KEY",
                "language": "zh",
            },
        )
        runtime = _get(base_url, "/admin/runtime")
        assert runtime["providers"]["llm"]["model"] == "qwen-test"
        assert runtime["providers"]["asr"]["base_url"] == "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime"
        assert runtime["providers"]["asr"]["language"] == "zh"

        customer = _post(base_url, "/admin/customers", {"email": "u@example.com", "display_name": "U"})["customer"]
        provisioned = _post(base_url, "/admin/devices/register", {"device_id": "ava-box-ops", "customer_id": customer["customer_id"]})
        activation = _post(base_url, "/device/activate", {"activation_code": provisioned["activation_code"], "customer_id": customer["customer_id"]})
        assert activation["device"]["status"] == "active"
        config = _post(base_url, "/admin/devices/ava_box_ops/config", {"ai_name": "Ava", "wake_phrases": "hey ava,hi ava", "volume": 88})
        assert config["config"]["volume"] == 88
        assert _get(base_url, "/admin/devices/ava_box_ops/config")["config"]["wake_phrases"] == ["hey ava", "hi ava"]
        assert _get(base_url, "/admin/devices/ava_box_ops/diagnostics")["ok"] is True
        revoked = _post(base_url, "/admin/devices/ava_box_ops/status", {"status": "revoked"})
        assert revoked["device"]["status"] == "revoked"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_gateway_customer_register_binds_app_device(tmp_path):
    settings = RuntimeSettings(control_plane_store_path=str(tmp_path / "control.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        provisioned = _post(base_url, "/admin/devices/register", {"device_id": "signup-box", "app_id": "ava_box"})
        registered = _post(
            base_url,
            "/customer/register",
            {
                "email": "signup@example.com",
                "display_name": "Signup User",
                "app_id": "ava_box",
                "activation_code": provisioned["activation_code"],
            },
        )
        assert registered["customer"]["email"] == "signup@example.com"
        assert registered["device"]["status"] == "active"
        users = _get(base_url, "/admin/apps/ava_box/customers")
        assert users["count"] == 1
        assert users["items"][0]["device_count"] == 1
        devices = _get(base_url, "/admin/apps/ava_box/devices")
        assert devices["items"][0]["customer_id"] == registered["customer"]["customer_id"]
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_gateway_customer_portal_login_and_activation(tmp_path):
    settings = RuntimeSettings(control_plane_store_path=str(tmp_path / "control.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        html = _get_text(base_url, "/customer")
        assert "Activate Ava Hardware" in html
        assert "id=\"demo-purchase-form\"" in html
        assert "name=\"app_id\" id=\"purchase_app_id\" value=\"ava_box\"" in html
        assert "name=\"plan_id\" value=\"plan_starter\"" in html
        assert "name=\"board_model\" value=\"esp32s3\"" in html
        assert "<label>App id</label>" not in html
        assert "<label>Plan</label>" not in html
        assert "<label>Board model</label>" not in html
        assert "id=\"wallet-login-form\"" in html
        assert "id=\"activation-form\"" in html

        status, body = _get_status(base_url, "/customer/me")
        assert status == 401
        assert body["error"] == "customer_token_required"

        provisioned = _post(base_url, "/admin/devices/register", {"device_id": "portal-box", "app_id": "ava_box"})
        login = _post(base_url, "/customer/login", {"email": "portal@example.com", "display_name": "Portal", "app_id": "ava_box"})
        assert login["customer_token"].startswith("avacus_")
        assert "customer_token_hash" not in login["customer"]
        headers = {"Authorization": "Bearer " + login["customer_token"]}

        status, profile = _get_status(base_url, "/customer/me", headers)
        assert status == 200
        assert profile["customer"]["email"] == "portal@example.com"
        assert profile["devices"] == []

        status, activated = _post_status(base_url, "/customer/activate", {"activation_code": provisioned["activation_code"]}, headers)
        assert status == 200
        assert activated["device"]["status"] == "active"
        assert activated["devices"][0]["device_id"] == "portal_box"

        users = _get(base_url, "/admin/apps/ava_box/customers")
        assert users["count"] == 1
        assert users["items"][0]["device_count"] == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_gateway_wallet_customer_purchase_flow(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from ava_devicekit.wallet import b58encode

    private_key = Ed25519PrivateKey.generate()
    wallet = b58encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    settings = RuntimeSettings(control_plane_store_path=str(tmp_path / "control.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        html = _get_text(base_url, "/customer")
        assert "wallet-login-form" in html
        assert "/customer/wallet/challenge" in html

        purchase = _post(
            base_url,
            "/admin/purchases",
            {
                "device_id": "wallet-http-box",
                "order_ref": "ORDER-HTTP",
                "app_id": "ava_box",
                "plan_id": "plan_starter",
                "customer_wallet": wallet,
            },
        )
        assert purchase["purchase"]["customer_wallet"] == wallet
        assert purchase["activation_card"]["activation_url"].startswith(base_url + "/customer?")
        assert "qr_svg" in purchase["activation_card"]
        assert _get(base_url, "/admin/purchases")["count"] == 1
        card = _get(base_url, f"/admin/purchases/{purchase['purchase']['purchase_id']}/activation-card")
        assert card["activation_card"]["activation_code"] == purchase["activation_code"]

        challenge = _post(base_url, "/customer/wallet/challenge", {"wallet": wallet, "app_id": "ava_box"})
        signature = b58encode(private_key.sign(challenge["message"].encode("utf-8")))
        login = _post(
            base_url,
            "/customer/wallet/login",
            {"wallet": wallet, "nonce": challenge["nonce"], "signature": signature, "app_id": "ava_box"},
        )
        assert login["auth_method"] == "wallet_signature"
        headers = {"Authorization": "Bearer " + login["customer_token"]}
        status, activated = _post_status(base_url, "/customer/activate", {"activation_code": purchase["activation_code"]}, headers)
        assert status == 200
        assert activated["device"]["device_id"] == "wallet_http_box"
        assert activated["device"]["entitlement"]["status"] == "active"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_gateway_customer_demo_purchase_auto_provisions_and_activates(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from ava_devicekit.wallet import b58encode

    private_key = Ed25519PrivateKey.generate()
    wallet = b58encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    settings = RuntimeSettings(control_plane_store_path=str(tmp_path / "control.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        purchase = _post(
            base_url,
            "/customer/demo-purchase",
            {"app_id": "ava_box", "plan_id": "plan_starter", "board_model": "esp32s3", "customer_wallet": wallet},
        )
        assert purchase["purchase"]["app_id"] == "ava_box"
        assert purchase["purchase"]["customer_wallet"] == wallet
        assert purchase["purchase"]["device_id"].startswith("ava_box_demo_")
        assert "provisioning_token" not in purchase
        assert "fulfillment/device side" in purchase["factory_note"]
        assert purchase["activation_card"]["activation_url"].startswith(base_url + "/customer?")
        assert _get(base_url, "/admin/purchases")["count"] == 1
        assert _get(base_url, "/admin/apps/ava_box/devices")["count"] == 1

        challenge = _post(base_url, "/customer/wallet/challenge", {"wallet": wallet, "app_id": "ava_box"})
        signature = b58encode(private_key.sign(challenge["message"].encode("utf-8")))
        login = _post(base_url, "/customer/wallet/login", {"wallet": wallet, "nonce": challenge["nonce"], "signature": signature, "app_id": "ava_box"})
        headers = {"Authorization": "Bearer " + login["customer_token"]}
        status, activated = _post_status(base_url, "/customer/activate", {"activation_code": purchase["activation_code"]}, headers)
        assert status == 200
        assert activated["device"]["status"] == "active"
        assert activated["device"]["customer_id"] == login["customer"]["customer_id"]

        users = _get(base_url, "/admin/apps/ava_box/customers")
        assert users["count"] == 1
        orders = _get(base_url, "/admin/purchases")
        assert orders["items"][0]["status"] == "activated"
        assert orders["items"][0]["customer_id"] == login["customer"]["customer_id"]
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_http_gateway_service_plans_entitlement_and_usage(tmp_path):
    settings = RuntimeSettings(control_plane_store_path=str(tmp_path / "control.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        provisioned = _post(base_url, "/admin/devices/register", {"device_id": "usage-box"})
        registered = _post(base_url, "/device/register", {"provisioning_token": provisioned["provisioning_token"], "device_id": "usage-box"})
        plan = _post(base_url, "/admin/service-plans", {"plan_id": "plan_usage", "name": "Usage", "limits": {"api_calls": 1}})
        assert plan["service_plan"]["plan_id"] == "plan_usage"
        assigned = _post(base_url, "/admin/devices/usage_box/entitlement", {"plan_id": "plan_usage", "status": "active"})
        assert assigned["entitlement"]["plan_id"] == "plan_usage"
        first = _post(base_url, "/admin/usage", {"device_id": "usage_box", "metric": "api_calls", "amount": 1})
        assert first["limit_status"]["ok"] is True
        req = urllib.request.Request(
            base_url + "/device/usage",
            data=json.dumps({"metric": "api_calls", "amount": 1}).encode(),
            headers={"X-Ava-Device-Id": "usage_box", "Authorization": "Bearer " + registered["device_token"], "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            second = json.loads(resp.read().decode())
        assert second["limit_status"]["ok"] is False
        report = _get(base_url, "/admin/usage?device_id=usage_box")
        assert report["items"][0]["usage"]["api_calls"] == 2
    finally:
        server.shutdown()
        thread.join(timeout=5)
