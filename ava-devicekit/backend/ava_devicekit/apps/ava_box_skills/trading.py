from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from ava_devicekit.apps.ava_box_skills.config import AvaBoxSkillConfig, SOLANA
from ava_devicekit.apps.ava_box_skills.paper import PaperExecutionProvider
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext
from ava_devicekit.formatting.numbers import format_count, format_money, parse_number
from ava_devicekit.screen import builders

DEFAULT_SOL_PRICE_USD = Decimal("150")


@dataclass(slots=True)
class PendingDraft:
    draft: ActionDraft
    params: dict[str, Any]
    created_at: int = field(default_factory=lambda: int(time.time()))


class TradingSkill:
    def __init__(self, config: AvaBoxSkillConfig, executor: Any | None = None, *, paper_executor: PaperExecutionProvider | None = None):
        self.config = config
        self.executor = executor
        self.paper_executor = paper_executor or (executor if isinstance(executor, PaperExecutionProvider) else None)
        self.pending: dict[str, PendingDraft] = {}

    def create_draft(self, action: str, params: dict[str, Any], *, context: AppContext | None = None) -> ActionDraft:
        token_id = str(params.get("token_id") or _selected_token_id(context) or "")
        symbol = str(params.get("symbol") or _selected_symbol(context) or "TOKEN")
        request_id = str(params.get("request_id") or f"ava_{int(time.time() * 1000)}")
        amount_sol = str(params.get("amount_sol") or params.get("amount_native") or self.config.default_buy_sol)
        execution_mode = _execution_mode(params, context, self.config.execution_mode)
        action_name = normalize_action(action)
        limit_price = params.get("limit_price")
        is_limit = action_name == "trade.limit_draft"
        estimate = _estimate_trade(action_name, amount_sol, params, symbol)
        summary = {
            "symbol": symbol,
            "token_id": token_id,
            "amount": amount_label(amount_sol),
            "action": action_name,
        }
        summary.update({k: v for k, v in estimate.items() if v not in (None, "")})
        if limit_price not in (None, ""):
            summary["limit_price"] = str(limit_price)
        screen_payload = {
            "trade_id": request_id,
            "action": screen_action_label(action_name),
            "symbol": symbol,
            "chain": SOLANA,
            "token_id": token_id,
            "amount_native": amount_label(amount_sol),
            "amount_usd": str(params.get("amount_usd") or estimate.get("amount_usd") or ""),
            "out_amount": str(params.get("out_amount") or estimate.get("out_amount") or ""),
            "timeout_sec": int(params.get("timeout_sec") or 30),
            "mode_label": str(params.get("mode_label") or execution_mode.upper()),
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
        self.pending[request_id] = PendingDraft(
            draft=draft,
            params={
                **params,
                **{k: v for k, v in estimate.items() if v not in (None, "")},
                "token_id": token_id,
                "request_id": request_id,
                "execution_mode": execution_mode,
            },
        )
        return draft

    def confirm(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        pending = self.pending.pop(request_id, None)
        if not pending:
            screen = builders.result("No pending action", "The draft expired or was already handled.", ok=False, context=context)
            return ActionResult(False, "pending action not found", screen=screen)
        summary = pending.draft.summary
        execution_mode = str(pending.params.get("execution_mode") or self.config.execution_mode).lower()
        executor = self.paper_executor if execution_mode == "paper" else self.executor
        execution = executor.execute(summary, pending.params) if executor else {}
        body = _result_body(summary, execution_mode)
        screen = builders.result("Action confirmed", body, ok=True, context=context)
        return ActionResult(True, "confirmed", screen=screen, data={**summary, "execution": execution})

    def cancel(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        self.pending.pop(request_id, None)
        screen = builders.result("Action cancelled", "No transaction was executed.", ok=True, context=context)
        return ActionResult(True, "cancelled", screen=screen)

    def submit_signed(self, request_id: str, signed_tx: str, *, context: AppContext | None = None) -> ActionResult:
        sender = getattr(self.executor, "send_signed_solana_tx", None)
        if not callable(sender):
            screen = builders.result("Signing unsupported", "The active execution provider does not submit signed transactions.", ok=False, context=context)
            return ActionResult(False, "signed transaction submission unsupported", screen=screen)
        response = sender(request_id, signed_tx)
        screen = builders.result("Transaction submitted", "Signed transaction was submitted to the execution provider.", ok=True, context=context)
        return ActionResult(True, "submitted", screen=screen, data={"request_id": request_id, "response": response})


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


def _estimate_trade(action: str, amount_native: Any, params: dict[str, Any], symbol: str) -> dict[str, str]:
    if action not in {"trade.market_draft", "trade.limit_draft"}:
        return {}
    native_amount = _decimal_amount(amount_native)
    token_price = _decimal_price(params.get("token_price_usd") or params.get("price_usd") or params.get("price_raw") or params.get("current_price"))
    native_price = _decimal_price(params.get("native_price_usd") or params.get("sol_price_usd")) or DEFAULT_SOL_PRICE_USD
    if native_amount <= 0:
        return {}
    amount_usd = native_amount * native_price
    out: dict[str, str] = {
        "amount_usd": format_money(float(amount_usd), max_chars=12),
        "amount_usd_raw": _fmt_decimal(amount_usd),
        "native_price_usd": _fmt_decimal(native_price),
    }
    if token_price > 0:
        token_amount = amount_usd / token_price
        out["token_amount"] = _fmt_decimal(token_amount)
        out["price_usd"] = _fmt_decimal(token_price)
        out["out_amount"] = f"{format_count(float(token_amount), max_chars=8)} {symbol or 'TOKEN'}"
    return out


def _decimal_amount(value: Any) -> Decimal:
    text = str(value or "0").upper().replace("SOL", "").replace(",", "").replace("$", "").strip()
    return _decimal(text)


def _decimal_price(value: Any) -> Decimal:
    number = parse_number(value, default=0)
    return _decimal(str(number))


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").strip() or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _fmt_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def _execution_mode(params: dict[str, Any], context: AppContext | None, default: str) -> str:
    mode = str(params.get("execution_mode") or params.get("trade_mode") or "").lower()
    if not mode and context:
        mode = str(context.state.get("trade_mode") or "").lower()
    if mode in {"paper", "demo", "mock"}:
        return "paper"
    if mode in {"real", "proxy", "proxy_wallet", "custodial", "hosted"}:
        return mode
    return str(default or "paper").lower()


def _result_body(summary: dict[str, Any], execution_mode: str) -> str:
    symbol = str(summary.get("symbol") or "TOKEN")
    action = str(summary.get("action") or "")
    mode = "Paper" if execution_mode == "paper" else "Real"
    if action == "trade.sell_draft":
        return f"{mode} sell filled for {symbol}."
    if action == "trade.limit_draft":
        return f"{mode} limit order created for {symbol}."
    return f"{mode} buy filled for {symbol}."


def _selected_token_id(context: AppContext | None) -> str:
    return context.selected.token_id if context and context.selected else ""


def _selected_symbol(context: AppContext | None) -> str:
    return context.selected.symbol if context and context.selected else ""
