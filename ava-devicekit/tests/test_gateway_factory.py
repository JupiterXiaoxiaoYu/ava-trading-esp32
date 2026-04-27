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


def test_ui_emitted_key_actions_are_routed_without_unknown_action(tmp_path):
    session = create_device_session(mock=True, skill_store_path=str(tmp_path / "skills.json"))
    feed = session.boot()
    token = feed["data"]["tokens"][0]
    token_payload = {
        "token_id": token["token_id"],
        "addr": token["addr"],
        "chain": token["chain"],
        "symbol": token["symbol"],
    }

    session.handle({"type": "key_action", "action": "favorite", **token_payload})
    session.handle({"type": "key_action", "action": "buy", **token_payload})

    cases = [
        {"type": "key_action", "action": "back"},
        {"type": "key_action", "action": "cancel_trade"},
        {"type": "key_action", "action": "feed_home"},
        {"type": "key_action", "action": "explorer_sync"},
        {"type": "key_action", "action": "trade_mode_set", "mode": "paper"},
        {"type": "key_action", "action": "feed_source", "source": "gainer"},
        {"type": "key_action", "action": "feed_platform", "platform": "pump_in_hot"},
        {"type": "key_action", "action": "feed_prev"},
        {"type": "key_action", "action": "feed_next"},
        {"type": "key_action", "action": "signals"},
        {"type": "key_action", "action": "signals_chain_cycle"},
        {"type": "key_action", "action": "watchlist"},
        {"type": "key_action", "action": "watchlist_chain_cycle"},
        {"type": "key_action", "action": "watchlist_remove", **token_payload},
        {"type": "key_action", "action": "watch", **token_payload},
        {"type": "key_action", "action": "quick_sell", **token_payload},
        {"type": "key_action", "action": "confirm"},
        {"type": "key_action", "action": "cancel"},
        {"type": "key_action", "action": "kline_interval", **token_payload, "interval": "240"},
        {"type": "key_action", "action": "disambiguation_select", **token_payload, "cursor": "0"},
        {"type": "key_action", "action": "portfolio_watch", **token_payload},
        {"type": "key_action", "action": "portfolio_activity_detail", **token_payload},
        {"type": "key_action", "action": "portfolio_sell", **token_payload, "balance_raw": "1.0"},
        {"type": "key_action", "action": "portfolio_chain_cycle"},
        {"type": "key_action", "action": "orders"},
        {"type": "key_action", "action": "portfolio"},
    ]

    for message in cases:
        reply = session.handle(message)
        data = reply.get("data", {})
        assert not (reply.get("screen") == "notify" and data.get("title") == "Unknown action"), message


def test_portfolio_payload_matches_device_screen_contract(tmp_path):
    session = create_device_session(mock=True, skill_store_path=str(tmp_path / "skills.json"))
    feed = session.boot()
    token = feed["data"]["tokens"][0]
    draft = session.handle({"type": "key_action", "action": "buy", **token})
    session.handle({"type": "confirm", "trade_id": draft["action_draft"]["request_id"]})

    portfolio = session.handle({"type": "key_action", "action": "portfolio"})
    data = portfolio["data"]
    assert portfolio["screen"] == "portfolio"
    assert isinstance(data["holdings"], list)
    assert {"total_usd", "pnl", "pnl_pct", "mode_label", "chain_label"} <= set(data)
    required = {"symbol", "avg_cost_usd", "value_usd", "pnl", "pnl_pct", "pnl_positive", "addr", "chain", "contract_tail", "source_tag", "balance_raw"}
    assert required <= set(data["holdings"][0])


def test_legacy_screen_context_token_is_treated_as_selected():
    session = create_device_session(mock=True)
    reply = session.handle(
        {
            "type": "listen_detect",
            "text": "buy",
            "context": {
                "screen": "feed",
                "cursor": 0,
                "token": {
                    "addr": "So11111111111111111111111111111111111111112",
                    "chain": "solana",
                    "symbol": "SOL",
                },
            },
        }
    )
    assert reply["screen"] == "confirm"
    assert reply["action_draft"]["summary"]["symbol"] == "SOL"


def test_generic_input_event_routes_semantic_action_with_context():
    session = create_device_session(mock=True)
    reply = session.handle(
        {
            "type": "input_event",
            "source": "joystick",
            "kind": "press",
            "code": "a",
            "semantic_action": "buy",
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
    assert reply["screen"] == "confirm"
    assert reply["action_draft"]["summary"]["symbol"] == "SOL"


def test_voice_can_add_selected_token_to_watchlist(tmp_path):
    session = create_device_session(mock=True, skill_store_path=str(tmp_path / "skills.json"))
    reply = session.handle(
        {
            "type": "listen_detect",
            "text": "收藏这个币",
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
    assert reply["screen"] == "notify"
    assert reply["data"]["title"] == "Watchlist"
    watchlist = session.handle({"type": "key_action", "action": "watchlist"})
    assert watchlist["data"]["tokens"][0]["symbol"] == "SOL"

from ava_devicekit.runtime.settings import RuntimeSettings


def test_runtime_settings_builds_ava_box_custodial_skill_config():
    settings = RuntimeSettings.from_dict({"execution": {"mode": "custodial", "proxy_wallet_id_env": "WALLET_ID", "secret_key_env": "SECRET"}})
    config = settings.ava_box_skill_config(store_path="state.json")
    assert config.execution_mode == "custodial"
    assert config.proxy_wallet_id_env == "WALLET_ID"
    assert config.execution_secret_key_env == "SECRET"
    assert config.store_path == "state.json"
