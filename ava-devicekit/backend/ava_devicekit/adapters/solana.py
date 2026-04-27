from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from ava_devicekit.adapters.base import ChainAdapter
from ava_devicekit.core.types import AppContext, ScreenPayload
from ava_devicekit.screen import builders

DATA_BASE = "https://data.ave-api.xyz/v2"
SOLANA = "solana"
PUMP_PLATFORMS = {"pump_in_hot", "pump_in_new"}
TOPICS = {"trending", "gainer", "loser", "new", "meme", "ai", "depin", "gamefi"}


@dataclass(slots=True)
class SolanaAdapterConfig:
    data_base: str = DATA_BASE
    api_key_env: str = "AVE_API_KEY"


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
        api_key = os.environ.get(self.config.api_key_env, "")
        if not api_key:
            raise RuntimeError(f"missing required environment variable: {self.config.api_key_env}")
        return {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        }


class SolanaAdapter(ChainAdapter):
    """Solana ChainAdapter for Ava DeviceKit.

    This module has no dependency on the legacy assistant runtime. It owns only
    basic Solana market/token data. App skills such as watchlist, portfolio, and
    trade drafts live in the app layer.
    """

    chain = SOLANA

    def __init__(self, config: SolanaAdapterConfig | None = None):
        self.config = config or SolanaAdapterConfig()
        self.client = SolanaDataClient(self.config)

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
            "is_watchlisted": False,
        }
        return builders.spotlight(payload, context=context)



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
