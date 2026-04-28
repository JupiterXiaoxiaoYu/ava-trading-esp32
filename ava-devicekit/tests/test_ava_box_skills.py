from __future__ import annotations

import sys
import types

from ava_devicekit.apps.ava_box_skills import AvaBoxSkillConfig, AvaBoxSkillService
from ava_devicekit.core.types import AppContext, Selection


def test_watchlist_portfolio_and_trade_skills_are_app_layer(tmp_path):
    service = AvaBoxSkillService(AvaBoxSkillConfig(store_path=str(tmp_path / "state.json")))
    context = AppContext(
        app_id="ava_box",
        chain="solana",
        screen="feed",
        selected=Selection(
            token_id="Bonk111111111111111111111111111111111111111-solana",
            addr="Bonk111111111111111111111111111111111111111",
            chain="solana",
            symbol="BONK",
        ),
    )

    added = service.add_watchlist(context.selected.to_dict(), context=context)
    assert added.screen == "notify"
    watchlist = service.get_watchlist(context=context)
    assert watchlist.screen == "feed"
    assert watchlist.payload["mode"] == "watchlist"
    assert watchlist.payload["tokens"][0]["symbol"] == "BONK"

    portfolio = service.get_portfolio(context=context)
    assert portfolio.screen == "portfolio"
    assert "holdings" in portfolio.payload
    assert portfolio.payload["mode_label"] == "Paper"
    assert portfolio.payload["total_usd"] == "Funds 1 SOL"
    assert portfolio.payload["pnl_reason"] == "Cash: 1 SOL"

    draft = service.create_action_draft("buy", {}, context=context)
    assert draft.action == "trade.market_draft"
    assert draft.requires_confirmation is True
    assert draft.screen.screen == "confirm"

    result = service.confirm_action(draft.request_id, context=context)
    assert result.ok is True
    assert result.screen and result.screen.screen == "result"
    assert result.data["execution"]["status"] == "paper_filled"
    portfolio_after_trade = service.get_portfolio(context=context)
    assert portfolio_after_trade.payload["holdings"][0]["symbol"] == "SOL"
    assert portfolio_after_trade.payload["holdings"][0]["value_usd"] == "0.9 SOL"
    holding = next(row for row in portfolio_after_trade.payload["holdings"] if row["symbol"] == "BONK")
    assert holding["symbol"] == "BONK"
    assert holding["value_usd"]
    assert holding["balance_raw"]
    assert portfolio_after_trade.payload["total_usd"] == "Funds 1 SOL"
    assert portfolio_after_trade.payload["pnl_reason"] == "Cash: 0.9 SOL"
    orders = service.get_orders(context=context)
    assert orders.screen == "feed"
    assert orders.payload["mode"] == "orders"
    assert orders.payload["tokens"][0]["symbol"] == "BONK"

from ava_devicekit.apps.ava_box_skills.execution import AveSolanaTradeConfig, AveSolanaTradeProvider, build_create_solana_tx_payload
from ava_devicekit.apps.ava_box_skills.paper import PaperExecutionProvider
from ava_devicekit.storage.json_store import JsonStore


def test_ave_solana_trade_provider_builds_external_signing_payload(monkeypatch):
    payload = build_create_solana_tx_payload(
        {"action": "trade.limit_draft", "token_id": "So111-solana", "symbol": "SOL", "limit_price": "100"},
        {"amount_sol": "0.1", "request_id": "r1", "wallet": "wallet1"},
    )
    assert payload["type"] == "limit"
    assert payload["side"] == "buy"
    assert payload["wallet"] == "wallet1"

    monkeypatch.setenv("TEST_AVE_KEY", "secret")
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok":true,"tx":"unsigned"}'

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = req.data.decode()
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = AveSolanaTradeProvider(AveSolanaTradeConfig(base_url="https://trade.example", api_key_env="TEST_AVE_KEY"))
    response = provider.create_solana_tx(payload)
    assert captured["url"].endswith("/v1/thirdParty/chainWallet/createSolanaTx")
    assert response["tx"] == "unsigned"


