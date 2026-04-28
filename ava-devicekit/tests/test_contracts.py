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


def test_demo_flow_contracts(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("demo_flow", ROOT / "examples" / "demo_flow.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    session = module.create_device_session(mock=True, skill_store_path=str(tmp_path / "skills.json"))
    feed = session.boot()
    assert feed["screen"] == "feed"
    detail = session.handle({"type": "key_action", "action": "watch"})
    assert detail["screen"] == "spotlight"
    draft = session.handle({"type": "key_action", "action": "buy"})
    assert draft["screen"] == "confirm"
    assert draft["action_draft"]["requires_confirmation"] is True
    result = session.handle({"type": "confirm"})
    assert result["screen"] == "result"
    assert result["data"]["success"] is True
    assert result["data"]["ok"] is True
    assert result["data"]["subtitle"]


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


def test_solana_depin_contract_schemas_have_required_fields():
    schemas = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in (ROOT / "schemas").glob("*.schema.json")
    }
    assert {"device_identity.schema.json", "device_telemetry.schema.json", "developer_service.schema.json", "transport_profile.schema.json"} <= set(schemas)
    assert {"device_id", "device_public_key", "challenge", "signature"} <= set(schemas["device_identity.schema.json"]["properties"])
    assert {"readings", "transport", "signature"} <= set(schemas["device_telemetry.schema.json"]["properties"])
    assert {"id", "kind", "options"} <= set(schemas["developer_service.schema.json"]["properties"])
    assert "allowed_paths" in schemas["developer_service.schema.json"]["properties"]["options"]["properties"]
    assert {"heartbeat_interval_ms", "reconnect_interval_ms", "http_fallback"} <= set(schemas["transport_profile.schema.json"]["properties"])


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


def test_generic_contracts_parse_context_and_input_events():
    from ava_devicekit.core.contracts import ContextSnapshot, InputEvent, ScreenContract
    from ava_devicekit.core.types import DeviceMessage

    contract = ScreenContract.from_dict({"screen_id": "sensor_panel", "actions": ["sensor.refresh"]})
    assert contract is not None
    assert contract.screen_id == "sensor_panel"
    assert contract.actions == ["sensor.refresh"]

    snapshot = ContextSnapshot.from_dict(
        {
            "screen": "sensor_panel",
            "cursor": 1,
            "token": {"addr": "Device111", "chain": "solana", "symbol": "DEV"},
            "focused_component": "row:1",
            "page_data": {"temperature": 24},
        }
    )
    assert snapshot is not None
    assert snapshot.selected is not None
    assert snapshot.selected.token_id == "Device111-solana"
    assert snapshot.focused_component == "row:1"

    event = InputEvent.from_dict(
        {
            "type": "input_event",
            "source": "joystick",
            "kind": "move",
            "code": "right",
            "semantic_action": "feed_next",
            "context": snapshot.to_dict(),
        }
    )
    assert event is not None
    assert event.semantic_action == "feed_next"
    assert event.context and event.context.screen == "sensor_panel"

    msg = DeviceMessage.from_dict(event.to_dict() | {"type": "input_event"})
    assert msg.type == "input_event"
    assert msg.context is not None


def test_board_profile_and_input_map_validate_framework_shape():
    from ava_devicekit.core.contracts import BoardProfile, InputMap, validate_board_profile, validate_input_map

    profile = BoardProfile.from_dict(
        {
            "board_id": "third_party_esp32",
            "name": "Third Party ESP32",
            "display": {"width": 240, "height": 240, "color": "rgb565"},
            "input_map": {
                "capabilities": [
                    {
                        "source": "joystick",
                        "kinds": ["move", "press"],
                        "codes": ["up", "down", "left", "right", "center"],
                        "semantic_actions": ["cursor.up", "cursor.down", "confirm"],
                    }
                ],
                "aliases": {"btn_a": "confirm"},
                "required_actions": ["confirm"],
            },
            "outputs": ["display", "speaker"],
        }
    )
    assert profile is not None
    assert profile.validate().ok
    assert validate_board_profile(profile.to_dict()).ok
    assert validate_input_map(profile.input_map).ok

    bad_map = InputMap.from_dict({"capabilities": [{"source": "button"}], "required_actions": ["confirm"]})
    result = bad_map.validate()
    assert not result.ok
    assert any("required action" in error for error in result.errors)


def test_screen_payload_validation_uses_generic_screen_contracts():
    from ava_devicekit.core.contracts import ScreenContract, ensure_screen_payload, validate_screen_payload
    from ava_devicekit.core.types import ScreenPayload

    contract = ScreenContract(
        screen_id="sensor_panel",
        payload_schema={
            "type": "object",
            "required": ["temperature"],
            "properties": {"temperature": {"type": "number"}, "unit": {"enum": ["c", "f"]}},
        },
        context_schema={"type": "object", "required": ["screen"], "properties": {"screen": {"const": "sensor_panel"}}},
    )
    payload = ScreenPayload("sensor_panel", {"temperature": 24.5, "unit": "c"})
    assert validate_screen_payload(payload, contracts=[contract]).ok
    assert ensure_screen_payload(payload, contracts=[contract])["screen"] == "sensor_panel"

    missing = validate_screen_payload({"type": "display", "screen": "sensor_panel", "data": {"unit": "c"}}, contracts=[contract])
    assert not missing.ok
    assert "data.temperature is required" in missing.errors

    undeclared = validate_screen_payload({"type": "display", "screen": "other", "data": {}}, contracts=[contract])
    assert not undeclared.ok
    assert "screen 'other' is not declared" in undeclared.errors


def test_selection_context_validation_is_generic_and_strict():
    from ava_devicekit.core.contracts import SelectionContext, validate_selection_context

    context = SelectionContext.from_dict(
        {
            "app_id": "weather_station",
            "screen": "sensor_panel",
            "cursor": 0,
            "selected": {"sensor_id": "outdoor", "label": "Outdoor"},
            "visible_rows": [{"sensor_id": "outdoor"}],
            "focused_component": "row:0",
        }
    )
    assert context is not None
    assert context.validate().ok
    assert context.selected == {"sensor_id": "outdoor", "label": "Outdoor"}

    bad = validate_selection_context({"screen": "sensor_panel", "cursor": 2, "visible_rows": [{"sensor_id": "outdoor"}]})
    assert not bad.ok
    assert any("cursor" in error for error in bad.errors)

    malformed = validate_selection_context({"screen": "sensor_panel", "visible_rows": ["not-object"]})
    assert not malformed.ok
    assert "visible_rows must be a list of objects" in malformed.errors


def test_device_identity_telemetry_and_transport_contracts_validate():
    from ava_devicekit.core.contracts import (
        DeviceIdentity,
        DeviceTelemetry,
        TransportProfile,
        validate_device_identity,
        validate_device_telemetry,
        validate_transport_profile,
    )

    identity = DeviceIdentity.from_dict(
        {
            "device_id": "sensor_001",
            "device_public_key": "ed25519:abc",
            "key_type": "ed25519",
            "challenge": {"nonce": "n1"},
            "signature": "sig",
            "secure_element_profile": "atecc608a",
        }
    )
    assert identity is not None
    assert identity.validate(require_signed_challenge=True).ok
    assert not validate_device_identity({"device_public_key": "ed25519:abc"}, require_signed_challenge=True).ok

    telemetry = DeviceTelemetry.from_dict(
        {
            "device_id": "sensor_001",
            "readings": {"temperature_c": 24.5, "active": True},
            "transport": "http_fallback",
            "signature": "sig",
        }
    )
    assert telemetry is not None
    assert telemetry.validate(require_signature=True).ok
    assert not validate_device_telemetry({"device_id": "sensor_001", "readings": {"bad": {"nested": True}}}).ok

    profile = TransportProfile.from_dict(
        {
            "protocol": "websocket_or_http",
            "websocket_primary": True,
            "http_fallback": True,
            "heartbeat_interval_ms": 15000,
            "reconnect_interval_ms": 3000,
            "uses_per_device_bearer_token": True,
            "acks_rendered_payloads": True,
        }
    )
    assert profile is not None
    assert profile.validate().ok
    assert not validate_transport_profile({"protocol": "http", "http_fallback": True}).ok
