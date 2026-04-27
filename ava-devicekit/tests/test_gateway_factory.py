from __future__ import annotations

from pathlib import Path

from ava_devicekit.adapters.registry import default_adapter_registry
from ava_devicekit.gateway.factory import create_device_session

ROOT = Path(__file__).resolve().parents[1]


def test_adapter_registry_exposes_real_and_mock_solana():
    registry = default_adapter_registry()
    assert registry.names() == ["mock_solana", "solana"]
    assert registry.create("mock-solana").chain == "solana"


def test_factory_loads_ava_box_with_mock_adapter():
    session = create_device_session(mock=True)
    assert session.app.manifest.app_id == "ava_box"
    assert session.boot()["screen"] == "feed"
    assert session.snapshot()["chain"] == "solana"


def test_factory_accepts_explicit_manifest_and_skill_store(tmp_path):
    session = create_device_session(
        manifest_path=ROOT / "apps" / "ava_box" / "manifest.json",
        mock=True,
        skill_store_path=str(tmp_path / "skills.json"),
    )
    session.boot()
    added = session.handle({"type": "key_action", "action": "favorite"})
    assert added["screen"] == "notify"
    watchlist = session.handle({"type": "key_action", "action": "watchlist"})
    assert watchlist["screen"] == "feed"
    assert watchlist["data"]["mode"] == "watchlist"


def test_voice_command_uses_device_selection_context():
    session = create_device_session(mock=True)
    draft = session.handle(
        {
            "type": "listen_detect",
            "text": "buy",
            "context": {
                "screen": "spotlight",
                "selected": {
                    "token_id": "So11111111111111111111111111111111111111112-solana",
                    "addr": "So11111111111111111111111111111111111111112",
                    "chain": "solana",
                    "symbol": "SOL",
                },
            },
        }
    )
    assert draft["screen"] == "confirm"
    assert draft["action_draft"]["summary"]["symbol"] == "SOL"

from ava_devicekit.runtime.settings import RuntimeSettings


def test_runtime_settings_builds_ava_box_custodial_skill_config():
    settings = RuntimeSettings.from_dict({"execution": {"mode": "custodial", "proxy_wallet_id_env": "WALLET_ID", "secret_key_env": "SECRET"}})
    config = settings.ava_box_skill_config(store_path="state.json")
    assert config.execution_mode == "custodial"
    assert config.proxy_wallet_id_env == "WALLET_ID"
    assert config.execution_secret_key_env == "SECRET"
    assert config.store_path == "state.json"
