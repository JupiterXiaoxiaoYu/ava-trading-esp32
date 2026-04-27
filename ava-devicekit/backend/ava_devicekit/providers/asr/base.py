from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class ASRResult:
    text: str
    language: str = ""
    confidence: float | None = None


class ASRProvider(Protocol):
    name: str

    async def transcribe_pcm16(self, audio: bytes, *, sample_rate: int = 16000, language: str = "zh") -> ASRResult:
        raise NotImplementedError
