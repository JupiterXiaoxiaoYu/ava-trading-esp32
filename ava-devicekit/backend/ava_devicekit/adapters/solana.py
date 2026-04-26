from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from ava_devicekit.adapters.base import ChainAdapter
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, ScreenPayload, Selection
from ava_devicekit.screen import builders
from ava_devicekit.storage.json_store import JsonStore

DATA_BASE = "https://data.ave-api.xyz/v2"
SOLANA = "solana"
NATIVE_SOL = "So11111111111111111111111111111111111111112"
PUMP_PLATFORMS = {"pump_in_hot", "pump_in_new"}
TOPICS = {"trending", "gainer", "loser", "new", "meme", "ai", "depin", "gamefi"}


@dataclass(slots=True)
class SolanaAdapterConfig:
    data_base: str = DATA_BASE
    api_key_env: str = "AVE_API_KEY"
    store_path: str = "data/ava_devicekit_solana.json"
    default_buy_sol: Decimal = Decimal("0.1")
    default_slippage_bps: int = 100


@dataclass(slots=True)
class _PendingDraft:
    draft: ActionDraft
    params: dict[str, Any]
    created_at: int = field(default_factory=lambda: int(time.time()))


class SolanaDataClient:
    def __init__(self, config: SolanaAdapterConfig):
        self.config = config

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.config.data_base}{path}"
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
            if query:
                url += "?" + query
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode() if exc.fp else ""
            raise RuntimeError(f"Solana data API {exc.code}: {body}") from exc

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{self.config.data_base}{path}",
            data=json.dumps(payload).encode(),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode() if exc.fp else ""
            raise RuntimeError(f"Solana data API {exc.code}: {body}") from exc

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-KEY": os.environ.get(self.config.api_key_env, ""),
            "Content-Type": "application/json",
        }


