from __future__ import annotations

import asyncio
import argparse
import json
from pathlib import Path
from typing import Any

from ava_devicekit.gateway.factory import create_device_session


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

    async def handler(ws: Any) -> None:
        session = create_device_session(
            app_id=app_id,
            manifest_path=manifest_path,
            adapter=adapter,
            mock=mock,
            skill_store_path=skill_store_path,
        )
        await ws.send(json.dumps(session.boot()))
        async for raw in ws:
            payload = session.handle_json(raw)
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
