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
