from __future__ import annotations

from ava_devicekit.providers.tts.base import TTSResult


class MockTTSProvider:
    name = "mock-tts"

    def synthesize(self, text: str, *, voice: str = "") -> TTSResult:
        return TTSResult(text=text, audio=b"", content_type="text/plain")
