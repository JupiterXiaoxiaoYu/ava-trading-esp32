from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

EVENT_DEVICE_CONNECTED = "device.connected"
EVENT_DEVICE_DISCONNECTED = "device.disconnected"
EVENT_SCREEN_CHANGED = "screen.changed"
EVENT_CONTEXT_UPDATED = "context.updated"
EVENT_OUTBOUND_QUEUED = "outbound.queued"
EVENT_OUTBOUND_SENT = "outbound.sent"
EVENT_OUTBOUND_ACKED = "outbound.acked"
EVENT_PROVIDER_ERROR = "provider.error"
EVENT_MARKET_EVENT = "market.event"

STANDARD_EVENT_NAMES = frozenset(
    {
        EVENT_DEVICE_CONNECTED,
        EVENT_DEVICE_DISCONNECTED,
        EVENT_SCREEN_CHANGED,
        EVENT_CONTEXT_UPDATED,
        EVENT_OUTBOUND_QUEUED,
        EVENT_OUTBOUND_SENT,
        EVENT_OUTBOUND_ACKED,
        EVENT_PROVIDER_ERROR,
        EVENT_MARKET_EVENT,
    }
)

RuntimeEventHandler = Callable[["RuntimeEvent"], None]


@dataclass(slots=True)
class RuntimeEvent:
    ts: float
    device_id: str
    event: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ts": self.ts, "device_id": self.device_id, "event": self.event, "payload": dict(self.payload)}


class RuntimeEventBus:
    """Small synchronous event bus with an in-memory event log."""

    def __init__(self, *, max_events: int = 1000, clock: Callable[[], float] | None = None):
        self.max_events = max(1, int(max_events))
        self._clock = clock or time.time
        self.events: list[RuntimeEvent] = []
        self._subscribers: dict[str | None, list[RuntimeEventHandler]] = {}

    def subscribe(self, handler: RuntimeEventHandler, event: str | None = None) -> Callable[[], None]:
        """Subscribe to one event name, or all events when event is None."""
        handlers = self._subscribers.setdefault(event, [])
        handlers.append(handler)

        def unsubscribe() -> None:
            self.unsubscribe(handler, event)

        return unsubscribe

    def unsubscribe(self, handler: RuntimeEventHandler, event: str | None = None) -> None:
        handlers = self._subscribers.get(event)
        if not handlers:
            return
        self._subscribers[event] = [item for item in handlers if item is not handler]
        if not self._subscribers[event]:
            self._subscribers.pop(event, None)

    def emit(self, device_id: str, event: str, payload: dict[str, Any] | None = None) -> RuntimeEvent:
        row = RuntimeEvent(self._clock(), _normalize_device_id(device_id), str(event), dict(payload or {}))
        self.events.append(row)
        if len(self.events) > self.max_events:
            del self.events[: len(self.events) - self.max_events]
        self._notify(row)
        return row

    # Back-compatible alias for older manager code/tests that record events.
    record = emit

    def event_log(self, *, device_id: str = "", event: str = "", limit: int = 100) -> dict[str, Any]:
        rows = self.events
        if device_id:
            normalized = _normalize_device_id(device_id)
            rows = [row for row in rows if row.device_id == normalized]
        if event:
            rows = [row for row in rows if row.event == event]
        rows = rows[-max(1, int(limit)) :]
        return {"items": [row.to_dict() for row in rows], "count": len(rows)}

    def device_connected(self, device_id: str, **payload: Any) -> RuntimeEvent:
        return self.emit(device_id, EVENT_DEVICE_CONNECTED, payload)

    def device_disconnected(self, device_id: str, **payload: Any) -> RuntimeEvent:
        return self.emit(device_id, EVENT_DEVICE_DISCONNECTED, payload)

    def screen_changed(self, device_id: str, *, screen: str, previous_screen: str = "", **payload: Any) -> RuntimeEvent:
        data = {"screen": screen, **({"previous_screen": previous_screen} if previous_screen else {}), **payload}
        return self.emit(device_id, EVENT_SCREEN_CHANGED, data)

    def context_updated(self, device_id: str, context: dict[str, Any], **payload: Any) -> RuntimeEvent:
        return self.emit(device_id, EVENT_CONTEXT_UPDATED, {"context": dict(context), **payload})

    def outbound_queued(self, device_id: str, outbound: dict[str, Any], **payload: Any) -> RuntimeEvent:
        return self.emit(device_id, EVENT_OUTBOUND_QUEUED, {"outbound": dict(outbound), **payload})

    def outbound_sent(self, device_id: str, outbound: dict[str, Any] | None = None, **payload: Any) -> RuntimeEvent:
        data = {**({"outbound": dict(outbound)} if outbound is not None else {}), **payload}
        return self.emit(device_id, EVENT_OUTBOUND_SENT, data)

    def outbound_acked(self, device_id: str, ack: dict[str, Any] | None = None, **payload: Any) -> RuntimeEvent:
        data = {**({"ack": dict(ack)} if ack is not None else {}), **payload}
        return self.emit(device_id, EVENT_OUTBOUND_ACKED, data)

    def provider_error(self, device_id: str, provider: str, error: Exception | str, **payload: Any) -> RuntimeEvent:
        data = {"provider": provider, "error": str(error), **payload}
        return self.emit(device_id, EVENT_PROVIDER_ERROR, data)

    def market_event(self, device_id: str, market: dict[str, Any], **payload: Any) -> RuntimeEvent:
        return self.emit(device_id, EVENT_MARKET_EVENT, {"market": dict(market), **payload})

    def _notify(self, row: RuntimeEvent) -> None:
        for handler in [*self._subscribers.get(row.event, []), *self._subscribers.get(None, [])]:
            handler(row)


def _normalize_device_id(device_id: str | None) -> str:
    text = str(device_id or "default").strip()
    return text or "default"
