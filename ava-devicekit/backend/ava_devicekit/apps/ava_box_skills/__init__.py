from __future__ import annotations

from typing import Any

from ava_devicekit.apps.ava_box_skills.config import AvaBoxSkillConfig
from ava_devicekit.apps.ava_box_skills.portfolio import PortfolioSkill
from ava_devicekit.apps.ava_box_skills.trading import TradingSkill
from ava_devicekit.apps.ava_box_skills.watchlist import WatchlistSkill
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, ScreenPayload
from ava_devicekit.storage.json_store import JsonStore


class AvaBoxSkillService:
    """Facade for Ava Box app-level skills.

    Trading, watchlist, portfolio, and action confirmation are app behavior, not
    generic chain-adapter behavior. This keeps the framework adapter interface
    focused on basic chain data.
    """

    def __init__(self, config: AvaBoxSkillConfig | None = None):
        self.config = config or AvaBoxSkillConfig()
        self.store = JsonStore(self.config.store_path)
        self.watchlist = WatchlistSkill(self.store)
        self.portfolio = PortfolioSkill(self.store)
        self.trading = TradingSkill(self.config)

    def get_portfolio(self, *, context: AppContext | None = None) -> ScreenPayload:
        return self.portfolio.open(context=context)

    def get_watchlist(self, *, context: AppContext | None = None) -> ScreenPayload:
        return self.watchlist.open(context=context)

    def add_watchlist(self, token: dict[str, Any], *, context: AppContext | None = None) -> ScreenPayload:
        return self.watchlist.add(token, context=context)

    def create_action_draft(self, action: str, params: dict[str, Any], *, context: AppContext | None = None) -> ActionDraft:
        return self.trading.create_draft(action, params, context=context)

    def confirm_action(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        return self.trading.confirm(request_id, context=context)

    def cancel_action(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        return self.trading.cancel(request_id, context=context)


__all__ = ["AvaBoxSkillConfig", "AvaBoxSkillService"]
