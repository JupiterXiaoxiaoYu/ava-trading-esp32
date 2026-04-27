from __future__ import annotations

from dataclasses import dataclass

from ava_devicekit.core.types import AppContext
from ava_devicekit.providers.llm.base import LLMMessage, LLMProvider
from ava_devicekit.providers.tts.base import TTSProvider, TTSResult
from ava_devicekit.providers.tts.mock import MockTTSProvider


@dataclass(slots=True)
class VoicePipelineResult:
    text: str
    tts: TTSResult | None = None


class VoicePipeline:
    """Minimal voice fallback pipeline for DeviceKit apps.

    Deterministic app actions should route before this class. The pipeline is
    used only when an app returns a model-fallback notification.
    """

    def __init__(self, llm: LLMProvider | None = None, tts: TTSProvider | None = None):
        self.llm = llm
        self.tts = tts or MockTTSProvider()

    def reply(self, user_text: str, *, context: AppContext | None = None) -> VoicePipelineResult:
        if self.llm:
            result = self.llm.complete(_messages(user_text, context))
            text = result.text.strip() or "OK"
        else:
            text = _deterministic_fallback(user_text, context)
        return VoicePipelineResult(text=text, tts=self.tts.synthesize(text))


def _messages(user_text: str, context: AppContext | None) -> list[LLMMessage]:
    selected = context.selected.to_dict() if context and context.selected else {}
    system = (
        "You are Ava, a concise Solana hardware app assistant. "
        "Use the provided screen and selected-token context when answering. "
        "Do not claim execution unless a device confirmation occurred."
    )
    ctx = f"screen={context.screen if context else ''}; selected={selected}"
    return [LLMMessage("system", system), LLMMessage("user", ctx + "\n" + user_text)]


def _deterministic_fallback(user_text: str, context: AppContext | None) -> str:
    if context and context.selected:
        sym = context.selected.symbol or "this token"
        return f"I am on {context.screen or 'the current screen'} with {sym} selected."
    return "I can help with token discovery, watchlists, portfolio views, and draft actions."
