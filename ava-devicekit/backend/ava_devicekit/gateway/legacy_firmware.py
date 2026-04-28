from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any

from ava_devicekit.gateway.audio import AudioInputBuffer, create_audio_decoder, run_async, transcribe_buffer, tts_frames
from ava_devicekit.gateway.runtime_manager import RuntimeManager, normalize_device_id, runtime_manager_for_settings
from ava_devicekit.gateway.session import DeviceSession
from ava_devicekit.providers.asr.base import ASRProvider
from ava_devicekit.providers.registry import ProviderBundle, create_provider_bundle
from ava_devicekit.providers.pipeline import VoicePipeline
from ava_devicekit.runtime.settings import RuntimeSettings
from ava_devicekit.streams.ave_data_wss import AveDataWSSAdapter, AveDataWSSConfig
from ava_devicekit.streams.base import MarketStreamEvent, StreamSubscription
from ava_devicekit.streams.runtime import MarketStreamRuntime


class LegacyFirmwareConnection:
    """legacy firmware WebSocket protocol shim backed by a DeviceKit session.

    Existing ESP32 firmware expects legacy-style text frames (`hello`,
    `listen`, `key_action`) and display payloads. This adapter preserves that
    wire shape while routing app behavior through Ava DeviceKit.
    """

    def __init__(
        self,
        session: DeviceSession,
        voice_pipeline: VoicePipeline | None = None,
        asr_provider: ASRProvider | None = None,
        audio: AudioInputBuffer | None = None,
        manager: RuntimeManager | None = None,
        device_id: str = "default",
    ):
        self.session = session
        self.manager = manager
        self.device_id = normalize_device_id(device_id)
        self.voice_pipeline = voice_pipeline or VoicePipeline()
        self.asr_provider = asr_provider
        self.session_id = uuid.uuid4().hex
        self.audio_params = {"format": "pcm16", "sample_rate": 16000, "channels": 1, "frame_duration": 60}
        self.audio = audio or AudioInputBuffer()
        self.market_runtime: MarketStreamRuntime | None = None
        self._market_task: asyncio.Task | None = None
        self._outbound_task: asyncio.Task | None = None

    async def open(self, ws: Any) -> None:
        if self.manager:
            self.manager.register_connection(self.device_id, transport="legacy_ws", session_id=self.session_id)
        self._start_market_stream(ws)
        self._start_outbound_queue(ws)
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    payloads = self.handle_binary(raw)
                else:
                    payloads = await self.handle_raw(raw)
                await self._send_payloads(ws, payloads)
        finally:
            if self._market_task:
                self._market_task.cancel()
            if self._outbound_task:
                self._outbound_task.cancel()
            if self.manager:
                self.manager.unregister_connection(self.device_id, reason="ws_closed")

    async def handle_raw(self, raw: str) -> list[dict[str, Any]]:
        return await self._handle_text(raw, allow_async_asr=True)

    def handle_text(self, raw: str) -> list[dict[str, Any]]:
        return run_async(self._handle_text(raw, allow_async_asr=False))

    def handle_binary(self, raw: bytes) -> list[dict[str, Any]]:
        self.audio.append(raw)
        return []

    async def _handle_text(self, raw: str, *, allow_async_asr: bool) -> list[dict[str, Any]]:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return [_system_error("invalid_json")]
        msg_type = str(msg.get("type") or "")
        if msg_type == "hello":
            return self._hello(msg)
        if msg_type == "ping":
            if self.manager:
                self.manager.touch_connection(self.device_id)
            return [{"type": "pong", "session_id": self.session_id}]
        if msg_type in {"ack", "message_ack"}:
            message_id = str(msg.get("message_id") or msg.get("id") or "")
            ok = self.manager.ack_outbound(self.device_id, message_id) if self.manager else False
            return [{"type": "ack", "message_id": message_id, "ok": ok, "session_id": self.session_id}]
        if msg_type == "goodbye":
            return [{"type": "goodbye", "session_id": self.session_id}]
        if msg_type == "key_action":
            return [self._handle_device_message(_device_message_from_key_action(msg))]
        if msg_type == "input_event":
            return [self._handle_device_message({"type": "input_event", **_message_context(msg), **{k: v for k, v in msg.items() if k not in {"type", "context", "selection"}}})]
        if msg_type == "screen_context":
            return [self._handle_device_message({"type": "screen_context", "payload": _message_context(msg).get("context", {})})]
        if msg_type == "listen":
            return await self._handle_listen(msg, allow_async_asr=allow_async_asr)
        if msg_type == "listen_detect":
            return self._route_detected_text(str(msg.get("text") or msg.get("wake_word") or ""), msg)
        if msg_type == "trade_action":
            return [self._handle_device_message(_device_message_from_trade_action(msg))]
        if msg_type == "mcp":
            payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}
            return [self._handle_device_message({"type": "input_event", "payload": {"semantic_action": "mcp", **payload}, **_message_context(msg)})]
        if msg_type == "confirm":
            return [self._handle_device_message({"type": "confirm", "payload": _message_payload(msg), **_message_context(msg)})]
        if msg_type == "cancel" or (msg_type == "abort"):
            return [self._handle_device_message({"type": "cancel", "payload": _message_payload(msg), **_message_context(msg)})]
        if msg_type == "signed_tx":
            return [self._handle_device_message({"type": "signed_tx", **_message_context(msg), **{k: v for k, v in msg.items() if k not in {"type", "context"}}})]
        return [_system_error(f"unsupported:{msg_type or 'empty'}")]

    def _hello(self, msg: dict[str, Any]) -> list[dict[str, Any]]:
        audio_params = msg.get("audio_params")
        if isinstance(audio_params, dict):
            self.audio_params.update(audio_params)
            self.audio.configure(self.audio_params)
        boot_error = ""
        try:
            boot = self.manager.boot(self.device_id) if self.manager else self.session.boot()
            if self.manager:
                self.session = self.manager.get(self.device_id)
            boot_screen = str(boot.get("screen") or "")
        except Exception as exc:
            boot = _display_notify("Ava Box", f"Boot failed: {exc}", level="error")
            boot_error = str(exc)
            boot_screen = str(boot.get("screen") or "notify")
        hello = {
            "type": "hello",
            "transport": "websocket",
            "session_id": self.session_id,
            "audio_params": self.audio_params,
            "devicekit": {"app_id": self.session.app.manifest.app_id, "boot_screen": boot_screen, **({"boot_error": boot_error} if boot_error else {})},
        }
        return [hello, boot]

    async def _handle_listen(self, msg: dict[str, Any], *, allow_async_asr: bool) -> list[dict[str, Any]]:
        state = str(msg.get("state") or "")
        if state == "start":
            self.audio.reset()
            return [{"type": "tts", "state": "stop", "session_id": self.session_id}]
        if state == "partial":
            text = str(msg.get("text") or "")
            return [{"type": "stt", "state": "partial", "text": text, "session_id": self.session_id}] if text else []
        if state == "stop":
            if not allow_async_asr:
                return []
            try:
                result = await transcribe_buffer(self.asr_provider, self.audio, language=str(msg.get("language") or ""))
            except Exception as exc:
                return [_system_error(f"asr_failed:{exc}")]
            finally:
                self.audio.reset()
            if result and result.text:
                return self._route_detected_text(result.text, msg)
            return []
        if state == "detect":
            text = str(msg.get("text") or "")
            return self._route_detected_text(text, msg)
        return []

    def _route_detected_text(self, text: str, msg: dict[str, Any]) -> list[dict[str, Any]]:
        result = self._handle_device_message({"type": "listen_detect", "text": text, **_message_context(msg)})
        spoken = _spoken_summary(result)
        tts_result = None
        if _is_model_fallback(result):
            try:
                reply = self.voice_pipeline.reply(text, context=self.session.app.context)
                spoken = reply.text
                tts_result = reply.tts
            except Exception as exc:
                spoken = f"Ava model reply failed: {exc}"
        else:
            try:
                tts_result = self.voice_pipeline.tts.synthesize(spoken)
            except Exception:
                tts_result = None
        return [
            {"type": "stt", "text": text, "session_id": self.session_id},
            result,
            {"type": "tts", "state": "sentence_start", "text": spoken, "session_id": self.session_id},
            *tts_frames(tts_result, session_id=self.session_id),
            {"type": "tts", "state": "stop", "session_id": self.session_id},
        ]

    async def _send_payloads(self, ws: Any, payloads: list[dict[str, Any]]) -> None:
        for payload in payloads:
            await ws.send(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        self._sync_market_subscriptions(payloads)

    def _start_market_stream(self, ws: Any) -> None:
        if not os.environ.get("AVE_API_KEY"):
            return
        adapter = AveDataWSSAdapter(AveDataWSSConfig(api_key_env="AVE_API_KEY"))
        self.market_runtime = MarketStreamRuntime(adapter)

        async def on_events(events: list[MarketStreamEvent]) -> None:
            if not self.market_runtime:
                return
            for payload in self.market_runtime.apply_events(self.session, events):
                if self.manager:
                    self.manager.persist(self.device_id)
                await ws.send(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                self._sync_market_subscriptions([payload])

        self._market_task = asyncio.create_task(adapter.run_forever(on_events), name="ava_devicekit_market_stream")

    def _sync_market_subscriptions(self, payloads: list[dict[str, Any]]) -> None:
        if not self.market_runtime:
            return
        for payload in payloads:
            if payload.get("type") != "display":
                continue
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            screen = str(payload.get("screen") or "")
            if screen == "feed":
                tokens = data.get("tokens") if isinstance(data.get("tokens"), list) else []
                token_ids = [str(row.get("token_id") or "") for row in tokens if isinstance(row, dict) and row.get("token_id")]
                if token_ids:
                    self.market_runtime.subscribe(StreamSubscription("price", token_ids[:20], chain=str(data.get("chain") or "solana")))
            elif screen == "spotlight":
                token_id = str(data.get("token_id") or "")
                chain = str(data.get("chain") or "solana")
                if token_id:
                    self.market_runtime.subscribe(StreamSubscription("price", [token_id], chain=chain))
                pair = str(data.get("main_pair_id") or "")
                if pair:
                    self.market_runtime.subscribe(StreamSubscription("kline", [pair], interval=_to_wss_kline_interval(str(data.get("interval") or "60")), chain=chain))

    def _start_outbound_queue(self, ws: Any) -> None:
        if not self.manager:
            return

        async def poll() -> None:
            while True:
                await asyncio.sleep(0.5)
                self.manager.state(self.device_id)
                self.session = self.manager.get(self.device_id)
                self.manager.touch_connection(self.device_id)
                for payload in self.manager.lease_queued_outbound(self.device_id):
                    await ws.send(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                    self.manager.ack_outbound(self.device_id, str(payload.get("message_id") or ""))
                    self._sync_market_subscriptions([payload])

        self._outbound_task = asyncio.create_task(poll(), name="ava_devicekit_outbound_queue")

    def _handle_device_message(self, message: dict[str, Any]) -> dict[str, Any]:
        if not self.manager:
            return self.session.handle(message)
        payload = self.manager.handle(self.device_id, message)
        self.session = self.manager.get(self.device_id)
        return payload


def _device_message_from_key_action(msg: dict[str, Any]) -> dict[str, Any]:
    payload = {k: v for k, v in msg.items() if k not in {"type", "action", "context", "selection"}}
    return {"type": "key_action", "action": str(msg.get("action") or ""), "payload": payload, **_message_context(msg)}


def _device_message_from_trade_action(msg: dict[str, Any]) -> dict[str, Any]:
    action = str(msg.get("action") or "").strip().lower()
    msg_type = "cancel" if action in {"cancel", "abort"} else "confirm"
    payload = _message_payload(msg, exclude={"action"})
    return {"type": msg_type, "payload": payload, **_message_context(msg)}


def _message_payload(msg: dict[str, Any], *, exclude: set[str] | None = None) -> dict[str, Any]:
    excluded = {"type", "context", "selection", *(exclude or set())}
    return {k: v for k, v in msg.items() if k not in excluded}


def _message_context(msg: dict[str, Any]) -> dict[str, Any]:
    context = msg.get("context") if isinstance(msg.get("context"), dict) else {}
    selection = msg.get("selection") if isinstance(msg.get("selection"), dict) else None
    token = context.get("token") if isinstance(context.get("token"), dict) else None
    if selection:
        selected = selection.get("selected") if isinstance(selection.get("selected"), dict) else selection.get("token") if isinstance(selection.get("token"), dict) else selection
        if isinstance(selected, dict) and selection.get("cursor") is not None and selected.get("cursor") is None:
            selected = {**selected, "cursor": selection.get("cursor")}
        context = {**selection, **context}
        if not context.get("selected"):
            context = {**context, "selected": selected}
    if token and not context.get("selected"):
        context = {**context, "selected": token}
    return {"context": context} if context else {}


def _system_error(message: str) -> dict[str, Any]:
    return {"type": "system", "command": "error", "message": message}


def _display_notify(title: str, body: str, *, level: str = "error") -> dict[str, Any]:
    return {"type": "display", "screen": "notify", "data": {"level": level, "title": title, "body": body}}


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


def _is_model_fallback(payload: dict[str, Any]) -> bool:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return payload.get("screen") == "notify" and "model fallback" in str(data.get("body") or "").lower()


def _to_wss_kline_interval(interval: str) -> str:
    value = str(interval or "60").strip().lower()
    if not value:
        return "k60"
    if value == "s1":
        return "s1"
    if value.startswith("k"):
        return value
    return f"k{value}"


def _websocket_device_id(ws: Any) -> str:
    headers = getattr(ws, "request_headers", {}) if hasattr(ws, "request_headers") else {}
    if hasattr(headers, "get"):
        for key in ("X-Ava-Device-Id", "x-ava-device-id"):
            value = headers.get(key)
            if value:
                return normalize_device_id(value)
    return "default"


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
    manager: RuntimeManager | None = None,
    providers: ProviderBundle | None = None,
) -> None:
    try:
        import websockets
    except ImportError as exc:  # pragma: no cover - optional dependency boundary
        raise RuntimeError("Install websockets or ava-devicekit[websocket] to run the legacy-firmware-compatible gateway") from exc

    settings = runtime_settings or RuntimeSettings.load()
    providers = providers or create_provider_bundle(settings)
    manager = manager or runtime_manager_for_settings(
        settings,
        app_id=app_id,
        manifest_path=manifest_path,
        adapter=adapter,
        mock=mock,
        skill_store_path=skill_store_path,
    )

    async def handler(ws: Any) -> None:
        device_id = _websocket_device_id(ws)
        session = manager.get(device_id)
        audio = AudioInputBuffer(decoder=create_audio_decoder(settings.audio_decoder_class, settings.audio_decoder_options))
        await LegacyFirmwareConnection(session, voice_pipeline=providers.pipeline, asr_provider=providers.asr, audio=audio, manager=manager, device_id=device_id).open(ws)

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
