from __future__ import annotations

from typing import Any

from ava_devicekit.apps.ava_box_skills.config import SOLANA
from ava_devicekit.apps.ava_box_skills.paper import DEFAULT_PAPER_CASH_SOL
from ava_devicekit.core.types import AppContext, ScreenPayload
from ava_devicekit.formatting.numbers import format_money, format_percent, parse_number
from ava_devicekit.screen import builders
from ava_devicekit.storage.json_store import JsonStore


class PortfolioSkill:
    def __init__(self, store: JsonStore):
        self.store = store

    def open(self, *, context: AppContext | None = None) -> ScreenPayload:
        state = _state(self.store)
        rows = [_portfolio_row(row) for row in state.get("paper_positions", []) if isinstance(row, dict)]
        if not rows:
            rows = [_portfolio_row({"symbol": "EMPTY", "chain": SOLANA, "value": "$0", "pnl": "$0", "source": "paper"})]
        pnl = _sum_money(row.get("pnl") for row in rows)
        starting_sol = _sol_label(state.get("paper_starting_sol", DEFAULT_PAPER_CASH_SOL))
        cash_sol = _sol_label(state.get("paper_cash_sol", DEFAULT_PAPER_CASH_SOL))
        return builders.portfolio(
            rows,
            chain=SOLANA,
            total_usd=f"Funds {starting_sol}",
            pnl=_money_label(pnl),
            pnl_pct=format_percent(0),
            mode_label="Paper",
            chain_label="SOL",
            pnl_reason=f"Cash: {cash_sol}",
            context=context,
        )

    def orders(self, *, context: AppContext | None = None, source_label: str = "PAPER ORDERS") -> ScreenPayload:
        rows = [_order_row(row) for row in _state(self.store).get("paper_orders", []) if isinstance(row, dict)]
        return builders.feed(rows, chain=SOLANA, source_label=source_label, mode="orders", context=context)


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


def _portfolio_row(row: dict[str, Any]) -> dict[str, Any]:
    token_id = str(row.get("token_id") or row.get("addr") or "").strip()
    addr = str(row.get("addr") or token_id.replace(f"-{SOLANA}", "")).strip()
    value = str(row.get("value_usd") or row.get("value") or "$0").strip() or "$0"
    pnl = str(row.get("pnl") or "$0").strip() or "$0"
    return {
        "symbol": str(row.get("symbol") or "TOKEN").strip() or "TOKEN",
        "chain": str(row.get("chain") or SOLANA),
        "addr": addr,
        "token_id": token_id if token_id.endswith(f"-{SOLANA}") else f"{token_id}-{SOLANA}" if token_id else "",
        "avg_cost_usd": str(row.get("avg_cost_usd") or row.get("avg_cost") or "N/A"),
        "value_usd": value,
        "pnl": pnl,
        "pnl_pct": str(row.get("pnl_pct") or "0.00%"),
        "pnl_positive": _money_value(pnl) >= 0,
        "contract_tail": str(row.get("contract_tail") or _contract_tail(addr)),
        "source_tag": str(row.get("source_tag") or row.get("source") or "paper"),
        "balance_raw": str(row.get("balance_raw") or row.get("amount_raw") or row.get("amount") or "0"),
        "last_price_usd": str(row.get("last_price_usd") or row.get("price_usd") or ""),
        "cost_basis_usd": str(row.get("cost_basis_usd") or ""),
    }


def _order_row(row: dict[str, Any]) -> dict[str, Any]:
    token_id = str(row.get("token_id") or row.get("addr") or "").strip()
    addr = str(row.get("addr") or token_id.replace(f"-{SOLANA}", "")).strip()
    return {
        "symbol": str(row.get("symbol") or "TOKEN").strip() or "TOKEN",
        "chain": str(row.get("chain") or SOLANA),
        "addr": addr,
        "token_id": token_id if token_id.endswith(f"-{SOLANA}") else f"{token_id}-{SOLANA}" if token_id else "",
        "price": str(row.get("amount") or row.get("limit_price") or "--"),
        "change_24h": str(row.get("status") or row.get("action") or "draft"),
        "change_positive": str(row.get("status") or "").lower() not in {"failed", "cancelled"},
        "source": "orders",
        "source_tag": "order",
        "contract_tail": _contract_tail(addr),
    }


def _contract_tail(addr: str) -> str:
    return addr[-4:] if len(addr) >= 4 else addr


def _sum_money(values: Any) -> float:
    return sum(_money_value(value) for value in values)


def _money_value(value: Any) -> float:
    return parse_number(value)


def _money_label(value: float) -> str:
    sign = "-" if value < 0 else ""
    return format_money(value)


def _sol_label(value: Any) -> str:
    amount = parse_number(value, default=1)
    text = f"{amount:.4f}".rstrip("0").rstrip(".")
    return f"{text or '0'} SOL"
