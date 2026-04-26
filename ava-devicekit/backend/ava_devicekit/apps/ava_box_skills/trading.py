from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ava_devicekit.apps.ava_box_skills.config import AvaBoxSkillConfig, SOLANA
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext
from ava_devicekit.screen import builders


@dataclass(slots=True)
class PendingDraft:
    draft: ActionDraft
    params: dict[str, Any]
    created_at: int = field(default_factory=lambda: int(time.time()))


class TradingSkill:
    def __init__(self, config: AvaBoxSkillConfig):
        self.config = config
        self.pending: dict[str, PendingDraft] = {}

    def create_draft(self, action: str, params: dict[str, Any], *, context: AppContext | None = None) -> ActionDraft:
        token_id = str(params.get("token_id") or _selected_token_id(context) or "")
        symbol = str(params.get("symbol") or _selected_symbol(context) or "TOKEN")
        request_id = str(params.get("request_id") or f"ava_{int(time.time() * 1000)}")
        amount_sol = str(params.get("amount_sol") or params.get("amount_native") or self.config.default_buy_sol)
        action_name = normalize_action(action)
        limit_price = params.get("limit_price")
        is_limit = action_name == "trade.limit_draft"
        summary = {
            "symbol": symbol,
            "token_id": token_id,
            "amount": amount_label(amount_sol),
            "action": action_name,
        }
        if limit_price not in (None, ""):
            summary["limit_price"] = str(limit_price)
        screen_payload = {
            "trade_id": request_id,
            "action": screen_action_label(action_name),
            "symbol": symbol,
            "chain": SOLANA,
            "token_id": token_id,
            "amount_native": amount_label(amount_sol),
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
        self.pending[request_id] = PendingDraft(draft=draft, params={**params, "token_id": token_id})
        return draft

    def confirm(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        pending = self.pending.pop(request_id, None)
        if not pending:
            screen = builders.result("No pending action", "The draft expired or was already handled.", ok=False, context=context)
            return ActionResult(False, "pending action not found", screen=screen)
        summary = pending.draft.summary
        screen = builders.result("Action confirmed", f"{summary.get('action')} {summary.get('symbol')} confirmed as draft.", ok=True, context=context)
        return ActionResult(True, "confirmed", screen=screen, data=summary)

    def cancel(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        self.pending.pop(request_id, None)
        screen = builders.result("Action cancelled", "No transaction was executed.", ok=True, context=context)
        return ActionResult(True, "cancelled", screen=screen)


def normalize_action(action: str) -> str:
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


def screen_action_label(action: str) -> str:
    return {
        "trade.market_draft": "BUY",
        "trade.sell_draft": "SELL",
        "trade.limit_draft": "LIMIT BUY",
        "order.cancel_draft": "CANCEL",
        "payment.send": "PAY",
    }.get(action, action.upper())


def amount_label(amount: str) -> str:
    text = str(amount or "").strip()
    return text if "SOL" in text.upper() else f"{text} SOL"


def _selected_token_id(context: AppContext | None) -> str:
    return context.selected.token_id if context and context.selected else ""


def _selected_symbol(context: AppContext | None) -> str:
    return context.selected.symbol if context and context.selected else ""
