from __future__ import annotations

import asyncio
import base64
import importlib
from dataclasses import dataclass, field
from typing import Any

from ava_devicekit.providers.asr.audio import AudioDecoder, AudioFrame, Pcm16PassthroughDecoder
from ava_devicekit.providers.asr.base import ASRProvider, ASRResult
from ava_devicekit.providers.tts.base import TTSResult


@dataclass
class AudioInputBuffer:
    """Collects firmware audio frames and normalizes them to PCM16 for ASR."""

    decoder: AudioDecoder = field(default_factory=Pcm16PassthroughDecoder)
    format: str = "pcm16"
    sample_rate: int = 16000
    channels: int = 1
    chunks: list[bytes] = field(default_factory=list)

    def configure(self, params: dict[str, Any]) -> None:
        self.format = str(params.get("format") or self.format).lower()
        self.sample_rate = _int(params.get("sample_rate"), self.sample_rate)
        self.channels = _int(params.get("channels"), self.channels)

    def reset(self) -> None:
        self.chunks.clear()

    def append(self, data: bytes) -> None:
        if data:
            self.chunks.append(data)

    def pcm16(self) -> bytes:
        if not self.chunks:
            return b""
        decoded = [
            self.decoder.decode_to_pcm16(AudioFrame(chunk, format=self.format, sample_rate=self.sample_rate, channels=self.channels))
            for chunk in self.chunks
        ]
        return b"".join(decoded)

    def duration_seconds(self) -> float:
        if not self.chunks or self.sample_rate <= 0 or self.channels <= 0:
            return 0.0
        if self.format == "pcm16":
            return sum(len(chunk) for chunk in self.chunks) / float(self.sample_rate * self.channels * 2)
        return 0.0


async def transcribe_buffer(asr: ASRProvider | None, audio: AudioInputBuffer, *, language: str = "") -> ASRResult | None:
    if asr is None or not audio.chunks:
        return None
    pcm = audio.pcm16()
    if not pcm:
        return None
    return await asr.transcribe_pcm16(pcm, sample_rate=audio.sample_rate, language=language)


def tts_frames(result: TTSResult | None, *, session_id: str) -> list[dict[str, Any]]:
    if result is None or not result.audio:
        return []
    return [
        {
            "type": "tts",
            "state": "audio",
            "session_id": session_id,
            "text": result.text,
            "content_type": result.content_type,
            "audio": base64.b64encode(result.audio).decode("ascii"),
        }
    ]


def run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("cannot run async coroutine synchronously while an event loop is already running") from None


def create_audio_decoder(class_path: str = "", options: dict[str, Any] | None = None) -> AudioDecoder:
    if not class_path:
        return Pcm16PassthroughDecoder()
    module_name, sep, attr = class_path.replace(":", ".").rpartition(".")
    if not sep:
        raise ValueError(f"invalid audio decoder class path: {class_path}")
    cls = getattr(importlib.import_module(module_name), attr)
    try:
        return cls(**(options or {}))
    except TypeError:
        return cls(options or {})


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
