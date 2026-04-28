from __future__ import annotations

from ava_devicekit.runtime.events import (
    EVENT_CONTEXT_UPDATED,
    EVENT_DEVICE_CONNECTED,
    EVENT_DEVICE_DISCONNECTED,
    EVENT_MARKET_EVENT,
    EVENT_OUTBOUND_ACKED,
    EVENT_OUTBOUND_QUEUED,
    EVENT_OUTBOUND_SENT,
    EVENT_PROVIDER_ERROR,
    EVENT_RUNTIME_ERROR,
    EVENT_SCREEN_CHANGED,
    STANDARD_EVENT_NAMES,
    RuntimeEventBus,
)


def test_runtime_event_bus_records_typed_events_and_keeps_log_shape():
    now = iter([10.0, 11.0, 12.0])
    bus = RuntimeEventBus(max_events=2, clock=lambda: next(now))

    bus.device_connected(" device-a ", transport="websocket")
    bus.screen_changed("device-a", screen="feed")
    bus.context_updated("device-b", {"screen": "feed"})

    assert bus.event_log()["count"] == 2
    assert bus.event_log(device_id="device-a")["items"][0] == {
        "ts": 11.0,
        "device_id": "device-a",
        "event": EVENT_SCREEN_CHANGED,
        "payload": {"screen": "feed"},
    }
    assert bus.event_log(event=EVENT_CONTEXT_UPDATED)["items"][0]["payload"] == {"context": {"screen": "feed"}}


def test_runtime_event_bus_subscribes_to_specific_and_all_events():
    bus = RuntimeEventBus(clock=lambda: 1.0)
    all_events = []
    screen_events = []

    unsubscribe_all = bus.subscribe(all_events.append)
    unsubscribe_screen = bus.subscribe(screen_events.append, EVENT_SCREEN_CHANGED)

    bus.device_connected("device-a")
    bus.screen_changed("device-a", screen="feed")
    unsubscribe_screen()
    bus.screen_changed("device-a", screen="spotlight")
    unsubscribe_all()
    bus.device_disconnected("device-a")

    assert [event.event for event in all_events] == [EVENT_DEVICE_CONNECTED, EVENT_SCREEN_CHANGED, EVENT_SCREEN_CHANGED]
    assert [event.payload["screen"] for event in screen_events] == ["feed"]


def test_runtime_event_bus_exposes_all_standard_typed_helpers():
    bus = RuntimeEventBus(clock=lambda: 1.0)

    bus.device_connected("device-a")
    bus.device_disconnected("device-a", reason="closed")
    bus.screen_changed("device-a", screen="feed", previous_screen="boot")
    bus.context_updated("device-a", {"screen": "feed"})
    bus.outbound_queued("device-a", {"screen": "feed"}, message_id="msg_1")
    bus.outbound_sent("device-a", {"message_id": "msg_1"})
    bus.outbound_acked("device-a", {"message_id": "msg_1"})
    bus.provider_error("device-a", "llm", RuntimeError("boom"))
    bus.market_event("device-a", {"symbol": "SOL"})
    bus.runtime_error("device-a", {"code": "runtime.state.invalid"})

    names = [item["event"] for item in bus.event_log(limit=20)["items"]]
    assert names == [
        EVENT_DEVICE_CONNECTED,
        EVENT_DEVICE_DISCONNECTED,
        EVENT_SCREEN_CHANGED,
        EVENT_CONTEXT_UPDATED,
        EVENT_OUTBOUND_QUEUED,
        EVENT_OUTBOUND_SENT,
        EVENT_OUTBOUND_ACKED,
        EVENT_PROVIDER_ERROR,
        EVENT_MARKET_EVENT,
        EVENT_RUNTIME_ERROR,
    ]
    assert set(names) == STANDARD_EVENT_NAMES
