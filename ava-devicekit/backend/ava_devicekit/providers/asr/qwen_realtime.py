from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any

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

    async def transcribe_pcm16(self, audio: bytes, *, sample_rate: int = 16000, language: str = "zh") -> ASRResult:
        raise RuntimeError(
            "Live Qwen realtime ASR transport is deployment-owned. Use url(), headers(), "
            "session_update_event(), and audio_append_event() to wire the WebSocket client."
        )

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
