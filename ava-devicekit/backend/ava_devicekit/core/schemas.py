from __future__ import annotations

from ava_devicekit.core.contracts import (
    BoardProfile,
    InputCapability,
    InputEvent,
    InputMap,
    ScreenContract,
    ScreenPayloadValidator,
    SelectionContext,
    ValidationResult,
    ensure_screen_payload,
    validate_board_profile,
    validate_input_map,
    validate_screen_payload,
    validate_selection_context,
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

__all__ = [
    "BOARD_PROFILE_SCHEMA",
    "INPUT_MAP_SCHEMA",
    "SCREEN_PAYLOAD_SCHEMA",
    "SELECTION_CONTEXT_SCHEMA",
    "BoardProfile",
    "InputCapability",
    "InputEvent",
    "InputMap",
    "ScreenContract",
    "ScreenPayloadValidator",
    "SelectionContext",
    "ValidationResult",
    "ensure_screen_payload",
    "validate_board_profile",
    "validate_input_map",
    "validate_screen_payload",
    "validate_selection_context",
]
