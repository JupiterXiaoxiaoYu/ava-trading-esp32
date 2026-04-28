from __future__ import annotations

from ava_devicekit.control_plane import ControlPlaneStore


def test_control_plane_bootstrap_and_device_registration(tmp_path):
    store = ControlPlaneStore(tmp_path / "control.json")
    snapshot = store.bootstrap()
    assert snapshot["users"][0]["username"] == "admin"
    assert snapshot["projects"][0]["chain"] == "solana"

    user = store.create_user({"username": "builder", "role": "developer"})["user"]
    project = store.create_project({"name": "Proof Devices", "owner_user_id": user["user_id"], "chain": "solana"})["project"]
    provisioned = store.provision_device({"device_id": "ava-box-001", "project_id": project["project_id"], "owner_user_id": user["user_id"], "app_id": "solana_ai_depin_device"})

    assert provisioned["device"]["device_id"] == "ava_box_001"
    assert "provisioning_token" in provisioned
    registered = store.register_device({"provisioning_token": provisioned["provisioning_token"], "device_id": "ava-box-001", "firmware_version": "1.0.0"})
    assert registered["device"]["status"] == "registered"
    assert registered["device_token"].startswith("avadev_")
    assert store.validate_device_token("ava-box-001", registered["device_token"])
    assert not store.validate_device_token("ava-box-001", "wrong")

    safe = store.snapshot()
    device = safe["devices"][0] if safe["devices"][0]["device_id"] == "ava_box_001" else safe["devices"][1]
    assert "device_token_hash" not in device
    assert "provisioning_token_hash" not in device


def test_control_plane_customer_activation_config_and_revoke(tmp_path):
    store = ControlPlaneStore(tmp_path / "control.json")
    provisioned = store.provision_device({"device_id": "box-3", "ai_name": "Ava", "volume": 80})
    customer = store.create_customer({"email": "user@example.com", "display_name": "User"})["customer"]

    activated = store.activate_device({"activation_code": provisioned["activation_code"], "customer_id": customer["customer_id"]})
    assert activated["device"]["status"] == "active"
    assert activated["device"]["customer_id"] == customer["customer_id"]

    updated = store.update_device_config("box_3", {"wake_phrases": "hey ava,hi ava", "volume": 55})
    assert updated["config"]["wake_phrases"] == ["hey ava", "hi ava"]
    assert updated["config"]["volume"] == 55

    registered = store.register_device({"provisioning_token": provisioned["provisioning_token"], "device_id": "box-3"})
    assert store.validate_device_token("box_3", registered["device_token"])
    store.update_device_status("box_3", "revoked")
    assert not store.validate_device_token("box_3", registered["device_token"])


def test_control_plane_runtime_config_is_persisted_and_redacted(tmp_path):
    store = ControlPlaneStore(tmp_path / "control.json")
    result = store.update_runtime_config({"providers": {"llm": {"provider": "openai-compatible", "model": "x", "api_key_env": "OPENAI_API_KEY", "api_key": "raw"}}})
    assert result["runtime_config"]["providers"]["llm"]["model"] == "x"
    assert store.runtime_config()["providers"]["llm"]["api_key"] == "raw"
    public = store.snapshot()["runtime_config"]
    assert public["providers"]["llm"]["api_key"] == "<redacted>"
