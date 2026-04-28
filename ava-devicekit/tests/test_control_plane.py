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
