from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

from ava_devicekit.providers.tts.base import TTSResult


@dataclass(slots=True)
class OpenAICompatibleTTSConfig:
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "gpt-4o-mini-tts"
    voice: str = "alloy"
    response_format: str = "opus"
    timeout_sec: int = 30


class OpenAICompatibleTTSProvider:
    """HTTP TTS provider for OpenAI-compatible `/audio/speech` APIs."""

    name = "openai-compatible-tts"

    def __init__(self, config: OpenAICompatibleTTSConfig | None = None):
        self.config = config or OpenAICompatibleTTSConfig()

    def synthesize(self, text: str, *, voice: str = "") -> TTSResult:
        api_key = os.environ.get(self.config.api_key_env, "")
        if not api_key:
            raise RuntimeError(f"missing API key env: {self.config.api_key_env}")
        payload = {
            "model": self.config.model,
            "voice": voice or self.config.voice,
            "input": text,
            "response_format": self.config.response_format,
        }
        req = urllib.request.Request(
            self.config.base_url.rstrip("/") + "/audio/speech",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
            audio = resp.read()
            content_type = resp.headers.get("Content-Type") or _content_type(self.config.response_format)
        return TTSResult(text=text, audio=audio, content_type=content_type)


def _content_type(fmt: str) -> str:
    return {
        "opus": "audio/opus",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "pcm": "audio/pcm",
    }.get(fmt, "application/octet-stream")
