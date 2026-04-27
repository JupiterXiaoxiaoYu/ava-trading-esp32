from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class LLMMessage:
    role: str
    content: str


@dataclass(slots=True)
class LLMResult:
    text: str
    raw: dict | None = None


class LLMProvider(Protocol):
    name: str

    def complete(self, messages: list[LLMMessage], *, temperature: float = 0.2) -> LLMResult:
        raise NotImplementedError
