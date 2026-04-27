from __future__ import annotations

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
