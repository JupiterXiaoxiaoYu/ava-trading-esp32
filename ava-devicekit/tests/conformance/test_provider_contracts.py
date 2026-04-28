from __future__ import annotations

from ava_devicekit.providers.asr.base import ASRResult
from ava_devicekit.providers.llm.base import LLMMessage, LLMResult
from ava_devicekit.providers.tts.base import TTSResult


class DemoASRProvider:
    name = "demo-asr"

    async def transcribe_pcm16(self, audio: bytes, *, sample_rate: int = 16000, language: str = "") -> ASRResult:
        return ASRResult(text="hello", language=language or "en")


class DemoLLMProvider:
    name = "demo-llm"

    def complete(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResult:
        assert messages
        return LLMResult(text="ok", raw={"temperature": temperature})


class DemoTTSProvider:
    name = "demo-tts"

    def synthesize(self, text: str, *, voice: str = "") -> TTSResult:
        return TTSResult(text=text, audio=b"voice", content_type="audio/opus")


def test_llm_provider_contract_shape():
    result = DemoLLMProvider().complete([LLMMessage(role="user", content="ping")])
    assert result.text == "ok"
    assert result.raw["temperature"] == 0.2


def test_tts_provider_contract_shape():
    result = DemoTTSProvider().synthesize("hello")
    assert result.text == "hello"
    assert result.audio == b"voice"
    assert result.content_type == "audio/opus"
