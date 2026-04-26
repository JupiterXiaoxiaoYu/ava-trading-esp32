from __future__ import annotations

import asyncio
import json
from typing import Any

from ava_devicekit.apps.ava_box import AvaBoxApp
from ava_devicekit.gateway.session import DeviceSession


async def run_websocket_gateway(host: str = "0.0.0.0", port: int = 8787) -> None:
    """Run an optional WebSocket gateway.

    The dependency is optional so the core framework remains stdlib-only.
    Install `ava-devicekit[websocket]` to use this server.
    """
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("Install websockets or ava-devicekit[websocket] to run the gateway") from exc

    async def handler(ws: Any) -> None:
        session = DeviceSession(AvaBoxApp.create())
        await ws.send(json.dumps(session.boot()))
        async for raw in ws:
            payload = session.handle_json(raw)
            await ws.send(json.dumps(payload))

    async with websockets.serve(handler, host, port):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(run_websocket_gateway())