class SolanaAdapter(ChainAdapter):
    """Solana ChainAdapter for Ava DeviceKit.

    This module has no dependency on the legacy assistant runtime. It owns API
    access, payload normalization, draft creation, and local paper state for the
    Ava Box reference app.
    """

    chain = SOLANA

    def __init__(self, config: SolanaAdapterConfig | None = None):
        self.config = config or SolanaAdapterConfig()
        self.client = SolanaDataClient(self.config)
        self.store = JsonStore(self.config.store_path)
        self.pending: dict[str, _PendingDraft] = {}

    def get_feed(self, *, topic: str = "trending", platform: str = "", context: AppContext | None = None) -> ScreenPayload:
        platform = platform if platform in PUMP_PLATFORMS else ""
        topic = topic if topic in TOPICS else "trending"
        if platform:
            resp = self.client.get("/tokens/platform", {"tag": platform, "limit": 20})
            rows = _extract_rows(resp)
            label = "PUMP HOT" if platform == "pump_in_hot" else "PUMP NEW"
        elif topic and topic != "trending":
            resp = self.client.get("/ranks", {"topic": topic, "chain": SOLANA, "limit": 20})
            rows = _extract_rows(resp)
            label = topic.upper()
        else:
            resp = self.client.get("/tokens/trending", {"chain": SOLANA, "current_page": 1, "page_size": 20})
            rows = _extract_rows(resp)
            label = "TRENDING"
        tokens = [_token_row(row) for row in rows[:20] if isinstance(row, dict)]
        return builders.feed(tokens, chain=SOLANA, source_label=label, mode="standard", context=context)

    def search_tokens(self, keyword: str, *, context: AppContext | None = None) -> ScreenPayload:
        resp = self.client.get("/tokens", {"keyword": keyword, "chain": SOLANA, "limit": 20})
        tokens = [_token_row(row) for row in _extract_rows(resp)[:20] if isinstance(row, dict)]
        return builders.feed(tokens, chain=SOLANA, source_label="SEARCH", mode="search", context=context)

    def get_token_detail(self, token_id: str, *, interval: str = "60", context: AppContext | None = None) -> ScreenPayload:
        addr, chain = split_token_reference(token_id)
        if not addr:
            raise ValueError("token_id is required")
        token = _first_payload(self.client.get(f"/tokens/{addr}-{chain}"))
        risk = _safe(lambda: self.client.get(f"/contracts/{addr}-{chain}"), {})
        kline = _safe(lambda: self.client.get(f"/klines/token/{addr}-{chain}", {"interval": interval, "limit": 48}), {})
        chart_points = _extract_chart(kline)
        flags = _risk_flags(risk)
        identity = _token_identity({**token, "addr": addr, "chain": chain, "token_id": f"{addr}-{chain}"})
        payload = {
            **identity,
            "addr": addr,
            "interval": interval,
            "pair": f"{identity.get('symbol', '???')} / USDC",
            "price": _fmt_price(token.get("current_price_usd", token.get("price"))),
            "price_raw": _safe_float(token.get("current_price_usd", token.get("price"))),
            "change_24h": _fmt_change(token.get("token_price_change_24h", token.get("price_change_24h"))),
            "change_positive": _safe_float(token.get("token_price_change_24h", token.get("price_change_24h"))) >= 0,
            "holders": f"{int(token['holders']):,}" if token.get("holders") else "N/A",
            "liquidity": _fmt_volume(token.get("main_pair_tvl", token.get("tvl"))),
            "volume_24h": _fmt_volume(token.get("token_tx_volume_usd_24h", token.get("tx_volume_u_24h"))),
            "market_cap": _fmt_volume(token.get("market_cap", token.get("fdv"))),
            "contract_short": _contract_short(addr),
            "chart": chart_points,
            "is_honeypot": flags["is_honeypot"],
            "is_mintable": flags["is_mintable"],
            "is_freezable": flags["is_freezable"],
            "risk_level": flags["risk_level"],
            "is_watchlisted": self._watchlist_contains(addr),
        }
        return builders.spotlight(payload, context=context)

    def get_portfolio(self, *, wallet_id: str = "paper", context: AppContext | None = None) -> ScreenPayload:
        state = self._state()
        positions = state.get("paper_positions", [])
        rows = [row for row in positions if isinstance(row, dict)]
        if not rows:
            rows = [{"symbol": "EMPTY", "chain": SOLANA, "value": "$0", "pnl": "$0", "source": "paper"}]
        return builders.portfolio(rows, chain=SOLANA, context=context)

    def get_watchlist(self, *, context: AppContext | None = None) -> ScreenPayload:
        rows = [_token_row(row) for row in self._state().get("watchlist", []) if isinstance(row, dict)]
        return builders.feed(rows, chain=SOLANA, source_label="WATCHLIST", mode="watchlist", context=context)

    def add_watchlist(self, token: dict[str, Any]) -> ScreenPayload:
        state = self._state()
        addr, chain = split_token_reference(token.get("token_id") or token.get("addr") or token.get("address") or "")
        if not addr:
            raise ValueError("token address is required")
        row = _token_row({**token, "addr": addr, "chain": chain, "token_id": f"{addr}-{chain}"})
        existing = [item for item in state.get("watchlist", []) if split_token_reference(item.get("token_id", ""))[0] != addr]
        existing.insert(0, row)
        state["watchlist"] = existing[:100]
        self._save(state)
        return builders.notify("Watchlist", f"Added {row.get('symbol', 'token')}")

    def create_action_draft(self, action: str, params: dict[str, Any], *, context: AppContext | None = None) -> ActionDraft:
        token_ref = params.get("token_id") or params.get("addr") or _selected_token_id(context)
        addr, chain = split_token_reference(str(token_ref or ""))
        symbol = str(params.get("symbol") or _selected_symbol(context) or "TOKEN")
        request_id = str(params.get("request_id") or f"sol_{int(time.time() * 1000)}")
        amount_sol = str(params.get("amount_sol") or params.get("amount_native") or self.config.default_buy_sol)
        action_name = _normalize_action(action)
        limit_price = params.get("limit_price")
        limit = action_name == "trade.limit_draft"
        summary = {
            "symbol": symbol,
            "token_id": f"{addr}-{chain}" if addr else "",
            "amount": f"{amount_sol} SOL",
            "action": action_name,
        }
        if limit_price not in (None, ""):
            summary["limit_price"] = str(limit_price)
        payload = {
            "trade_id": request_id,
            "action": _screen_action_label(action_name),
            "symbol": symbol,
            "chain": chain,
            "token_id": f"{addr}-{chain}" if addr else "",
            "amount_native": f"{amount_sol} SOL" if "SOL" not in amount_sol.upper() else amount_sol,
            "amount_usd": str(params.get("amount_usd") or ""),
            "timeout_sec": int(params.get("timeout_sec") or 30),
            "mode_label": str(params.get("mode_label") or "DRAFT"),
        }
        if limit:
            payload.update({"limit_price": str(limit_price or ""), "current_price": str(params.get("current_price") or ""), "distance": str(params.get("distance") or "")})
        else:
            payload.update({"tp_pct": params.get("tp_pct"), "sl_pct": params.get("sl_pct"), "slippage_pct": self.config.default_slippage_bps / 100})
        draft = ActionDraft(
            action=action_name,
            chain=chain,
            summary=summary,
            risk={"level": "medium", "reason": "Requires physical confirmation on device."},
            requires_confirmation=True,
            request_id=request_id,
            screen=builders.confirm(payload, context=context, limit=limit),
        )
        self.pending[request_id] = _PendingDraft(draft=draft, params={**params, "addr": addr, "chain": chain})
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

    def _watchlist_contains(self, addr: str) -> bool:
        for row in self._state().get("watchlist", []):
            row_addr, _ = split_token_reference(row.get("token_id") or row.get("addr") or "")
            if row_addr == addr:
                return True
        return False


