from __future__ import annotations

import json
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.gateway.http_server import make_handler
from ava_devicekit.runtime.settings import RuntimeSettings


def _request(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    data = json.dumps(payload or {}).encode() if method != "GET" else None
    req = urllib.request.Request(
        base_url + path,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        settings = RuntimeSettings(
            control_plane_store_path=str(Path(tmp) / "control_plane.json"),
            runtime_state_dir=str(Path(tmp) / "runtime_state"),
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: create_device_session(mock=True), settings))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            app = _request(base_url, "POST", "/admin/projects", {"name": "Demo Solana Device", "app_id": "ava_box", "chain": "solana"})
            provider = _request(
                base_url,
                "POST",
                "/admin/apps/ava_box/runtime/providers",
                {"kind": "llm", "provider": "openai-compatible", "model": "demo-llm", "base_url": "https://llm.example/v1", "api_key_env": "DEMO_LLM_KEY"},
            )
            service = _request(
                base_url,
                "POST",
                "/admin/apps/ava_box/developer/services",
                {"id": "solana_rpc_demo", "kind": "solana_rpc", "base_url": "https://api.mainnet-beta.solana.com", "allow_paths": ["/"], "capabilities": ["rpc"]},
            )
            plan = _request(base_url, "POST", "/admin/service-plans", {"plan_id": "plan_demo", "name": "Demo", "limits": {"api_calls": 100}})
            purchase = _request(base_url, "POST", "/admin/purchases", {"device_id": "demo-box-001", "app_id": "ava_box", "plan_id": "plan_demo", "order_ref": "DEMO-001"})
            registered = _request(base_url, "POST", "/device/register", {"device_id": "demo-box-001", "provisioning_token": purchase["provisioning_token"]})
            headers = {"X-Ava-Device-Id": "demo-box-001", "Authorization": "Bearer " + registered["device_token"]}
            boot = _request(base_url, "POST", "/device/boot", {}, headers=headers)
            action = _request(base_url, "POST", "/device/message", {"type": "key_action", "action": "watch"}, headers=headers)
            dashboard = _request(base_url, "GET", "/admin/dashboard.json")
            print(
                json.dumps(
                    {
                        "ok": True,
                        "app_id": app["project"]["app_id"],
                        "app_provider_applied": provider["applied_to_running_gateway"],
                        "app_service_count": service["count"],
                        "plan_id": plan["service_plan"]["plan_id"],
                        "activation_code": purchase["activation_code"],
                        "device_registered": bool(registered["device_token"]),
                        "boot_screen": boot["screen"],
                        "next_screen": action["screen"],
                        "onboarding_percent": dashboard["onboarding"]["percent"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
