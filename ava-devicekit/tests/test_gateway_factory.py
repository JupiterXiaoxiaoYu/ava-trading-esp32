from __future__ import annotations

from pathlib import Path
import sys
import types

from ava_devicekit.adapters.registry import default_adapter_registry
from ava_devicekit.core.types import AppContext
from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.screen import builders

ROOT = Path(__file__).resolve().parents[1]


def test_adapter_registry_exposes_real_and_mock_solana():
    registry = default_adapter_registry()
    assert registry.names() == ["mock_solana", "solana"]
    assert registry.create("mock-solana").chain == "solana"


def test_adapter_registry_loads_custom_chain_adapter():
    module = types.ModuleType("_ava_test_adapters")

    class CustomAdapter:
        chain = "custom"

        def __init__(self, label="CUSTOM"):
            self.label = label

        def get_feed(self, *, topic: str = "trending", platform: str = "", context: AppContext | None = None):
            return builders.feed([], chain=self.chain, source_label=self.label, context=context)

        def search_tokens(self, keyword: str, *, context: AppContext | None = None):
            return builders.feed([], chain=self.chain, source_label="SEARCH", context=context)

        def get_token_detail(self, token_id: str, *, interval: str = "60", context: AppContext | None = None):
            return builders.spotlight({"symbol": token_id or "TOKEN", "chain": self.chain}, context=context)

    module.CustomAdapter = CustomAdapter
    sys.modules[module.__name__] = module

    adapter = default_adapter_registry().create("custom", class_path="_ava_test_adapters.CustomAdapter", options={"label": "ALT"})
    assert adapter.chain == "custom"
    assert adapter.get_feed().payload["source_label"] == "ALT"


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


def test_factory_passes_custom_adapter_options():
    module = types.ModuleType("_ava_test_factory_adapters")

    class CustomAdapter:
        chain = "solana"

        def __init__(self, label="CUSTOM"):
            self.label = label

        def get_feed(self, *, topic: str = "trending", platform: str = "", context: AppContext | None = None):
            return builders.feed([], chain="solana", source_label=self.label, context=context)

        def search_tokens(self, keyword: str, *, context: AppContext | None = None):
            return builders.feed([], chain="solana", source_label="SEARCH", context=context)

        def get_token_detail(self, token_id: str, *, interval: str = "60", context: AppContext | None = None):
            return builders.spotlight({"symbol": "CUSTOM", "chain": "solana"}, context=context)

    module.CustomAdapter = CustomAdapter
    sys.modules[module.__name__] = module

    session = create_device_session(
        adapter="custom",
        adapter_options={"class_path": "_ava_test_factory_adapters.CustomAdapter", "options": {"label": "ALT-FEED"}},
    )
    assert session.boot()["data"]["source_label"] == "ALT-FEED"


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
    assert draft["data"]["amount_usd"] == "$15"
    assert draft["data"]["out_amount"] == "750K BONK"
    buy_result = session.handle({"type": "confirm", "trade_id": draft["action_draft"]["request_id"]})
    assert buy_result["data"]["success"] is True
    assert buy_result["data"]["out_amount"] == "750K BONK"
    assert buy_result["data"]["amount_usd"] == "$15"

    portfolio = session.handle({"type": "key_action", "action": "portfolio"})
    data = portfolio["data"]
    assert portfolio["screen"] == "portfolio"
    assert isinstance(data["holdings"], list)
    assert {"total_usd", "pnl", "pnl_pct", "mode_label", "chain_label"} <= set(data)
    required = {"symbol", "avg_cost_usd", "value_usd", "pnl", "pnl_pct", "pnl_positive", "addr", "chain", "contract_tail", "source_tag", "balance_raw"}
    assert required <= set(data["holdings"][0])
    assert data["holdings"][0]["symbol"] == "SOL"
    assert data["holdings"][0]["source_tag"] == "native"
    assert data["holdings"][0]["value_usd"] == "0.9 SOL"
    token_holding = next(row for row in data["holdings"] if row["symbol"] == "BONK")
    assert token_holding["avg_cost_usd"] == "$0.00002"
    assert token_holding["value_usd"] == "$15.00"
    assert token_holding["pnl"] == "$0"

    sell_draft = session.handle({"type": "key_action", "action": "portfolio_sell", **token_holding})
    assert sell_draft["screen"] == "confirm"
    assert sell_draft["data"]["action"] == "SELL"
    assert sell_draft["data"]["amount_native"] == "750K BONK"
    assert sell_draft["data"]["out_amount"] == "0.1 SOL"
    sell_result = session.handle({"type": "confirm", "trade_id": sell_draft["action_draft"]["request_id"]})
    assert sell_result["data"]["success"] is True
    assert sell_result["data"]["out_amount"] == "0.1 SOL"
    portfolio_after_sell = session.handle({"type": "key_action", "action": "portfolio"})
    assert portfolio_after_sell["data"]["pnl_reason"] == "Cash: 1 SOL"


