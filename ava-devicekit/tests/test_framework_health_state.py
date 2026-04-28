from __future__ import annotations

import json

from ava_devicekit.gateway.runtime_manager import RuntimeManager
from ava_devicekit.providers.health import provider_health_report
from ava_devicekit.runtime.errors import ERROR_DEVICE_QUEUE_EXPIRED, ERROR_RUNTIME_STATE_INVALID
from ava_devicekit.runtime.settings import RuntimeSettings
from ava_devicekit.runtime.state import RUNTIME_STATE_VERSION, migrate_runtime_state


def test_provider_health_reports_missing_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = RuntimeSettings.from_dict({"providers": {"llm": {"provider": "openai", "api_key_env": "OPENAI_API_KEY"}}})

    report = provider_health_report(settings)

    llm = next(item for item in report["items"] if item["kind"] == "llm")
    assert report["ok"] is False
    assert llm["status"] == "missing_env"
    assert llm["configured"] is False


def test_runtime_state_migration_normalizes_old_shape():
    migrated, errors = migrate_runtime_state({"context": "bad", "last_screen": "bad"})

    assert errors == []
    assert migrated["version"] == RUNTIME_STATE_VERSION
    assert migrated["context"] == {}
    assert migrated["last_screen"] is None


def test_runtime_state_migration_reports_invalid_json_shape():
    migrated, errors = migrate_runtime_state([])

    assert migrated["version"] == RUNTIME_STATE_VERSION
    assert errors[0].code == ERROR_RUNTIME_STATE_INVALID


def test_runtime_manager_restores_old_state_without_crashing(tmp_path):
    state_store = tmp_path / "runtime-state"
    state_file = state_store / "device-a.json"
    state_store.mkdir()
    state_file.write_text(json.dumps({"context": "bad", "last_screen": "bad"}), encoding="utf-8")

    manager = RuntimeManager.for_app(mock=True, state_store_path=state_store)

    assert isinstance(manager.state("device-a"), dict)
    assert manager.boot("device-a")["screen"] == "feed"


def test_outbound_queue_expiry_emits_framework_error(tmp_path):
    manager = RuntimeManager.for_app(mock=True, state_store_path=tmp_path / "runtime-state", queue_outbound=True)

    manager.boot("device-a")
    manager.handle("device-a", {"type": "key_action", "action": "watch"})
    first = manager.lease_queued_outbound("device-a", visibility_timeout_sec=0, max_attempts=1)
    assert first
    assert manager.lease_queued_outbound("device-a", visibility_timeout_sec=0, max_attempts=1) == []

    errors = manager.event_log(device_id="device-a", event="runtime.error")["items"]
    assert errors[-1]["payload"]["error"]["code"] == ERROR_DEVICE_QUEUE_EXPIRED
