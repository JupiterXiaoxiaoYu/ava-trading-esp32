from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class StreamSubscription:
    channel: str
    token_ids: list[str] = field(default_factory=list)
    interval: str = "60"


@dataclass(slots=True)
class MarketStreamEvent:
    channel: str
    token_id: str
    data: dict[str, Any]


class MarketStreamAdapter(Protocol):
    name: str

    def subscribe(self, subscription: StreamSubscription) -> None:
        raise NotImplementedError

    def snapshot(self) -> list[MarketStreamEvent]:
        raise NotImplementedError
