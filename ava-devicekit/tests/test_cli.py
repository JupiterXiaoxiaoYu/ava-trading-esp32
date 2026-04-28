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
    assert (target / "board.profile.json").exists()


def test_cli_init_app_type_creates_reference_template(tmp_path, capsys):
    target = tmp_path / "payment"
    main(["init-app", str(target), "--type", "payment"])
    body = json.loads(capsys.readouterr().out)
    assert body["ok"] is True
    assert body["type"] == "payment"
    assert (target / "manifest.json").exists()
    assert (target / "app.py").exists()
    assert (target / "tests" / "test_manifest.py").exists()


def test_cli_init_app_depin_template(tmp_path, capsys):
    target = tmp_path / "depin"
    main(["init-app", str(target), "--type", "depin"])
    body = json.loads(capsys.readouterr().out)
    assert body["ok"] is True
    assert body["type"] == "depin"
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["app_id"] == "solana_ai_depin_device"
    assert "proof.submit" in manifest["actions"]


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
