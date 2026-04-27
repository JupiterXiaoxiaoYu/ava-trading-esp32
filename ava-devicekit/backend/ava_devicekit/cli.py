from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from ava_devicekit.gateway.http_server import run_http_gateway
from ava_devicekit.gateway.legacy_firmware import run_legacy_firmware_gateway
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
    init_app.add_argument("--force", action="store_true")

    init_board = sub.add_parser("init-board", help="Create a starter ESP32 board port from userland templates")
    init_board.add_argument("path")
    init_board.add_argument("--force", action="store_true")

    http = sub.add_parser("run-http", help="Run the HTTP gateway")
    _add_runtime_args(http, default_port=8788)

    ws = sub.add_parser("run-legacy-ws", help="Run the existing-firmware-compatible WebSocket gateway")
    _add_runtime_args(ws, default_port=8787)

    args = parser.parse_args(argv)
    if args.command == "capabilities":
        _print_json(json.loads((USERLAND / "capabilities.json").read_text(encoding="utf-8")))
        return
    if args.command == "validate":
        _print_json(RuntimeSettings.load(args.config).sanitized_dict())
        return
    if args.command == "init-app":
        _init_app(Path(args.path), force=args.force)
        return
    if args.command == "init-board":
        _init_board(Path(args.path), force=args.force)
        return
    if args.command == "run-http":
        settings = RuntimeSettings.load(args.config)
        run_http_gateway(args.host, args.port, app_id=args.app_id, manifest_path=args.manifest, adapter=args.adapter, mock=args.mock, skill_store_path=args.skill_store, runtime_settings=settings)
        return
    if args.command == "run-legacy-ws":
        import asyncio

        settings = RuntimeSettings.load(args.config)
        asyncio.run(run_legacy_firmware_gateway(args.host, args.port, app_id=args.app_id, manifest_path=args.manifest, adapter=args.adapter, mock=args.mock, skill_store_path=args.skill_store, runtime_settings=settings))


def _add_runtime_args(parser: argparse.ArgumentParser, *, default_port: int) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--app-id", default="ava_box")
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--adapter", default="auto")
    parser.add_argument("--skill-store", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--mock", action="store_true")


def _init_app(path: Path, *, force: bool = False) -> None:
    if path.exists() and any(path.iterdir()) and not force:
        raise SystemExit(f"target exists and is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(USERLAND / "app" / "manifest.template.json", path / "manifest.json")
    shutil.copy2(USERLAND / "app" / "app_template.py", path / "app.py")
    shutil.copy2(USERLAND / "runtime.example.json", path / "runtime.example.json")
    (path / "README.md").write_text("# DeviceKit App\n\nStart from `manifest.json`, `app.py`, and `runtime.example.json`.\n", encoding="utf-8")
    _print_json({"ok": True, "path": str(path)})


def _init_board(path: Path, *, force: bool = False) -> None:
    if path.exists() and any(path.iterdir()) and not force:
        raise SystemExit(f"target exists and is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)
    for src in (USERLAND / "hardware_port" / "templates").iterdir():
        if src.is_file():
            shutil.copy2(src, path / src.name)
    _print_json({"ok": True, "path": str(path)})


def _print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