def split_token_reference(token_ref: str, chain: str = SOLANA) -> tuple[str, str]:
    token = str(token_ref or "").strip()
    if token.lower().endswith("-solana"):
        token = token[:-7]
    return token, SOLANA


def _extract_rows(resp: dict[str, Any]) -> list[Any]:
    data = resp.get("data", resp)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("tokens", "list", "ranks", "items", "points", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    return []


def _first_payload(resp: dict[str, Any]) -> dict[str, Any]:
    data = resp.get("data", resp)
    if isinstance(data, dict):
        token = data.get("token", data)
        if isinstance(token, list):
            return token[0] if token and isinstance(token[0], dict) else {}
        return token if isinstance(token, dict) else {}
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else {}
    return {}


def _token_identity(token: dict[str, Any]) -> dict[str, Any]:
    raw = str(token.get("token_id") or token.get("addr") or token.get("address") or token.get("token") or "").strip()
    addr, chain = split_token_reference(raw or str(token.get("addr") or ""))
    symbol = str(token.get("symbol") or token.get("base_symbol") or token.get("token_symbol") or "?").strip() or "?"
    return {
        "symbol": symbol,
        "chain": chain,
        "addr": addr,
        "token_id": f"{addr}-{chain}" if addr else raw,
        "contract_tail": addr[-4:] if len(addr) >= 4 else addr,
        "source_tag": str(token.get("platform") or token.get("issue_platform") or token.get("source") or "").strip(),
    }


def _token_row(token: dict[str, Any]) -> dict[str, Any]:
    identity = _token_identity(token)
    change = token.get("token_price_change_24h", token.get("price_change_24h"))
    return {
        **identity,
        "price": _fmt_price(token.get("current_price_usd", token.get("price"))),
        "price_raw": _safe_float(token.get("current_price_usd", token.get("price"))),
        "change_24h": _fmt_change(change),
        "change_positive": _safe_float(change) >= 0,
        "volume_24h": _fmt_volume(token.get("token_tx_volume_usd_24h", token.get("tx_volume_u_24h"))),
        "market_cap": _fmt_volume(token.get("market_cap", token.get("fdv"))),
        "source": identity.get("source_tag") or "solana",
        "risk_level": str(token.get("risk_level") or "UNKNOWN"),
    }


def _extract_chart(kline_resp: dict[str, Any]) -> list[int]:
    points = _extract_rows(kline_resp)
    closes = [_safe_float(p.get("close", p.get("c"))) for p in points if isinstance(p, dict)]
    closes = [v for v in closes if v > 0]
    if not closes:
        return []
    lo, hi = min(closes), max(closes)
    if hi <= lo:
        return [500 for _ in closes]
    return [int((value - lo) / (hi - lo) * 1000) for value in closes]


def _risk_flags(resp: dict[str, Any]) -> dict[str, Any]:
    data = resp.get("data", resp) if isinstance(resp, dict) else {}
    if isinstance(data, dict) and isinstance(data.get("contract"), dict):
        data = data["contract"]
    text = json.dumps(data).lower() if isinstance(data, dict) else ""
    is_honeypot = "honeypot" in text and "true" in text
    is_mintable = bool(data.get("is_mintable") or data.get("mintable")) if isinstance(data, dict) else False
    is_freezable = bool(data.get("is_freezable") or data.get("freezable")) if isinstance(data, dict) else False
    level = "CRITICAL" if is_honeypot else ("HIGH" if is_mintable or is_freezable else "LOW")
    return {"is_honeypot": is_honeypot, "is_mintable": is_mintable, "is_freezable": is_freezable, "risk_level": level}


def _fmt_price(price: Any) -> str:
    value = _safe_float(price)
    if value <= 0:
        return "$0"
    if value >= 1000:
        return f"${value:,.0f}"
    if value >= 1:
        return f"${value:.4f}"
    if value >= 0.01:
        return f"${value:.6f}"
    decimals = max(2, -math.floor(math.log10(abs(value))) + 3)
    return f"${value:.{decimals}f}"


def _fmt_change(pct: Any) -> str:
    value = _safe_float(pct)
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):.2f}%"


def _fmt_volume(vol: Any) -> str:
    value = _safe_float(vol, default=-1)
    if value < 0:
        return "N/A"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        if math.isfinite(parsed):
            return parsed
    except (TypeError, ValueError):
        pass
    return default


def _contract_short(addr: str) -> str:
    return f"{addr[:4]}...{addr[-4:]}" if len(addr) > 10 else addr


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


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
