from __future__ import annotations

import asyncio
import argparse
import json
from pathlib import Path
from typing import Any

from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.gateway.runtime_manager import RuntimeManager, normalize_device_id


async def run_websocket_gateway(
    host: str = "0.0.0.0",
    port: int = 8787,
    *,
    app_id: str = "ava_box",
    manifest_path: str | Path | None = None,
    adapter: str = "auto",
    mock: bool = False,
    skill_store_path: str | None = None,
) -> None:
    """Run an optional WebSocket gateway.

    The dependency is optional so the core framework remains stdlib-only.
    Install `ava-devicekit[websocket]` to use this server.
    """
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("Install websockets or ava-devicekit[websocket] to run the gateway") from exc

    manager = RuntimeManager(
        lambda device_id: create_device_session(
            app_id=app_id,
            manifest_path=manifest_path,
            adapter=adapter,
            mock=mock,
            skill_store_path=skill_store_path,
        )
    )

    async def handler(ws: Any) -> None:
        device_id = normalize_device_id(getattr(ws, "request_headers", {}).get("X-Ava-Device-Id") if hasattr(ws, "request_headers") else "")
        await ws.send(json.dumps(manager.boot(device_id)))
        async for raw in ws:
            msg = json.loads(raw)
            device_id = normalize_device_id(msg.get("device_id") or msg.get("device") or device_id)
            payload = manager.handle(device_id, msg)
            await ws.send(json.dumps(payload))

    async with websockets.serve(handler, host, port):
        await asyncio.Future()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Ava DeviceKit optional WebSocket gateway.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--app-id", default="ava_box")
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--adapter", default="auto")
    parser.add_argument("--skill-store", default=None)
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        run_websocket_gateway(
            args.host,
            args.port,
            app_id=args.app_id,
            manifest_path=args.manifest,
            adapter=args.adapter,
            mock=args.mock,
            skill_store_path=args.skill_store,
        )
    )
