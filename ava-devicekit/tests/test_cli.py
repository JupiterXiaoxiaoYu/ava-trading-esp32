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


def test_cli_init_adapter_and_provider_templates(tmp_path, capsys):
    adapter = tmp_path / "adapter"
    provider = tmp_path / "provider"

    main(["init-adapter", str(adapter)])
    assert json.loads(capsys.readouterr().out)["ok"] is True
    main(["init-provider", str(provider)])
    assert json.loads(capsys.readouterr().out)["ok"] is True

    assert (adapter / "chain_adapter_template.py").exists()
    assert (provider / "provider.catalog.example.json").exists()


def test_cli_firmware_publish_and_list(tmp_path, capsys):
    cfg = tmp_path / "runtime.json"
    bin_dir = tmp_path / "bin"
    source = tmp_path / "build.bin"
    source.write_bytes(b"bin")
    cfg.write_text(json.dumps({"firmware_bin_dir": str(bin_dir)}), encoding="utf-8")

    main(["firmware", "publish", "--config", str(cfg), "--model", "scratch-arcade", "--version", "1.0.1", "--source", str(source)])
    assert json.loads(capsys.readouterr().out)["firmware"]["filename"] == "scratch-arcade_1.0.1.bin"
    main(["firmware", "list", "--config", str(cfg)])
    assert json.loads(capsys.readouterr().out)["count"] == 1
