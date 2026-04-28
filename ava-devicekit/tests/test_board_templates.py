from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_board_template_includes_ack_and_ota_trigger_hooks():
    header = (ROOT / "userland" / "hardware_port" / "templates" / "board_port.h").read_text(encoding="utf-8")
    source = (ROOT / "userland" / "hardware_port" / "templates" / "board_port.c").read_text(encoding="utf-8")
    profile = (ROOT / "userland" / "hardware_port" / "templates" / "board.profile.json").read_text(encoding="utf-8")

    assert "start_ota_check" in header
    assert "ava_board_send_ack" in header
    assert "ota_check" in source
    assert "message_id" in source
    assert "acks_rendered_payloads" in profile
