from __future__ import annotations

from ava_devicekit.core.contracts import (
    BoardProfile,
    DeviceIdentity,
    DeviceTelemetry,
    InputCapability,
    InputEvent,
    InputMap,
    ScreenContract,
    ScreenPayloadValidator,
    SelectionContext,
    TransportProfile,
    ValidationResult,
    ensure_screen_payload,
    validate_board_profile,
    validate_device_identity,
    validate_device_telemetry,
    validate_input_map,
    validate_screen_payload,
    validate_selection_context,
    validate_transport_profile,
)

BOARD_PROFILE_SCHEMA = {
    "type": "object",
    "required": ["board_id"],
    "properties": {
        "board_id": {"type": "string"},
        "name": {"type": "string"},
        "display": {"type": "object"},
        "input_map": {"type": "object"},
        "outputs": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": True,
}

INPUT_MAP_SCHEMA = {
    "type": "object",
    "properties": {
        "capabilities": {"type": "array", "items": {"type": "object"}},
        "inputs": {"type": ["array", "object"]},
        "aliases": {"type": "object"},
        "required_actions": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": True,
}

SCREEN_PAYLOAD_SCHEMA = {
    "type": "object",
    "required": ["type", "screen", "data"],
    "properties": {
        "type": {"const": "display"},
        "screen": {"type": "string"},
        "data": {"type": "object"},
        "context": {"type": "object"},
    },
    "additionalProperties": True,
}

SELECTION_CONTEXT_SCHEMA = {
    "type": "object",
    "required": ["screen"],
    "properties": {
        "app_id": {"type": "string"},
        "screen": {"type": "string"},
        "cursor": {"type": ["integer", "null"]},
        "selected": {"type": "object"},
        "visible_rows": {"type": "array", "items": {"type": "object"}},
        "focused_component": {"type": "string"},
        "page_data": {"type": "object"},
        "state": {"type": "object"},
    },
    "additionalProperties": True,
}

DEVICE_IDENTITY_SCHEMA = {
    "type": "object",
    "required": ["device_id"],
    "properties": {
        "device_id": {"type": "string"},
        "device_public_key": {"type": "string"},
        "key_type": {"enum": ["ed25519", "secp256k1", "unknown", "none"]},
        "secure_element_profile": {"type": "string"},
        "challenge": {"type": "object"},
        "signature": {"type": "string"},
        "attestation": {"type": "object"},
        "metadata": {"type": "object"},
    },
    "additionalProperties": True,
}

DEVICE_TELEMETRY_SCHEMA = {
    "type": "object",
    "required": ["device_id", "readings"],
    "properties": {
        "device_id": {"type": "string"},
        "ts": {"type": ["integer", "number", "string"]},
        "readings": {"type": "object"},
        "unit": {"type": "string"},
        "location": {"type": "object"},
        "transport": {"enum": ["websocket", "http_fallback", "serial", "test", "unknown"]},
        "signature": {"type": "string"},
        "device_public_key": {"type": "string"},
        "metadata": {"type": "object"},
    },
    "additionalProperties": True,
}

TRANSPORT_PROFILE_SCHEMA = {
    "type": "object",
    "required": ["protocol"],
    "properties": {
        "protocol": {"enum": ["websocket", "http", "websocket_or_http", "serial", "custom"]},
        "websocket_primary": {"type": "boolean"},
        "http_fallback": {"type": "boolean"},
        "heartbeat_interval_ms": {"type": "integer"},
        "reconnect_interval_ms": {"type": "integer"},
        "uses_per_device_bearer_token": {"type": "boolean"},
        "acks_rendered_payloads": {"type": "boolean"},
        "supports_ota_check_command": {"type": "boolean"},
        "sends_context_snapshot": {"type": "boolean"},
    },
    "additionalProperties": True,
}

__all__ = [
    "BOARD_PROFILE_SCHEMA",
    "DEVICE_IDENTITY_SCHEMA",
    "DEVICE_TELEMETRY_SCHEMA",
    "INPUT_MAP_SCHEMA",
    "SCREEN_PAYLOAD_SCHEMA",
    "SELECTION_CONTEXT_SCHEMA",
    "TRANSPORT_PROFILE_SCHEMA",
    "BoardProfile",
    "DeviceIdentity",
    "DeviceTelemetry",
    "InputCapability",
    "InputEvent",
    "InputMap",
    "ScreenContract",
    "ScreenPayloadValidator",
    "SelectionContext",
    "TransportProfile",
    "ValidationResult",
    "ensure_screen_payload",
    "validate_board_profile",
    "validate_device_identity",
    "validate_device_telemetry",
    "validate_input_map",
    "validate_screen_payload",
    "validate_selection_context",
    "validate_transport_profile",
]
