from __future__ import annotations

import asyncio
import io
import json
import os
import urllib.request
import uuid
import wave
from dataclasses import dataclass
from typing import Any

from ava_devicekit.providers.asr.base import ASRResult


@dataclass(slots=True)
class OpenAICompatibleASRConfig:
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "whisper-1"
    language: str = ""
    timeout_sec: int = 30
    response_format: str = "json"


class OpenAICompatibleASRProvider:
    """ASR provider for OpenAI-compatible `/audio/transcriptions` APIs.

    The DeviceKit ASR interface accepts PCM16. This provider wraps PCM16 in a
    temporary WAV payload before sending it to file-upload transcription APIs.
    """

    name = "openai-compatible-asr"

    def __init__(self, config: OpenAICompatibleASRConfig | None = None):
        self.config = config or OpenAICompatibleASRConfig()

    async def transcribe_pcm16(self, audio: bytes, *, sample_rate: int = 16000, language: str = "") -> ASRResult:
        return await asyncio.to_thread(self._transcribe_pcm16_blocking, audio, sample_rate, language)

    def _transcribe_pcm16_blocking(self, audio: bytes, sample_rate: int, language: str) -> ASRResult:
        api_key = os.environ.get(self.config.api_key_env, "")
        if not api_key:
            raise RuntimeError(f"missing API key env: {self.config.api_key_env}")
        body, content_type = _multipart_body(
            {
                "model": self.config.model,
                "response_format": self.config.response_format,
                "language": language or self.config.language,
            },
            file_field="file",
            filename="audio.wav",
            file_content=_pcm16_wav(audio, sample_rate=sample_rate),
            file_content_type="audio/wav",
        )
        req = urllib.request.Request(
            self.config.base_url.rstrip("/") + "/audio/transcriptions",
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": content_type},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = str(data.get("text") or data.get("transcript") or "")
        return ASRResult(text=text, language=language or self.config.language, confidence=_optional_float(data.get("confidence")))


def _pcm16_wav(audio: bytes, *, sample_rate: int, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio)
    return buf.getvalue()


def _multipart_body(fields: dict[str, Any], *, file_field: str, filename: str, file_content: bytes, file_content_type: str) -> tuple[bytes, str]:
    boundary = "----AvaDeviceKit" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for key, value in fields.items():
        if value in (None, ""):
            continue
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
            str(value).encode(),
            b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {file_content_type}\r\n\r\n".encode(),
        file_content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
