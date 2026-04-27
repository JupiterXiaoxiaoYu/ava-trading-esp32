from __future__ import annotations

import base64
import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

from ava_devicekit.providers.asr.base import ASRResult


@dataclass(slots=True)
class QwenRealtimeASRConfig:
    api_key_env: str = "DASHSCOPE_API_KEY"
    model: str = "qwen3-asr-flash-realtime"
    base_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    language: str = "zh"
    sample_rate: int = 16000
    vad_threshold: float = 0.2
    silence_duration_ms: int = 800


class QwenRealtimeASRProvider:
    """Qwen realtime ASR adapter boundary.

    The provider is intentionally optional-dependency based. Deployments that
    need live ASR install `websocket-client`; tests can validate request payloads
    without opening a network connection.
    """

    name = "qwen3-asr-flash-realtime"

    def __init__(self, config: QwenRealtimeASRConfig | None = None):
        self.config = config or QwenRealtimeASRConfig()

    def url(self) -> str:
        return f"{self.config.base_url}?model={self.config.model}"

    def headers(self) -> list[str]:
        api_key = os.environ.get(self.config.api_key_env, "")
        return ["Authorization: Bearer " + api_key, "OpenAI-Beta: realtime=v1"]

    def session_update_event(self, *, event_id: str = "event_session_update") -> dict[str, Any]:
        return {
            "event_id": event_id,
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                "input_audio_format": "pcm",
                "sample_rate": self.config.sample_rate,
                "input_audio_transcription": {"language": self.config.language},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": self.config.vad_threshold,
                    "silence_duration_ms": self.config.silence_duration_ms,
                },
            },
        }

    def audio_append_event(self, audio: bytes, *, event_id: str) -> dict[str, Any]:
        return {
            "event_id": event_id,
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(audio).decode("ascii"),
        }

    def create_session(self, transport: RealtimeTransport) -> "QwenRealtimeASRSession":
        return QwenRealtimeASRSession(self, transport)

    async def transcribe_pcm16(self, audio: bytes, *, sample_rate: int = 16000, language: str = "zh") -> ASRResult:
        if sample_rate != self.config.sample_rate or language != self.config.language:
            self.config = QwenRealtimeASRConfig(
                api_key_env=self.config.api_key_env,
                model=self.config.model,
                base_url=self.config.base_url,
                language=language,
                sample_rate=sample_rate,
                vad_threshold=self.config.vad_threshold,
                silence_duration_ms=self.config.silence_duration_ms,
            )
        return await asyncio.to_thread(self._transcribe_pcm16_blocking, audio)

    def _transcribe_pcm16_blocking(self, audio: bytes) -> ASRResult:
        try:
            import websocket
        except ImportError as exc:  # pragma: no cover - optional dependency boundary
            raise RuntimeError("Install websocket-client to use Qwen realtime ASR transport") from exc
        ws = websocket.create_connection(self.url(), header=self.headers(), timeout=30)
        transport = WebSocketClientTransport(ws)
        session = self.create_session(transport)
        try:
            session.start()
            session.append(audio)
            session.commit()
            deadline = time.time() + 30
            while time.time() < deadline:
                result = session.receive_transcript(timeout=1)
                if result and result.text:
                    return result
        finally:
            session.close()
        return ASRResult(text="", language=self.config.language)

    def parse_transcript_event(self, message: str | dict[str, Any]) -> ASRResult | None:
        data = json.loads(message) if isinstance(message, str) else message
        text = _find_text(data)
        if not text:
            return None
        return ASRResult(text=text, language=self.config.language)


def _find_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("transcript", "text"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
        for item in value.values():
            found = _find_text(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_text(item)
            if found:
                return found
    return ""


class RealtimeTransport(Protocol):
    def send(self, payload: str) -> None:
        raise NotImplementedError

    def recv(self, timeout: float | None = None) -> str | bytes:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class WebSocketClientTransport:
    def __init__(self, ws: Any):
        self.ws = ws

    def send(self, payload: str) -> None:
        self.ws.send(payload)

    def recv(self, timeout: float | None = None) -> str | bytes:
        if timeout is not None and hasattr(self.ws, "settimeout"):
            self.ws.settimeout(timeout)
        return self.ws.recv()

    def close(self) -> None:
        self.ws.close()


class QwenRealtimeASRSession:
    """Stateful PCM16 streaming session for Qwen realtime ASR."""

    def __init__(self, provider: QwenRealtimeASRProvider, transport: RealtimeTransport):
        self.provider = provider
        self.transport = transport
        self.started = False
        self._seq = 0

    def start(self) -> None:
        self._send(self.provider.session_update_event(event_id=self._event_id("session")))
        self.started = True

    def append(self, audio: bytes) -> None:
        if not self.started:
            self.start()
        self._send(self.provider.audio_append_event(audio, event_id=self._event_id("audio")))

    def commit(self) -> None:
        self._send({"event_id": self._event_id("commit"), "type": "input_audio_buffer.commit"})

    def receive_transcript(self, *, timeout: float | None = None) -> ASRResult | None:
        raw = self.transport.recv(timeout)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        return self.provider.parse_transcript_event(raw)

    def close(self) -> None:
        self.transport.close()

    def _send(self, event: dict[str, Any]) -> None:
        self.transport.send(json.dumps(event, ensure_ascii=False, separators=(",", ":")))

    def _event_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}_{int(time.time() * 1000)}_{self._seq}"
