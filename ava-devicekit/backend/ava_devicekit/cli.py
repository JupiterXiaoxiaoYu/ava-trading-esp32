from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from ava_devicekit.gateway.http_server import run_http_gateway
from ava_devicekit.gateway.firmware_compat import run_firmware_compat_gateway
from ava_devicekit.gateway.server import run_server
from ava_devicekit.ota.publish import firmware_catalog, publish_firmware
from ava_devicekit.runtime.settings import RuntimeSettings

ROOT = Path(__file__).resolve().parents[2]
USERLAND = ROOT / "userland"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ava-devicekit", description="Ava DeviceKit developer CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capabilities", help="Print framework and userland capability map")

    validate = sub.add_parser("validate", help="Validate a runtime config file can be loaded")
    validate.add_argument("--config", default=None)

    init_app = sub.add_parser("init-app", help="Create a starter hardware app directory from userland templates")
    init_app.add_argument("path")
    init_app.add_argument(
        "--type",
        choices=[
            "starter",
            "payment",
            "payment_terminal",
            "alert",
            "token_alert",
            "sensor",
            "sensor_registry",
            "depin",
            "solana_ai_depin_device",
            "depin_reward_device",
            "depin-reward",
            "sensor_oracle_device",
            "sensor-oracle",
            "onchain_event_listener",
            "event-listener",
            "hardware_signer_approval",
            "signer",
        ],
        default="starter",
    )
    init_app.add_argument("--force", action="store_true")

    init_board = sub.add_parser("init-board", help="Create a starter ESP32 board port from userland templates")
    init_board.add_argument("path")
    init_board.add_argument("--force", action="store_true")

    init_adapter = sub.add_parser("init-adapter", help="Create starter adapter templates")
    init_adapter.add_argument("path")
    init_adapter.add_argument("--force", action="store_true")

    init_provider = sub.add_parser("init-provider", help="Create starter provider configuration examples")
    init_provider.add_argument("path")
    init_provider.add_argument("--force", action="store_true")

    firmware = sub.add_parser("firmware", help="List or publish OTA firmware binaries")
    firmware_sub = firmware.add_subparsers(dest="firmware_command", required=True)
    firmware_list = firmware_sub.add_parser("list", help="List firmware binaries available to OTA")
    firmware_list.add_argument("--config", default=None)
    firmware_publish = firmware_sub.add_parser("publish", help="Copy a firmware .bin into the OTA bin directory")
    firmware_publish.add_argument("--config", default=None)
    firmware_publish.add_argument("--model", required=True)
    firmware_publish.add_argument("--version", required=True)
    firmware_publish.add_argument("--source", required=True)

    http = sub.add_parser("run-http", help="Run the HTTP gateway")
    _add_runtime_args(http, default_port=8788)

    ws = sub.add_parser("run-firmware-ws", help="Run the deployed-firmware-compatible WebSocket gateway")
    _add_runtime_args(ws, default_port=8787)

    server = sub.add_parser("run-server", help="Run HTTP, firmware-compatible WebSocket and runtime tasks in one process")
    _add_runtime_args(server, default_port=8788)
    server.add_argument("--ws-port", type=int, default=None)

    args = parser.parse_args(argv)
    if args.command == "capabilities":
        _print_json(json.loads((_userland_root() / "capabilities.json").read_text(encoding="utf-8")))
        return
    if args.command == "validate":
        _print_json(RuntimeSettings.load(args.config).sanitized_dict())
        return
    if args.command == "init-app":
        _init_app(Path(args.path), app_type=args.type, force=args.force)
        return
    if args.command == "init-board":
        _init_board(Path(args.path), force=args.force)
        return
    if args.command == "init-adapter":
        _copy_tree(_userland_root() / "adapter", Path(args.path), force=args.force)
        return
    if args.command == "init-provider":
        _copy_tree(_userland_root() / "provider", Path(args.path), force=args.force)
        return
    if args.command == "firmware":
        settings = RuntimeSettings.load(args.config)
        if args.firmware_command == "list":
            _print_json(firmware_catalog(settings))
            return
        if args.firmware_command == "publish":
            _print_json(publish_firmware(settings, model=args.model, version=args.version, source_path=args.source))
            return
    if args.command == "run-http":
        settings = RuntimeSettings.load(args.config)
        run_http_gateway(args.host, args.port, app_id=args.app_id, manifest_path=args.manifest, adapter=args.adapter, mock=args.mock, skill_store_path=args.skill_store, runtime_settings=settings)
        return
    if args.command == "run-firmware-ws":
        import asyncio

        settings = RuntimeSettings.load(args.config)
        asyncio.run(run_firmware_compat_gateway(args.host, args.port, app_id=args.app_id, manifest_path=args.manifest, adapter=args.adapter, mock=args.mock, skill_store_path=args.skill_store, runtime_settings=settings))
        return
    if args.command == "run-server":
        settings = RuntimeSettings.load(args.config)
        settings.host = args.host
        settings.http_port = args.port
        if args.ws_port is not None:
            settings.websocket_port = args.ws_port
        run_server(settings=settings, app_id=args.app_id, manifest_path=args.manifest, adapter=args.adapter, mock=args.mock, skill_store_path=args.skill_store)


