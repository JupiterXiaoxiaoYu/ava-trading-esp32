from __future__ import annotations

import json

from ava_devicekit.gateway.runtime_manager import RuntimeManager


def test_runtime_manager_keeps_independent_device_sessions():
    manager = RuntimeManager.for_app(mock=True)
    a = manager.boot("device-a")
    b = manager.boot("device-b")
    assert a["screen"] == "feed"
    assert b["screen"] == "feed"
    manager.handle("device-a", {"type": "key_action", "action": "watch"})
    assert manager.state("device-a")["screen"] == "spotlight"
    assert manager.state("device-b")["screen"] == "feed"
    assert len(manager.list_devices()) == 2
    assert manager.event_log()["count"] >= 3


def test_runtime_manager_persists_and_restores_device_context(tmp_path):
    state_store = tmp_path / "runtime-state"
    manager = RuntimeManager.for_app(mock=True, state_store_path=state_store)

    manager.boot("device-a")
    detail = manager.handle("device-a", {"type": "key_action", "action": "watch"})

    assert detail["screen"] == "spotlight"
    state_file = state_store / "device-a.json"
    persisted = json.loads(state_file.read_text(encoding="utf-8"))
    assert persisted["context"]["screen"] == "spotlight"
    assert persisted["last_screen"]["screen"] == "spotlight"

    restored = RuntimeManager.for_app(mock=True, state_store_path=state_store)
    assert restored.state("device-a")["screen"] == "spotlight"
    assert restored.state("device-a")["context"]["selected"]["symbol"] == "BONK"

    boot = restored.boot("device-a")
    assert boot["screen"] == "spotlight"
    assert boot["context"]["screen"] == "spotlight"

    back = restored.handle("device-a", {"type": "key_action", "action": "back"})
    assert back["screen"] == "feed"


def test_runtime_manager_state_store_is_per_device(tmp_path):
    state_store = tmp_path / "runtime-state.json"
    manager = RuntimeManager.for_app(mock=True, state_store_path=state_store)

    manager.boot("device-a")
    manager.handle("device-a", {"type": "key_action", "action": "watch"})
    manager.boot("device-b")

    assert (tmp_path / "runtime-state.device-a.json").exists()
    assert (tmp_path / "runtime-state.device-b.json").exists()

    restored = RuntimeManager.for_app(mock=True, state_store_path=state_store)
    assert restored.state("device-a")["screen"] == "spotlight"
    assert restored.state("device-b")["screen"] == "feed"


def test_runtime_manager_refreshes_external_state_changes(tmp_path):
    state_store = tmp_path / "runtime-state"
    first = RuntimeManager.for_app(mock=True, state_store_path=state_store)
    second = RuntimeManager.for_app(mock=True, state_store_path=state_store)

    first.boot("device-a")
    first.handle("device-a", {"type": "key_action", "action": "watch"})

    assert second.state("device-a")["screen"] == "spotlight"
    second.handle("device-a", {"type": "key_action", "action": "back"})

    assert first.state("device-a")["screen"] == "feed"


def test_runtime_manager_queues_cross_process_outbound_payloads(tmp_path):
    state_store = tmp_path / "runtime-state"
    http_side = RuntimeManager.for_app(mock=True, state_store_path=state_store, queue_outbound=True)
    ws_side = RuntimeManager.for_app(mock=True, state_store_path=state_store)

    http_side.boot("device-a")
    reply = http_side.handle("device-a", {"type": "key_action", "action": "watch"})
    assert reply["screen"] == "spotlight"

    queued = ws_side.pop_queued_outbound("device-a")
    assert [item["screen"] for item in queued] == ["spotlight"]
    assert ws_side.pop_queued_outbound("device-a") == []
    assert ws_side.state("device-a")["screen"] == "spotlight"


def test_runtime_manager_outbound_ack_and_retry(tmp_path):
    state_store = tmp_path / "runtime-state"
    manager = RuntimeManager.for_app(mock=True, state_store_path=state_store, queue_outbound=True)

    manager.boot("device-a")
    manager.handle("device-a", {"type": "key_action", "action": "watch"})
    first = manager.lease_queued_outbound("device-a", visibility_timeout_sec=60)
    assert len(first) == 1
    assert first[0]["ack_required"] is True
    message_id = first[0]["message_id"]

    assert manager.lease_queued_outbound("device-a", visibility_timeout_sec=60) == []
    assert manager.ack_outbound("device-a", message_id) is True
    assert manager.lease_queued_outbound("device-a", visibility_timeout_sec=0) == []


def test_runtime_manager_queues_ota_check_command(tmp_path):
    state_store = tmp_path / "runtime-state"
    manager = RuntimeManager.for_app(mock=True, state_store_path=state_store)

    queued = manager.queue_ota_check("device-a")
    leased = manager.lease_queued_outbound("device-a", visibility_timeout_sec=0)

    assert queued["ok"] is True
    assert leased[0]["type"] == "device_command"
    assert leased[0]["command"] == "ota_check"
    assert leased[0]["ack_required"] is True


def test_runtime_manager_connection_registry(tmp_path):
    state_store = tmp_path / "runtime-state"
    manager = RuntimeManager.for_app(mock=True, state_store_path=state_store)

    state = manager.register_connection("device-a", transport="legacy_ws", session_id="s1")
    assert state["connected"] is True
    assert manager.connection_state("device-a")["transport"] == "legacy_ws"
    assert manager.list_devices()[0]["connection"]["connected"] is True

    manager.unregister_connection("device-a", reason="closed")
    assert manager.connection_state("device-a")["connected"] is False
    assert manager.event_log()["items"][-1]["event"] == "device.disconnected"


def test_runtime_manager_emits_framework_runtime_events(tmp_path):
    state_store = tmp_path / "runtime-state"
    manager = RuntimeManager.for_app(mock=True, state_store_path=state_store, queue_outbound=True)

    manager.register_connection("device-a", transport="websocket", session_id="session-1")
    manager.boot("device-a")
    manager.handle("device-a", {"type": "key_action", "action": "watch"})
    sent = manager.lease_queued_outbound("device-a")
    assert sent and sent[0]["ack_required"] is True
    assert manager.ack_outbound("device-a", sent[0]["message_id"])
    manager.unregister_connection("device-a", reason="closed")

    names = [item["event"] for item in manager.event_log(device_id="device-a", limit=20)["items"]]
    assert "device.connected" in names
    assert "screen.changed" in names
    assert "context.updated" in names
    assert "outbound.queued" in names
    assert "outbound.sent" in names
    assert "outbound.acked" in names
    assert "device.disconnected" in names

    screen_events = manager.event_log(device_id="device-a", event="screen.changed", limit=10)["items"]
    assert [item["payload"]["screen"] for item in screen_events] == ["feed", "spotlight"]
