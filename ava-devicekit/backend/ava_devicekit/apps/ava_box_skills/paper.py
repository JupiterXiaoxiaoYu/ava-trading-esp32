from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

from ava_devicekit.storage.json_store import JsonStore

DEFAULT_PAPER_CASH_SOL = Decimal("1")


class PaperExecutionProvider:
    """Safe execution provider used by Ava Box demos.

    It records confirmed drafts as paper orders and folds simple buy/sell flows
    into local positions. Real execution providers can replace this at the app
    layer without changing DeviceKit core adapters.
    """

    def __init__(self, store: JsonStore):
        self.store = store

    def execute(self, summary: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        state = _state(self.store)
        order = {
            "id": str(params.get("request_id") or f"paper_{int(time.time() * 1000)}"),
            "ts": int(time.time()),
            "status": "confirmed_draft",
            "action": str(summary.get("action") or ""),
            "symbol": str(summary.get("symbol") or "TOKEN"),
            "token_id": str(summary.get("token_id") or params.get("token_id") or ""),
            "amount": str(summary.get("amount") or ""),
            "limit_price": str(summary.get("limit_price") or ""),
        }
        state.setdefault("paper_orders", []).insert(0, order)
        state["paper_orders"] = state["paper_orders"][:100]
        _apply_position(state, order)
        _apply_cash(state, order)
        self.store.write(state)
        return order

    def orders(self) -> list[dict[str, Any]]:
        return [row for row in _state(self.store).get("paper_orders", []) if isinstance(row, dict)]


def _apply_position(state: dict[str, Any], order: dict[str, Any]) -> None:
    action = str(order.get("action") or "")
    token_id = str(order.get("token_id") or "")
    if not token_id:
        return
    positions = [row for row in state.get("paper_positions", []) if isinstance(row, dict)]
    existing = next((row for row in positions if row.get("token_id") == token_id), None)
    if not existing:
        existing = {
            "symbol": order.get("symbol") or "TOKEN",
            "chain": "solana",
            "token_id": token_id,
            "amount": "0",
            "value": "$0",
            "pnl": "$0",
            "source": "paper",
        }
        positions.insert(0, existing)
    qty = _decimal(existing.get("amount"))
    delta = _extract_amount(order.get("amount"))
    if action == "trade.sell_draft":
        qty -= delta
    else:
        qty += delta
    if qty < 0:
        qty = Decimal("0")
    existing["amount"] = _fmt_decimal(qty)
    existing["value"] = str(order.get("amount") or existing.get("value") or "$0")
    state["paper_positions"] = [row for row in positions if _decimal(row.get("amount")) > 0][:100]


def _apply_cash(state: dict[str, Any], order: dict[str, Any]) -> None:
    cash = _paper_cash(state)
    delta = _extract_amount(order.get("amount"))
    if delta <= 0:
        return
    if str(order.get("action") or "") == "trade.sell_draft":
        cash += delta
    else:
        cash -= delta
    if cash < 0:
        cash = Decimal("0")
    state["paper_cash_sol"] = _fmt_decimal(cash)


def _paper_cash(state: dict[str, Any]) -> Decimal:
    return _decimal(state.get("paper_cash_sol", DEFAULT_PAPER_CASH_SOL))


def _extract_amount(value: Any) -> Decimal:
    text = str(value or "0").upper().replace("SOL", "").strip()
    return _decimal(text)


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").strip() or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _fmt_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def _state(store: JsonStore) -> dict[str, Any]:
    return store.read(
        {
            "watchlist": [],
            "paper_positions": [],
            "paper_orders": [],
            "paper_cash_sol": str(DEFAULT_PAPER_CASH_SOL),
            "paper_starting_sol": str(DEFAULT_PAPER_CASH_SOL),
        }
    )
