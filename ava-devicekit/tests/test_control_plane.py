from __future__ import annotations

from ava_devicekit.control_plane import ControlPlaneStore, control_plane_usage_recorder
from ava_devicekit.runtime.settings import RuntimeSettings


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


def test_control_plane_customer_registration_and_app_users(tmp_path):
    store = ControlPlaneStore(tmp_path / "control.json")
    project = store.create_project({"name": "Ava Box App", "app_id": "ava_box"})["project"]
    provisioned = store.provision_device({"device_id": "box-9", "project_id": project["project_id"], "app_id": "ava_box"})

    registered = store.register_customer(
        {
            "email": "buyer@example.com",
            "display_name": "Buyer",
            "wallet": "Wallet111",
            "app_id": "ava_box",
            "activation_code": provisioned["activation_code"],
        }
    )

    assert registered["customer"]["email"] == "buyer@example.com"
    assert registered["device"]["status"] == "active"
    assert "ava_box" in registered["customer"]["app_ids"]
    app_users = store.app_customers("ava_box")
    assert app_users["count"] == 1
    assert app_users["items"][0]["device_count"] == 1
    assert store.app_devices("ava_box")["items"][0]["device_id"] == "box_9"

    same = store.register_customer({"email": "buyer@example.com", "app_id": "ava_box"})
    assert same["customer"]["customer_id"] == registered["customer"]["customer_id"]


def test_control_plane_customer_session_token_and_activation(tmp_path):
    store = ControlPlaneStore(tmp_path / "control.json")
    provisioned = store.provision_device({"device_id": "portal-box", "app_id": "ava_box"})

    login = store.login_customer({"email": "portal@example.com", "display_name": "Portal User", "app_id": "ava_box"})
    assert login["customer_token"].startswith("avacus_")
    assert login["customer"]["email"] == "portal@example.com"
    assert "customer_token_hash" not in login["customer"]

    session = store.customer_session(login["customer_token"])
    assert session["customer"]["customer_id"] == login["customer"]["customer_id"]
    assert session["devices"] == []

    activated = store.activate_customer_device(login["customer"]["customer_id"], {"activation_code": provisioned["activation_code"]})
    assert activated["device"]["status"] == "active"
    assert activated["devices"][0]["device_id"] == "portal_box"

    public = store.snapshot()
    assert "customer_token_hash" not in public["customers"][0]


def test_control_plane_runtime_config_is_persisted_and_redacted(tmp_path):
    store = ControlPlaneStore(tmp_path / "control.json")
    result = store.update_runtime_config({"providers": {"llm": {"provider": "openai-compatible", "model": "x", "api_key_env": "OPENAI_API_KEY", "api_key": "raw"}}})
    assert result["runtime_config"]["providers"]["llm"]["model"] == "x"
    assert store.runtime_config()["providers"]["llm"]["api_key"] == "raw"
    public = store.snapshot()["runtime_config"]
    assert public["providers"]["llm"]["api_key"] == "<redacted>"


def test_control_plane_service_plan_entitlement_and_usage(tmp_path):
    store = ControlPlaneStore(tmp_path / "control.json")
    provisioned = store.provision_device({"device_id": "metered-box"})
    store.register_device({"provisioning_token": provisioned["provisioning_token"], "device_id": "metered-box"})
    plan = store.create_service_plan({"plan_id": "plan_small", "name": "Small", "limits": {"llm_tokens": 100, "api_calls": 2}})["service_plan"]
    assert plan["limits"]["llm_tokens"] == 100

    entitlement = store.set_device_entitlement("metered_box", {"plan_id": "plan_small", "status": "active"})
    assert entitlement["entitlement"]["plan_id"] == "plan_small"

    first = store.record_usage({"device_id": "metered_box", "metric": "llm_tokens", "amount": 40, "source": "test"})
    assert first["limit_status"]["ok"] is True
    second = store.record_usage({"device_id": "metered_box", "metric": "llm_tokens", "amount": 70, "source": "test"})
    assert second["limit_status"]["ok"] is False
    assert second["limit_status"]["reason"] == "limit_exceeded"

    report = store.usage_report(device_id="metered_box")
    assert report["items"][0]["usage"]["llm_tokens"] == 110
    assert report["items"][0]["limit_status"]["exceeded"] == ["llm_tokens"]
    assert store.snapshot()["counts"]["service_plans"] >= 3


def test_control_plane_usage_recorder_is_best_effort(tmp_path):
    settings = RuntimeSettings.from_dict({"control_plane": {"store_path": str(tmp_path / "control.json")}})
    store = ControlPlaneStore(settings.control_plane_store_path)
    provisioned = store.provision_device({"device_id": "voice-box"})
    store.register_device({"provisioning_token": provisioned["provisioning_token"], "device_id": "voice-box"})

    recorder = control_plane_usage_recorder(settings)
    recorder("voice_box", "tts_chars", 12, "tts", {"provider": "mock"})
    recorder("unknown_device", "tts_chars", 99, "tts", {})

    report = store.usage_report(device_id="voice_box")
    assert report["items"][0]["usage"]["tts_chars"] == 12
