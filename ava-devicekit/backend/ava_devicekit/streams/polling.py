from __future__ import annotations

from ava_devicekit.adapters.base import ChainAdapter
from ava_devicekit.streams.base import MarketStreamEvent, StreamSubscription


class PollingMarketStreamAdapter:
    """Small polling-backed stream adapter for deployments without live WSS."""

    name = "polling-market-stream"

    def __init__(self, chain_adapter: ChainAdapter):
        self.chain_adapter = chain_adapter
        self.subscriptions: list[StreamSubscription] = []

    def subscribe(self, subscription: StreamSubscription) -> None:
        self.subscriptions.append(subscription)

    def snapshot(self) -> list[MarketStreamEvent]:
        events: list[MarketStreamEvent] = []
        for sub in self.subscriptions:
            if sub.channel != "price":
                continue
            for token_id in sub.token_ids:
                detail = self.chain_adapter.get_token_detail(token_id, interval=sub.interval)
                data = detail.payload
                events.append(MarketStreamEvent("price", token_id, {"price": data.get("price"), "price_raw": data.get("price_raw")}))
        return events
