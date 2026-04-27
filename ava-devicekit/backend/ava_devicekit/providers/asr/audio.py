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


class OpusLibDecoder:
    """Optional OPUS decoder using the `opuslib` package when deployments install it."""

    name = "opuslib"

    def __init__(self, frame_duration_ms: int = 60):
        self.frame_duration_ms = frame_duration_ms
        self._decoders = {}

    def decode_to_pcm16(self, frame: AudioFrame) -> bytes:
        try:
            import opuslib
        except ImportError as exc:  # pragma: no cover - optional dependency boundary
            raise RuntimeError("Install opuslib or configure a custom AudioDecoder to decode OPUS audio") from exc
        if frame.format.lower() not in {"opus", "ogg_opus"}:
            raise ValueError(f"unsupported audio format for OPUS decoder: {frame.format}")
        key = (frame.sample_rate, frame.channels)
        decoder = self._decoders.get(key)
        if decoder is None:
            decoder = opuslib.Decoder(frame.sample_rate, frame.channels)
            self._decoders[key] = decoder
        frame_size = int(frame.sample_rate * self.frame_duration_ms / 1000)
        return decoder.decode(frame.data, frame_size)