def test_portfolio_sell_legacy_na_position_removes_and_returns_to_portfolio(tmp_path):
    import json

    store_path = tmp_path / "skills.json"
    legacy_addr = "Legacy111"
    store_path.write_text(
        json.dumps(
            {
                "trade_mode": "paper",
                "paper_cash_sol": "0.9",
                "paper_starting_sol": "1",
                "paper_orders": [],
                "paper_positions": [
                    {
                        "symbol": "OLD",
                        "chain": "solana",
                        "token_id": f"{legacy_addr}-solana",
                        "amount": "0.1",
                        "value": "0.1 SOL",
                        "pnl": "$0",
                        "source": "paper",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    session = create_device_session(mock=True, skill_store_path=str(store_path))
    portfolio = session.handle({"type": "key_action", "action": "portfolio"})
    holding = next(row for row in portfolio["data"]["holdings"] if row["symbol"] == "OLD")
    assert holding["avg_cost_usd"] == "N/A"

    draft = session.handle(
        {
            "type": "key_action",
            "action": "portfolio_sell",
            "addr": legacy_addr,
            "chain": "solana",
            "symbol": "OLD",
            "balance_raw": "0.1",
        }
    )
    assert draft["screen"] == "confirm"
    result = session.handle({"type": "confirm", "trade_id": draft["action_draft"]["request_id"]})
    assert result["screen"] == "result"

    back = session.handle({"type": "key_action", "action": "back"})
    assert back["screen"] == "portfolio"
    assert back["data"]["holdings"][0]["symbol"] == "SOL"
    assert all(row["symbol"] != "OLD" for row in back["data"]["holdings"])


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


def test_voice_introduce_selected_token_uses_model_fallback():
    session = create_device_session(mock=True)
    reply = session.handle(
        {
            "type": "listen_detect",
            "text": "介绍一下这个币",
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
    assert reply["data"]["body"] == "Command routed to model fallback"

from ava_devicekit.runtime.settings import RuntimeSettings


def test_runtime_settings_builds_ava_box_custodial_skill_config():
    settings = RuntimeSettings.from_dict({"execution": {"mode": "custodial", "proxy_wallet_id_env": "WALLET_ID", "secret_key_env": "SECRET"}})
    config = settings.ava_box_skill_config(store_path="state.json")
    assert config.execution_mode == "custodial"
    assert config.proxy_wallet_id_env == "WALLET_ID"
    assert config.execution_secret_key_env == "SECRET"
    assert config.store_path == "state.json"


def test_runtime_settings_exposes_custom_adapter_and_execution_provider():
    settings = RuntimeSettings.from_dict(
        {
            "adapters": {"chain": {"provider": "custom", "class": "pkg.Adapter", "options": {"endpoint": "https://data.example"}}},
            "execution": {"mode": "custom", "class": "pkg.Executor", "options": {"endpoint": "https://exec.example"}},
        }
    )
    assert settings.chain_adapter == "custom"
    assert settings.chain_adapter_class == "pkg.Adapter"
    assert settings.chain_adapter_options == {"endpoint": "https://data.example"}
    config = settings.ava_box_skill_config()
    assert config.execution_mode == "custom"
    assert config.execution_provider_class == "pkg.Executor"
    assert config.execution_options == {"endpoint": "https://exec.example"}
