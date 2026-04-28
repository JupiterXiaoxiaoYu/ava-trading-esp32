from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ava_devicekit.core.types import AppContext
from ava_devicekit.providers.llm.base import LLMMessage, LLMProvider
from ava_devicekit.providers.tts.base import TTSProvider, TTSResult
from ava_devicekit.providers.tts.mock import MockTTSProvider

UsageRecorder = Callable[[str, str, float, str, dict[str, Any] | None], None]


@dataclass(slots=True)
class VoicePipelineResult:
    text: str
    tts: TTSResult | None = None


class VoicePipeline:
    """Minimal voice fallback pipeline for DeviceKit apps.

    Deterministic app actions should route before this class. The pipeline is
    used only when an app returns a model-fallback notification.
    """

    def __init__(self, llm: LLMProvider | None = None, tts: TTSProvider | None = None, usage_recorder: UsageRecorder | None = None):
        self.llm = llm
        self.tts = tts or MockTTSProvider()
        self.usage_recorder = usage_recorder

    def reply(self, user_text: str, *, context: AppContext | None = None, device_id: str = "") -> VoicePipelineResult:
        if self.llm:
            messages = _messages(user_text, context)
            result = self.llm.complete(messages)
            text = result.text.strip() or "OK"
            self.record_usage(
                device_id,
                "llm_tokens",
                _llm_token_usage(result.raw, messages, text),
                source="llm",
                metadata={"provider": getattr(self.llm, "name", "llm")},
            )
        else:
            text = _deterministic_fallback(user_text, context)
        tts = self.tts.synthesize(text)
        self.record_usage(
            device_id,
            "tts_chars",
            len(text),
            source="tts",
            metadata={"provider": getattr(self.tts, "name", "tts"), "content_type": tts.content_type},
        )
        return VoicePipelineResult(text=text, tts=tts)

    def record_usage(
        self,
        device_id: str,
        metric: str,
        amount: float,
        *,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.usage_recorder or not device_id or amount <= 0:
            return
        self.usage_recorder(device_id, metric, amount, source, metadata or {})


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


def _llm_token_usage(raw: dict | None, messages: list[LLMMessage], text: str) -> float:
    usage = raw.get("usage") if isinstance(raw, dict) else None
    if isinstance(usage, dict):
        for key in ("total_tokens", "completion_tokens"):
            try:
                value = float(usage.get(key) or 0)
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                return value
    chars = len(text) + sum(len(item.content) for item in messages)
    return max(1.0, round(chars / 4.0, 2))
