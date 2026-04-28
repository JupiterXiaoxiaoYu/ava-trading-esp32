from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

from ava_devicekit.storage.json_store import JsonStore

DEFAULT_PAPER_CASH_SOL = Decimal("1")
DEFAULT_NATIVE_PRICE_USD = Decimal("150")
NATIVE_SOL_MINT = "So11111111111111111111111111111111111111112"


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
        action = str(summary.get("action") or "")
        is_limit = action == "trade.limit_draft"
        order = {
            "id": str(params.get("request_id") or f"paper_{int(time.time() * 1000)}"),
            "ts": int(time.time()),
            "status": "paper_open" if is_limit else "paper_filled",
            "action": action,
            "symbol": str(summary.get("symbol") or "TOKEN"),
            "token_id": _normalize_token_id(summary.get("token_id") or params.get("token_id") or ""),
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
        _enrich_sell_order_from_position(state, order)
        if _is_insufficient_paper_cash(state, order):
            order["status"] = "paper_rejected"
            order["reason"] = "Insufficient paper SOL balance"
            state.setdefault("paper_orders", []).insert(0, order)
            state["paper_orders"] = state["paper_orders"][:100]
            self.store.write(state)
            return order
        if is_limit:
            _reserve_limit_cash(state, order)
        state.setdefault("paper_orders", []).insert(0, order)
        state["paper_orders"] = state["paper_orders"][:100]
        if not is_limit and not _is_native_sol_order(order):
            _apply_position(state, order)
            _apply_cash(state, order)
        self.store.write(state)
        return order

    def orders(self) -> list[dict[str, Any]]:
        return [row for row in _state(self.store).get("paper_orders", []) if isinstance(row, dict)]

    def fill_limits(self, prices: dict[str, Any]) -> list[dict[str, Any]]:
        state = _state(self.store)
        filled: list[dict[str, Any]] = []
        for order in [row for row in state.get("paper_orders", []) if isinstance(row, dict)]:
            if not _is_open_limit_order(order):
                continue
            price = _price_for_order(order, prices)
            if price <= 0 or price > _decimal_money(order.get("limit_price")):
                continue
            _fill_limit_order(state, order, price)
            filled.append(order)
        if filled:
            self.store.write(state)
        return filled


def _apply_position(state: dict[str, Any], order: dict[str, Any]) -> None:
    action = str(order.get("action") or "")
    token_id = _normalize_token_id(order.get("token_id") or "")
    if not token_id:
        return
    positions = [row for row in state.get("paper_positions", []) if isinstance(row, dict)]
    existing = next((row for row in positions if _normalize_token_id(row.get("token_id") or row.get("addr") or "") == token_id), None)
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
    price_usd = _decimal(order.get("price_usd")) or _decimal(existing.get("last_price_usd"))
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


def _reserve_limit_cash(state: dict[str, Any], order: dict[str, Any]) -> None:
    reserved = _decimal(order.get("native_amount")) or _extract_amount(order.get("amount"))
    if reserved <= 0:
        return
    order["reserved_native_amount"] = _fmt_decimal(reserved)
    cash = _paper_cash(state) - reserved
    state["paper_cash_sol"] = _fmt_decimal(cash if cash > 0 else Decimal("0"))


def _fill_limit_order(state: dict[str, Any], order: dict[str, Any], fill_price: Decimal) -> None:
    native_amount = _decimal(order.get("reserved_native_amount")) or _decimal(order.get("native_amount")) or _extract_amount(order.get("amount"))
    native_price = _decimal(order.get("native_price_usd")) or DEFAULT_NATIVE_PRICE_USD
    amount_usd = native_amount * native_price
    token_amount = amount_usd / fill_price if fill_price > 0 else Decimal("0")
    order["status"] = "paper_filled"
    order["filled_ts"] = int(time.time())
    order["fill_price_usd"] = _fmt_decimal(fill_price)
    order["price_usd"] = _fmt_decimal(fill_price)
    order["amount_usd"] = _fmt_decimal(amount_usd)
    order["token_amount"] = _fmt_decimal(token_amount)
    order["out_amount"] = _fmt_decimal(token_amount)
    _apply_position(state, order)


def _enrich_sell_order_from_position(state: dict[str, Any], order: dict[str, Any]) -> None:
    if str(order.get("action") or "") != "trade.sell_draft":
        return
    position = _find_position(state, order.get("token_id") or "")
    if not position:
        return
    token_amount = _decimal(order.get("token_amount")) or _extract_amount(order.get("amount"))
    if token_amount <= 0:
        token_amount = _decimal(position.get("balance_raw") or position.get("amount_raw") or position.get("amount"))
        if token_amount > 0:
            order["token_amount"] = _fmt_decimal(token_amount)
    price_usd = _decimal(order.get("price_usd")) or _decimal(position.get("last_price_usd") or position.get("price_usd"))
    if price_usd <= 0:
        value_usd = _decimal_money(position.get("value_usd") or position.get("value"))
        position_amount = _decimal(position.get("balance_raw") or position.get("amount_raw") or position.get("amount"))
        if value_usd > 0 and position_amount > 0:
            price_usd = value_usd / position_amount
    if price_usd > 0 and not str(order.get("price_usd") or "").strip():
        order["price_usd"] = _fmt_decimal(price_usd)
    if token_amount > 0 and price_usd > 0:
        amount_usd = _decimal(order.get("amount_usd"))
        if amount_usd <= 0:
            amount_usd = token_amount * price_usd
            order["amount_usd"] = _fmt_decimal(amount_usd)
        native_price = _decimal(order.get("native_price_usd")) or DEFAULT_NATIVE_PRICE_USD
        if not str(order.get("native_price_usd") or "").strip():
            order["native_price_usd"] = _fmt_decimal(native_price)
        if _decimal(order.get("out_native_amount")) <= 0 and native_price > 0:
            order["out_native_amount"] = _fmt_decimal(amount_usd / native_price)


def _find_position(state: dict[str, Any], token_id: Any) -> dict[str, Any] | None:
    normalized = _normalize_token_id(token_id)
    for row in state.get("paper_positions", []):
        if not isinstance(row, dict):
            continue
        if _normalize_token_id(row.get("token_id") or row.get("addr") or "") == normalized:
            return row
    return None


def _is_insufficient_paper_cash(state: dict[str, Any], order: dict[str, Any]) -> bool:
    if str(order.get("action") or "") == "trade.sell_draft" or _is_native_sol_order(order):
        return False
    required = _decimal(order.get("native_amount")) or _extract_amount(order.get("amount"))
    return required > 0 and required > _paper_cash(state)


def _is_open_limit_order(order: dict[str, Any]) -> bool:
    return str(order.get("action") or "") == "trade.limit_draft" and str(order.get("status") or "").lower() in {"", "open", "pending", "paper_open", "created"}


def _price_for_order(order: dict[str, Any], prices: dict[str, Any]) -> Decimal:
    token_id = _normalize_token_id(order.get("token_id") or "")
    candidates = [
        token_id,
        token_id.replace("-solana", ""),
        str(order.get("symbol") or "").upper(),
    ]
    for key in candidates:
        if key in prices:
            return _decimal_money(prices[key])
    return Decimal("0")


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


def _normalize_token_id(value: Any) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    return token if token.endswith("-solana") else f"{token}-solana"


def _is_native_sol_order(order: dict[str, Any]) -> bool:
    symbol = str(order.get("symbol") or "").strip().upper()
    token_id = _normalize_token_id(order.get("token_id") or "")
    addr = token_id.replace("-solana", "")
    return symbol == "SOL" or addr == NATIVE_SOL_MINT


def _sell_cash_delta(order: dict[str, Any]) -> Decimal:
    explicit = _decimal(order.get("out_native_amount"))
    if explicit > 0:
        return explicit
    amount_usd = _decimal(order.get("amount_usd"))
    native_price = _decimal(order.get("native_price_usd"))
    if amount_usd > 0 and native_price > 0:
        return amount_usd / native_price
    token_amount = _decimal(order.get("token_amount")) or _extract_amount(order.get("amount"))
    price_usd = _decimal(order.get("price_usd"))
    if token_amount > 0 and price_usd > 0 and native_price > 0:
        return (token_amount * price_usd) / native_price
    return Decimal("0")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").strip() or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _decimal_money(value: Any) -> Decimal:
    text = str(value or "0").replace("$", "").replace(",", "").strip()
    return _decimal(text)


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
