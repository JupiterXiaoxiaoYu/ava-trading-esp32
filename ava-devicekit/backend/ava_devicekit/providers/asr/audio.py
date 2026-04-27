from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class AudioFrame:
    data: bytes
    format: str = "pcm16"
    sample_rate: int = 16000
    channels: int = 1


class AudioDecoder(Protocol):
    name: str

    def decode_to_pcm16(self, frame: AudioFrame) -> bytes:
        raise NotImplementedError


class Pcm16PassthroughDecoder:
    name = "pcm16-passthrough"

    def decode_to_pcm16(self, frame: AudioFrame) -> bytes:
        if frame.format.lower() not in {"pcm", "pcm16", "s16le"}:
            raise ValueError(f"unsupported audio format for passthrough decoder: {frame.format}")
        return frame.data


class OpusDecoderPlaceholder:
    """Explicit extension point for deployments that receive OPUS from firmware."""

    name = "opus-decoder-placeholder"

    def decode_to_pcm16(self, frame: AudioFrame) -> bytes:
        raise RuntimeError("OPUS decode is deployment-owned; install/provide an AudioDecoder that returns PCM16 before ASR")
