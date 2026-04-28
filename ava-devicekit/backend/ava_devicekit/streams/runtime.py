from __future__ import annotations

from dataclasses import dataclass, field

from ava_devicekit.gateway.session import DeviceSession
from ava_devicekit.streams.base import MarketStreamAdapter, MarketStreamEvent, StreamSubscription


@dataclass
class MarketStreamRuntime:
    """Connects a MarketStreamAdapter to an app session without hardcoding a vendor."""

    adapter: MarketStreamAdapter
    subscriptions: list[StreamSubscription] = field(default_factory=list)

    def subscribe(self, subscription: StreamSubscription) -> None:
        if _subscription_key(subscription) in {_subscription_key(item) for item in self.subscriptions}:
            return
        self.subscriptions.append(subscription)
        self.adapter.subscribe(subscription)

    def subscribe_selected_price(self, session: DeviceSession) -> None:
        selected = session.app.context.selected
        if not selected or not selected.token_id:
            return
        self.subscribe(StreamSubscription("price", [selected.token_id], chain=selected.chain))

    def poll_once(self, session: DeviceSession) -> list[dict]:
        events = self.adapter.snapshot()
        return self.apply_events(session, events)

    def apply_events(self, session: DeviceSession, events: list[MarketStreamEvent]) -> list[dict]:
        apply = getattr(session.app, "apply_market_events", None)
        if not callable(apply):
            return []
        screen = apply(events)
        if not screen:
            return []
        return [session.emit(screen)]


def _subscription_key(subscription: StreamSubscription) -> tuple:
    return (
        subscription.channel,
        tuple(subscription.token_ids),
        subscription.interval,
        subscription.chain,
    )
