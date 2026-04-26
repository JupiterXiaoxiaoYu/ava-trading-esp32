from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, ScreenPayload
from ava_devicekit.screen import builders
from ava_devicekit.storage.json_store import JsonStore

SOLANA = "solana"
DEFAULT_STORE = "data/ava_box_app_state.json"


@dataclass(slots=True)
class AvaBoxSkillConfig:
    store_path: str = DEFAULT_STORE
    default_buy_sol: Decimal = Decimal("0.1")
    default_slippage_bps: int = 100


@dataclass(slots=True)
class _PendingDraft:
    draft: ActionDraft
    params: dict[str, Any]
    created_at: int = field(default_factory=lambda: int(time.time()))


class AvaBoxSkillService:
    """Ava Box app-level skills.

    Trading, watchlist, portfolio, and action confirmation are app behavior, not
    generic chain-adapter behavior. This keeps the framework adapter interface
    focused on basic chain data.
    """

    def __init__(self, config: AvaBoxSkillConfig | None = None):
        self.config = config or AvaBoxSkillConfig()
        self.store = JsonStore(self.config.store_path)
        self.pending: dict[str, _PendingDraft] = {}

    def get_portfolio(self, *, context: AppContext | None = None) -> ScreenPayload:
        rows = [row for row in self._state().get("paper_positions", []) if isinstance(row, dict)]
        if not rows:
            rows = [{"symbol": "EMPTY", "chain": SOLANA, "value": "$0", "pnl": "$0", "source": "paper"}]
        return builders.portfolio(rows, chain=SOLANA, context=context)

    def get_watchlist(self, *, context: AppContext | None = None) -> ScreenPayload:
        rows = [row for row in self._state().get("watchlist", []) if isinstance(row, dict)]
        return builders.feed(rows, chain=SOLANA, source_label="WATCHLIST", mode="watchlist", context=context)

    def add_watchlist(self, token: dict[str, Any], *, context: AppContext | None = None) -> ScreenPayload:
        token_id = str(token.get("token_id") or token.get("addr") or "")
        if not token_id:
            return builders.notify("Watchlist", "No token selected", level="warn", context=context)
        row = _token_identity(token)
        state = self._state()
        state["watchlist"] = [item for item in state.get("watchlist", []) if item.get("token_id") != row["token_id"]]
        state["watchlist"].insert(0, row)
        state["watchlist"] = state["watchlist"][:100]
        self._save(state)
        return builders.notify("Watchlist", f"Added {row.get('symbol', 'token')}", context=context)

    def create_action_draft(self, action: str, params: dict[str, Any], *, context: AppContext | None = None) -> ActionDraft:
        token_id = str(params.get("token_id") or _selected_token_id(context) or "")
        symbol = str(params.get("symbol") or _selected_symbol(context) or "TOKEN")
        request_id = str(params.get("request_id") or f"ava_{int(time.time() * 1000)}")
        amount_sol = str(params.get("amount_sol") or params.get("amount_native") or self.config.default_buy_sol)
        action_name = _normalize_action(action)
        limit_price = params.get("limit_price")
        is_limit = action_name == "trade.limit_draft"
        summary = {
            "symbol": symbol,
            "token_id": token_id,
            "amount": _amount_label(amount_sol),
            "action": action_name,
        }
        if limit_price not in (None, ""):
            summary["limit_price"] = str(limit_price)
        screen_payload = {
            "trade_id": request_id,
            "action": _screen_action_label(action_name),
            "symbol": symbol,
            "chain": SOLANA,
            "token_id": token_id,
            "amount_native": _amount_label(amount_sol),
            "amount_usd": str(params.get("amount_usd") or ""),
            "timeout_sec": int(params.get("timeout_sec") or 30),
            "mode_label": str(params.get("mode_label") or "DRAFT"),
        }
        if is_limit:
            screen_payload.update({
                "limit_price": str(limit_price or ""),
                "current_price": str(params.get("current_price") or ""),
                "distance": str(params.get("distance") or ""),
            })
        else:
            screen_payload.update({
                "tp_pct": params.get("tp_pct"),
                "sl_pct": params.get("sl_pct"),
                "slippage_pct": self.config.default_slippage_bps / 100,
            })
        draft = ActionDraft(
            action=action_name,
            chain=SOLANA,
            summary=summary,
            risk={"level": "medium", "reason": "Requires physical confirmation on device."},
            requires_confirmation=True,
            request_id=request_id,
            screen=builders.confirm(screen_payload, context=context, limit=is_limit),
        )
        self.pending[request_id] = _PendingDraft(draft=draft, params={**params, "token_id": token_id})
        return draft

    def confirm_action(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        pending = self.pending.pop(request_id, None)
        if not pending:
            screen = builders.result("No pending action", "The draft expired or was already handled.", ok=False, context=context)
            return ActionResult(False, "pending action not found", screen=screen)
        summary = pending.draft.summary
        screen = builders.result("Action confirmed", f"{summary.get('action')} {summary.get('symbol')} confirmed as draft.", ok=True, context=context)
        return ActionResult(True, "confirmed", screen=screen, data=summary)

    def cancel_action(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        self.pending.pop(request_id, None)
        screen = builders.result("Action cancelled", "No transaction was executed.", ok=True, context=context)
        return ActionResult(True, "cancelled", screen=screen)

    def _state(self) -> dict[str, Any]:
        return self.store.read({"watchlist": [], "paper_positions": []})

    def _save(self, state: dict[str, Any]) -> None:
        self.store.write(state)


def _token_identity(token: dict[str, Any]) -> dict[str, Any]:
    token_id = str(token.get("token_id") or token.get("addr") or "").strip()
    return {
        "symbol": str(token.get("symbol") or "?").strip() or "?",
        "chain": str(token.get("chain") or SOLANA),
        "addr": str(token.get("addr") or token_id.replace("-solana", "")),
        "token_id": token_id if token_id.endswith("-solana") else f"{token_id}-{SOLANA}" if token_id else "",
        "price": str(token.get("price") or ""),
        "change_24h": str(token.get("change_24h") or ""),
        "change_positive": bool(token.get("change_positive", True)),
        "source": str(token.get("source") or token.get("source_tag") or "watchlist"),
    }


def _selected_token_id(context: AppContext | None) -> str:
    return context.selected.token_id if context and context.selected else ""


def _selected_symbol(context: AppContext | None) -> str:
    return context.selected.symbol if context and context.selected else ""


def _normalize_action(action: str) -> str:
    value = str(action or "").strip().lower()
    aliases = {
        "buy": "trade.market_draft",
        "market_buy": "trade.market_draft",
        "sell": "trade.sell_draft",
        "market_sell": "trade.sell_draft",
        "limit": "trade.limit_draft",
        "limit_buy": "trade.limit_draft",
        "cancel_order": "order.cancel_draft",
    }
    return aliases.get(value, value or "trade.market_draft")


def _screen_action_label(action: str) -> str:
    return {
        "trade.market_draft": "BUY",
        "trade.sell_draft": "SELL",
        "trade.limit_draft": "LIMIT BUY",
        "order.cancel_draft": "CANCEL",
        "payment.send": "PAY",
    }.get(action, action.upper())


def _amount_label(amount: str) -> str:
    text = str(amount or "").strip()
    return text if "SOL" in text.upper() else f"{text} SOL"
