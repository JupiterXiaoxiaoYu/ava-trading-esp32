from __future__ import annotations

import json

from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.gateway.legacy_firmware import LegacyFirmwareConnection


def test_legacy_firmware_hello_and_key_action_flow():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))
    hello = conn.handle_text(json.dumps({"type": "hello", "transport": "websocket", "audio_params": {"sample_rate": 16000}}))
    assert hello[0]["type"] == "hello"
    assert hello[0]["transport"] == "websocket"

    detail = conn.handle_text(json.dumps({"type": "key_action", "action": "watch"}))
    assert detail[0]["screen"] == "spotlight"


def test_legacy_firmware_listen_detect_preserves_selection_context():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))
    replies = conn.handle_text(
        json.dumps(
            {
                "type": "listen",
                "state": "detect",
                "text": "buy",
                "selection": {
                    "token_id": "So11111111111111111111111111111111111111112-solana",
                    "addr": "So11111111111111111111111111111111111111112",
                    "chain": "solana",
                    "symbol": "SOL",
                },
            }
        )
    )
    display = next(item for item in replies if item.get("type") == "display")
    assert display["screen"] == "confirm"
    assert display["action_draft"]["summary"]["symbol"] == "SOL"
    assert replies[-1]["type"] == "tts"
    assert replies[-1]["state"] == "stop"
