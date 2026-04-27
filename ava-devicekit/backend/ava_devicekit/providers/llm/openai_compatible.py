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
            "temperature": temperature,
        }
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
