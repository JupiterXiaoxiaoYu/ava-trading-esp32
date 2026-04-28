from __future__ import annotations

import os
from typing import Any

from ava_devicekit.apps.ava_box_skills.config import AvaBoxSkillConfig, SOLANA
from ava_devicekit.apps.ava_box_skills.execution import AveProxyWalletTradeProvider, AveSolanaTradeConfig, AveSolanaTradeProvider, load_trade_execution_provider
from ava_devicekit.apps.ava_box_skills.paper import PaperExecutionProvider
from ava_devicekit.apps.ava_box_skills.portfolio import PortfolioSkill
from ava_devicekit.apps.ava_box_skills.trading import TradingSkill
from ava_devicekit.apps.ava_box_skills.watchlist import WatchlistSkill
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, ScreenPayload
from ava_devicekit.screen import builders
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
        self.paper_executor = PaperExecutionProvider(self.store)
        self.executor = self._create_executor()
        self.trading = TradingSkill(self.config, self.executor, paper_executor=self.paper_executor)

    def get_trade_mode(self) -> str:
        state = self.store.read({})
        mode = _normalize_trade_mode(state.get("trade_mode") or self.config.execution_mode)
        return mode

    def set_trade_mode(self, mode: str) -> str:
        normalized = _normalize_trade_mode(mode)
        state = self.store.read({"watchlist": [], "paper_positions": [], "paper_orders": []})
        state["trade_mode"] = normalized
        self.store.write(state)
        return normalized

    def get_portfolio(self, *, context: AppContext | None = None) -> ScreenPayload:
        return self.portfolio.open(context=context)

    def get_orders(self, *, mode: str = "", context: AppContext | None = None) -> ScreenPayload:
        normalized = _normalize_trade_mode(mode or self.get_trade_mode())
        if normalized == "paper":
            return self.portfolio.orders(context=context, source_label="PAPER ORDERS")
        return self._real_orders(context=context, source_label="REAL ORDERS", status="open")

    def get_history(self, *, mode: str = "", context: AppContext | None = None) -> ScreenPayload:
        normalized = _normalize_trade_mode(mode or self.get_trade_mode())
        if normalized == "paper":
            return self.portfolio.history(context=context, source_label="PAPER HISTORY")
        return self._real_orders(context=context, source_label="REAL HISTORY", status="")

    def get_watchlist(self, *, context: AppContext | None = None) -> ScreenPayload:
        return self.watchlist.open(context=context)

    def add_watchlist(self, token: dict[str, Any], *, context: AppContext | None = None) -> ScreenPayload:
        return self.watchlist.add(token, context=context)

    def remove_watchlist(self, token: dict[str, Any], *, context: AppContext | None = None) -> ScreenPayload:
        return self.watchlist.remove(token, context=context)

    def create_action_draft(self, action: str, params: dict[str, Any], *, context: AppContext | None = None) -> ActionDraft:
        return self.trading.create_draft(action, params, context=context)

    def confirm_action(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        return self.trading.confirm(request_id, context=context)

    def cancel_action(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        return self.trading.cancel(request_id, context=context)

    def submit_signed_action(self, request_id: str, signed_tx: str, *, context: AppContext | None = None) -> ActionResult:
        return self.trading.submit_signed(request_id, signed_tx, context=context)

    def _real_orders(self, *, context: AppContext | None = None, source_label: str = "REAL ORDERS", status: str = "open") -> ScreenPayload:
        get_limit_orders = getattr(self.executor, "get_limit_orders", None)
        if not callable(get_limit_orders):
            rows = [_empty_order_row("REAL", "Real execution provider has no order list")]
            return builders.feed(rows, chain=SOLANA, source_label=source_label, mode="orders", context=context)
        assets_id = os.environ.get(self.config.proxy_wallet_id_env, "").strip()
        if not assets_id:
            rows = [_empty_order_row("REAL", "No proxy wallet configured")]
            return builders.feed(rows, chain=SOLANA, source_label=source_label, mode="orders", context=context)
        try:
            resp = get_limit_orders(SOLANA, assets_id, status=status, page_size=20, page_no=0)
            rows = [_real_order_row(row) for row in _extract_rows(resp) if isinstance(row, dict)]
        except Exception as exc:
            rows = [_empty_order_row("REAL", f"Order fetch failed: {exc}")]
        if not rows:
            rows = [_empty_order_row("ORDERS" if "ORDERS" in source_label else "HISTORY", "No matching rows")]
        return builders.feed(rows[:20], chain=SOLANA, source_label=source_label, mode="orders", context=context)

    def _create_executor(self):
        mode = self.config.execution_mode.lower()
        if self.config.execution_provider_class or mode in {"custom", "class", "python"}:
            return load_trade_execution_provider(self.config.execution_provider_class, self.config.execution_options or {})
        if mode == "paper":
            return None
        if mode in {"proxy", "proxy_wallet", "custodial", "hosted", "real"}:
            return AveProxyWalletTradeProvider(
                AveSolanaTradeConfig(
                    base_url=self.config.execution_base_url,
                    api_key_env=self.config.execution_api_key_env,
                    secret_key_env=self.config.execution_secret_key_env,
                    proxy_wallet_id_env=self.config.proxy_wallet_id_env,
                    proxy_default_gas=self.config.proxy_default_gas,
                )
            )
        if mode in {"ave_solana", "chain_wallet", "self_custody", "wallet"}:
            return AveSolanaTradeProvider(
                AveSolanaTradeConfig(
                    base_url=self.config.execution_base_url,
                    api_key_env=self.config.execution_api_key_env,
                )
            )
        return None


def _normalize_trade_mode(mode: Any) -> str:
    value = str(mode or "").strip().lower()
    return "paper" if value in {"paper", "demo", "mock"} else "real"


def _extract_rows(resp: dict[str, Any]) -> list[Any]:
    data: Any = resp.get("data", resp) if isinstance(resp, dict) else resp
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("list", "items", "orders", "records", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _real_order_row(row: dict[str, Any]) -> dict[str, Any]:
    token_id = str(row.get("token") or row.get("tokenAddress") or row.get("outTokenAddress") or row.get("inTokenAddress") or "").strip()
    symbol = str(row.get("symbol") or row.get("tokenSymbol") or row.get("outTokenSymbol") or row.get("inTokenSymbol") or "ORDER").strip()
    price = str(row.get("limitPrice") or row.get("price") or row.get("amount") or row.get("inAmount") or row.get("volume") or "--")
    status = str(row.get("status") or row.get("state") or row.get("orderStatus") or "real").strip()
    return {
        "symbol": symbol or "ORDER",
        "chain": SOLANA,
        "addr": token_id.replace(f"-{SOLANA}", ""),
        "token_id": token_id if token_id.endswith(f"-{SOLANA}") else f"{token_id}-{SOLANA}" if token_id else "",
        "price": price,
        "change_24h": status or "real",
        "change_positive": status.lower() not in {"failed", "cancelled", "canceled", "rejected"},
        "source": "real_orders",
        "source_tag": "real",
    }


def _empty_order_row(symbol: str, message: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "chain": SOLANA,
        "price": "--",
        "change_24h": message[:16],
        "change_positive": False,
        "source": "orders",
        "source_tag": message,
    }


__all__ = ["AvaBoxSkillConfig", "AvaBoxSkillService", "AveProxyWalletTradeProvider", "AveSolanaTradeConfig", "AveSolanaTradeProvider", "load_trade_execution_provider"]