def _add_runtime_args(parser: argparse.ArgumentParser, *, default_port: int) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--app-id", default="ava_box")
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--adapter", default="auto")
    parser.add_argument("--skill-store", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--mock", action="store_true")


def _init_app(path: Path, *, app_type: str = "starter", force: bool = False) -> None:
    if path.exists() and any(path.iterdir()) and not force:
        raise SystemExit(f"target exists and is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)
    userland = _userland_root()
    if app_type == "starter":
        shutil.copy2(userland / "app" / "manifest.template.json", path / "manifest.json")
        shutil.copy2(userland / "app" / "app_template.py", path / "app.py")
    else:
        example = _examples_root() / "apps" / {
            "payment": "payment_terminal",
            "payment_terminal": "payment_terminal",
            "alert": "token_alert",
            "token_alert": "token_alert",
            "sensor": "sensor_registry",
            "sensor_registry": "sensor_registry",
            "depin": "solana_ai_depin_device",
            "solana_ai_depin_device": "solana_ai_depin_device",
            "depin_reward_device": "depin_reward_device",
            "depin-reward": "depin_reward_device",
            "sensor_oracle_device": "sensor_oracle_device",
            "sensor-oracle": "sensor_oracle_device",
            "onchain_event_listener": "onchain_event_listener",
            "event-listener": "onchain_event_listener",
            "hardware_signer_approval": "hardware_signer_approval",
            "signer": "hardware_signer_approval",
        }[app_type]
        _copy_tree_contents(example, path)
        if not (path / "app.py").exists():
            shutil.copy2(userland / "app" / "app_template.py", path / "app.py")
    shutil.copy2(userland / "runtime.example.json", path / "runtime.example.json")
    tests = path / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_manifest.py").write_text(
        "import json\nfrom pathlib import Path\nfrom ava_devicekit.core.manifest import HardwareAppManifest\n\n"
        "def test_manifest_loads():\n"
        "    manifest = HardwareAppManifest.from_dict(json.loads((Path(__file__).parents[1] / 'manifest.json').read_text()))\n"
        "    assert manifest.app_id\n"
        "    assert manifest.screens\n",
        encoding="utf-8",
    )
    (path / "README.md").write_text(f"# DeviceKit App\n\nType: `{app_type}`.\n\nStart from `manifest.json`, `app.py`, `runtime.example.json`, and `tests/`.\n", encoding="utf-8")
    _print_json({"ok": True, "path": str(path), "type": app_type})


def _init_board(path: Path, *, force: bool = False) -> None:
    if path.exists() and any(path.iterdir()) and not force:
        raise SystemExit(f"target exists and is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)
    for src in (_userland_root() / "hardware_port" / "templates").iterdir():
        if src.is_file():
            shutil.copy2(src, path / src.name)
    _print_json({"ok": True, "path": str(path)})


def _copy_tree(source: Path, path: Path, *, force: bool = False) -> None:
    if path.exists() and any(path.iterdir()) and not force:
        raise SystemExit(f"target exists and is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)
    _copy_tree_contents(source, path, force=force)
    _print_json({"ok": True, "path": str(path)})


def _copy_tree_contents(source: Path, path: Path, *, force: bool = True) -> None:
    for src in source.iterdir():
        dst = path / src.name
        if src.is_file():
            shutil.copy2(src, dst)
        elif src.is_dir():
            if dst.exists() and force:
                shutil.rmtree(dst)
            shutil.copytree(src, dst, dirs_exist_ok=force)


def _print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _userland_root() -> Path:
    return _first_existing(
        USERLAND,
        Path(sys.prefix) / "share" / "ava-devicekit" / "userland",
        Path.cwd() / "ava-devicekit" / "userland",
    )


def _examples_root() -> Path:
    return _first_existing(
        ROOT / "examples",
        Path(sys.prefix) / "share" / "ava-devicekit" / "examples",
        Path.cwd() / "ava-devicekit" / "examples",
    )


def _first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


if __name__ == "__main__":
    main()
