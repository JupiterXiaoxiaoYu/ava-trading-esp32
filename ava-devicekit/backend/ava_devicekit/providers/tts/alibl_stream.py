from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from ava_devicekit.providers.tts.base import TTSResult


@dataclass(slots=True)
class AliBLTTSConfig:
    """Alibaba Bailian CosyVoice WebSocket TTS configuration."""

    api_key_env: str = "ALIBL_TTS_API_KEY"
    ws_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/inference/"
    model: str = "cosyvoice-v2"
    voice: str = "longcheng_v2"
    response_format: str = "opus"
    sample_rate: int = 16000
    volume: int = 50
    rate: float = 1.0
    pitch: float = 1.0
    timeout_sec: int = 30
    data_inspection: str = "enable"


class AliBLTTSProvider:
    """Aliyun Bailian CosyVoice TTS provider.

    This mirrors the original Ava server's `AliBLTTS` settings while exposing it
    through the DeviceKit `TTSProvider` boundary. It asks Bailian for device-
    playable audio directly, so the gateway does not need the old server's OPUS
    encoder pipeline.
    """

    name = "alibl-tts"

    def __init__(self, config: AliBLTTSConfig | None = None):
        self.config = config or AliBLTTSConfig()

    def synthesize(self, text: str, *, voice: str = "") -> TTSResult:
        api_key = os.environ.get(self.config.api_key_env, "")
        if not api_key:
            raise RuntimeError(f"missing API key env: {self.config.api_key_env}")
        return _run_coro_sync(self._synthesize(text, api_key=api_key, voice=voice or self.config.voice))

    async def _synthesize(self, text: str, *, api_key: str, voice: str) -> TTSResult:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - optional dependency boundary
            raise RuntimeError("Install websockets or ava-devicekit[websocket] to use AliBL TTS") from exc

        task_id = uuid.uuid4().hex
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-DashScope-DataInspection": self.config.data_inspection,
        }
        chunks: list[bytes] = []
        async with websockets.connect(
            self.config.ws_url,
            additional_headers=headers,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=10,
            max_size=10 * 1024 * 1024,
        ) as ws:
            await ws.send(json.dumps(self._run_task(task_id, voice), ensure_ascii=False, separators=(",", ":")))
            await self._wait_for_event(ws, "task-started")
            filtered = _clean_text(text)
            if filtered:
                await ws.send(json.dumps(self._continue_task(task_id, filtered), ensure_ascii=False, separators=(",", ":")))
            await ws.send(json.dumps(self._finish_task(task_id), ensure_ascii=False, separators=(",", ":")))
            await self._collect_audio(ws, chunks)
        return TTSResult(text=text, audio=b"".join(chunks), content_type=_content_type(self.config.response_format))

    def _run_task(self, task_id: str, voice: str) -> dict[str, Any]:
        return {
            "header": {"action": "run-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {
                "task_group": "audio",
                "task": "tts",
                "function": "SpeechSynthesizer",
                "model": self.config.model,
                "parameters": {
                    "text_type": "PlainText",
                    "voice": voice,
                    "format": self.config.response_format,
                    "sample_rate": self.config.sample_rate,
                    "volume": self.config.volume,
                    "rate": self.config.rate,
                    "pitch": self.config.pitch,
                },
                "input": {},
            },
        }

    @staticmethod
    def _continue_task(task_id: str, text: str) -> dict[str, Any]:
        return {
            "header": {"action": "continue-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {"input": {"text": text}},
        }

    @staticmethod
    def _finish_task(task_id: str) -> dict[str, Any]:
        return {
            "header": {"action": "finish-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {"input": {}},
        }

    async def _wait_for_event(self, ws: Any, event: str) -> None:
        deadline = asyncio.get_running_loop().time() + self.config.timeout_sec
        while asyncio.get_running_loop().time() < deadline:
            msg = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - asyncio.get_running_loop().time()))
            if isinstance(msg, (bytes, bytearray)):
                continue
            header = json.loads(msg).get("header", {})
            if header.get("event") == event:
                return
            if header.get("event") == "task-failed":
                raise RuntimeError(f"AliBL TTS failed: {header.get('error_code', 'unknown')} - {header.get('error_message', '')}")
        raise TimeoutError(f"timed out waiting for AliBL TTS event: {event}")

    async def _collect_audio(self, ws: Any, chunks: list[bytes]) -> None:
        deadline = asyncio.get_running_loop().time() + self.config.timeout_sec
        while asyncio.get_running_loop().time() < deadline:
            msg = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - asyncio.get_running_loop().time()))
            if isinstance(msg, (bytes, bytearray)):
                chunks.append(bytes(msg))
                continue
            header = json.loads(msg).get("header", {})
            if header.get("event") == "task-finished":
                return
            if header.get("event") == "task-failed":
                raise RuntimeError(f"AliBL TTS failed: {header.get('error_code', 'unknown')} - {header.get('error_message', '')}")
        raise TimeoutError("timed out waiting for AliBL TTS audio")


def _clean_text(text: str) -> str:
    text = re.sub(r"```.*?```", "", text or "", flags=re.S)
    text = re.sub(r"[`*_#>\[\](){}]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _content_type(fmt: str) -> str:
    return {
        "opus": "audio/opus",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "pcm": "audio/pcm",
    }.get(str(fmt or "").lower(), "application/octet-stream")


def _run_coro_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - re-raised in caller thread
            result["error"] = exc

    thread = threading.Thread(target=_runner, name="alibl-tts", daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result["value"]
