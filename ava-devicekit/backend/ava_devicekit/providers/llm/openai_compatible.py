from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

from ava_devicekit.providers.llm.base import LLMMessage, LLMResult


@dataclass(slots=True)
class OpenAICompatibleLLMConfig:
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "gpt-4o-mini"
    timeout_sec: int = 30
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None


class OpenAICompatibleLLMProvider:
    name = "openai-compatible"

    def __init__(self, config: OpenAICompatibleLLMConfig | None = None):
        self.config = config or OpenAICompatibleLLMConfig()

    def complete(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResult:
        api_key = os.environ.get(self.config.api_key_env, "")
        if not api_key:
            raise RuntimeError(f"missing API key env: {self.config.api_key_env}")
        payload = {
            "model": self.config.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "temperature": self.config.temperature if self.config.temperature is not None else temperature,
        }
        if self.config.max_tokens is not None:
            payload["max_tokens"] = self.config.max_tokens
        if self.config.top_p is not None:
            payload["top_p"] = self.config.top_p
        if self.config.frequency_penalty is not None:
            payload["frequency_penalty"] = self.config.frequency_penalty
        req = urllib.request.Request(
            self.config.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return LLMResult(text=str(text), raw=data)
