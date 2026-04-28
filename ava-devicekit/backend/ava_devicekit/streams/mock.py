from __future__ import annotations

from ava_devicekit.streams.base import MarketStreamEvent, StreamSubscription
from ava_devicekit.formatting.numbers import format_money


class MockMarketStreamAdapter:
    name = "mock-market-stream"

    def __init__(self):
        self.subscriptions: list[StreamSubscription] = []
        self.prices: dict[str, float] = {}

    def subscribe(self, subscription: StreamSubscription) -> None:
        self.subscriptions.append(subscription)
        for token_id in subscription.token_ids:
            self.prices.setdefault(token_id, 1.0)

    def set_price(self, token_id: str, price: float) -> None:
        self.prices[token_id] = price

    def snapshot(self) -> list[MarketStreamEvent]:
        events: list[MarketStreamEvent] = []
        for sub in self.subscriptions:
            for token_id in sub.token_ids:
                price = self.prices.get(token_id, 1.0)
                events.append(MarketStreamEvent(sub.channel, token_id, {"price_raw": price, "price": format_money(price)}))
        return events
