from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ava_devicekit.adapters.base import ChainAdapter
from ava_devicekit.core.types import AppContext, ScreenPayload
from ava_devicekit.formatting.numbers import format_compact_money, format_count, format_money, format_percent, parse_number
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

    This module has no dependency on the source assistant runtime. It owns only
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


    def get_signals(self, *, context: AppContext | None = None) -> ScreenPayload:
        resp = self.client.get("/signals/public/list", {"chain": SOLANA, "limit": 20, "pageSize": 20, "pageNO": 1})
        raw = resp.get("data", {})
        if isinstance(raw, dict):
            raw = raw.get("list", raw.get("items", []))
        rows = [_signal_row(row) for row in (raw if isinstance(raw, list) else []) if isinstance(row, dict)]
        return ScreenPayload(
            "browse",
            {
                "tokens": rows[:20],
                "chain": SOLANA,
                "mode": "signals",
                "source_label": "SIGNALS",
                "cursor": 0,
            },
            context,
        )

    def search_tokens(self, keyword: str, *, context: AppContext | None = None) -> ScreenPayload:
        resp = self.client.get("/tokens", {"keyword": keyword, "chain": SOLANA, "limit": 20})
        tokens = [_token_row(row) for row in _extract_rows(resp)[:20] if isinstance(row, dict)]
        return builders.feed(tokens, chain=SOLANA, source_label="SEARCH", mode="search", context=context)

    def get_token_detail(self, token_id: str, *, interval: str = "60", context: AppContext | None = None) -> ScreenPayload:
        addr, chain = split_token_reference(token_id)
        if not addr:
            raise ValueError("token_id is required")
        interval = str(interval or "60").strip().lower() or "60"
        token = _first_payload(self.client.get(f"/tokens/{addr}-{chain}"))
        risk = _safe(lambda: self.client.get(f"/contracts/{addr}-{chain}"), {})
        top100 = _safe(lambda: self.client.get(f"/tokens/top100/{addr}-{chain}"), {})
        is_live_second = interval == "s1"
        kline = {} if is_live_second else _safe(lambda: self.client.get(f"/klines/token/{addr}-{chain}", {"interval": interval, "limit": 48}), {})
        chart = _extract_chart_payload(kline)
        if is_live_second and not chart.get("chart"):
            price_now = _safe_float(token.get("current_price_usd", token.get("price")))
            if price_now > 0:
                chart = _extract_chart_payload({"data": {"points": [{"close": price_now, "time": 0} for _ in range(12)]}})
                chart["chart"] = [500] * 12
        flags = _risk_flags(risk)
        identity = _token_identity({**token, "addr": addr, "chain": chain, "token_id": f"{addr}-{chain}"})
        main_pair_id = _extract_main_pair_id(token)
        payload = {
            **identity,
            "addr": addr,
            "main_pair_id": main_pair_id,
            "interval": interval,
            "pair": f"{identity.get('symbol', '???')} / USDC",
            "price": _fmt_price(token.get("current_price_usd", token.get("price"))),
            "price_raw": _safe_float(token.get("current_price_usd", token.get("price"))),
            "change_24h": _fmt_change(token.get("token_price_change_24h", token.get("price_change_24h"))),
            "change_positive": _safe_float(token.get("token_price_change_24h", token.get("price_change_24h"))) >= 0,
            "holders": format_count(token.get("holders")) if token.get("holders") else "N/A",
            "liquidity": _fmt_volume(token.get("main_pair_tvl", token.get("tvl"))),
            "volume_24h": _fmt_volume(token.get("token_tx_volume_usd_24h", token.get("tx_volume_u_24h"))),
            "market_cap": _fmt_volume(token.get("market_cap", token.get("fdv"))),
            "top100_concentration": _extract_top100_concentration(top100),
            "contract_short": _contract_short(addr),
            **chart,
            "is_honeypot": flags["is_honeypot"],
            "is_mintable": flags["is_mintable"],
            "is_freezable": flags["is_freezable"],
            "risk_level": flags["risk_level"],
            "is_watchlisted": False,
        }
        if context and context.visible_rows:
            payload["total"] = len(context.visible_rows)
            cursor = context.cursor
            if cursor is None and context.selected:
                cursor = context.selected.cursor
            if cursor is not None:
                payload["cursor"] = cursor
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


def _extract_main_pair_id(token: dict[str, Any]) -> str:
    raw_main_pair = token.get("main_pair") if isinstance(token, dict) else None
    if isinstance(raw_main_pair, str):
        return raw_main_pair.strip()
    if isinstance(raw_main_pair, dict):
        for key in ("pair_id", "pair_address", "pair", "address", "id"):
            value = str(raw_main_pair.get(key) or "").strip()
            if value:
                return value
    for key in ("pair_id", "pair_address", "main_pair_address"):
        value = str(token.get(key) or "").strip() if isinstance(token, dict) else ""
        if value:
            return value
    return ""