def test_paper_execution_does_not_create_native_sol_position(tmp_path):
    store = JsonStore(tmp_path / "state.json")
    provider = PaperExecutionProvider(store)
    provider.execute(
        {
            "action": "trade.market_draft",
            "symbol": "SOL",
            "token_id": "So11111111111111111111111111111111111111112-solana",
            "amount": "0.1 SOL",
            "native_amount": "0.1",
            "amount_usd_raw": "15",
            "token_amount": "0.1",
            "price_usd": "150",
        },
        {"request_id": "native-sol"},
    )
    state = store.read({})
    assert state["paper_cash_sol"] == "1"
    assert state.get("paper_positions", []) == []
    assert state["paper_orders"][0]["symbol"] == "SOL"

from ava_devicekit.apps.ava_box_skills.trading import TradingSkill


class _SignedExecutor:
    def execute(self, summary, params):
        return {"status": "transaction_created", "request_id": params["request_id"]}

    def send_signed_solana_tx(self, request_id, signed_tx):
        return {"ok": True, "request_id": request_id, "signed_tx": signed_tx}


def test_trading_skill_submits_signed_transaction_with_external_executor():
    skill = TradingSkill(AvaBoxSkillConfig(execution_mode="ave_solana"), _SignedExecutor())
    result = skill.submit_signed("r1", "signed-payload")
    assert result.ok is True
    assert result.data["response"]["signed_tx"] == "signed-payload"


class _NamedExecutor:
    def __init__(self, name):
        self.name = name

    def execute(self, summary, params):
        return {"executor": self.name, "mode": params.get("execution_mode")}


def test_trading_skill_respects_paper_trade_mode_override():
    from ava_devicekit.apps.ava_box_skills.trading import TradingSkill

    context = AppContext(
        app_id="ava_box",
        chain="solana",
        screen="spotlight",
        selected=Selection(token_id="So111-solana", addr="So111", chain="solana", symbol="SOL"),
        state={"trade_mode": "paper"},
    )
    skill = TradingSkill(
        AvaBoxSkillConfig(execution_mode="custodial"),
        _NamedExecutor("real"),
        paper_executor=_NamedExecutor("paper"),
    )
    draft = skill.create_draft("buy", {}, context=context)
    result = skill.confirm(draft.request_id, context=context)
    assert result.ok is True
    assert result.data["execution"]["executor"] == "paper"
    assert result.data["execution"]["mode"] == "paper"


def test_skill_service_persists_trade_mode(tmp_path):
    store_path = str(tmp_path / "mode.json")
    service = AvaBoxSkillService(AvaBoxSkillConfig(store_path=store_path, execution_mode="custodial"))

    assert service.get_trade_mode() == "real"
    assert service.set_trade_mode("paper") == "paper"

    reloaded = AvaBoxSkillService(AvaBoxSkillConfig(store_path=store_path, execution_mode="custodial"))
    assert reloaded.get_trade_mode() == "paper"


def test_skill_service_separates_paper_and_real_order_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_PROXY_WALLET_ID", "assets-1")
    service = AvaBoxSkillService(
        AvaBoxSkillConfig(
            store_path=str(tmp_path / "orders.json"),
            execution_mode="custodial",
            proxy_wallet_id_env="TEST_PROXY_WALLET_ID",
        )
    )
    context = AppContext(
        app_id="ava_box",
        chain="solana",
        screen="spotlight",
        selected=Selection(token_id="So111-solana", addr="So111", chain="solana", symbol="SOL"),
        state={"trade_mode": "paper"},
    )
    draft = service.create_action_draft("buy", {}, context=context)
    service.confirm_action(draft.request_id, context=context)

    def fake_limit_orders(self, chain, assets_id, *, status="", token="", page_size=20, page_no=0):
        return {
            "data": {
                "list": [
                    {
                        "tokenAddress": "Real111",
                        "tokenSymbol": "REAL",
                        "limitPrice": "0.42",
                        "status": "open",
                    }
                ]
            }
        }

    monkeypatch.setattr(AveProxyWalletTradeProvider, "get_limit_orders", fake_limit_orders)

    paper = service.get_orders(mode="paper", context=context)
    real = service.get_orders(mode="real", context=context)

    assert paper.payload["source_label"] == "PAPER ORDERS"
    assert paper.payload["tokens"][0]["symbol"] == "SOL"
    assert real.payload["source_label"] == "REAL ORDERS"
    assert real.payload["tokens"][0]["symbol"] == "REAL"

