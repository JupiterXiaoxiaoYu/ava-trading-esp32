from __future__ import annotations

import json

from ava_devicekit.cli import main


def test_cli_init_board_creates_port_template(tmp_path, capsys):
    target = tmp_path / "board"
    main(["init-board", str(target)])
    body = json.loads(capsys.readouterr().out)
    assert body["ok"] is True
    assert (target / "board_port.h").exists()
    assert (target / "board_port.c").exists()


def test_cli_validate_outputs_sanitized_runtime(tmp_path, capsys):
    cfg = tmp_path / "runtime.json"
    cfg.write_text('{"admin_token_env":"ADMIN_TOKEN","providers":{"tts":{"provider":"mock","options":{"api_secret":"hidden"}}}}', encoding="utf-8")
    main(["validate", "--config", str(cfg)])
    body = json.loads(capsys.readouterr().out)
    assert body["admin_token_env"] == "ADMIN_TOKEN"
    assert body["providers"]["tts"]["options"]["api_secret"] == "<redacted>"