def _extract_chart_payload(kline_resp: dict[str, Any]) -> dict[str, Any]:
    points = _extract_rows(kline_resp)
    closes = [_safe_float(p.get("close", p.get("c"))) for p in points if isinstance(p, dict)]
    closes = [v for v in closes if v > 0]
    if not closes:
        return {
            "chart": [],
            "chart_min": "--",
            "chart_max": "--",
            "chart_min_y": "--",
            "chart_mid_y": "--",
            "chart_max_y": "--",
            "chart_t_start": "",
            "chart_t_mid": "",
            "chart_t_end": "now",
        }
    lo, hi = min(closes), max(closes)
    times = [_safe_int(p.get("time", p.get("t"))) for p in points if isinstance(p, dict)]
    times = [v for v in times if v > 0]
    chart: list[int]
    if hi <= lo:
        chart = [500 for _ in closes]
    else:
        chart = [int((value - lo) / (hi - lo) * 1000) for value in closes]
    return {
        "chart": chart,
        "chart_min": _fmt_price(lo),
        "chart_max": _fmt_price(hi),
        "chart_min_y": _fmt_y_label(lo),
        "chart_mid_y": _fmt_y_label((lo + hi) / 2.0),
        "chart_max_y": _fmt_y_label(hi),
        "chart_t_start": _fmt_chart_time(times[0]) if times else "",
        "chart_t_mid": _fmt_chart_time(times[len(times) // 2]) if times else "",
        "chart_t_end": "now",
    }


def _balance_ratio_to_percent_points(raw_value: Any) -> float | None:
    parsed = parse_number(raw_value, default=math.nan)
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    if isinstance(raw_value, str) and "%" in raw_value:
        pct = parsed
    elif 0 <= parsed <= 1:
        pct = parsed * 100
    elif 0 <= parsed <= 100:
        pct = parsed
    else:
        return None
    return pct if math.isfinite(pct) else None


def _fmt_percent_points(value: float) -> str:
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{text}%"


def _extract_top100_concentration(top100_resp: dict[str, Any]) -> str:
    payload: Any = top100_resp.get("data", top100_resp) if isinstance(top100_resp, dict) else top100_resp
    summary_nodes: list[dict[str, Any]] = []
    top100_lists: list[list[Any]] = []

    if isinstance(payload, dict):
        summary_nodes.append(payload)
        if isinstance(payload.get("summary"), dict):
            summary_nodes.append(payload["summary"])
        for key in ("top100", "holders", "items", "list", "data"):
            entries = payload.get(key)
            if isinstance(entries, list) and entries:
                top100_lists.append(entries)
    elif isinstance(payload, list):
        top100_lists.append(payload)
        summary_nodes.extend(item for item in payload if isinstance(item, dict))

    for node in summary_nodes:
        for key in ("top100_concentration", "top_100_holding_rate", "top100_holding_rate", "top100_rate"):
            if node.get(key) not in (None, ""):
                pct = _balance_ratio_to_percent_points(node.get(key))
                return _fmt_percent_points(pct) if pct is not None else "N/A"

    for entries in top100_lists:
        total = 0.0
        seen = False
        for holder in entries[:100]:
            if not isinstance(holder, dict):
                continue
            share = holder.get("balance_ratio", holder.get("holding_rate", holder.get("rate", holder.get("percentage"))))
            pct = _balance_ratio_to_percent_points(share)
            if pct is None:
                continue
            total += pct
            seen = True
        if seen:
            return _fmt_percent_points(total)
    return "N/A"


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
    return format_money(price)


def _fmt_change(pct: Any) -> str:
    return format_percent(pct)


def _fmt_volume(vol: Any) -> str:
    value = _safe_float(vol, default=-1)
    if value < 0:
        return "N/A"
    return format_compact_money(value)


def _fmt_y_label(price: Any) -> str:
    value = _safe_float(price, default=-1)
    if value <= 0:
        return "N/A"
    return format_money(value)


def _fmt_chart_time(ts: int) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%m/%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return ""


def _safe_float(value: Any, default: float = 0.0) -> float:
    return parse_number(value, default=default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _contract_short(addr: str) -> str:
    return f"{addr[:4]}...{addr[-4:]}" if len(addr) > 10 else addr


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _compact_signal_number(amount: float) -> str:
    if amount >= 1_000_000:
        text = f"{amount / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if amount >= 1_000:
        text = f"{amount / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{text}K"
    if amount >= 100:
        return f"{amount:.1f}".rstrip("0").rstrip(".")
    if amount >= 1:
        return f"{amount:.2f}".rstrip("0").rstrip(".")
    return f"{amount:.4f}".rstrip("0").rstrip(".")


def _signal_default_quote_symbol(chain: str) -> str:
    return "SOL"


def _fmt_signal_amount(value: Any) -> str:
    amount = parse_number(value, default=-1)
    if amount < 0:
        return "0"
    return _compact_signal_number(abs(float(amount)))


def _fmt_signal_age(raw_ts: Any) -> str:
    ts = parse_number(raw_ts, default=-1)
    if ts <= 0:
        return ""
    try:
        delta = max(0, int(datetime.now().timestamp()) - int(ts))
    except Exception:
        return ""
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    return f"{delta // 86400}d"


def _signal_label_from_item(item: dict[str, Any]) -> str:
    text = str(item.get("action_type") or item.get("signal_type") or "").strip().lower()
    if "sell" in text:
        return "SELL"
    if "buy" in text:
        return "BUY"
    return ""


def _build_signal_meta_fields(item: dict[str, Any]) -> tuple[str, str, str, str, str]:
    first_age = _fmt_signal_age(item.get("first_signal_time"))
    first_text = f"First {first_age}" if first_age else "First -"
    last_age = _fmt_signal_age(item.get("signal_time"))
    last_text = f"Last {last_age}" if last_age else "Last -"
    action_count = parse_number(item.get("action_count"), default=-1)
    count_text = f"Count {int(action_count)}" if action_count > 0 else "Count -"
    volume_value = item.get("tx_volume_u_24h", item.get("token_tx_volume_usd_24h", item.get("volume_24h")))
    volume_text = _fmt_volume(volume_value)
    vol_text = f"Vol {volume_text}" if volume_text != "N/A" else "Vol -"
    return first_text, last_text, count_text, vol_text, f"{first_text} {last_text} {count_text} {vol_text}"


def _build_signal_display(item: dict[str, Any], chain: str) -> tuple[str, str, str, str, str, str, str]:
    label = _signal_label_from_item(item)
    value_text = label or "SIGNAL"
    first_text, last_text, count_text, vol_text, summary = _build_signal_meta_fields(item)
    actions = item.get("actions")
    if not isinstance(actions, list) or not actions:
        return label, value_text, first_text, last_text, count_text, vol_text, summary

    buy_total = 0.0
    sell_total = 0.0
    unit = ""
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("action_type") or "").strip().lower()
        volume = parse_number(action.get("quote_token_volume"), default=math.nan)
        if math.isnan(volume):
            volume = parse_number(action.get("volume_usd"), default=math.nan)
        if math.isnan(volume):
            volume = parse_number(action.get("base_token_volume"), default=math.nan)
        if math.isnan(volume):
            continue
        quote_token = str(action.get("quote_token_symbol") or action.get("quote_token") or "").strip()
        base_token = str(action.get("base_token_symbol") or action.get("base_token") or "").strip()
        if not unit:
            if quote_token and len(quote_token) <= 12 and quote_token.isascii():
                unit = quote_token.upper()
            elif base_token and len(base_token) <= 12 and base_token.isascii():
                unit = base_token.upper()
        if action_type == "sell":
            sell_total += volume
        else:
            buy_total += volume

    if not unit:
        unit = _signal_default_quote_symbol(chain)
    if buy_total > 0 and buy_total >= sell_total:
        return "BUY", f"BUY {_fmt_signal_amount(buy_total)} {unit}", first_text, last_text, count_text, vol_text, summary
    if sell_total > 0:
        return "SELL", f"SELL {_fmt_signal_amount(sell_total)} {unit}", first_text, last_text, count_text, vol_text, summary
    return label, value_text, first_text, last_text, count_text, vol_text, summary


def _signal_row(item: dict[str, Any]) -> dict[str, Any]:
    token_id = str(item.get("token") or item.get("token_id") or item.get("address") or "").strip()
    chain = SOLANA
    identity = _token_identity({"token_id": token_id, "chain": chain, "symbol": item.get("symbol"), "source": "signals"})
    change_value = item.get("price_change_24h", item.get("token_price_change_24h"))
    signal_label, signal_value, signal_first, signal_last, signal_count, signal_vol, signal_summary = _build_signal_display(item, chain)
    market_cap = item.get("mc_cur", item.get("market_cap", item.get("fdv")))
    volume = item.get("tx_volume_u_24h", item.get("token_tx_volume_usd_24h", item.get("volume_24h")))
    return {
        **identity,
        "price": _fmt_price(item.get("current_price_usd", item.get("price"))),
        "price_raw": _safe_float(item.get("current_price_usd", item.get("price"))),
        "change_24h": _fmt_change(change_value),
        "change_positive": _safe_float(change_value) >= 0,
        "volume_24h": _fmt_volume(volume),
        "market_cap": _fmt_volume(market_cap),
        "signal_type": str(item.get("signal_type") or "").strip(),
        "signal_label": signal_label,
        "signal_value": signal_value,
        "signal_first": signal_first,
        "signal_last": signal_last,
        "signal_count": signal_count,
        "signal_vol": signal_vol,
        "signal_summary": signal_summary,
        "headline": str(item.get("headline") or "").strip(),
        "signal_time": str(item.get("signal_time") or "").strip(),
        "source": "signals",
        "risk_level": str(item.get("risk_level") or "UNKNOWN"),
    }
