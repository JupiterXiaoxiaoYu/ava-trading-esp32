from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class TTSResult:
    text: str
    audio: bytes = b""
    content_type: str = "audio/opus"


class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, *, voice: str = "") -> TTSResult:
        raise NotImplementedError
