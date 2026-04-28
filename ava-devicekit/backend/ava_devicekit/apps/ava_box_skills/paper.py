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
            "status": "paper_filled",
            "action": str(summary.get("action") or ""),
            "symbol": str(summary.get("symbol") or "TOKEN"),
            "token_id": str(summary.get("token_id") or params.get("token_id") or ""),
            "amount": str(summary.get("amount") or ""),
            "limit_price": str(summary.get("limit_price") or ""),
            "amount_usd": str(summary.get("amount_usd_raw") or params.get("amount_usd_raw") or ""),
            "token_amount": str(summary.get("token_amount") or params.get("token_amount") or ""),
            "price_usd": str(summary.get("price_usd") or params.get("price_usd") or ""),
            "native_amount": str(summary.get("native_amount") or params.get("native_amount") or ""),
            "out_native_amount": str(summary.get("out_native_amount") or params.get("out_native_amount") or ""),
            "native_price_usd": str(summary.get("native_price_usd") or params.get("native_price_usd") or ""),
            "out_amount": str(summary.get("out_amount") or params.get("out_amount") or ""),
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
    cost_basis = _decimal(existing.get("cost_basis_usd"))
    delta = _token_delta(order)
    trade_usd = _decimal(order.get("amount_usd"))
    price_usd = _decimal(order.get("price_usd"))
    if action == "trade.sell_draft":
        prev_qty = qty
        qty -= delta
        if prev_qty > 0 and cost_basis > 0 and delta > 0:
            cost_basis -= cost_basis * min(delta, prev_qty) / prev_qty
    else:
        qty += delta
        cost_basis += trade_usd
    if qty < 0:
        qty = Decimal("0")
    if cost_basis < 0:
        cost_basis = Decimal("0")
    if price_usd <= 0 and qty > 0 and trade_usd > 0 and delta > 0:
        price_usd = trade_usd / delta
    value_usd = qty * price_usd if price_usd > 0 else trade_usd
    avg_cost = cost_basis / qty if qty > 0 and cost_basis > 0 else Decimal("0")
    pnl = value_usd - cost_basis
    existing["amount"] = _fmt_decimal(qty)
    existing["amount_raw"] = _fmt_decimal(qty)
    existing["balance_raw"] = _fmt_decimal(qty)
    existing["avg_cost_usd"] = _money(avg_cost) if avg_cost > 0 else "N/A"
    existing["cost_basis_usd"] = _fmt_decimal(cost_basis)
    existing["last_price_usd"] = _fmt_decimal(price_usd)
    existing["value"] = _money(value_usd)
    existing["value_usd"] = _money(value_usd)
    existing["pnl"] = _money(pnl, zero_small=True)
    existing["pnl_pct"] = _pct((pnl / cost_basis) * Decimal("100")) if cost_basis > 0 else "0.00%"
    state["paper_positions"] = [row for row in positions if _decimal(row.get("amount")) > 0][:100]


def _apply_cash(state: dict[str, Any], order: dict[str, Any]) -> None:
    cash = _paper_cash(state)
    if str(order.get("action") or "") == "trade.sell_draft":
        delta = _sell_cash_delta(order)
    else:
        delta = _decimal(order.get("native_amount")) or _extract_amount(order.get("amount"))
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


def _token_delta(order: dict[str, Any]) -> Decimal:
    explicit = _decimal(order.get("token_amount"))
    if explicit > 0:
        return explicit
    trade_usd = _decimal(order.get("amount_usd"))
    price_usd = _decimal(order.get("price_usd"))
    if trade_usd > 0 and price_usd > 0:
        return trade_usd / price_usd
    return _extract_amount(order.get("amount"))


def _sell_cash_delta(order: dict[str, Any]) -> Decimal:
    explicit = _decimal(order.get("out_native_amount"))
    if explicit > 0:
        return explicit
    amount_usd = _decimal(order.get("amount_usd"))
    native_price = _decimal(order.get("native_price_usd"))
    if amount_usd > 0 and native_price > 0:
        return amount_usd / native_price
    return Decimal("0")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").strip() or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _fmt_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def _money(value: Decimal, *, zero_small: bool = False) -> str:
    if zero_small and abs(value) < Decimal("0.005"):
        return "$0"
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= Decimal("1"):
        text = f"{value:.2f}"
    elif value > 0:
        text = f"{value:.8f}".rstrip("0").rstrip(".")
    else:
        text = "0"
    return f"{sign}${text}"


def _pct(value: Decimal) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


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
