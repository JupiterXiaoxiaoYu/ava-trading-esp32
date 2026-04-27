from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_loads():
    from ava_devicekit.core.manifest import HardwareAppManifest

    manifest = HardwareAppManifest.load(ROOT / "apps" / "ava_box" / "manifest.json")
    assert manifest.app_id == "ava_box"
    assert manifest.chain == "solana"
    assert "trade.market_draft" in manifest.actions


def test_demo_flow_contracts():
    import importlib.util

    spec = importlib.util.spec_from_file_location("demo_flow", ROOT / "examples" / "demo_flow.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    session = module.create_device_session(mock=True)
    feed = session.boot()
    assert feed["screen"] == "feed"
    detail = session.handle({"type": "key_action", "action": "watch"})
    assert detail["screen"] == "spotlight"
    draft = session.handle({"type": "key_action", "action": "buy"})
    assert draft["screen"] == "confirm"
    assert draft["action_draft"]["requires_confirmation"] is True
    result = session.handle({"type": "confirm"})
    assert result["screen"] == "result"


def test_clean_framework_has_no_legacy_imports():
    forbidden = ("plugins_func", "core.connection", "config.logger", "register_function")
    for path in (ROOT / "backend" / "ava_devicekit").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(name.startswith(forbidden) or name in forbidden for name in names), (path, names)


def test_json_files_parse():
    paths = (
        list((ROOT / "schemas").glob("*.json"))
        + [
            ROOT / "apps" / "ava_box" / "manifest.json",
            ROOT / "userland" / "capabilities.json",
            ROOT / "userland" / "runtime.example.json",
            ROOT / "userland" / "app" / "manifest.template.json",
        ]
    )
    for path in paths:
        json.loads(path.read_text(encoding="utf-8"))


def test_userland_capability_map_declares_extension_points():
    data = json.loads((ROOT / "userland" / "capabilities.json").read_text(encoding="utf-8"))
    extension_ids = {item["id"] for item in data["extension_points"]}
    assert {"hardware_app", "chain_adapter", "market_stream_adapter", "model_providers", "hardware_port", "ui_screens"} <= extension_ids


def test_device_message_preserves_selection_context():
    from ava_devicekit.core.types import DeviceMessage

    msg = DeviceMessage.from_dict(
        {
            "type": "listen_detect",
            "text": "buy",
            "context": {
                "screen": "spotlight",
                "selected": {
                    "token_id": "So11111111111111111111111111111111111111112-solana",
                    "addr": "So11111111111111111111111111111111111111112",
                    "chain": "solana",
                    "symbol": "SOL",
                    "cursor": 2,
                },
            },
        }
    )
    assert msg.context is not None
    assert msg.context.selected is not None
    assert msg.context.screen == "spotlight"
    assert msg.context.selected.symbol == "SOL"
    assert "context" not in msg.payload


def test_device_message_flattens_payload_object():
    from ava_devicekit.core.types import DeviceMessage

    msg = DeviceMessage.from_dict({"type": "key_action", "action": "buy", "payload": {"amount_sol": "0.1"}})
    assert msg.payload == {"amount_sol": "0.1"}
