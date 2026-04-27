from __future__ import annotations

from ava_devicekit.streams.base import MarketStreamEvent, StreamSubscription


class MyMarketStreamAdapter:
    name = "my-market-stream"

    def __init__(self) -> None:
        self.subscriptions: list[StreamSubscription] = []

    def subscribe(self, subscription: StreamSubscription) -> None:
        self.subscriptions.append(subscription)

    def snapshot(self) -> list[MarketStreamEvent]:
        return []
