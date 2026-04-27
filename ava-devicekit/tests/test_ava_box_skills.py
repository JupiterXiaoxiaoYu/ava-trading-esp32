from __future__ import annotations

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

    draft = service.create_action_draft("buy", {}, context=context)
    assert draft.action == "trade.market_draft"
    assert draft.requires_confirmation is True
    assert draft.screen.screen == "confirm"

    result = service.confirm_action(draft.request_id, context=context)
    assert result.ok is True
    assert result.screen and result.screen.screen == "result"
    assert result.data["execution"]["status"] == "confirmed_draft"
    portfolio_after_trade = service.get_portfolio(context=context)
    assert portfolio_after_trade.payload["items"][0]["symbol"] == "BONK"
    orders = service.get_orders(context=context)
    assert orders.payload["mode"] == "orders"
    assert orders.payload["items"][0]["symbol"] == "BONK"

from ava_devicekit.apps.ava_box_skills.execution import AveSolanaTradeConfig, AveSolanaTradeProvider, build_create_solana_tx_payload


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
