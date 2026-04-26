from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.gateway.session import DeviceSession
from ava_devicekit.runtime.settings import RuntimeSettings


class LegacyFirmwareConnection:
    """legacy firmware WebSocket protocol shim backed by a DeviceKit session.

    Existing ESP32 firmware expects legacy-style text frames (`hello`,
    `listen`, `key_action`) and display payloads. This adapter preserves that
    wire shape while routing app behavior through Ava DeviceKit.
    """

    def __init__(self, session: DeviceSession):
        self.session = session
        self.session_id = uuid.uuid4().hex
        self.audio_params = {"format": "opus", "sample_rate": 16000, "channels": 1, "frame_duration": 60}

    async def open(self, ws: Any) -> None:
        async for raw in ws:
            if isinstance(raw, bytes):
                continue
            for payload in self.handle_text(raw):
                await ws.send(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    def handle_text(self, raw: str) -> list[dict[str, Any]]:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return [_system_error("invalid_json")]
        msg_type = str(msg.get("type") or "")
        if msg_type == "hello":
            return [self._hello(msg)]
        if msg_type == "ping":
            return [{"type": "pong", "session_id": self.session_id}]
        if msg_type == "key_action":
            return [self.session.handle(_device_message_from_key_action(msg))]
        if msg_type == "listen":
            return self._handle_listen(msg)
        if msg_type == "confirm":
            return [self.session.handle({"type": "confirm", **_message_context(msg)})]
        if msg_type == "cancel" or (msg_type == "abort"):
            return [self.session.handle({"type": "cancel", **_message_context(msg)})]
        return [_system_error(f"unsupported:{msg_type or 'empty'}")]

    def _hello(self, msg: dict[str, Any]) -> dict[str, Any]:
        audio_params = msg.get("audio_params")
        if isinstance(audio_params, dict):
            self.audio_params.update(audio_params)
        boot = self.session.boot()
        return {
            "type": "hello",
            "transport": "websocket",
            "session_id": self.session_id,
            "audio_params": self.audio_params,
            "devicekit": {"app_id": self.session.app.manifest.app_id, "boot_screen": boot.get("screen")},
        }

    def _handle_listen(self, msg: dict[str, Any]) -> list[dict[str, Any]]:
        state = str(msg.get("state") or "")
        if state == "start":
            return [{"type": "tts", "state": "stop", "session_id": self.session_id}]
        if state == "stop":
            return []
        if state == "detect":
            text = str(msg.get("text") or "")
            result = self.session.handle({"type": "listen_detect", "text": text, **_message_context(msg)})
            return [
                {"type": "stt", "text": text, "session_id": self.session_id},
                result,
                {"type": "tts", "state": "sentence_start", "text": _spoken_summary(result), "session_id": self.session_id},
                {"type": "tts", "state": "stop", "session_id": self.session_id},
            ]
        return []


def _device_message_from_key_action(msg: dict[str, Any]) -> dict[str, Any]:
    payload = {k: v for k, v in msg.items() if k not in {"type", "action", "context", "selection"}}
    return {"type": "key_action", "action": str(msg.get("action") or ""), "payload": payload, **_message_context(msg)}


def _message_context(msg: dict[str, Any]) -> dict[str, Any]:
    context = msg.get("context") if isinstance(msg.get("context"), dict) else {}
    selection = msg.get("selection") if isinstance(msg.get("selection"), dict) else None
    if selection and not context.get("selected"):
        context = {**context, "selected": selection}
    return {"context": context} if context else {}


def _system_error(message: str) -> dict[str, Any]:
    return {"type": "system", "command": "error", "message": message}


def _spoken_summary(payload: dict[str, Any]) -> str:
    screen = str(payload.get("screen") or "")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if screen == "confirm":
        return f"Draft ready: {data.get('action', 'ACTION')} {data.get('symbol', '')}".strip()
    if screen == "spotlight":
        return f"Showing {data.get('symbol', 'token')} details"
    if screen == "feed":
        return str(data.get("source_label") or "Feed updated")
    if screen == "result":
        return str(data.get("title") or data.get("body") or "Done")
    if screen == "notify":
        return str(data.get("body") or data.get("title") or "OK")
    return "OK"


async def run_legacy_firmware_gateway(
    host: str = "0.0.0.0",
    port: int = 8787,
    *,
    app_id: str = "ava_box",
    manifest_path: str | Path | None = None,
    adapter: str = "auto",
    mock: bool = False,
    skill_store_path: str | None = None,
    runtime_settings: RuntimeSettings | None = None,
) -> None:
    try:
        import websockets
    except ImportError as exc:  # pragma: no cover - optional dependency boundary
        raise RuntimeError("Install websockets or ava-devicekit[websocket] to run the legacy-firmware-compatible gateway") from exc

    settings = runtime_settings or RuntimeSettings.load()

    async def handler(ws: Any) -> None:
        session = create_device_session(
            app_id=app_id,
            manifest_path=manifest_path,
            adapter=adapter,
            mock=mock,
            skill_store_path=skill_store_path,
        )
        await LegacyFirmwareConnection(session).open(ws)

    async with websockets.serve(
        handler,
        host,
        port,
        ping_interval=settings.websocket_ping_interval,
        ping_timeout=settings.websocket_ping_timeout,
    ):
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the legacy-firmware-compatible Ava DeviceKit WebSocket gateway.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--app-id", default="ava_box")
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--adapter", default="auto")
    parser.add_argument("--skill-store", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        run_legacy_firmware_gateway(
            args.host,
            args.port,
            app_id=args.app_id,
            manifest_path=args.manifest,
            adapter=args.adapter,
            mock=args.mock,
            skill_store_path=args.skill_store,
            runtime_settings=RuntimeSettings.load(args.config),
        )
    )


if __name__ == "__main__":
    main()