from ava_devicekit.apps.ava_box_skills.execution import AveProxyWalletTradeProvider, build_proxy_wallet_order_payload


def test_proxy_wallet_order_payload_uses_custodial_assets_id(monkeypatch):
    monkeypatch.setenv("TEST_PROXY_WALLET_ID", "assets-1")
    payload = build_proxy_wallet_order_payload(
        {"action": "trade.market_draft", "token_id": "Token111-solana", "symbol": "TOK", "amount": "0.1 SOL"},
        {"request_id": "r1"},
        AveSolanaTradeConfig(proxy_wallet_id_env="TEST_PROXY_WALLET_ID"),
    )
    assert payload["assetsId"] == "assets-1"
    assert payload["inTokenAddress"] == "sol"
    assert payload["outTokenAddress"] == "Token111"
    assert payload["inAmount"] == "100000000"
    assert payload["gas"] == "1000000"


def test_proxy_wallet_provider_posts_signed_hmac_order(monkeypatch):
    monkeypatch.setenv("TEST_AVE_KEY", "key")
    monkeypatch.setenv("TEST_AVE_SECRET", "secret")
    monkeypatch.setenv("TEST_PROXY_WALLET_ID", "assets-1")
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok":true,"data":{"orderId":"order-1"}}'

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = req.data.decode()
        captured["headers"] = dict(req.header_items())
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = AveProxyWalletTradeProvider(
        AveSolanaTradeConfig(
            base_url="https://trade.example",
            api_key_env="TEST_AVE_KEY",
            secret_key_env="TEST_AVE_SECRET",
            proxy_wallet_id_env="TEST_PROXY_WALLET_ID",
        )
    )
    result = provider.execute(
        {"action": "trade.market_draft", "token_id": "Token111-solana", "symbol": "TOK", "amount": "0.1 SOL"},
        {"request_id": "r1"},
    )
    assert captured["url"].endswith("/v1/thirdParty/tx/sendSwapOrder")
    assert "ave-access-sign" in {k.lower(): v for k, v in captured["headers"].items()}
    assert result["status"] == "order_submitted"


def test_skill_service_real_mode_uses_proxy_wallet_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_PROXY_WALLET_ID", "assets-1")
    service = AvaBoxSkillService(AvaBoxSkillConfig(store_path=str(tmp_path / "s.json"), execution_mode="custodial", proxy_wallet_id_env="TEST_PROXY_WALLET_ID"))
    assert isinstance(service.executor, AveProxyWalletTradeProvider)


def test_skill_service_loads_custom_execution_provider(tmp_path):
    module = types.ModuleType("_ava_test_execution")

    class CustomExecutor:
        name = "custom-executor"

        def __init__(self, endpoint: str = ""):
            self.endpoint = endpoint

        def execute(self, summary, params):
            return {"status": "submitted", "endpoint": self.endpoint, "symbol": summary.get("symbol")}

    module.CustomExecutor = CustomExecutor
    sys.modules[module.__name__] = module

    service = AvaBoxSkillService(
        AvaBoxSkillConfig(
            store_path=str(tmp_path / "custom.json"),
            execution_mode="custom",
            execution_provider_class="_ava_test_execution.CustomExecutor",
            execution_options={"endpoint": "https://example.invalid/trade"},
        )
    )
    context = AppContext(
        app_id="ava_box",
        chain="solana",
        screen="spotlight",
        selected=Selection(token_id="So111-solana", addr="So111", chain="solana", symbol="SOL"),
    )
    draft = service.create_action_draft("buy", {}, context=context)
    result = service.confirm_action(draft.request_id, context=context)
    assert result.ok is True
    assert result.data["execution"]["endpoint"] == "https://example.invalid/trade"
    assert result.data["execution"]["symbol"] == "SOL"
