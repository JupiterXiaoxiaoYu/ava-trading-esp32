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
