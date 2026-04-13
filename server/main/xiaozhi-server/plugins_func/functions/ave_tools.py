"""
AVE Cloud MCP tools for xiaozhi-esp32-server.

7 tools:
  ave_get_trending   → FEED screen
  ave_token_detail   → SPOTLIGHT screen
  ave_risk_check     → NOTIFY (block on CRITICAL)
  ave_buy_token      → CONFIRM screen
  ave_limit_order    → LIMIT_CONFIRM screen
  ave_sell_token     → CONFIRM screen (sell)
  ave_portfolio      → PORTFOLIO screen

All tools push display messages to the device via conn.loop.create_task().
"""
import json
import math
import os
import asyncio
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path
from typing import TYPE_CHECKING

from config.logger import setup_logging
from plugins_func.functions.ave_paper_store import (
    PaperStoreError,
    get_paper_account,
    get_trade_mode as load_trade_mode,
    list_open_orders as list_paper_open_orders,
    mutate_account as mutate_paper_account,
    set_trade_mode as persist_trade_mode,
)
from plugins_func.functions.ave_watchlist_store import (
    add_watchlist_entry,
    list_watchlist_entries,
    remove_watchlist_entry,
    watchlist_contains,
)
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from plugins_func.functions.ave_trade_mgr import (
    TRADE_CONFIRM_TIMEOUT_SEC,
    trade_mgr,
    _send_display,
    NATIVE_SOL,
    DEFAULT_SOLANA_AUTO_GAS,
    DEFAULT_SOLANA_GAS_LAMPORTS,
    _normalize_proxy_trade_payload,
    _normalize_quote_token_address,
    _trade_get,
)

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

DATA_BASE = "https://data.ave-api.xyz/v2"
TRADE_BASE = "https://bot-api.ave.ai"

# Default trade settings (overridable by voice)
DEFAULT_BUY_NATIVE_AMOUNT = 0.1
DEFAULT_TP_PCT = 25             # %
DEFAULT_SL_PCT = 15             # %
DEFAULT_SLIPPAGE = 100          # basis points (1%)
_BATCH_PRICE_EVM_SUFFIXES = ("-bsc", "-eth", "-base")
_CHAIN_SUFFIXES = ("solana", "bsc", "eth", "base")
_SUPPORTED_FEED_CHAINS = frozenset(_CHAIN_SUFFIXES)
_CHAIN_CYCLE_ORDER = ("solana", "base", "eth", "bsc")
_SIGNALS_SUPPORTED_CHAINS = frozenset({"solana", "bsc"})
_SIGNALS_CHAIN_CYCLE_ORDER = ("solana", "bsc")
_MAX_DISAMBIGUATION_ITEMS = 12
_DEFERRED_RESULT_FLUSH_POLL_ATTEMPTS = 200
_DEFERRED_RESULT_FLUSH_BLOCKED_DELAY_SEC = 0.05
_WATCHLIST_STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "ave_watchlists.json"
_PAPER_STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "ave_paper_accounts.json"
_TRADE_MODE_REAL = "real"
_TRADE_MODE_PAPER = "paper"
_VALID_TRADE_MODES = frozenset({_TRADE_MODE_REAL, _TRADE_MODE_PAPER})
_PAPER_NATIVE_TOKEN_META = {
    "solana": {
        "symbol": "SOL",
        "token_id": f"{NATIVE_SOL}-solana",
    },
    "eth": {
        "symbol": "ETH",
        "token_id": "0xC02aaA39b223FE8D0A0E5C4F27eAD9083C756Cc2-eth",
    },
    "base": {
        "symbol": "ETH",
        "token_id": "0x4200000000000000000000000000000000000006-base",
    },
    "bsc": {
        "symbol": "BNB",
        "token_id": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c-bsc",
    },
}

_CHAIN_NATIVE_BASE_UNITS = {
    "solana": Decimal("1000000000"),
    "eth": Decimal("1000000000000000000"),
    "base": Decimal("1000000000000000000"),
    "bsc": Decimal("1000000000000000000"),
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get_api_key():
    return os.environ.get("AVE_API_KEY", "")


def _data_headers():
    return {"X-API-KEY": _get_api_key(), "Content-Type": "application/json"}


def _data_get(path: str, params: dict = None) -> dict:
    url = f"{DATA_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers=_data_headers())
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"AVE data API {e.code}: {body}")


def _data_post(path: str, payload) -> dict:
    url = f"{DATA_BASE}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=_data_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"AVE data API {e.code}: {body}")


# ---------------------------------------------------------------------------
# Price formatting
# ---------------------------------------------------------------------------

def _fmt_price(price) -> str:
    """Format price with appropriate decimal places."""
    if price is None:
        return "N/A"
    price = float(price)
    if price == 0:
        return "$0"
    if price >= 1000:
        return f"${price:,.0f}"
    if price >= 1:
        return f"${price:.4f}"
    if price >= 0.01:
        return f"${price:.6f}"
    # Find first significant digit
    mag = math.floor(math.log10(abs(price)))
    decimals = max(2, -mag + 3)
    return f"${price:.{decimals}f}"


def _fmt_y_label(price) -> str:
    """Compact Y-axis price label (≤8 chars) for chart scale."""
    if price is None or price <= 0:
        return "N/A"
    price = float(price)
    if price >= 1000:
        return f"${price:,.0f}"
    if price >= 1:
        return f"${price:.2f}"
    if price >= 0.001:
        return f"${price:.4f}"
    # Sub-penny: scientific notation e.g. "2.34e-5"
    exp = int(math.floor(math.log10(abs(price))))
    mantissa = price / (10 ** exp)
    return f"{mantissa:.2f}e{exp}"


def _kline_limit_for_interval(interval: str) -> int:
    interval_to_size = {
        "s1": 48,
        "1": 48,
        "5": 48,
        "60": 48,
        "240": 42,
        "1440": 30,
    }
    return interval_to_size.get(str(interval), 48)


def _to_wss_kline_interval(interval: str) -> str:
    value = str(interval or "60").strip().lower()
    if not value:
        return "k60"
    if value == "s1":
        return "s1"
    if value.startswith("k"):
        return value
    return f"k{value}"


def _fmt_change(pct) -> str:
    if pct is None:
        return "N/A"
    pct = float(pct)
    sign = "+" if pct >= 0 else "-"
    return f"{sign}{abs(pct):.2f}%"


def _fmt_chart_time(ts: int) -> str:
    """Format a unix timestamp as 'MM/DD HH:MM' for chart axis labels."""
    if not ts:
        return ""
    from datetime import datetime
    try:
        return datetime.fromtimestamp(ts).strftime("%m/%d %H:%M")
    except Exception:
        return ""


def _fmt_volume(vol) -> str:
    if vol is None:
        return "N/A"
    if isinstance(vol, str):
        text = vol.strip().replace(",", "")
        if not text or text.lower() in {"n/a", "na", "none", "null", "--"}:
            return "N/A"
        vol = text
    try:
        vol = float(vol)
    except (TypeError, ValueError):
        return "N/A"
    if not math.isfinite(vol):
        return "N/A"
    if vol >= 1_000_000:
        return f"${vol/1_000_000:.1f}M"
    if vol >= 1_000:
        return f"${vol/1_000:.1f}K"
    return f"${vol:.0f}"


def _fmt_signed_volume(vol) -> str:
    numeric = _parse_numeric_value(vol)
    if numeric is None:
        return "N/A"
    sign = "+" if numeric >= 0 else "-"
    return f"{sign}{_fmt_volume(abs(numeric))}"


def _fmt_portfolio_pnl(vol) -> str:
    numeric = _parse_numeric_value(vol)
    if numeric is None:
        return "N/A"
    sign = "+" if numeric >= 0 else "-"
    abs_value = abs(float(numeric))
    if abs_value >= 1_000:
        return f"{sign}{_fmt_volume(abs_value)}"
    return f"{sign}${abs_value:.2f}"


def _parse_numeric_value(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return None
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text or text.lower() in {"n/a", "na", "none", "null", "--"}:
            return None
        if text.endswith("%"):
            text = text[:-1].strip()
        try:
            num = float(text)
        except ValueError:
            return None
        if not math.isfinite(num):
            return None
        return num
    return None


def _coalesce_numeric_value(primary, fallback=None):
    if _parse_numeric_value(primary) is not None:
        return primary
    if _parse_numeric_value(fallback) is not None:
        return fallback
    return None


def _fmt_percent(value, *, normalize_fraction: bool = False) -> str:
    if value in (None, ""):
        return "N/A"
    has_percent_suffix = isinstance(value, str) and "%" in value
    pct = _parse_numeric_value(value)
    if pct is None:
        return "N/A"
    if normalize_fraction and not has_percent_suffix and 0 <= pct <= 1:
        pct *= 100
    return f"{pct:.1f}%"


def _contract_short(addr: str) -> str:
    text = str(addr or "").strip()
    if not text:
        return "N/A"
    if len(text) <= 8:
        return text
    return f"{text[:4]}...{text[-4:]}"


def _signal_default_quote_symbol(chain: str) -> str:
    normalized = _normalize_chain_name(chain, "solana")
    if normalized == "solana":
        return "SOL"
    if normalized == "bsc":
        return "BNB"
    return "ETH"


def _native_token_meta(chain: str) -> dict:
    normalized = _normalize_chain_name(chain, "solana")
    return dict(_PAPER_NATIVE_TOKEN_META.get(normalized) or _PAPER_NATIVE_TOKEN_META["solana"])


def _native_token_address(chain: str) -> str:
    normalized = _normalize_chain_name(chain, "solana")
    if normalized == "solana":
        return _normalize_quote_token_address(normalized, NATIVE_SOL)

    token_id = str(_native_token_meta(normalized).get("token_id") or "")
    addr, _ = _split_token_reference(token_id, normalized)
    return addr


def _native_amount_label(chain: str, amount) -> str:
    native_symbol = str(_native_token_meta(chain).get("symbol") or "SOL")
    return f"{amount} {native_symbol}"


def _native_amount_to_base_units(chain: str, amount) -> int:
    multiplier = _CHAIN_NATIVE_BASE_UNITS.get(
        _normalize_chain_name(chain, "solana"),
        Decimal("1000000000"),
    )
    try:
        value = Decimal(str(amount))
    except (ArithmeticError, InvalidOperation, TypeError, ValueError):
        value = Decimal("0")
    if value <= 0:
        return 0
    return int((value * multiplier).to_integral_value())


def _estimate_native_usd(chain: str, amount) -> float:
    native_meta = _native_token_meta(chain)
    native_token_id = str(native_meta.get("token_id") or "")
    native_token_price_key = _normalize_batch_price_token_id(native_token_id)
    fallback_prices = {
        "solana": 150.0,
        "eth": 3000.0,
        "base": 3000.0,
        "bsc": 600.0,
    }

    try:
        amount_num = float(amount)
    except (TypeError, ValueError):
        return 0.0

    try:
        price_resp = _data_post("/tokens/price", _build_batch_price_payload([native_token_id]))
        price_data = price_resp.get("data", {})
        if isinstance(price_data, dict):
            native_entry = (
                price_data.get(native_token_id)
                or price_data.get(native_token_price_key)
                or {}
            )
            native_price = float(native_entry.get("current_price_usd", 0) or 0)
        elif isinstance(price_data, list) and price_data:
            native_price = float(price_data[0].get("current_price_usd", 0) or 0)
        else:
            native_price = 0
    except Exception:
        native_price = fallback_prices.get(_normalize_chain_name(chain, "solana"), 0.0)

    return amount_num * native_price


def _fmt_signal_amount(value) -> str:
    amount = _parse_numeric_value(value)
    if amount is None:
        return "0"
    amount = abs(float(amount))
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"{amount / 1_000:.1f}K"
    if amount >= 100:
        return f"{amount:.1f}".rstrip("0").rstrip(".")
    if amount >= 1:
        return f"{amount:.2f}".rstrip("0").rstrip(".")
    return f"{amount:.4f}".rstrip("0").rstrip(".")


def _fmt_signal_age(raw_ts, now_ts=None) -> str:
    ts = _parse_numeric_value(raw_ts)
    if ts is None or ts <= 0:
        return ""
    now_value = int(now_ts if now_ts is not None else time.time())
    delta = max(0, now_value - int(ts))
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    return f"{delta // 86400}d"


def _signal_label_from_totals(buy_total: float, sell_total: float) -> str:
    if buy_total > 0 and buy_total >= sell_total:
        return "BUY"
    if sell_total > 0:
        return "SELL"
    return ""


def _signal_label_from_item(item: dict) -> str:
    text = str(item.get("action_type") or item.get("signal_type") or "").strip().lower()
    if "sell" in text:
        return "SELL"
    if "buy" in text:
        return "BUY"
    return ""


def _build_signal_meta_fields(item: dict, now_ts=None) -> tuple[str, str, str, str, str]:
    first_age = _fmt_signal_age(item.get("first_signal_time"), now_ts)
    first_text = f"First {first_age}" if first_age else "First -"

    last_age = _fmt_signal_age(item.get("signal_time"), now_ts)
    last_text = f"Last {last_age}" if last_age else "Last -"

    action_count = _parse_numeric_value(item.get("action_count"))
    if action_count is not None and action_count > 0:
        count_text = f"Count {int(action_count)}"
    else:
        count_text = "Count -"

    volume_value = _coalesce_numeric_value(
        _coalesce_numeric_value(item.get("tx_volume_u_24h"), item.get("token_tx_volume_usd_24h")),
        item.get("volume_24h"),
    )
    volume_text = _fmt_volume(volume_value)
    if volume_text != "N/A":
        vol_text = f"Vol {volume_text}"
    else:
        vol_text = "Vol -"

    summary = f"{first_text} {last_text} {count_text} {vol_text}"
    return first_text, last_text, count_text, vol_text, summary


def _build_signal_display(item: dict, chain: str) -> tuple[str, str, str, str, str, str, str]:
    actions = item.get("actions")
    label = _signal_label_from_item(item)
    value_text = label or "SIGNAL"
    first_text, last_text, count_text, vol_text, summary = _build_signal_meta_fields(item)
    if not isinstance(actions, list) or not actions:
        return label, value_text, first_text, last_text, count_text, vol_text, summary

    buy_total = 0.0
    sell_total = 0.0
    unit = ""
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("action_type") or "").strip().lower()
        volume = _parse_numeric_value(action.get("quote_token_volume"))
        if volume is None:
            volume = _parse_numeric_value(action.get("volume_usd"))
        if volume is None:
            volume = _parse_numeric_value(action.get("base_token_volume"))
        if volume is None:
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

    label = _signal_label_from_totals(buy_total, sell_total)
    amount_total = 0.0
    if label == "BUY":
        amount_total = buy_total
    elif label == "SELL":
        amount_total = sell_total

    if label and amount_total > 0:
        value_text = f"{label} {_fmt_signal_amount(amount_total)} {unit}"
    else:
        label = label or _signal_label_from_item(item)
        value_text = label or "SIGNAL"

    return label, value_text, first_text, last_text, count_text, vol_text, summary


def _balance_ratio_to_percent_points(raw_value):
    """
    Convert a top-holder share value into percent points.

    /tokens/top100 balance_ratio is expected to be a fraction-of-1 value
    (for example 0.334417 -> 33.4417%), while explicit percent strings
    ("33.4%") are already percent points.
    """
    parsed = _parse_numeric_value(raw_value)
    if parsed is None:
        return None
    if isinstance(raw_value, str) and "%" in raw_value:
        pct = parsed
    elif 0 <= parsed <= 1:
        pct = parsed * 100
    elif 0 <= parsed <= 100:
        # Backward compatibility with payloads that already send percent points.
        pct = parsed
    else:
        return None
    if not math.isfinite(pct):
        return None
    return pct


def _extract_top100_concentration(top100_resp: dict) -> str:
    root = top100_resp if isinstance(top100_resp, dict) else top100_resp
    payload = root.get("data", root) if isinstance(root, dict) else root
    summary_nodes = []
    top100_lists = []

    if isinstance(payload, dict):
        summary_nodes.append(payload)
        summary = payload.get("summary")
        if isinstance(summary, dict):
            summary_nodes.append(summary)
        for key in ("top100", "holders", "items", "list", "data"):
            entries = payload.get(key)
            if isinstance(entries, list) and entries:
                top100_lists.append(entries)
    elif isinstance(payload, list):
        top100_lists.append(payload)
        for item in payload:
            if isinstance(item, dict):
                summary_nodes.append(item)

    for node in summary_nodes:
        if not isinstance(node, dict):
            continue
        for key in ("top100_concentration", "top_100_holding_rate", "top100_holding_rate", "top100_rate"):
            if node.get(key) not in (None, ""):
                return _fmt_percent(node.get(key), normalize_fraction=True)

    for entries in top100_lists:
        total = 0.0
        seen = False
        for top_holder in entries[:100]:
            if not isinstance(top_holder, dict):
                continue
            share = top_holder.get(
                "balance_ratio",
                top_holder.get("holding_rate", top_holder.get("rate", top_holder.get("percentage"))),
            )
            percent_points = _balance_ratio_to_percent_points(share)
            if percent_points is None:
                continue
            total += percent_points
            seen = True
        if seen:
            return _fmt_percent(total)
    return "N/A"


def _safe_top100_summary_get(addr: str, chain: str) -> dict:
    try:
        return _data_get(f"/tokens/top100/{addr}-{chain}")
    except Exception as exc:
        logger.bind(tag=TAG).warning(
            f"top100 lookup failed; returning empty summary token={addr} chain={chain} error={exc}"
        )
        return {}


def _normalize_batch_price_token_id(token_id: str) -> str:
    token_id = str(token_id or "")
    if token_id.endswith(_BATCH_PRICE_EVM_SUFFIXES):
        return token_id.lower()
    return token_id


def _coerce_json_number(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else value
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    return int(num) if num.is_integer() else num


def _build_batch_price_payload(token_ids, tvl_min=None, tx_24h_volume_min=None) -> dict:
    payload = {
        "token_ids": [
            _normalize_batch_price_token_id(token_id)
            for token_id in token_ids
            if token_id
        ]
    }
    tvl_min_value = _coerce_json_number(tvl_min)
    if tvl_min_value is not None:
        payload["tvl_min"] = tvl_min_value
    volume_min_value = _coerce_json_number(tx_24h_volume_min)
    if volume_min_value is not None:
        payload["tx_24h_volume_min"] = volume_min_value
    return payload


def _trim_points(points: list, limit: int) -> list:
    if not isinstance(points, list):
        return []
    if limit <= 0:
        return points
    if len(points) <= limit:
        return points
    return points[-limit:]


def _format_token_units(raw_amount, decimals=None, symbol: str = "") -> str:
    if raw_amount in (None, ""):
        return ""

    amount_text = str(raw_amount)
    if decimals not in (None, ""):
        try:
            scaled = Decimal(amount_text) / (Decimal(10) ** int(decimals))
            amount_text = _format_display_amount(scaled)
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            amount_text = str(raw_amount)
    else:
        parsed_amount = _parse_decimal_amount(amount_text)
        if parsed_amount is not None:
            amount_text = _format_display_amount(parsed_amount)

    return f"{amount_text} {symbol}".strip()


def _format_quote_out_amount(quote_resp: dict, symbol: str = "") -> str:
    data = quote_resp.get("data", quote_resp)
    if not isinstance(data, dict):
        return ""

    formatted = data.get("outAmountFormatted", data.get("estimateOutFormatted", data.get("out_amount_formatted", "")))
    if formatted:
        return _normalize_display_amount_text(str(formatted))

    return _format_token_units(
        data.get("estimateOut", data.get("outAmount", data.get("out_amount", ""))),
        data.get("decimals"),
        symbol,
    )


def _split_token_reference(token_ref: str, chain: str = "solana") -> tuple[str, str]:
    token_text = str(token_ref or "").strip()
    chain_text = str(chain or "solana").strip().lower() or "solana"
    if not token_text:
        return "", chain_text

    token_lower = token_text.lower()
    for suffix_chain in _CHAIN_SUFFIXES:
        suffix = f"-{suffix_chain}"
        if token_lower.endswith(suffix):
            base_addr = token_text[:-len(suffix)]
            if base_addr:
                return base_addr, suffix_chain
    return token_text, chain_text


def _asset_identity_fields(token: dict) -> dict:
    token_data = token if isinstance(token, dict) else {}
    raw_token_id = str(
        token_data.get("token_id")
        or token_data.get("addr")
        or token_data.get("address")
        or token_data.get("token")
        or ""
    ).strip()
    raw_chain = _normalize_chain_name(token_data.get("chain"), "solana")
    addr, chain = _split_token_reference(raw_token_id, raw_chain)
    addr = str(token_data.get("addr") or token_data.get("address") or addr or raw_token_id).strip()
    contract_tail = addr[-4:] if len(addr) >= 4 else addr
    return {
        "symbol": str(token_data.get("symbol") or "?").strip() or "?",
        "chain": chain,
        "contract_tail": contract_tail,
        "token_id": raw_token_id or addr,
        "source_tag": str(
            token_data.get("platform")
            or token_data.get("issue_platform")
            or token_data.get("source")
            or ""
        ).strip(),
    }


def _extract_main_pair_id(token: dict) -> str:
    token_data = token if isinstance(token, dict) else {}
    raw_main_pair = token_data.get("main_pair")
    if isinstance(raw_main_pair, str):
        return raw_main_pair.strip()
    if isinstance(raw_main_pair, dict):
        for key in ("pair_id", "pair_address", "pair", "address", "id"):
            value = str(raw_main_pair.get(key) or "").strip()
            if value:
                return value
    for key in ("pair_id", "pair_address", "main_pair_address"):
        value = str(token_data.get(key) or "").strip()
        if value:
            return value
    return ""


def _build_disambiguation_payload(items: list[dict], *, nav_from: str = "feed") -> dict:
    normalized_items = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        identity = _asset_identity_fields(item)
        if not identity.get("token_id"):
            continue
        normalized_items.append(identity)
    total_candidates = len(normalized_items)
    visible_items = normalized_items[:_MAX_DISAMBIGUATION_ITEMS]
    return {
        "items": visible_items,
        "cursor": 0,
        "nav_from": nav_from,
        "total_candidates": total_candidates,
        "overflow_count": max(0, total_candidates - len(visible_items)),
    }


# ---------------------------------------------------------------------------
# Pending trade state / result payload helpers
# ---------------------------------------------------------------------------

def _ensure_ave_state(conn: "ConnectionHandler") -> dict:
    state = getattr(conn, "ave_state", None)
    if not isinstance(state, dict):
        conn.ave_state = {}
    return conn.ave_state


def _resolve_spotlight_symbol(state: dict, addr: str, chain: str, symbol: str = "", cursor=None) -> str:
    resolved_symbol = str(symbol or "").strip()
    if resolved_symbol:
        return resolved_symbol

    current_token = state.get("current_token")
    if isinstance(current_token, dict):
        cur_addr, cur_chain = _split_token_reference(
            current_token.get("addr", ""),
            current_token.get("chain", chain),
        )
        if cur_addr == addr and cur_chain == chain:
            resolved_symbol = str(current_token.get("symbol") or "").strip()
            if resolved_symbol:
                return resolved_symbol

    feed_list = state.get("feed_token_list", [])
    if isinstance(feed_list, list):
        if cursor is not None:
            try:
                idx = int(cursor)
            except (TypeError, ValueError):
                idx = -1
            if 0 <= idx < len(feed_list):
                item = feed_list[idx]
                if isinstance(item, dict):
                    item_addr, item_chain = _split_token_reference(
                        item.get("addr", ""),
                        item.get("chain", chain),
                    )
                    if item_addr == addr and item_chain == chain:
                        resolved_symbol = str(item.get("symbol") or "").strip()
                        if resolved_symbol:
                            return resolved_symbol

        for item in feed_list:
            if not isinstance(item, dict):
                continue
            item_addr, item_chain = _split_token_reference(
                item.get("addr", ""),
                item.get("chain", chain),
            )
            if item_addr == addr and item_chain == chain:
                resolved_symbol = str(item.get("symbol") or "").strip()
                if resolved_symbol:
                    return resolved_symbol

    return addr[:8] if addr else "?"


def _resolve_trade_symbol(conn: "ConnectionHandler", addr: str, chain: str, symbol: str = "") -> str:
    resolved_symbol = str(symbol or "").strip()
    if resolved_symbol and resolved_symbol != "TOKEN":
        return resolved_symbol

    state = _ensure_ave_state(conn)
    spotlight_symbol = _resolve_spotlight_symbol(state, addr, chain, "")
    if spotlight_symbol and spotlight_symbol not in {"?", addr[:8] if addr else ""}:
        return spotlight_symbol

    account = get_paper_account(_paper_store_path(), _trade_namespace(conn))
    positions = account.get("positions", {})
    if isinstance(positions, dict):
        existing = positions.get(_paper_position_key(addr, chain))
        if isinstance(existing, dict):
            existing_symbol = str(existing.get("symbol") or "").strip()
            if existing_symbol and existing_symbol != "TOKEN":
                return existing_symbol

    return resolved_symbol or "TOKEN"


def _build_spotlight_loading_payload(addr: str, chain: str, *, symbol: str = "",
                                     interval: str = "60", feed_cursor=None, feed_total=None,
                                     origin_hint: str = "", is_watchlisted: bool = False) -> dict:
    resolved_symbol = str(symbol or "").strip() or (addr[:8] if addr else "?")
    identity = _asset_identity_fields(
        {
            "addr": addr,
            "chain": chain,
            "symbol": resolved_symbol,
            "token_id": f"{addr}-{chain}",
        }
    )
    spotlight_data = {
        **identity,
        "addr": addr,
        "interval": str(interval or "60"),
        "pair": f"{resolved_symbol} / USDC",
        "price": "--",
        "price_raw": 0,
        "change_24h": "Loading",
        "change_positive": True,
        "holders": "--",
        "liquidity": "--",
        "volume_24h": "--",
        "market_cap": "--",
        "top100_concentration": "--",
        "contract_short": _contract_short(addr),
        "chart": [500] * 12,
        "chart_min": "--",
        "chart_max": "--",
        "chart_min_y": "--",
        "chart_mid_y": "--",
        "chart_max_y": "--",
        "chart_t_start": "",
        "chart_t_mid": "",
        "chart_t_end": "now",
        "is_honeypot": False,
        "is_mintable": False,
        "is_freezable": False,
        "risk_level": "LOADING",
        "origin_hint": str(origin_hint or "").strip(),
        "is_watchlisted": bool(is_watchlisted),
    }
    if feed_cursor is not None and feed_total is not None:
        spotlight_data["cursor"] = feed_cursor
        spotlight_data["total"] = feed_total
    return spotlight_data


def _is_same_spotlight_token(state: dict, addr: str, chain: str) -> bool:
    if str(state.get("screen") or "") != "spotlight":
        return False
    current_token = state.get("current_token")
    if not isinstance(current_token, dict):
        return False
    cur_addr, cur_chain = _split_token_reference(
        current_token.get("addr", ""),
        current_token.get("chain", chain),
    )
    return cur_addr == addr and cur_chain == chain


def _spotlight_request_is_current(state: dict, request_seq: int) -> bool:
    return int(state.get("spotlight_request_seq", 0) or 0) == int(request_seq or 0)


def _normalized_interval_value(interval: str) -> str:
    value = str(interval or "").strip().lower()
    if value.startswith("k"):
        return value[1:]
    return value


async def _ave_token_detail_async(conn: "ConnectionHandler", *, addr: str, chain: str, symbol: str = "",
                                  interval: str = "60", feed_cursor=None, feed_total=None,
                                  request_seq: int = 0, previous_screen: str = ""):
    try:
        interval = str(interval or "60").strip().lower() or "60"
        is_live_second = interval == "s1"
        kline_limit = _kline_limit_for_interval(interval)

        token_task = asyncio.to_thread(_data_get, f"/tokens/{addr}-{chain}")
        risk_task = asyncio.to_thread(_data_get, f"/contracts/{addr}-{chain}")
        top100_task = asyncio.to_thread(_safe_top100_summary_get, addr, chain)
        if is_live_second:
            token_resp, risk_resp, top100_resp = await asyncio.gather(token_task, risk_task, top100_task)
            kline_resp = {"data": {"points": []}}
        else:
            kline_task = asyncio.to_thread(
                _data_get,
                f"/klines/token/{addr}-{chain}",
                {"interval": interval, "limit": kline_limit},
            )
            token_resp, kline_resp, risk_resp, top100_resp = await asyncio.gather(
                token_task,
                kline_task,
                risk_task,
                top100_task,
            )

        token_data = token_resp.get("data", token_resp)
        token = token_data.get("token", token_data) if isinstance(token_data, dict) else token_data
        if isinstance(token, list) and token:
            token = token[0]

        kline_points = _trim_points(kline_resp.get("data", {}).get("points", []), kline_limit)
        if not is_live_second and not kline_points:
            main_pair_id = _extract_main_pair_id(token)
            if main_pair_id:
                try:
                    pair_kline_resp = await asyncio.to_thread(
                        _data_get,
                        f"/klines/pair/{main_pair_id}-{chain}",
                        {"interval": interval, "limit": kline_limit},
                    )
                    kline_points = _trim_points(
                        pair_kline_resp.get("data", {}).get("points", []),
                        kline_limit,
                    )
                except Exception:
                    pass
        raw_closes = [float(p.get("close", p.get("c", 0)) or 0) for p in kline_points if p.get("close") or p.get("c")]
        raw_times = [int(p.get("time", p.get("t", 0)) or 0) for p in kline_points if p.get("close") or p.get("c")]
        price_now = float(token.get("current_price_usd", token.get("price", 0)) or 0)
        if is_live_second:
            token_id = f"{addr}-{chain}"
            seeded_closes = []
            seeded_times = []
            if hasattr(conn, "ave_wss"):
                wss = conn.ave_wss
                raw_owner_token_id = str(getattr(wss, "_spotlight_raw_owner_token_id", "") or "")
                raw_owner_chain = str(getattr(wss, "_spotlight_raw_owner_chain", "") or "").strip().lower()
                raw_owner_interval = _normalized_interval_value(
                    getattr(wss, "_spotlight_raw_owner_interval", "")
                )
                owner_token_matches = (not raw_owner_token_id) or (raw_owner_token_id == token_id)
                owner_chain_matches = (not raw_owner_chain) or (raw_owner_chain == chain)
                owner_interval_matches = (not raw_owner_interval) or (raw_owner_interval == "s1")
                if (
                    getattr(wss, "_spotlight_id", "") == token_id
                    and owner_token_matches
                    and owner_chain_matches
                    and owner_interval_matches
                ):
                    seeded_closes = list(getattr(wss, "_spotlight_raw_closes", []) or [])
                    seeded_times = list(getattr(wss, "_spotlight_raw_times", []) or [])
            raw_closes = [float(v) for v in seeded_closes if v is not None and float(v) > 0][-kline_limit:]
            raw_times = [int(v) for v in seeded_times if v][-kline_limit:]
            if not raw_closes and price_now > 0:
                raw_closes = [price_now] * 12
            kline_points = [
                {"close": value, "time": raw_times[idx] if idx < len(raw_times) else 0}
                for idx, value in enumerate(raw_closes)
            ]
        chart_values = _normalize_kline(kline_points)
        if is_live_second and raw_closes and len(set(raw_closes)) == 1:
            chart_values = [500] * len(raw_closes)
        price_min = min(raw_closes) if raw_closes else 0
        price_max = max(raw_closes) if raw_closes else 0
        n_pts = len(raw_times)
        t_start = raw_times[0] if n_pts > 0 else 0
        t_mid = raw_times[n_pts // 2] if n_pts > 0 else 0

        flags = _risk_flags(risk_resp)
        state = _ensure_ave_state(conn)
        if not _spotlight_request_is_current(state, request_seq):
            return

        identity = _asset_identity_fields(
            {
                **(token if isinstance(token, dict) else {}),
                "addr": addr,
                "chain": chain,
                "symbol": token.get("symbol", symbol or "???"),
                "token_id": f"{addr}-{chain}",
            }
        )
        origin_hint = _resolve_spotlight_origin_hint(state, addr, chain, previous_screen=previous_screen)
        is_watchlisted = _is_watchlisted_for_token(conn, addr, chain)
        spotlight_data = {
            **identity,
            "addr": addr,
            "interval": str(interval or "60"),
            "pair": f"{token.get('symbol', symbol or '???')} / USDC",
            "price": _fmt_price(token.get("current_price_usd", token.get("price"))),
            "price_raw": price_now,
            "change_24h": _fmt_change(token.get("token_price_change_24h", token.get("price_change_24h"))),
            "change_positive": float(token.get("token_price_change_24h", token.get("price_change_24h", 0)) or 0) >= 0,
            "holders": f"{int(token['holders']):,}" if token.get("holders") else "N/A",
            "liquidity": _fmt_volume(token.get("main_pair_tvl", token.get("tvl"))),
            "volume_24h": _fmt_volume(
                _coalesce_numeric_value(
                    token.get("token_tx_volume_usd_24h"),
                    token.get("tx_volume_u_24h"),
                )
            ),
            "market_cap": _fmt_volume(
                _coalesce_numeric_value(
                    token.get("market_cap"),
                    token.get("fdv"),
                )
            ),
            "top100_concentration": _extract_top100_concentration(top100_resp),
            "contract_short": _contract_short(addr),
            "chart": chart_values,
            "chart_min": _fmt_price(price_min),
            "chart_max": _fmt_price(price_max),
            "chart_min_y": _fmt_y_label(price_min),
            "chart_mid_y": _fmt_y_label((price_min + price_max) / 2.0),
            "chart_max_y": _fmt_y_label(price_max),
            "chart_t_start": _fmt_chart_time(t_start),
            "chart_t_mid": _fmt_chart_time(t_mid),
            "chart_t_end": "now",
            "is_honeypot": flags["is_honeypot"],
            "is_mintable": flags["is_mintable"],
            "is_freezable": flags["is_freezable"],
            "risk_level": flags["risk_level"],
            "origin_hint": origin_hint,
            "is_watchlisted": bool(is_watchlisted),
        }
        if feed_cursor is not None and feed_total is not None:
            spotlight_data["cursor"] = feed_cursor
            spotlight_data["total"] = feed_total

        await _send_display(conn, "spotlight", spotlight_data)
        state = _ensure_ave_state(conn)
        if not _spotlight_request_is_current(state, request_seq):
            return

        if hasattr(conn, "ave_wss"):
            wss_interval = _to_wss_kline_interval(interval)
            conn.ave_wss.set_spotlight(
                addr,
                chain,
                spotlight_data,
                raw_closes,
                raw_times,
                interval=wss_interval,
            )

        sym = token.get("symbol", symbol or "???")
        state = _ensure_ave_state(conn)
        if not _spotlight_request_is_current(state, request_seq):
            return
        state["screen"] = "spotlight"
        state["current_token"] = {
            "addr": addr,
            "chain": chain,
            "symbol": sym,
            "token_id": identity.get("token_id", f"{addr}-{chain}"),
            "contract_tail": identity.get("contract_tail", ""),
            "source_tag": identity.get("source_tag", ""),
            "origin_hint": origin_hint,
        }
        state["spotlight_snapshot"] = {
            "addr": addr,
            "chain": chain,
            "symbol": sym,
            "pair": spotlight_data.get("pair", ""),
            "price": spotlight_data.get("price", ""),
            "change_24h": spotlight_data.get("change_24h", ""),
            "market_cap": spotlight_data.get("market_cap", ""),
            "volume_24h": spotlight_data.get("volume_24h", ""),
            "liquidity": spotlight_data.get("liquidity", ""),
            "holders": spotlight_data.get("holders", ""),
            "top100_concentration": spotlight_data.get("top100_concentration", ""),
            "risk_level": spotlight_data.get("risk_level", ""),
            "is_watchlisted": bool(is_watchlisted),
            "origin_hint": origin_hint,
            "cursor": spotlight_data.get("cursor"),
            "total": spotlight_data.get("total"),
        }
        state["spotlight_origin_hint"] = origin_hint
        state["spotlight_is_watchlisted"] = bool(is_watchlisted)
        if "nav_from" not in state:
            state["nav_from"] = "feed"
    except Exception as e:
        logger.bind(tag=TAG).error(f"ave_token_detail error: {e}")
        try:
            state = _ensure_ave_state(conn)
            if _spotlight_request_is_current(state, request_seq):
                await _send_display(conn, "notify", {
                    "level": "error", "title": "Lookup Failed", "body": str(e)[:60],
                })
        except Exception:
            pass


def _normalize_search_session_items(items) -> list[dict]:
    normalized_items = []
    for item in items or []:
        if isinstance(item, dict) and item.get("token_id"):
            normalized_items.append(dict(item))
    return normalized_items


def _clear_search_state(state: dict) -> None:
    for key in (
        "search_query",
        "search_chain",
        "search_results",
        "search_cursor",
        "search_session",
        "disambiguation_items",
        "disambiguation_cursor",
    ):
        state.pop(key, None)


def _next_feed_session(state: dict) -> int:
    try:
        current = int(state.get("feed_session", 0) or 0)
    except (TypeError, ValueError):
        current = 0
    if current < 0:
        current = 0
    session = current + 1
    state["feed_session"] = session
    return session


def _current_feed_session(state: dict) -> int:
    try:
        session = int(state.get("feed_session", 0) or 0)
    except (TypeError, ValueError):
        session = 0
    if session <= 0:
        session = _next_feed_session(state)
    else:
        state["feed_session"] = session
    return session


def _invalidate_live_feed_session(
    conn: "ConnectionHandler",
    *,
    session: int = None,
    chain: str = None,
    clear_tokens: bool = True,
) -> int:
    state = _ensure_ave_state(conn)
    if session is None:
        session = _next_feed_session(state)
    else:
        try:
            session = int(session)
        except (TypeError, ValueError):
            session = _next_feed_session(state)
        else:
            state["feed_session"] = session

    wss = getattr(conn, "ave_wss", None)
    if wss is not None:
        try:
            wss.invalidate_feed_session(
                session=session,
                chain=chain,
                clear_tokens=clear_tokens,
            )
        except Exception:
            pass
    return session


def _reset_to_standard_feed_state(state: dict) -> None:
    state["screen"] = "feed"
    state["feed_mode"] = "standard"
    state.pop("nav_from", None)
    state.pop("order_list", None)
    _clear_search_state(state)


def _remember_home_feed_state(state: dict, *, source: str = "trending", platform: str = "") -> None:
    normalized_source = str(source or "trending").strip().lower() or "trending"
    if normalized_source in {"signals", "watchlist", "orders"}:
        normalized_source = "trending"
    state["home_feed_source"] = normalized_source
    state["home_feed_platform"] = str(platform or "").strip()


def _refresh_home_feed(conn: "ConnectionHandler") -> ActionResponse:
    state = _ensure_ave_state(conn)
    remembered_source = str(
        state.get("home_feed_source") or state.get("feed_source", "trending") or "trending"
    ).strip().lower() or "trending"
    remembered_platform = str(
        state.get("home_feed_platform") or state.get("feed_platform", "") or ""
    ).strip()
    if remembered_source in {"signals", "watchlist", "orders"}:
        remembered_source = "trending"
    _invalidate_live_feed_session(conn)
    _reset_to_standard_feed_state(state)
    if remembered_platform:
        return ave_get_trending(conn, topic="", platform=remembered_platform)
    return ave_get_trending(conn, topic=remembered_source)


def _save_search_session(
    conn: "ConnectionHandler",
    *,
    query: str,
    chain: str = "all",
    items=None,
    cursor: int = 0,
) -> dict:
    state = _ensure_ave_state(conn)
    session_items = _normalize_search_session_items(items)
    try:
        cursor = int(cursor)
    except (TypeError, ValueError):
        cursor = 0
    if session_items:
        cursor = max(0, min(cursor, len(session_items) - 1))
    else:
        cursor = 0
    session = {
        "query": str(query or "").strip(),
        "chain": str(chain or "all").strip().lower() or "all",
        "cursor": cursor,
        "items": session_items,
    }
    state["search_session"] = session
    state["search_query"] = session["query"]
    state["search_chain"] = session["chain"]
    state["search_cursor"] = session["cursor"]
    state["search_results"] = list(session_items)
    return session


def _ensure_search_session(state: dict) -> dict:
    session = state.get("search_session")
    if isinstance(session, dict):
        items = _normalize_search_session_items(session.get("items", []))
        if items:
            try:
                cursor = int(session.get("cursor", state.get("search_cursor", 0)))
            except (TypeError, ValueError):
                cursor = 0
            cursor = max(0, min(cursor, len(items) - 1))
            session["query"] = str(session.get("query", state.get("search_query", "")) or "").strip()
            session["chain"] = str(session.get("chain", state.get("search_chain", "all")) or "all").strip().lower() or "all"
            session["cursor"] = cursor
            session["items"] = items
            state["search_session"] = session
            state["search_query"] = session["query"]
            state["search_chain"] = session["chain"]
            state["search_cursor"] = cursor
            state["search_results"] = list(items)
            return session

    legacy_items = _normalize_search_session_items(state.get("search_results"))
    if not legacy_items:
        legacy_items = _normalize_search_session_items(state.get("disambiguation_items"))
    if not legacy_items:
        return {}

    try:
        cursor = int(state.get("search_cursor", state.get("feed_cursor", 0)))
    except (TypeError, ValueError):
        cursor = 0
    cursor = max(0, min(cursor, len(legacy_items) - 1))
    session = {
        "query": str(state.get("search_query", "") or "").strip(),
        "chain": str(state.get("search_chain", "all") or "all").strip().lower() or "all",
        "cursor": cursor,
        "items": legacy_items,
    }
    state["search_session"] = session
    state["search_query"] = session["query"]
    state["search_chain"] = session["chain"]
    state["search_cursor"] = cursor
    state["search_results"] = list(legacy_items)
    return session


def _set_search_session_cursor(state: dict, cursor: int) -> dict:
    session = _ensure_search_session(state)
    if not session:
        return {}
    try:
        cursor = int(cursor)
    except (TypeError, ValueError):
        cursor = 0
    items = session.get("items", [])
    if items:
        cursor = max(0, min(cursor, len(items) - 1))
    else:
        cursor = 0
    session["cursor"] = cursor
    state["search_session"] = session
    state["search_cursor"] = cursor
    return session


def _set_feed_navigation_state(state: dict, items, *, cursor: int = 0) -> list[dict]:
    session_items = _normalize_search_session_items(items)
    try:
        cursor = int(cursor)
    except (TypeError, ValueError):
        cursor = 0
    feed_token_list = [
        {
            "addr": item.get("token_id", "").split("-")[0] if item.get("token_id") else "",
            "chain": item.get("chain", "solana"),
            "symbol": item.get("symbol", ""),
        }
        for item in session_items
    ]
    if feed_token_list:
        cursor = max(0, min(cursor, len(feed_token_list) - 1))
    else:
        cursor = 0
    feed_tokens = {}
    feed_symbol_entries = {}
    for item in session_items:
        symbol = str(item.get("symbol", "")).upper()
        token_id = str(item.get("token_id", "")).strip()
        if not symbol or not token_id:
            continue
        entry = {
            "addr": token_id,
            "chain": item.get("chain", "solana"),
        }
        feed_tokens.setdefault(symbol, dict(entry))
        feed_symbol_entries.setdefault(symbol, []).append(dict(entry))
    state["feed_cursor"] = cursor
    state["feed_token_list"] = feed_token_list
    state["feed_tokens"] = feed_tokens
    state["feed_symbol_entries"] = feed_symbol_entries
    return feed_token_list


def _watchlist_namespace(conn: "ConnectionHandler") -> str:
    wallet_id = str(os.environ.get("AVE_PROXY_WALLET_ID", "") or "").strip()
    if wallet_id:
        return wallet_id
    state = _ensure_ave_state(conn)
    fallback_wallet = str(state.get("wallet_id") or "").strip()
    return fallback_wallet or "default"


def _watchlist_store_path() -> Path:
    override = str(os.environ.get("AVE_WATCHLIST_STORE_PATH", "") or "").strip()
    return Path(override) if override else _WATCHLIST_STORE_PATH


def _trade_namespace(conn: "ConnectionHandler") -> str:
    return _watchlist_namespace(conn)


def _resolve_proxy_wallet_target(
    conn: "ConnectionHandler",
    chain: str = "",
) -> tuple[str, str]:
    requested_chain = _normalize_chain_name(chain)
    state = _ensure_ave_state(conn)

    cached_wallets = state.get("portfolio_wallets")
    if isinstance(cached_wallets, list) and cached_wallets:
        wallets = cached_wallets
    else:
        assets_id = str(os.environ.get("AVE_PROXY_WALLET_ID", "") or "").strip()
        if not assets_id:
            raise ValueError("AVE proxy wallet is not configured")
        wallet_resp = _trade_get(
            "/v1/thirdParty/user/getUserByAssetsId",
            {"assetsIds": assets_id},
        )
        wallets = _normalize_portfolio_wallets(wallet_resp.get("data", []))
        state["portfolio_wallets"] = wallets

    for wallet in wallets:
        for address_info in wallet.get("addresses", []):
            chain_name = _normalize_chain_name(address_info.get("chain"))
            address = str(address_info.get("address", "") or "").strip()
            if not chain_name or not address:
                continue
            if requested_chain and chain_name == requested_chain:
                return address, chain_name

    first_wallet = wallets[0] if wallets else {}
    first_address = (first_wallet.get("addresses") or [{}])[0]
    fallback_address = str(first_address.get("address", "") or "").strip()
    fallback_chain = _normalize_chain_name(first_address.get("chain"), requested_chain or "solana")
    if not fallback_address:
        raise ValueError("AVE proxy wallet has no usable chain address")
    return fallback_address, fallback_chain


def _paper_store_path() -> Path:
    override = str(os.environ.get("AVE_PAPER_STORE_PATH", "") or "").strip()
    return Path(override) if override else _PAPER_STORE_PATH


def _normalize_trade_mode(mode) -> str:
    normalized = str(mode or "").strip().lower()
    return normalized if normalized in _VALID_TRADE_MODES else _TRADE_MODE_REAL


def _trade_mode_label(mode: str) -> str:
    return "Paper Trading" if _normalize_trade_mode(mode) == _TRADE_MODE_PAPER else "Real Trading"


def _trade_mode_marker(conn: "ConnectionHandler") -> str:
    return "PAPER" if _get_trade_mode(conn) == _TRADE_MODE_PAPER else ""


def _get_trade_mode(conn: "ConnectionHandler", *, refresh: bool = False) -> str:
    state = _ensure_ave_state(conn)
    if not refresh:
        cached = _normalize_trade_mode(state.get("trade_mode"))
        if cached in _VALID_TRADE_MODES and state.get("trade_mode"):
            return cached

    try:
        mode = _normalize_trade_mode(load_trade_mode(_paper_store_path(), _trade_namespace(conn)))
    except PaperStoreError as exc:
        logger.bind(tag=TAG).warning(f"load trade mode failed; defaulting to real: {exc}")
        mode = _TRADE_MODE_REAL

    state["trade_mode"] = mode
    return mode


def _set_trade_mode(conn: "ConnectionHandler", mode: str) -> str:
    normalized = _normalize_trade_mode(mode)
    normalized = _normalize_trade_mode(
        persist_trade_mode(_paper_store_path(), _trade_namespace(conn), normalized)
    )
    _ensure_ave_state(conn)["trade_mode"] = normalized
    return normalized


def _build_explorer_payload(conn: "ConnectionHandler") -> dict:
    mode = _get_trade_mode(conn)
    return {
        "trade_mode": mode,
        "trade_mode_label": _trade_mode_label(mode),
    }


def _resolve_feed_total(state: dict) -> int | None:
    feed_list = state.get("feed_token_list")
    if not isinstance(feed_list, list) or not feed_list:
        return None
    return len(feed_list)


def _resolve_spotlight_origin_hint(
    state: dict,
    addr: str,
    chain: str,
    *,
    previous_screen: str = "",
) -> str:
    return ""


def _is_watchlisted_for_token(conn: "ConnectionHandler", addr: str, chain: str) -> bool:
    if not addr or not chain:
        return False
    try:
        return watchlist_contains(
            _watchlist_store_path(),
            _watchlist_namespace(conn),
            addr,
            chain,
        )
    except Exception as exc:
        logger.bind(tag=TAG).warning(f"watchlist_contains failed for {addr}-{chain}: {exc}")
        return False


def _resolve_watchlist_target(
    state: dict,
    token: dict | None = None,
    *,
    cursor=None,
) -> dict | None:
    if isinstance(token, dict):
        addr, chain = _split_token_reference(
            token.get("addr") or token.get("token_id") or "",
            token.get("chain") or "solana",
        )
        if addr and chain:
            return {
                "addr": addr,
                "chain": chain,
                "symbol": str(token.get("symbol") or "").strip(),
            }

    current = state.get("current_token")
    if isinstance(current, dict):
        addr, chain = _split_token_reference(
            current.get("addr", ""),
            current.get("chain", "solana"),
        )
        if addr and chain:
            return {
                "addr": addr,
                "chain": chain,
                "symbol": str(current.get("symbol") or "").strip(),
            }

    feed_rows = state.get("feed_token_list")
    if isinstance(feed_rows, list) and feed_rows:
        try:
            idx = int(cursor if cursor is not None else state.get("feed_cursor", 0))
        except (TypeError, ValueError):
            idx = 0
        idx = max(0, min(idx, len(feed_rows) - 1))
        row = feed_rows[idx]
        if isinstance(row, dict):
            addr, chain = _split_token_reference(
                row.get("addr", ""),
                row.get("chain", "solana"),
            )
            if addr and chain:
                return {
                    "addr": addr,
                    "chain": chain,
                    "symbol": str(row.get("symbol") or "").strip(),
                }
    return None


def _refresh_spotlight_for_token(conn: "ConnectionHandler", token: dict) -> ActionResponse:
    state = _ensure_ave_state(conn)
    nav_from = str(state.get("nav_from") or "").strip().lower()
    feed_total = None
    feed_cursor = None
    if nav_from == "feed":
        feed_total = _resolve_feed_total(state)
        if feed_total is not None:
            feed_cursor = state.get("feed_cursor")
    return ave_token_detail(
        conn,
        addr=token.get("addr", ""),
        chain=token.get("chain", "solana"),
        symbol=token.get("symbol", ""),
        feed_cursor=feed_cursor,
        feed_total=feed_total,
    )


def _build_signals_rows(items: list[dict]) -> list[dict]:
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        token_id = str(
            item.get("token")
            or item.get("token_id")
            or item.get("address")
            or ""
        ).strip()
        chain = _normalize_chain_name(item.get("chain"), "solana")
        if not token_id or chain not in _SUPPORTED_FEED_CHAINS:
            continue
        identity = _asset_identity_fields(
            {
                "token_id": token_id,
                "chain": chain,
                "symbol": item.get("symbol"),
                "source": "signals",
            }
        )
        change_value = _parse_numeric_value(item.get("price_change_24h"))
        (
            signal_label,
            signal_value,
            signal_first,
            signal_last,
            signal_count,
            signal_vol,
            signal_summary,
        ) = _build_signal_display(item, chain)
        rows.append(
            {
                **identity,
                "price": _fmt_volume(_coalesce_numeric_value(item.get("mc_cur"), item.get("market_cap"))),
                "change_24h": _fmt_change(change_value if change_value is not None else 0),
                "change_positive": True if change_value is None else change_value >= 0,
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
            }
        )
    return rows[:20]


def _build_watchlist_rows(saved_rows: list[dict]) -> list[dict]:
    rows = []
    for row in saved_rows[:20]:
        if not isinstance(row, dict):
            continue
        addr, chain = _split_token_reference(
            row.get("addr", ""),
            row.get("chain", "solana"),
        )
        chain = _normalize_chain_name(chain, "solana")
        if not addr or chain not in _SUPPORTED_FEED_CHAINS:
            continue
        identity = _asset_identity_fields(
            {
                "token_id": addr,
                "chain": chain,
                "symbol": row.get("symbol"),
                "source": "watchlist",
            }
        )
        rows.append(
            {
                **identity,
                "price": "--",
                "change_24h": "--",
                "change_positive": True,
                "headline": "Saved token",
                "source": "watchlist",
            }
        )
    return rows


def _empty_feed_row(symbol: str, subtitle: str) -> dict:
    return {
        "token_id": "",
        "chain": "solana",
        "symbol": symbol,
        "price": "--",
        "change_24h": "--",
        "change_positive": True,
        "headline": subtitle,
        "source": "local",
    }


def _watchlist_store_error_response(
    conn: "ConnectionHandler",
    *,
    user_message: str,
    exc: Exception,
) -> ActionResponse:
    logger.bind(tag=TAG).error(f"watchlist store operation failed: {exc}")
    conn.loop.create_task(
        _send_display(
            conn,
            "notify",
            {
                "level": "error",
                "title": "Watchlist unavailable",
                "body": user_message,
            },
        )
    )
    return ActionResponse(action=Action.RESPONSE, result=str(exc), response=user_message)


def _restore_search_session_payload(state: dict) -> dict | None:
    session = _ensure_search_session(state)
    if not session:
        return None

    search_chain = session.get("chain", "all")
    session_items = _normalize_search_session_items(session.get("items", []))
    if any(
        isinstance(item, dict) and any(key in item for key in ("price", "change_24h", "volume_24h"))
        for item in session_items
    ):
        tokens = [dict(item) for item in session_items]
    else:
        tokens = _build_token_list(
            session_items,
            search_chain if search_chain != "all" else "???",
        )
    cursor = session.get("cursor", 0)
    if tokens:
        cursor = max(0, min(cursor, len(tokens) - 1))
    else:
        cursor = 0
    session["cursor"] = cursor

    state["screen"] = "feed"
    state["feed_mode"] = "search"
    state["search_session"] = session
    state["search_query"] = session.get("query", "")
    state["search_chain"] = search_chain
    state["search_cursor"] = cursor
    state["search_results"] = list(session.get("items", []))
    _set_feed_navigation_state(state, session.get("items", []), cursor=cursor)
    feed_session = _next_feed_session(state)

    return {
        "tokens": tokens,
        "chain": search_chain,
        "source_label": "SEARCH",
        "mode": "search",
        "search_query": state["search_query"],
        "cursor": cursor,
        "feed_session": feed_session,
    }


def _set_pending_trade(
    conn: "ConnectionHandler",
    trade_id: str,
    trade_type: str,
    action: str,
    symbol: str = "TOKEN",
    amount_native: str = "",
    amount_usd: str = "",
    screen: str = "confirm",
    chain: str = "",
    asset_token_address: str = "",
    order_ids=None,
) -> dict:
    state = _ensure_ave_state(conn)
    current_screen = str(state.get("screen") or "").strip().lower()
    current_nav_from = str(state.get("nav_from") or "").strip().lower()
    current_token = state.get("current_token") if isinstance(state.get("current_token"), dict) else {}
    pending = {
        "trade_id": trade_id,
        "trade_type": trade_type,
        "action": action,
        "symbol": symbol or "TOKEN",
        "amount_native": amount_native or "",
        "amount_usd": amount_usd or "",
        "created_at": int(time.time()),
        "chain": _normalize_chain_name(chain),
        "asset_token_address": str(asset_token_address or "").strip(),
        "return_screen": current_screen,
        "return_nav_from": current_nav_from,
    }
    if current_token.get("addr") and current_token.get("chain"):
        pending["return_token"] = {
            "addr": str(current_token.get("addr") or "").strip(),
            "chain": _normalize_chain_name(current_token.get("chain")),
            "symbol": str(current_token.get("symbol") or symbol or "TOKEN").strip() or "TOKEN",
        }
    if order_ids:
        pending["order_ids"] = [str(item) for item in order_ids if item not in (None, "")]
    state["pending_trade"] = pending
    # Keep legacy keys for backward compatibility.
    state["pending_trade_id"] = trade_id
    state["pending_symbol"] = pending["symbol"]
    state["screen"] = screen or "confirm"
    return pending


def _restore_cancel_target(conn: "ConnectionHandler", pending: dict) -> ActionResponse:
    state = _ensure_ave_state(conn)
    return_screen = str(pending.get("return_screen") or "").strip().lower()
    return_nav_from = str(pending.get("return_nav_from") or "").strip().lower()
    return_token = pending.get("return_token") if isinstance(pending.get("return_token"), dict) else {}

    if return_screen == "portfolio" or return_nav_from == "portfolio":
        return ave_portfolio(conn)

    if return_screen == "spotlight":
        addr = str(return_token.get("addr") or pending.get("asset_token_address") or "").strip()
        chain = _normalize_chain_name(return_token.get("chain") or pending.get("chain"), "solana")
        symbol = str(return_token.get("symbol") or pending.get("symbol") or "TOKEN").strip() or "TOKEN"
        if addr and chain:
            if return_nav_from in {"feed", "signals", "watchlist", "portfolio"}:
                state["nav_from"] = return_nav_from
            return ave_token_detail(conn, addr=addr, chain=chain, symbol=symbol)

    if return_nav_from == "signals":
        return ave_list_signals(conn)
    if return_nav_from == "watchlist":
        return ave_open_watchlist(conn, cursor=state.get("feed_cursor", 0))

    return _refresh_home_feed(conn)


def _get_pending_trade(conn: "ConnectionHandler") -> dict:
    state = getattr(conn, "ave_state", {})
    if not isinstance(state, dict):
        return {}

    pending = state.get("pending_trade")
    if isinstance(pending, dict) and pending.get("trade_id"):
        return pending

    # Legacy fallback.
    trade_id = state.get("pending_trade_id")
    if not trade_id:
        return {}
    return {
        "trade_id": trade_id,
        "trade_type": "",
        "action": "TRADE",
        "symbol": state.get("pending_symbol", "TOKEN"),
        "amount_native": "",
        "amount_usd": "",
    }


def _clear_pending_trade(conn: "ConnectionHandler", trade_id: str = "") -> None:
    state = getattr(conn, "ave_state", None)
    if not isinstance(state, dict):
        return

    pending = state.get("pending_trade")
    if trade_id and isinstance(pending, dict):
            pending_id = pending.get("trade_id", "")
            if pending_id and pending_id != trade_id:
                return

    state.pop("pending_trade", None)
    if not trade_id or state.get("pending_trade_id") == trade_id:
        state.pop("pending_trade_id", None)
        state.pop("pending_symbol", None)
    _schedule_deferred_result_flush(conn)


def _queue_deferred_result_payload(conn: "ConnectionHandler", payload: dict) -> None:
    state = _ensure_ave_state(conn)
    queue = state.setdefault("deferred_result_queue", [])
    if not isinstance(queue, list):
        queue = []
        state["deferred_result_queue"] = queue
    queued_payload = dict(payload or {})
    queued_payload.setdefault("explain_state", "deferred_result")
    queue.append(queued_payload)
    _schedule_deferred_result_flush(conn)


def _can_present_trade_result_now(state: dict) -> bool:
    screen = str(state.get("screen", "") or "").strip().lower()
    return screen in {"", "feed"}


def _is_active_trade_flow_screen(state: dict) -> bool:
    screen = str(state.get("screen", "") or "").strip().lower()
    return screen in {"confirm", "limit_confirm"}


async def _flush_deferred_result_queue(conn: "ConnectionHandler") -> None:
    state = _ensure_ave_state(conn)
    if state.get("_deferred_result_flush_running"):
        return
    state["_deferred_result_flush_running"] = True
    retry_needed = False
    try:
        # Allow caller to finish setting screen state after pending clear.
        await asyncio.sleep(0)
        for _ in range(_DEFERRED_RESULT_FLUSH_POLL_ATTEMPTS):
            pending = state.get("pending_trade")
            if isinstance(pending, dict) and pending.get("trade_id"):
                return
            if not _can_present_trade_result_now(state):
                await asyncio.sleep(_DEFERRED_RESULT_FLUSH_BLOCKED_DELAY_SEC)
                continue
            queue = state.get("deferred_result_queue")
            if not isinstance(queue, list) or not queue:
                return
            payload = queue.pop(0)
            await _send_display(conn, "result", payload)
            state["screen"] = "result"
            if queue:
                _schedule_deferred_result_flush(conn)
            return
        queue = state.get("deferred_result_queue")
        retry_needed = bool(isinstance(queue, list) and queue)
    finally:
        state.pop("_deferred_result_flush_running", None)
        if retry_needed:
            _schedule_deferred_result_flush(conn)


def _schedule_deferred_result_flush(conn: "ConnectionHandler") -> None:
    try:
        conn.loop.create_task(_flush_deferred_result_queue(conn))
    except Exception:
        pass


def _get_submitted_trades(conn: "ConnectionHandler") -> list:
    state = _ensure_ave_state(conn)
    trades = state.setdefault("submitted_trades", [])
    if not isinstance(trades, list):
        trades = []
        state["submitted_trades"] = trades
    return trades


def _clear_submitted_trade(
    conn: "ConnectionHandler",
    *,
    trade_id: str = "",
    swap_order_id: str = "",
) -> None:
    trades = _get_submitted_trades(conn)
    if not trades:
        return

    keep = []
    for item in trades:
        if not isinstance(item, dict):
            continue
        item_trade_id = str(item.get("trade_id", "") or "")
        item_swap_order_id = str(item.get("swap_order_id", "") or "")
        if trade_id and item_trade_id == trade_id:
            continue
        if swap_order_id and item_swap_order_id == swap_order_id:
            continue
        keep.append(item)
    trades[:] = keep


def _remember_submitted_trade(conn: "ConnectionHandler", pending: dict, result: dict) -> dict:
    pending = dict(pending or {})
    trade_type = str(pending.get("trade_type", "") or "")
    if trade_type not in {"market_buy", "market_sell"}:
        return {}

    data, _ = _result_data_dict_and_list(result.get("data") if isinstance(result, dict) else {})
    swap_order_id = str(
        data.get("id")
        or data.get("swapOrderId")
        or data.get("swap_order_id")
        or ""
    )
    if not swap_order_id:
        return {}

    record = dict(pending)
    record["swap_order_id"] = swap_order_id
    record["chain"] = _normalize_chain_name(
        (result or {}).get("chain")
        or data.get("chain")
        or record.get("chain")
        or "solana"
    )
    trades = _get_submitted_trades(conn)
    _clear_submitted_trade(
        conn,
        trade_id=str(record.get("trade_id", "") or ""),
        swap_order_id=swap_order_id,
    )
    trades.append(record)
    return record


def _is_terminal_trade_result(result: dict) -> bool:
    status = _normalize_result_status((result or {}).get("status"))
    return status in {"confirmed", "error", "failed", "cancelled", "canceled", "auto_cancelled"}


async def _present_trade_result_or_defer(
    conn: "ConnectionHandler",
    payload: dict,
    *,
    current_trade_id: str = "",
) -> None:
    state = _ensure_ave_state(conn)
    current_pending = _get_pending_trade(conn)
    active_trade_id = str(current_pending.get("trade_id", "") or "")
    current_trade_id = str(current_trade_id or "")
    if active_trade_id and active_trade_id != str(current_trade_id or ""):
        _queue_deferred_result_payload(conn, payload)
        await _send_display(conn, "notify", _build_trade_state_notify_payload("deferred_result"))
        return
    if active_trade_id and active_trade_id == current_trade_id and _is_active_trade_flow_screen(state):
        await _send_display(conn, "result", payload)
        state["screen"] = "result"
        return
    if not _can_present_trade_result_now(state):
        _queue_deferred_result_payload(conn, payload)
        return

    await _send_display(conn, "result", payload)
    state["screen"] = "result"


async def _reconcile_submitted_trade(conn: "ConnectionHandler", submitted: dict) -> None:
    submitted = dict(submitted or {})
    if not submitted:
        return

    trade_id = str(submitted.get("trade_id", "") or "")
    swap_order_id = str(submitted.get("swap_order_id", "") or "")
    reconcile_keys = (trade_id, swap_order_id)
    state = _ensure_ave_state(conn)
    in_flight = state.setdefault("_submitted_trade_reconcile", set())
    if not isinstance(in_flight, set):
        in_flight = set()
        state["_submitted_trade_reconcile"] = in_flight

    if reconcile_keys in in_flight:
        return

    in_flight.add(reconcile_keys)
    try:
        for _ in range(12):
            still_present = any(
                isinstance(item, dict)
                and str(item.get("trade_id", "") or "") == trade_id
                and str(item.get("swap_order_id", "") or "") == swap_order_id
                for item in _get_submitted_trades(conn)
            )
            if not still_present:
                return

            result = await trade_mgr.reconcile_swap_order(submitted, attempts=1)
            if _is_terminal_trade_result(result):
                payload = _build_result_payload(result, pending=submitted)
                _clear_submitted_trade(conn, trade_id=trade_id, swap_order_id=swap_order_id)
                await _present_trade_result_or_defer(
                    conn,
                    payload,
                    current_trade_id=trade_id,
                )
                return

            await asyncio.sleep(1.0)
    finally:
        in_flight.discard(reconcile_keys)


def _schedule_submitted_trade_reconcile(conn: "ConnectionHandler", submitted: dict) -> None:
    if not submitted:
        return
    try:
        conn.loop.create_task(_reconcile_submitted_trade(conn, submitted))
    except Exception:
        pass


def _result_action_from_trade_type(trade_type: str) -> str:
    action_map = {
        "market_buy": "BUY",
        "market_sell": "SELL",
        "limit_buy": "LIMIT_BUY",
        "cancel_order": "CANCEL_ORDER",
    }
    return action_map.get(trade_type, "TRADE")


def _label_trade_action(trade_type: str) -> str:
    label_map = {
        "market_buy": "买入",
        "market_sell": "卖出",
        "limit_buy": "限价买入",
        "cancel_order": "撤销挂单",
    }
    return label_map.get(trade_type, "交易")


def _result_title(trade_type: str, success: bool) -> str:
    if success:
        title_map = {
            "market_buy": "Bought!",
            "market_sell": "Sold!",
            "limit_buy": "Limit Order Placed",
            "cancel_order": "Order Cancelled",
        }
        return title_map.get(trade_type, "Trade Success")

    title_map = {
        "cancel_order": "Cancel Failed",
    }
    return title_map.get(trade_type, "Trade Failed")


def _cancel_result_title(trade_type: str) -> str:
    title_map = {
        "cancel_order": "Order Cancelled",
    }
    return title_map.get(trade_type, "Trade Cancelled")


def _result_symbol(trade_type: str, data: dict, pending: dict) -> str:
    if pending.get("symbol"):
        return pending["symbol"]
    if trade_type in ("market_sell", "limit_buy", "cancel_order"):
        return (
            data.get("inTokenSymbol")
            or data.get("outTokenSymbol")
            or "TOKEN"
        )
    return (
        data.get("outTokenSymbol")
        or data.get("inTokenSymbol")
        or "TOKEN"
    )


def _stringify_amount(value) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def _parse_decimal_amount(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, InvalidOperation, TypeError, ValueError):
        return None


def _format_display_amount(value, *, max_decimals: int = 6) -> str:
    amount = _parse_decimal_amount(value)
    if amount is None:
        return ""
    if amount == 0:
        return "0"

    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    tiny_threshold = Decimal(1) / (Decimal(10) ** max_decimals)
    if amount < tiny_threshold:
        return f"{sign}{float(amount):.{max_decimals - 1}e}"

    quant = Decimal(1) / (Decimal(10) ** max_decimals)
    truncated = amount.quantize(quant, rounding=ROUND_DOWN)
    text = format(truncated, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".") or "0"
    return f"{sign}{text}"


def _normalize_display_amount_text(text: str, *, max_decimals: int = 6) -> str:
    raw_text = str(text or "").strip()
    if not raw_text:
        return ""

    parts = raw_text.split(None, 1)
    amount = _parse_decimal_amount(parts[0])
    if amount is None:
        return raw_text

    formatted = _format_display_amount(amount, max_decimals=max_decimals)
    if len(parts) == 1:
        return formatted
    return f"{formatted} {parts[1].strip()}".strip()


def _decimal_to_string(value) -> str:
    if value is None:
        return ""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".") or "0"
    return text


def _scale_raw_balance_decimal(raw_balance_decimal, decimals) -> Decimal | None:
    if raw_balance_decimal is None:
        return None
    try:
        decimals_int = int(str(decimals))
    except (TypeError, ValueError):
        return None
    if decimals_int < 0:
        return None
    try:
        return raw_balance_decimal / (Decimal(10) ** decimals_int)
    except (ArithmeticError, InvalidOperation, OverflowError):
        return None


def _normalize_chain_name(value, default: str = "") -> str:
    chain_name = str(value or "").strip().lower()
    return chain_name or default


def _normalize_surface_chain(value, default: str, *, allow_all: bool = False) -> str:
    chain_name = _normalize_chain_name(value, default)
    if allow_all and chain_name == "all":
        return "all"
    if chain_name not in _SUPPORTED_FEED_CHAINS:
        return default
    return chain_name


def _cycle_surface_chain(current, *, allow_all: bool = False) -> str:
    order = (("all",) + _CHAIN_CYCLE_ORDER) if allow_all else _CHAIN_CYCLE_ORDER
    normalized = _normalize_surface_chain(current, order[0], allow_all=allow_all)
    try:
        idx = order.index(normalized)
    except ValueError:
        idx = 0
    return order[(idx + 1) % len(order)]


def _surface_chain_label(chain: str) -> str:
    normalized = _normalize_chain_name(chain)
    if normalized == "solana":
        return "SOL"
    if normalized == "base":
        return "BASE"
    if normalized == "eth":
        return "ETH"
    if normalized == "bsc":
        return "BSC"
    if normalized == "all":
        return "ALL"
    return normalized.upper() if normalized else ""


def _browse_source_label(base_label: str, chain: str) -> str:
    chain_label = _surface_chain_label(chain)
    return f"{base_label} {chain_label}".strip()


def _normalize_signals_chain(value, default: str = "solana") -> str:
    chain_name = _normalize_surface_chain(value, default, allow_all=False)
    if chain_name not in _SIGNALS_SUPPORTED_CHAINS:
        return default
    return chain_name


def _filter_supported_feed_items(items, fallback_chain: str = "") -> list:
    filtered = []
    fallback = _normalize_chain_name(fallback_chain)
    for item in items or []:
        if not isinstance(item, dict):
            continue
        chain_name = _normalize_chain_name(item.get("chain"), fallback)
        if chain_name not in _SUPPORTED_FEED_CHAINS:
            continue
        normalized_item = dict(item)
        normalized_item["chain"] = chain_name
        filtered.append(normalized_item)
    return filtered


def _normalize_portfolio_wallets(wallets) -> list:
    normalized = []
    for wallet in wallets or []:
        if not isinstance(wallet, dict):
            continue

        seen = set()
        addresses = []
        for address_info in wallet.get("addressList", []):
            if not isinstance(address_info, dict):
                continue
            chain_name = _normalize_chain_name(
                address_info.get("chain"),
                _normalize_chain_name(wallet.get("chain")),
            )
            address = str(address_info.get("address", "") or "").strip()
            if not chain_name or not address:
                continue
            dedupe_key = (chain_name, address)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            addresses.append({
                "chain": chain_name,
                "address": address,
            })

        normalized.append({
            "assets_id": str(wallet.get("assetsId", "") or ""),
            "assets_name": str(wallet.get("assetsName", "") or ""),
            "status": str(wallet.get("status", "") or ""),
            "addresses": addresses,
        })

    return normalized


def _portfolio_explanation_fields(pnl_value: str = "N/A") -> dict:
    pnl_text = str(pnl_value or "").strip()
    return {
        "wallet_source_label": "Proxy wallet",
        "pnl_reason": "Cost basis unavailable" if pnl_text == "N/A" else "",
    }


def _iter_portfolio_token_groups(wallet: dict):
    wallet_chain = _normalize_chain_name(wallet.get("chain"), "solana")

    for field in ("tokens", "holdings"):
        tokens = wallet.get(field)
        if isinstance(tokens, list):
            yield f"getUserByAssetsId.{field}", wallet_chain, tokens

    for address_info in wallet.get("addressList", []):
        if not isinstance(address_info, dict):
            continue
        address_chain = _normalize_chain_name(address_info.get("chain"), wallet_chain)
        for field in ("tokens", "holdings"):
            tokens = address_info.get(field)
            if isinstance(tokens, list):
                yield f"getUserByAssetsId.addressList[].{field}", address_chain, tokens


def _collect_portfolio_holdings(wallets) -> tuple[list, dict, list]:
    token_ids = []
    holdings_map = {}
    holding_sources = set()
    seen_token_ids = set()

    for wallet in wallets or []:
        if not isinstance(wallet, dict):
            continue
        for source_name, chain_name, tokens in _iter_portfolio_token_groups(wallet):
            for tok in tokens:
                if not isinstance(tok, dict):
                    continue

                token_chain = _normalize_chain_name(tok.get("chain"), chain_name or "solana")
                tok_addr = str(
                    tok.get("token_address")
                    or tok.get("tokenAddress")
                    or tok.get("address")
                    or ""
                ).strip()
                display_balance_decimal = _parse_decimal_amount(tok.get("balance", tok.get("amount", "")))
                raw_balance_decimal = _parse_decimal_amount(
                    tok.get("rawBalance", tok.get("raw_balance", tok.get("amount_raw", tok.get("balance_raw", ""))))
                )
                if display_balance_decimal is None:
                    display_balance_decimal = _scale_raw_balance_decimal(raw_balance_decimal, tok.get("decimals"))
                if display_balance_decimal is None:
                    continue

                if not tok_addr or display_balance_decimal <= 0:
                    continue

                token_id = f"{tok_addr}-{token_chain}"
                if token_id not in seen_token_ids:
                    token_ids.append(token_id)
                    seen_token_ids.add(token_id)
                identity = _asset_identity_fields(
                    {
                        **tok,
                        "addr": tok_addr,
                        "chain": token_chain,
                        "symbol": tok.get("symbol", tok.get("name", "???")),
                        "token_id": token_id,
                    }
                )
                entry = holdings_map.get(token_id)
                if not entry:
                    holdings_map[token_id] = {
                        **identity,
                        "addr": tok_addr,
                        "display_balance_decimal": display_balance_decimal,
                        "raw_balance_decimal": raw_balance_decimal,
                        "has_complete_raw_balance": raw_balance_decimal is not None,
                    }
                else:
                    entry["display_balance_decimal"] += display_balance_decimal
                    if (
                        entry.get("has_complete_raw_balance")
                        and entry.get("raw_balance_decimal") is not None
                        and raw_balance_decimal is not None
                    ):
                        entry["raw_balance_decimal"] += raw_balance_decimal
                    else:
                        entry["raw_balance_decimal"] = None
                        entry["has_complete_raw_balance"] = False
                holding_sources.add(source_name)

    return token_ids, holdings_map, sorted(holding_sources)


def _price_map_for_token_ids(token_ids: list[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    if not token_ids:
        return prices

    price_resp = _data_post("/tokens/price", _build_batch_price_payload(token_ids[:50]))
    price_data = price_resp.get("data", {})
    if isinstance(price_data, dict):
        for tid_str, info in price_data.items():
            if isinstance(info, dict):
                prices[_normalize_batch_price_token_id(tid_str)] = float(
                    info.get("current_price_usd", 0) or 0
                )
    elif isinstance(price_data, list):
        for row in price_data:
            if not isinstance(row, dict):
                continue
            tid_str = row.get("token_id", "")
            prices[_normalize_batch_price_token_id(tid_str)] = float(
                row.get("current_price_usd", row.get("price", 0)) or 0
            )
    return prices


def _paper_positions_rows(account: dict) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    token_ids: list[str] = []
    raw_positions = account.get("positions", {})

    if isinstance(raw_positions, dict):
        iterable = raw_positions.values()
    elif isinstance(raw_positions, list):
        iterable = raw_positions
    else:
        iterable = []

    for position in iterable:
        if not isinstance(position, dict):
            continue
        token_id = str(position.get("token_id") or "").strip()
        if token_id:
            token_ids.append(token_id)
        rows.append(position)
    return rows, token_ids


def _load_token_symbol(addr: str, chain: str) -> str:
    if not addr or not chain:
        return ""
    try:
        token_resp = _data_get(f"/tokens/{addr}-{chain}")
    except Exception:
        return ""

    token_data = token_resp.get("data", token_resp) if isinstance(token_resp, dict) else token_resp
    token = token_data.get("token", token_data) if isinstance(token_data, dict) else token_data
    if isinstance(token, list):
        token = token[0] if token else {}
    if not isinstance(token, dict):
        return ""
    return str(
        token.get("symbol")
        or token.get("base_symbol")
        or token.get("token_symbol")
        or ""
    ).strip()


def _repair_paper_positions(conn: "ConnectionHandler", account: dict) -> bool:
    positions = account.get("positions", {})
    fills = account.get("fills", [])
    if not isinstance(positions, dict) or not isinstance(fills, list):
        return False

    changed = False
    for _, position in positions.items():
        if not isinstance(position, dict):
            continue
        addr, chain = _split_token_reference(position.get("addr", ""), position.get("chain", ""))
        if not addr or not chain:
            continue

        if not str(position.get("token_id") or "").strip():
            position["token_id"] = f"{addr}-{chain}"
            changed = True

        symbol = str(position.get("symbol") or "").strip()
        if not symbol or symbol == "TOKEN":
            resolved_symbol = ""
            for fill in fills:
                if not isinstance(fill, dict):
                    continue
                fill_addr, fill_chain = _split_token_reference(fill.get("addr", ""), fill.get("chain", ""))
                if fill_addr != addr or fill_chain != chain:
                    continue
                fill_symbol = str(fill.get("symbol") or "").strip()
                if fill_symbol and fill_symbol != "TOKEN":
                    resolved_symbol = fill_symbol
                    break
            if not resolved_symbol:
                resolved_symbol = _load_token_symbol(addr, chain)
            if resolved_symbol:
                position["symbol"] = resolved_symbol
                changed = True

        amount = _parse_decimal_amount(position.get("amount")) or Decimal("0")
        avg_cost = _parse_decimal_amount(position.get("avg_cost_usd"))
        cost_basis = _parse_decimal_amount(position.get("cost_basis_usd"))
        if amount > 0 and (avg_cost is None or avg_cost <= 0 or cost_basis is None or cost_basis <= 0):
            total_buy_amount = Decimal("0")
            total_buy_usd = Decimal("0")
            for fill in fills:
                if not isinstance(fill, dict):
                    continue
                fill_addr, fill_chain = _split_token_reference(fill.get("addr", ""), fill.get("chain", ""))
                if fill_addr != addr or fill_chain != chain:
                    continue
                trade_type = str(fill.get("trade_type") or "").strip().lower()
                if trade_type not in {"market_buy", "limit_buy"}:
                    continue
                token_amount = _parse_decimal_amount(fill.get("token_amount"))
                amount_usd = _parse_decimal_amount(fill.get("amount_usd"))
                if token_amount is None or token_amount <= 0 or amount_usd is None or amount_usd <= 0:
                    continue
                total_buy_amount += token_amount
                total_buy_usd += amount_usd

            if total_buy_amount > 0 and total_buy_usd > 0:
                repaired_avg_cost = total_buy_usd / total_buy_amount
                position["avg_cost_usd"] = _decimal_to_string(repaired_avg_cost)
                position["cost_basis_usd"] = _decimal_to_string(repaired_avg_cost * amount)
                changed = True

    return changed


def _build_paper_portfolio_payload(conn: "ConnectionHandler", chain_filter: str = "solana") -> dict:
    account = get_paper_account(_paper_store_path(), _trade_namespace(conn))
    if _repair_paper_positions(conn, account):
        def _persist_repair(stored: dict):
            stored["positions"] = account.get("positions", {})
        mutate_paper_account(_paper_store_path(), _trade_namespace(conn), _persist_repair)

    token_ids = [meta["token_id"] for meta in _PAPER_NATIVE_TOKEN_META.values()]
    paper_positions, position_token_ids = _paper_positions_rows(account)
    token_ids.extend(position_token_ids)
    prices = _price_map_for_token_ids(token_ids)

    holdings = []
    total_usd = 0.0
    total_pnl_usd = _parse_numeric_value(account.get("realized_pnl_usd")) or 0.0
    total_cost_basis_usd = 0.0
    normalized_chain_filter = _normalize_surface_chain(chain_filter, "solana", allow_all=False)

    for chain, balance in (account.get("balances") or {}).items():
        if chain not in _PAPER_NATIVE_TOKEN_META or not isinstance(balance, dict):
            continue
        if chain != normalized_chain_filter:
            continue
        token_meta = _PAPER_NATIVE_TOKEN_META[chain]
        symbol = str(balance.get("symbol") or token_meta["symbol"])
        try:
            amount = float(balance.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        price = prices.get(_normalize_batch_price_token_id(token_meta["token_id"]), 0.0)
        value = amount * price
        total_usd += value
        holdings.append({
            "symbol": symbol,
            "addr": "",
            "chain": chain,
            "contract_tail": "",
            "token_id": token_meta["token_id"],
            "source_tag": "",
            "balance": f"{amount:.4f}",
            "balance_raw": "",
            "amount_raw": "",
            "value_usd": _fmt_volume(value),
            "_value_raw": value,
            "price": _fmt_price(price),
            "avg_cost_usd": "N/A",
            "pnl": "N/A",
            "pnl_pct": "N/A",
            "pnl_positive": None,
        })

    for position in paper_positions:
        symbol = str(position.get("symbol") or "TOKEN").strip() or "TOKEN"
        chain = _normalize_chain_name(position.get("chain"), "solana")
        if chain != normalized_chain_filter:
            continue
        addr = str(position.get("addr") or "").strip()
        token_id = str(position.get("token_id") or f"{addr}-{chain}").strip()
        try:
            amount = float(position.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        price = prices.get(_normalize_batch_price_token_id(token_id), 0.0)
        value = amount * price
        total_usd += value
        balance_raw = str(position.get("amount_raw") or "").strip()
        cost_basis = _parse_numeric_value(position.get("cost_basis_usd"))
        avg_cost = _parse_numeric_value(position.get("avg_cost_usd"))
        pnl_value = None
        pnl_pct_value = None
        pnl_positive = None
        if cost_basis is not None and cost_basis > 0:
            pnl_value = value - float(cost_basis)
            pnl_pct_value = (pnl_value / float(cost_basis)) * 100.0
            pnl_positive = pnl_value >= 0
            total_pnl_usd += pnl_value
            total_cost_basis_usd += float(cost_basis)
        holdings.append({
            "symbol": symbol,
            "addr": addr,
            "chain": chain,
            "contract_tail": str(position.get("contract_tail") or ""),
            "token_id": token_id,
            "source_tag": "",
            "balance": f"{amount:.4f}",
            "balance_raw": balance_raw,
            "amount_raw": balance_raw,
            "value_usd": _fmt_volume(value),
            "_value_raw": value,
            "price": _fmt_price(price),
            "avg_cost_usd": _fmt_price(avg_cost) if avg_cost is not None and avg_cost > 0 else "N/A",
            "cost_basis_usd": _fmt_volume(cost_basis) if cost_basis is not None and cost_basis > 0 else "N/A",
            "pnl": _fmt_portfolio_pnl(pnl_value) if pnl_value is not None else "N/A",
            "pnl_pct": _fmt_change(pnl_pct_value) if pnl_pct_value is not None else "N/A",
            "pnl_positive": pnl_positive,
        })

    holdings.sort(key=lambda row: row.get("_value_raw", 0), reverse=True)
    state = _ensure_ave_state(conn)
    cursor = _coerce_portfolio_cursor(state.get("portfolio_cursor", 0), len(holdings))
    has_pnl = total_cost_basis_usd > 0
    return {
        "holdings": holdings,
        "cursor": cursor,
        "wallets": [],
        "holding_source": "paper_store",
        "wallet_source_label": "Paper account",
        "mode_label": "PAPER",
        "chain_label": _surface_chain_label(normalized_chain_filter),
        "total_usd": _fmt_volume(total_usd),
        "pnl": _fmt_portfolio_pnl(total_pnl_usd) if has_pnl else "N/A",
        "pnl_pct": _fmt_change((total_pnl_usd / total_cost_basis_usd) * 100.0) if has_pnl else "N/A",
        "pnl_reason": "" if has_pnl else "Paper account",
    }


def _pick_activity_value(data: dict, *keys, default=""):
    if not isinstance(data, dict):
        return default
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def _fmt_activity_time(raw_value) -> str:
    if raw_value in (None, "", 0, "0"):
        return "N/A"

    numeric = _parse_numeric_value(raw_value)
    if numeric is not None and numeric > 0:
        timestamp = int(numeric / 1000) if numeric > 1_000_000_000_000 else int(numeric)
        return _fmt_chart_time(timestamp) or "N/A"

    text = str(raw_value).strip()
    if not text:
        return "N/A"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%m/%d %H:%M")
    except Exception:
        return text[:16]


def _fmt_activity_metric(raw_value, *, kind: str = "price", signed: bool = False) -> str:
    if isinstance(raw_value, Decimal):
        raw_value = float(raw_value)

    if kind == "count":
        numeric = _parse_numeric_value(raw_value)
        if numeric is None:
            return "0"
        return str(int(numeric))

    if signed:
        return _fmt_signed_volume(raw_value)

    if kind == "volume":
        return _fmt_volume(raw_value)

    return _fmt_price(raw_value)


def _find_portfolio_holding_snapshot(conn: "ConnectionHandler", addr: str, chain: str) -> dict:
    state = _ensure_ave_state(conn)
    holdings = state.get("portfolio_holdings", [])
    if not isinstance(holdings, list):
        return {}

    normalized_addr, normalized_chain = _split_token_reference(addr, chain)
    for row in holdings:
        if not isinstance(row, dict):
            continue
        row_addr, row_chain = _split_token_reference(row.get("addr", ""), row.get("chain", ""))
        if row_addr == normalized_addr and row_chain == normalized_chain:
            return row
    return {}


def _build_real_portfolio_activity_payload(
    conn: "ConnectionHandler",
    *,
    addr: str,
    chain: str,
    symbol: str = "",
) -> dict:
    normalized_chain = _normalize_chain_name(chain, "solana")
    state = _ensure_ave_state(conn)
    holding = _find_portfolio_holding_snapshot(conn, addr, normalized_chain)
    resolved_symbol = (
        str(symbol or holding.get("symbol") or "").strip()
        or _load_token_symbol(addr, normalized_chain)
        or "TOKEN"
    )

    payload = {
        "view": "detail",
        "symbol": resolved_symbol,
        "addr": addr,
        "chain": normalized_chain,
        "chain_label": _surface_chain_label(normalized_chain),
        "mode_label": "",
        "buy_avg": "N/A",
        "buy_total": "N/A",
        "sell_avg": "N/A",
        "sell_total": "N/A",
        "realized_pnl": "N/A",
        "open_orders": "0",
        "first_buy": "N/A",
        "last_buy": "N/A",
        "first_sell": "N/A",
        "last_sell": "N/A",
        "note": "",
    }

    wallet_address, wallet_chain = _resolve_proxy_wallet_target(conn, normalized_chain)
    try:
        pnl_resp = _data_get(
            "/address/pnl",
            {
                "wallet_address": wallet_address,
                "chain": wallet_chain,
                "token_address": addr,
            },
        )
        pnl_data = pnl_resp.get("data", pnl_resp) if isinstance(pnl_resp, dict) else {}

        payload["buy_avg"] = _fmt_activity_metric(
            _pick_activity_value(pnl_data, "average_purchase_price_usd", "averagePurchasePriceUsd"),
            kind="price",
        )
        payload["buy_total"] = _fmt_activity_metric(
            _pick_activity_value(pnl_data, "total_purchased_usd", "totalPurchasedUsd"),
            kind="volume",
        )
        payload["sell_avg"] = _fmt_activity_metric(
            _pick_activity_value(pnl_data, "average_sold_price_usd", "averageSoldPriceUsd"),
            kind="price",
        )
        payload["sell_total"] = _fmt_activity_metric(
            _pick_activity_value(pnl_data, "total_sold_usd", "totalSoldUsd"),
            kind="volume",
        )
        payload["realized_pnl"] = _fmt_activity_metric(
            _pick_activity_value(pnl_data, "profit_realized", "profitRealized"),
            kind="volume",
            signed=True,
        )
        payload["first_buy"] = _fmt_activity_time(
            _pick_activity_value(pnl_data, "first_purchase_time", "firstPurchaseTime")
        )
        payload["last_buy"] = _fmt_activity_time(
            _pick_activity_value(pnl_data, "last_purchase_time", "lastPurchaseTime")
        )
        payload["first_sell"] = _fmt_activity_time(
            _pick_activity_value(pnl_data, "first_sold_time", "firstSoldTime")
        )
        payload["last_sell"] = _fmt_activity_time(
            _pick_activity_value(pnl_data, "last_sold_time", "lastSoldTime")
        )
    except Exception as exc:
        payload["note"] = str(exc)[:63]

    assets_id = str(os.environ.get("AVE_PROXY_WALLET_ID", "") or "").strip()
    if assets_id:
        try:
            order_resp = _trade_get(
                "/v1/thirdParty/tx/getLimitOrder",
                {
                    "assetsId": assets_id,
                    "chain": wallet_chain,
                    "pageSize": "20",
                    "pageNo": "0",
                    "status": "waiting",
                    "token": addr,
                },
            )
            orders = _extract_limit_order_list(order_resp)
            payload["open_orders"] = _fmt_activity_metric(len(orders), kind="count")
        except Exception as exc:
            if not payload["note"]:
                payload["note"] = str(exc)[:63]

    state["current_token"] = {
        "addr": addr,
        "chain": normalized_chain,
        "symbol": resolved_symbol,
    }
    state["portfolio_detail_token"] = dict(state["current_token"])
    state["portfolio_view"] = "detail"
    state["screen"] = "portfolio"
    return payload


def _build_paper_portfolio_activity_payload(
    conn: "ConnectionHandler",
    *,
    addr: str,
    chain: str,
    symbol: str = "",
) -> dict:
    normalized_chain = _normalize_chain_name(chain, "solana")
    account = get_paper_account(_paper_store_path(), _trade_namespace(conn))
    fills = account.get("fills", [])
    open_orders = account.get("open_orders", [])
    matching_fills = []

    for fill in fills if isinstance(fills, list) else []:
        if not isinstance(fill, dict):
            continue
        fill_addr, fill_chain = _split_token_reference(fill.get("addr", ""), fill.get("chain", ""))
        if fill_addr != addr or fill_chain != normalized_chain:
            continue
        matching_fills.append(fill)

    matching_fills.sort(key=lambda item: int(_parse_numeric_value(item.get("created_at")) or 0))

    total_buy_usd = Decimal("0")
    total_buy_amount = Decimal("0")
    total_sell_usd = Decimal("0")
    total_sell_amount = Decimal("0")
    realized_pnl = Decimal("0")
    running_amount = Decimal("0")
    running_cost = Decimal("0")
    first_buy = None
    last_buy = None
    first_sell = None
    last_sell = None
    resolved_symbol = str(symbol or "").strip() or "TOKEN"

    for fill in matching_fills:
        fill_symbol = str(fill.get("symbol") or "").strip()
        if fill_symbol and resolved_symbol == "TOKEN":
            resolved_symbol = fill_symbol

        trade_type = str(fill.get("trade_type") or "").strip().lower()
        token_amount = _parse_decimal_amount(fill.get("token_amount")) or Decimal("0")
        amount_usd = _parse_decimal_amount(fill.get("amount_usd")) or Decimal("0")
        created_at = int(_parse_numeric_value(fill.get("created_at")) or 0)

        if trade_type in {"market_buy", "limit_buy"}:
            total_buy_usd += amount_usd
            total_buy_amount += token_amount
            running_amount += token_amount
            running_cost += amount_usd
            if created_at > 0:
                first_buy = created_at if first_buy is None else min(first_buy, created_at)
                last_buy = created_at if last_buy is None else max(last_buy, created_at)
        elif trade_type == "market_sell":
            total_sell_usd += amount_usd
            total_sell_amount += token_amount
            avg_cost = (running_cost / running_amount) if running_amount > 0 else Decimal("0")
            sold_amount = token_amount if token_amount <= running_amount else running_amount
            realized_pnl += amount_usd - (avg_cost * sold_amount)
            running_amount -= sold_amount
            running_cost -= avg_cost * sold_amount
            if running_amount < 0:
                running_amount = Decimal("0")
            if running_cost < 0:
                running_cost = Decimal("0")
            if created_at > 0:
                first_sell = created_at if first_sell is None else min(first_sell, created_at)
                last_sell = created_at if last_sell is None else max(last_sell, created_at)

    open_order_count = 0
    for order in open_orders if isinstance(open_orders, list) else []:
        if not isinstance(order, dict):
            continue
        order_addr, order_chain = _split_token_reference(order.get("addr", ""), order.get("chain", ""))
        if order_addr == addr and order_chain == normalized_chain and str(order.get("status") or "waiting") == "waiting":
            open_order_count += 1

    state = _ensure_ave_state(conn)
    state["current_token"] = {
        "addr": addr,
        "chain": normalized_chain,
        "symbol": resolved_symbol,
    }
    state["portfolio_detail_token"] = dict(state["current_token"])
    state["portfolio_view"] = "detail"
    state["screen"] = "portfolio"

    return {
        "view": "detail",
        "symbol": resolved_symbol,
        "addr": addr,
        "chain": normalized_chain,
        "chain_label": _surface_chain_label(normalized_chain),
        "mode_label": "PAPER",
        "buy_avg": _fmt_activity_metric((total_buy_usd / total_buy_amount) if total_buy_amount > 0 else None, kind="price"),
        "buy_total": _fmt_activity_metric(total_buy_usd if total_buy_usd > 0 else None, kind="volume"),
        "sell_avg": _fmt_activity_metric((total_sell_usd / total_sell_amount) if total_sell_amount > 0 else None, kind="price"),
        "sell_total": _fmt_activity_metric(total_sell_usd if total_sell_usd > 0 else None, kind="volume"),
        "realized_pnl": _fmt_activity_metric(realized_pnl, kind="volume", signed=True),
        "open_orders": _fmt_activity_metric(open_order_count, kind="count"),
        "first_buy": _fmt_activity_time(first_buy),
        "last_buy": _fmt_activity_time(last_buy),
        "first_sell": _fmt_activity_time(first_sell),
        "last_sell": _fmt_activity_time(last_sell),
        "note": "",
    }


def ave_portfolio_activity_detail(
    conn: "ConnectionHandler",
    *,
    addr: str,
    chain: str,
    symbol: str = "",
):
    try:
        normalized_addr, normalized_chain = _split_token_reference(addr, chain)
        if not normalized_addr or not normalized_chain:
            return ActionResponse(action=Action.RESPONSE, result="missing_token", response="Missing portfolio token")

        state = _ensure_ave_state(conn)
        state["nav_from"] = "portfolio"
        state["portfolio_selected_token"] = {"addr": normalized_addr, "chain": normalized_chain}

        if _get_trade_mode(conn) == _TRADE_MODE_PAPER:
            payload = _build_paper_portfolio_activity_payload(
                conn,
                addr=normalized_addr,
                chain=normalized_chain,
                symbol=symbol,
            )
        else:
            payload = _build_real_portfolio_activity_payload(
                conn,
                addr=normalized_addr,
                chain=normalized_chain,
                symbol=symbol,
            )

        conn.loop.create_task(_send_display(conn, "portfolio", payload))
        return ActionResponse(action=Action.NONE, result="portfolio_activity_detail", response=None)
    except Exception as exc:
        logger.bind(tag=TAG).error(f"ave_portfolio_activity_detail error: {exc}")
        return ActionResponse(action=Action.RESPONSE, result=str(exc), response="Open activity detail failed")


def _paper_limit_order_rows(conn: "ConnectionHandler", chain: str) -> list[dict]:
    rows = []
    for order in list_paper_open_orders(_paper_store_path(), _trade_namespace(conn)):
        if not isinstance(order, dict):
            continue
        row_chain = _normalize_chain_name(order.get("chain"), chain)
        if row_chain != chain:
            continue
        rows.append({
            "id": str(order.get("id") or ""),
            "outTokenAddress": str(order.get("addr") or ""),
            "symbol": str(order.get("symbol") or "TOKEN"),
            "chain": row_chain,
            "limitPrice": order.get("limit_price"),
            "createPrice": order.get("create_price"),
        })
    return _build_limit_order_rows(rows, chain=chain)


def _try_fill_paper_limit_orders(
    conn: "ConnectionHandler",
    *,
    chain: str = "",
    token_addr: str = "",
) -> list[dict]:
    normalized_chain = _normalize_chain_name(chain)
    resolved_addr, _ = _split_token_reference(token_addr, normalized_chain)
    account = get_paper_account(_paper_store_path(), _trade_namespace(conn))
    open_orders = account.get("open_orders", [])
    candidates = []
    token_ids = set()
    native_token_ids = set()

    for order in open_orders:
        if not isinstance(order, dict):
            continue
        if str(order.get("status") or "waiting") != "waiting":
            continue
        order_chain = _normalize_chain_name(order.get("chain"), normalized_chain or "solana")
        order_addr = str(order.get("addr") or "").strip()
        if normalized_chain and order_chain != normalized_chain:
            continue
        if resolved_addr and order_addr != resolved_addr:
            continue
        token_id = f"{order_addr}-{order_chain}" if order_addr else ""
        native_meta = _PAPER_NATIVE_TOKEN_META.get(order_chain)
        if not token_id or not native_meta:
            continue
        candidates.append((order, token_id, native_meta))
        token_ids.add(token_id)
        native_token_ids.add(native_meta["token_id"])

    if not candidates:
        return []

    prices = _price_map_for_token_ids(list(token_ids) + list(native_token_ids))
    fill_plan: dict[str, dict] = {}

    for order, token_id, native_meta in candidates:
        current_price = Decimal(str(prices.get(_normalize_batch_price_token_id(token_id), 0) or 0))
        native_price = Decimal(
            str(prices.get(_normalize_batch_price_token_id(native_meta["token_id"]), 0) or 0)
        )
        limit_price = _parse_decimal_amount(order.get("limit_price"))
        native_amount = _parse_decimal_amount(order.get("native_amount"))
        if current_price <= 0 or native_price <= 0 or limit_price is None or native_amount is None:
            continue
        if current_price > limit_price:
            continue
        usd_value = native_amount * native_price
        token_amount = usd_value / current_price if current_price > 0 else Decimal("0")
        fill_plan[str(order.get("id") or "")] = {
            "symbol": str(order.get("symbol") or "TOKEN"),
            "addr": str(order.get("addr") or ""),
            "chain": _normalize_chain_name(order.get("chain"), "solana"),
            "token_id": token_id,
            "native_amount": native_amount,
            "native_symbol": native_meta["symbol"],
            "token_amount": token_amount,
            "price_usd": current_price,
            "amount_usd": usd_value,
            "fill_id": f"paper-fill-{int(time.time() * 1000)}-{str(order.get('id') or '')}",
            "order_id": str(order.get("id") or ""),
        }

    if not fill_plan:
        return []

    def _mutate(account_data: dict):
        open_orders_data = account_data.setdefault("open_orders", [])
        positions = account_data.setdefault("positions", {})
        fills = account_data.setdefault("fills", [])
        kept = []
        applied = []
        for order in open_orders_data:
            if not isinstance(order, dict):
                continue
            order_id = str(order.get("id") or "")
            fill = fill_plan.get(order_id)
            if not fill:
                kept.append(order)
                continue

            position_key = _paper_position_key(fill["addr"], fill["chain"])
            existing = positions.get(position_key)
            prev_amount = _parse_decimal_amount((existing or {}).get("amount")) or Decimal("0")
            prev_cost = _parse_decimal_amount((existing or {}).get("cost_basis_usd")) or Decimal("0")
            new_amount = prev_amount + fill["token_amount"]
            new_cost = prev_cost + fill["amount_usd"]
            avg_cost = (new_cost / new_amount) if new_amount > 0 else Decimal("0")
            positions[position_key] = {
                "addr": fill["addr"],
                "chain": fill["chain"],
                "symbol": fill["symbol"],
                "token_id": fill["token_id"],
                "amount": _decimal_to_string(new_amount),
                "amount_raw": _decimal_to_string(new_amount),
                "avg_cost_usd": _decimal_to_string(avg_cost),
                "cost_basis_usd": _decimal_to_string(new_cost),
                "last_price_usd": _decimal_to_string(fill["price_usd"]),
            }
            fills.insert(0, {
                "id": fill["fill_id"],
                "order_id": fill["order_id"],
                "trade_type": "limit_buy",
                "fill_source": "paper_limit_match",
                "chain": fill["chain"],
                "addr": fill["addr"],
                "symbol": fill["symbol"],
                "native_amount": _decimal_to_string(fill["native_amount"]),
                "native_symbol": fill["native_symbol"],
                "token_amount": _decimal_to_string(fill["token_amount"]),
                "price_usd": _decimal_to_string(fill["price_usd"]),
                "amount_usd": _decimal_to_string(fill["amount_usd"]),
                "created_at": int(time.time()),
            })
            applied.append(fill)
        account_data["open_orders"] = kept
        return applied

    _, applied_fills = mutate_paper_account(_paper_store_path(), _trade_namespace(conn), _mutate)
    if applied_fills:
        symbols = [str(item.get("symbol") or "TOKEN") for item in applied_fills[:3]]
        body = ", ".join(symbols)
        if len(applied_fills) > 3:
            body = f"{body} +{len(applied_fills) - 3} more"
        conn.loop.create_task(_send_display(conn, "notify", {
            "level": "info",
            "title": "Paper Order Filled",
            "body": body,
        }))
    return applied_fills or []


def _paper_position_key(addr: str, chain: str) -> str:
    resolved_addr, resolved_chain = _split_token_reference(addr, chain)
    return f"{resolved_addr}-{resolved_chain}" if resolved_addr and resolved_chain else ""


def _format_paper_amount(amount: Decimal, symbol: str) -> str:
    return f"{_format_display_amount(amount)} {symbol}".strip()


def _paper_market_buy(conn: "ConnectionHandler", trade_type: str, params: dict) -> dict:
    chain = _normalize_chain_name(params.get("chain"), "solana")
    token_addr, token_chain = _split_token_reference(params.get("outTokenAddress", ""), chain)
    if not token_addr:
        return {"trade_type": trade_type, "status": "failed", "error": "Missing token address"}

    native_meta = _PAPER_NATIVE_TOKEN_META.get(token_chain)
    if not native_meta:
        return {"trade_type": trade_type, "status": "failed", "error": f"Unsupported paper chain: {token_chain}"}

    native_amount = _parse_decimal_amount(params.get("paper_native_amount"))
    if native_amount is None:
        try:
            native_amount = Decimal(str(params.get("inAmount", "0"))) / Decimal("1000000000")
        except (ArithmeticError, InvalidOperation, TypeError, ValueError):
            native_amount = None
    if native_amount is None or native_amount <= 0:
        return {"trade_type": trade_type, "status": "failed", "error": "Invalid trade amount"}

    symbol = _resolve_trade_symbol(
        conn,
        token_addr,
        token_chain,
        str(params.get("paper_symbol") or params.get("symbol") or "").strip(),
    )
    prices = _price_map_for_token_ids([native_meta["token_id"], f"{token_addr}-{token_chain}"])
    native_price = Decimal(str(prices.get(_normalize_batch_price_token_id(native_meta["token_id"]), 0) or 0))
    token_price = Decimal(str(prices.get(_normalize_batch_price_token_id(f"{token_addr}-{token_chain}"), 0) or 0))
    if native_price <= 0 or token_price <= 0:
        return {"trade_type": trade_type, "status": "failed", "error": "Paper price unavailable"}

    usd_value = native_amount * native_price
    token_amount = usd_value / token_price
    position_key = _paper_position_key(token_addr, token_chain)
    tx_id = f"paper-{int(time.time() * 1000)}"

    def _mutate(account: dict):
        balances = account.setdefault("balances", {})
        native_balance = balances.setdefault(
            token_chain,
            {"symbol": native_meta["symbol"], "amount": "0"},
        )
        balance_amount = _parse_decimal_amount(native_balance.get("amount")) or Decimal("0")
        if balance_amount < native_amount:
            raise PaperStoreError(f"Insufficient {native_meta['symbol']} balance")
        native_balance["symbol"] = native_meta["symbol"]
        native_balance["amount"] = _decimal_to_string(balance_amount - native_amount)

        positions = account.setdefault("positions", {})
        existing = positions.get(position_key)
        prev_amount = _parse_decimal_amount((existing or {}).get("amount")) or Decimal("0")
        prev_cost = _parse_decimal_amount((existing or {}).get("cost_basis_usd")) or Decimal("0")
        new_amount = prev_amount + token_amount
        new_cost = prev_cost + usd_value
        avg_cost = (new_cost / new_amount) if new_amount > 0 else Decimal("0")
        positions[position_key] = {
            "addr": token_addr,
            "chain": token_chain,
            "symbol": symbol,
            "token_id": f"{token_addr}-{token_chain}",
            "amount": _decimal_to_string(new_amount),
            "amount_raw": _decimal_to_string(new_amount),
            "avg_cost_usd": _decimal_to_string(avg_cost),
            "cost_basis_usd": _decimal_to_string(new_cost),
            "last_price_usd": _decimal_to_string(token_price),
        }

        fills = account.setdefault("fills", [])
        fills.insert(0, {
            "id": tx_id,
            "trade_type": trade_type,
            "chain": token_chain,
            "addr": token_addr,
            "symbol": symbol,
            "native_amount": _decimal_to_string(native_amount),
            "token_amount": _decimal_to_string(token_amount),
            "price_usd": _decimal_to_string(token_price),
            "amount_usd": _decimal_to_string(usd_value),
            "created_at": int(time.time()),
        })

    try:
        mutate_paper_account(_paper_store_path(), _trade_namespace(conn), _mutate)
    except PaperStoreError as exc:
        return {"trade_type": trade_type, "status": "failed", "error": str(exc)}

    return {
        "trade_type": trade_type,
        "status": "confirmed",
        "title": "Paper Bought!",
        "subtitle": "Paper trade executed.",
        "mode_label": "PAPER",
        "data": {
            "txId": tx_id,
            "outAmountFormatted": _format_paper_amount(token_amount, symbol),
            "outAmountUsd": f"${usd_value:.2f}",
            "outTokenSymbol": symbol,
            "outTokenAddress": token_addr,
        },
    }


def _paper_market_sell(conn: "ConnectionHandler", trade_type: str, params: dict) -> dict:
    chain = _normalize_chain_name(params.get("chain"), "solana")
    token_addr, token_chain = _split_token_reference(params.get("inTokenAddress", ""), chain)
    if not token_addr:
        return {"trade_type": trade_type, "status": "failed", "error": "Missing token address"}

    native_meta = _PAPER_NATIVE_TOKEN_META.get(token_chain)
    if not native_meta:
        return {"trade_type": trade_type, "status": "failed", "error": f"Unsupported paper chain: {token_chain}"}

    symbol = _resolve_trade_symbol(
        conn,
        token_addr,
        token_chain,
        str(params.get("paper_symbol") or params.get("symbol") or "").strip(),
    )
    sell_ratio = _parse_decimal_amount(params.get("paper_sell_ratio")) or Decimal("1")
    requested_amount = _parse_decimal_amount(params.get("paper_position_amount"))
    position_key = _paper_position_key(token_addr, token_chain)
    prices = _price_map_for_token_ids([native_meta["token_id"], f"{token_addr}-{token_chain}"])
    native_price = Decimal(str(prices.get(_normalize_batch_price_token_id(native_meta["token_id"]), 0) or 0))
    token_price = Decimal(str(prices.get(_normalize_batch_price_token_id(f"{token_addr}-{token_chain}"), 0) or 0))
    if native_price <= 0 or token_price <= 0:
        return {"trade_type": trade_type, "status": "failed", "error": "Paper price unavailable"}

    tx_id = f"paper-{int(time.time() * 1000)}"

    def _mutate(account: dict):
        positions = account.setdefault("positions", {})
        existing = positions.get(position_key)
        if not isinstance(existing, dict):
            raise PaperStoreError("No paper position to sell")

        held_amount = _parse_decimal_amount(existing.get("amount")) or Decimal("0")
        if held_amount <= 0:
            raise PaperStoreError("No paper position to sell")

        amount_to_sell = requested_amount if requested_amount is not None else held_amount
        amount_to_sell = amount_to_sell * sell_ratio
        if amount_to_sell <= 0:
            raise PaperStoreError("Sell amount must be positive")
        if amount_to_sell > held_amount:
            amount_to_sell = held_amount

        avg_cost = _parse_decimal_amount(existing.get("avg_cost_usd")) or Decimal("0")
        cost_basis = avg_cost * amount_to_sell
        proceeds_usd = amount_to_sell * token_price
        native_out = proceeds_usd / native_price
        remaining = held_amount - amount_to_sell

        balances = account.setdefault("balances", {})
        native_balance = balances.setdefault(
            token_chain,
            {"symbol": native_meta["symbol"], "amount": "0"},
        )
        balance_amount = _parse_decimal_amount(native_balance.get("amount")) or Decimal("0")
        native_balance["symbol"] = native_meta["symbol"]
        native_balance["amount"] = _decimal_to_string(balance_amount + native_out)

        if remaining <= Decimal("0.000000001"):
            positions.pop(position_key, None)
        else:
            remaining_cost = (avg_cost * remaining)
            existing["amount"] = _decimal_to_string(remaining)
            existing["amount_raw"] = _decimal_to_string(remaining)
            existing["cost_basis_usd"] = _decimal_to_string(remaining_cost)
            existing["last_price_usd"] = _decimal_to_string(token_price)

        realized = _parse_decimal_amount(account.get("realized_pnl_usd")) or Decimal("0")
        account["realized_pnl_usd"] = _decimal_to_string(realized + (proceeds_usd - cost_basis))

        fills = account.setdefault("fills", [])
        fills.insert(0, {
            "id": tx_id,
            "trade_type": trade_type,
            "chain": token_chain,
            "addr": token_addr,
            "symbol": symbol,
            "native_amount": _decimal_to_string(native_out),
            "token_amount": _decimal_to_string(amount_to_sell),
            "price_usd": _decimal_to_string(token_price),
            "amount_usd": _decimal_to_string(proceeds_usd),
            "created_at": int(time.time()),
        })
        return native_out, proceeds_usd

    try:
        _, mutate_result = mutate_paper_account(_paper_store_path(), _trade_namespace(conn), _mutate)
    except PaperStoreError as exc:
        return {"trade_type": trade_type, "status": "failed", "error": str(exc)}

    native_out, proceeds_usd = mutate_result
    return {
        "trade_type": trade_type,
        "status": "confirmed",
        "title": "Paper Sold!",
        "subtitle": "Paper trade executed.",
        "mode_label": "PAPER",
        "data": {
            "txId": tx_id,
            "outAmountFormatted": _format_paper_amount(native_out, native_meta["symbol"]),
            "outAmountUsd": f"${proceeds_usd:.2f}",
            "inTokenSymbol": symbol,
            "inTokenAddress": token_addr,
        },
    }


def _paper_limit_buy(conn: "ConnectionHandler", trade_type: str, params: dict) -> dict:
    chain = _normalize_chain_name(params.get("chain"), "solana")
    token_addr, token_chain = _split_token_reference(params.get("outTokenAddress", ""), chain)
    if not token_addr:
        return {"trade_type": trade_type, "status": "failed", "error": "Missing token address"}

    native_meta = _PAPER_NATIVE_TOKEN_META.get(token_chain)
    if not native_meta:
        return {"trade_type": trade_type, "status": "failed", "error": f"Unsupported paper chain: {token_chain}"}

    native_amount = _parse_decimal_amount(params.get("paper_native_amount"))
    if native_amount is None:
        try:
            native_amount = Decimal(str(params.get("inAmount", "0"))) / Decimal("1000000000")
        except (ArithmeticError, InvalidOperation, TypeError, ValueError):
            native_amount = None
    limit_price = _parse_decimal_amount(params.get("limitPrice"))
    create_price = _parse_decimal_amount(params.get("paper_current_price"))
    if native_amount is None or native_amount <= 0:
        return {"trade_type": trade_type, "status": "failed", "error": "Invalid trade amount"}
    if limit_price is None or limit_price <= 0:
        return {"trade_type": trade_type, "status": "failed", "error": "Invalid limit price"}

    symbol = _resolve_trade_symbol(
        conn,
        token_addr,
        token_chain,
        str(params.get("paper_symbol") or params.get("symbol") or "").strip(),
    )
    order_id = f"paper-order-{int(time.time() * 1000)}"

    def _mutate(account: dict):
        balances = account.setdefault("balances", {})
        native_balance = balances.setdefault(
            token_chain,
            {"symbol": native_meta["symbol"], "amount": "0"},
        )
        balance_amount = _parse_decimal_amount(native_balance.get("amount")) or Decimal("0")
        if balance_amount < native_amount:
            raise PaperStoreError(f"Insufficient {native_meta['symbol']} balance")
        native_balance["symbol"] = native_meta["symbol"]
        native_balance["amount"] = _decimal_to_string(balance_amount - native_amount)

        open_orders = account.setdefault("open_orders", [])
        open_orders.insert(0, {
            "id": order_id,
            "addr": token_addr,
            "chain": token_chain,
            "symbol": symbol,
            "limit_price": _decimal_to_string(limit_price),
            "create_price": _decimal_to_string(create_price),
            "native_amount": _decimal_to_string(native_amount),
            "native_symbol": native_meta["symbol"],
            "status": "waiting",
            "created_at": int(time.time()),
        })

    try:
        mutate_paper_account(_paper_store_path(), _trade_namespace(conn), _mutate)
    except PaperStoreError as exc:
        return {"trade_type": trade_type, "status": "failed", "error": str(exc)}

    return {
        "trade_type": trade_type,
        "status": "confirmed",
        "title": "Paper Limit Order Placed",
        "subtitle": "Paper limit order created.",
        "mode_label": "PAPER",
        "data": {
            "id": order_id,
            "outTokenSymbol": symbol,
            "outTokenAddress": token_addr,
            "outAmount": "1 order",
        },
    }


def _paper_cancel_order(conn: "ConnectionHandler", trade_type: str, params: dict) -> dict:
    chain = _normalize_chain_name(params.get("chain"), "solana")
    resolved_ids = [str(item) for item in params.get("ids", []) if item not in (None, "")]
    if not resolved_ids:
        return {"trade_type": trade_type, "status": "failed", "error": "No paper order ids"}

    restored = Decimal("0")
    cancelled_ids: list[str] = []

    def _mutate(account: dict):
        nonlocal restored
        open_orders = account.setdefault("open_orders", [])
        kept = []
        balances = account.setdefault("balances", {})
        native_meta = _PAPER_NATIVE_TOKEN_META.get(chain)
        if native_meta:
            native_balance = balances.setdefault(
                chain,
                {"symbol": native_meta["symbol"], "amount": "0"},
            )
            balance_amount = _parse_decimal_amount(native_balance.get("amount")) or Decimal("0")
        else:
            native_balance = None
            balance_amount = Decimal("0")

        for order in open_orders:
            if not isinstance(order, dict):
                continue
            order_id = str(order.get("id") or "")
            if order_id in resolved_ids:
                native_amount = _parse_decimal_amount(order.get("native_amount")) or Decimal("0")
                restored += native_amount
                cancelled_ids.append(order_id)
                continue
            kept.append(order)

        if not cancelled_ids:
            raise PaperStoreError("No waiting paper orders")

        if native_balance is not None:
            native_balance["amount"] = _decimal_to_string(balance_amount + restored)
        account["open_orders"] = kept

    try:
        mutate_paper_account(_paper_store_path(), _trade_namespace(conn), _mutate)
    except PaperStoreError as exc:
        return {"trade_type": trade_type, "status": "failed", "error": str(exc)}

    return {
        "trade_type": trade_type,
        "status": "confirmed",
        "title": "Paper Order Cancelled",
        "subtitle": "Paper order cancelled.",
        "mode_label": "PAPER",
        "data": {
            "ids": cancelled_ids,
        },
    }


def _execute_paper_trade(conn: "ConnectionHandler", trade_type: str, params: dict) -> dict:
    if trade_type == "limit_buy":
        return _paper_limit_buy(conn, trade_type, params)
    if trade_type == "cancel_order":
        return _paper_cancel_order(conn, trade_type, params)
    if trade_type == "market_buy":
        return _paper_market_buy(conn, trade_type, params)
    if trade_type == "market_sell":
        return _paper_market_sell(conn, trade_type, params)
    return {
        "trade_type": trade_type,
        "status": "failed",
        "error": "Paper mode does not support this trade yet",
    }


def _portfolio_holding_index(holdings: list, addr: str, chain: str) -> int:
    target_addr, target_chain = _split_token_reference(addr, chain)
    if not target_addr:
        return -1

    for idx, row in enumerate(holdings or []):
        if not isinstance(row, dict):
            continue
        row_addr, row_chain = _split_token_reference(row.get("addr", ""), row.get("chain", ""))
        if row_addr == target_addr and row_chain == target_chain:
            return idx
    return -1


def _coerce_portfolio_cursor(value, total: int) -> int:
    try:
        cursor = int(value)
    except (TypeError, ValueError):
        cursor = 0
    if total <= 0:
        return 0
    return max(0, min(cursor, total - 1))


def _trim_result_tx_id(value) -> str:
    if not value:
        return ""
    return str(value)[:12]


def _normalize_result_status(status):
    if isinstance(status, bool):
        return None
    if isinstance(status, int):
        return status
    if isinstance(status, str):
        text = status.strip()
        if not text:
            return None
        if text.lstrip("-").isdigit():
            return int(text)
        return text.lower()
    return None


def _is_result_success_status(status) -> bool:
    return status in {0, 1, 200, "confirmed", "success", "ok"}


def _result_error_message(result: dict) -> str:
    for key in ("error", "errorMessage", "errorMsg", "msg", "message"):
        value = result.get(key)
        if value not in (None, ""):
            return str(value)
    return "Trade failed"


def _result_data_dict_and_list(data) -> tuple[dict, list]:
    if isinstance(data, dict):
        return data, []
    if isinstance(data, list):
        return {}, data
    return {}, []


def _looks_raw_numeric_amount(value) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    # Keep plain raw numbers out of RESULT until they can be rendered with units.
    return text.replace(".", "", 1).isdigit()


def _pick_result_out_amount(data: dict) -> str:
    for key in ("outAmountFormatted", "out_amount_formatted", "estimateOutFormatted"):
        value = data.get(key)
        if value not in (None, ""):
            return _normalize_display_amount_text(str(value))

    for key in ("outAmount", "out_amount", "estimateOut"):
        value = data.get(key)
        if value in (None, ""):
            continue
        if _looks_raw_numeric_amount(value):
            return ""
        return str(value)

    return ""


def _has_trade_execution_evidence(data: dict) -> bool:
    for key in ("txId", "tx_id", "txHash", "tx_hash"):
        value = data.get(key)
        if value not in (None, ""):
            return True
    return False


def _submission_title(trade_type: str) -> str:
    title_map = {
        "market_buy": "Order Submitted",
        "market_sell": "Order Submitted",
        "limit_buy": "Limit Order Submitted",
    }
    return title_map.get(trade_type, "Order Submitted")


def _trade_status_copy(reason: str, trade_type: str = "") -> tuple[str, str]:
    reason_key = str(reason or "").strip().lower()
    if reason_key == "trade_submitted":
        return _submission_title(trade_type), "Waiting for chain confirmation."

    mapping = {
        "confirm_timeout": ("Trade Cancelled", "Nothing was executed."),
        "ack_timeout": ("Still Pending", "We did not receive a final confirmation yet."),
        "deferred_result": ("Result Deferred", "Another confirmation flow is active. Result will appear next."),
    }
    return mapping.get(reason_key, ("Trade Update", "Trade state updated."))


def _trade_status_notify_level(reason: str) -> str:
    return {
        "ack_timeout": "warning",
        "confirm_timeout": "warning",
    }.get(str(reason or "").strip().lower(), "info")


def _build_trade_state_result_payload(
    reason: str,
    *,
    pending: dict = None,
    trade_type: str = "",
) -> dict:
    pending = pending or {}
    resolved_trade_type = str(trade_type or pending.get("trade_type", "") or "")
    title, subtitle = _trade_status_copy(reason, trade_type=resolved_trade_type)
    return {
        "success": False,
        "title": title,
        "action": _result_action_from_trade_type(resolved_trade_type),
        "symbol": pending.get("symbol", "TOKEN"),
        "error": subtitle,
        "subtitle": subtitle,
        "explain_state": str(reason or "").strip().lower(),
    }


def _build_trade_state_notify_payload(
    reason: str,
    *,
    pending: dict = None,
    trade_type: str = "",
) -> dict:
    pending = pending or {}
    resolved_trade_type = str(trade_type or pending.get("trade_type", "") or "")
    title, subtitle = _trade_status_copy(reason, trade_type=resolved_trade_type)
    return {
        "level": _trade_status_notify_level(reason),
        "title": title,
        "body": subtitle,
        "subtitle": subtitle,
        "explain_state": str(reason or "").strip().lower(),
    }


def _is_submit_only_ack(result: dict, pending: dict = None) -> bool:
    pending = pending or {}
    if not isinstance(result, dict):
        return False
    if result.get("error") not in (None, ""):
        return False

    trade_type = result.get("trade_type") or pending.get("trade_type", "")
    if trade_type not in {"market_buy", "market_sell", "limit_buy"}:
        return False

    if "status" not in result:
        return False
    normalized_status = _normalize_result_status(result.get("status"))
    if normalized_status not in {0, 1, 200, "success", "ok"}:
        return False

    data, _ = _result_data_dict_and_list(result.get("data"))
    return not _has_trade_execution_evidence(data)


def _build_submission_notice(result: dict, pending: dict = None) -> dict:
    pending = pending or {}
    trade_type = (result.get("trade_type") if isinstance(result, dict) else "") or pending.get("trade_type", "")
    return _build_trade_state_notify_payload("trade_submitted", pending=pending, trade_type=trade_type)


async def _push_submit_ack_transition(conn: "ConnectionHandler", result: dict, pending: dict = None) -> None:
    pending = pending or {}
    submitted = _remember_submitted_trade(conn, pending, result)
    await _send_display(conn, "notify", _build_submission_notice(result, pending=pending))
    _clear_pending_trade(conn, pending.get("trade_id", ""))
    state = _ensure_ave_state(conn)
    state["screen"] = "feed"
    state.pop("nav_from", None)
    await _send_display(conn, "feed", {"reason": "trade_submitted", "feed_session": _current_feed_session(state)})
    _schedule_submitted_trade_reconcile(conn, submitted)


def _normalize_result_data(result: dict, pending: dict = None) -> dict:
    pending = pending or {}
    if not isinstance(result, dict):
        result = {"error": "Malformed trade response", "status": "malformed", "data": {}}

    trade_type = result.get("trade_type") or pending.get("trade_type", "")
    normalized_status = _normalize_result_status(result.get("status")) if "status" in result else None
    success = False
    error_message = ""
    is_cancelled = normalized_status in {"cancelled", "canceled", "auto_cancelled"}

    if "error" in result and result.get("error") not in (None, ""):
        error_message = _result_error_message(result)
    elif "status" not in result:
        error_message = "Invalid trade response: missing status"
    elif _is_result_success_status(normalized_status):
        success = True
    else:
        error_message = _result_error_message(result)
        raw_status = result.get("status")
        if not error_message:
            error_message = f"Trade rejected: status={raw_status}"
        elif "status" not in error_message.lower():
            error_message = f"{error_message} (status={raw_status})"
        if is_cancelled and error_message in {"Trade failed", f"Trade rejected: status={raw_status}"}:
            error_message = "Order was cancelled before execution."

    data, data_list = _result_data_dict_and_list(result.get("data"))
    out_amount = _pick_result_out_amount(data)
    is_submission_ack = (
        success
        and normalized_status in {0, 1, 200}
        and trade_type in {"market_buy", "market_sell", "limit_buy"}
        and not _has_trade_execution_evidence(data)
    )

    if success and not out_amount and trade_type == "cancel_order":
        cancelled = data.get("ids", data.get("orderIds", data.get("list", [])))
        if (not isinstance(cancelled, list)) or (not cancelled and data_list):
            cancelled = data_list if isinstance(data_list, list) else []
        if isinstance(cancelled, list):
            out_amount = f"{len(cancelled)} orders"

    if success and not out_amount:
        out_amount = pending.get("amount_native", "")

    title = result.get("title")
    if not title:
        if is_submission_ack:
            title = _submission_title(trade_type)
        elif is_cancelled:
            title = _cancel_result_title(trade_type)
        else:
            title = _result_title(trade_type, success)

    subtitle = ""
    explain_state = ""
    if isinstance(result, dict):
        subtitle = _stringify_amount(
            result.get("subtitle", result.get("detail", result.get("body", "")))
        )
        explain_state = _stringify_amount(result.get("explain_state"))
    if success and trade_type == "cancel_order" and not subtitle:
        subtitle = "This changed an order state, not your wallet balance."

    return {
        "success": success,
        "trade_type": trade_type,
        "action": _result_action_from_trade_type(trade_type),
        "symbol": _result_symbol(trade_type, data, pending),
        "title": title,
        "out_amount": _stringify_amount(out_amount),
        "amount_usd": _stringify_amount(
            data.get("outAmountUsd", data.get("amountUsd", pending.get("amount_usd", "")))
        ),
        "tx_id": _trim_result_tx_id(
            data.get("txId", data.get("tx_id", data.get("txHash", data.get("tx_hash", ""))))
        ),
        "mode_label": _stringify_amount(result.get("mode_label", pending.get("mode_label", ""))),
        "error": error_message if not success else "",
        "subtitle": subtitle,
        "explain_state": explain_state,
    }


def _build_result_payload(result: dict, pending: dict = None) -> dict:
    normalized = _normalize_result_data(result, pending=pending)
    payload = {
        "success": normalized["success"],
        "title": normalized["title"],
        "action": normalized["action"],
        "symbol": normalized["symbol"],
    }
    if normalized["mode_label"]:
        payload["mode_label"] = normalized["mode_label"]
    if normalized["success"]:
        payload["out_amount"] = normalized["out_amount"]
        payload["amount"] = payload["out_amount"]
        payload["amount_usd"] = normalized["amount_usd"]
        payload["tx_id"] = normalized["tx_id"]
    else:
        payload["error"] = normalized["error"]
    if normalized["subtitle"]:
        payload["subtitle"] = normalized["subtitle"]
    if normalized["explain_state"]:
        payload["explain_state"] = normalized["explain_state"]

    return payload


# ---------------------------------------------------------------------------
# Risk check helper
# ---------------------------------------------------------------------------

def _normalize_ave_bool(value) -> bool:
    """Normalize AVE risk booleans where sentinel values like -1 mean false."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        text = value.strip().lower()
        return text in {"true", "1", "yes", "y"}
    return False


def _parse_risk_score(value):
    """Parse contract risk score safely; return None for malformed values."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 100 else None
    if isinstance(value, float):
        if value.is_integer():
            score = int(value)
            return score if 0 <= score <= 100 else None
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            score = int(text)
            return score if 0 <= score <= 100 else None
        except ValueError:
            return None
    return None


def _risk_level_from_response(risk_data: dict) -> str:
    """Extract risk level from contracts API response.

    The contracts endpoint returns a numeric ``risk_score`` (0-100) and
    individual boolean flags like ``is_honeypot``.  We map the score to
    a human-readable level string.
    """
    root = risk_data if isinstance(risk_data, dict) else {}
    data = root.get("data", root)
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        data = {}
    # Check for honeypot first — always CRITICAL
    if _normalize_ave_bool(data.get("is_honeypot")):
        return "CRITICAL"
    score = _parse_risk_score(data.get("risk_score", data.get("ave_risk_level")))
    if score is None:
        return "UNKNOWN"
    if score >= 80:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 20:
        return "MEDIUM"
    return "LOW"


def _risk_flags(risk_data: dict) -> dict:
    """Extract honeypot/mint/freeze flags."""
    root = risk_data if isinstance(risk_data, dict) else {}
    data = root.get("data", root)
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        data = {}
    return {
        "is_honeypot": _normalize_ave_bool(data.get("is_honeypot")),
        "is_mintable": _normalize_ave_bool(data.get("has_mint_method", data.get("is_mintable"))),
        "is_freezable": _normalize_ave_bool(data.get("has_black_method", data.get("is_freezable"))),
        "risk_level": _risk_level_from_response(risk_data),
    }


# ---------------------------------------------------------------------------
# Kline normalization (log scale for extreme-small prices like BONK)
# ---------------------------------------------------------------------------

def _normalize_kline(points: list) -> list:
    """Return int16-range values safe for lv_chart."""
    if not points:
        return []
    closes = []
    for p in points:
        c = p.get("close", p.get("c"))
        if c is not None:
            closes.append(float(c))
    if not closes:
        return []

    mn = min(closes)
    mx = max(closes)
    if mn <= 0:
        # Shift to positive
        offset = abs(mn) + 1e-12
        closes = [v + offset for v in closes]
        mn = min(closes)
        mx = max(closes)

    # Log transform
    log_min = math.log10(mn)
    log_max = math.log10(mx)
    log_range = log_max - log_min if log_max != log_min else 1.0

    result = []
    for v in closes:
        normalized = (math.log10(v) - log_min) / log_range  # 0..1
        result.append(int(normalized * 1000))  # 0..1000 fits int16

    return result


# ---------------------------------------------------------------------------
# Tool: ave_list_signals / ave_open_watchlist
# ---------------------------------------------------------------------------

ave_list_signals_desc = {
    "type": "function",
    "function": {
        "name": "ave_list_signals",
        "description": "查看公开 Signals 列表并展示到 FEED。用于 Explore->Signals 或语音打开信号页。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


ave_open_watchlist_desc = {
    "type": "function",
    "function": {
        "name": "ave_open_watchlist",
        "description": "打开本地 Watchlist 并展示到 FEED。用于 Explore->Watchlist 或语音打开观察列表。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


ave_add_watchlist_desc = {
    "type": "function",
    "function": {
        "name": "ave_add_current_watchlist_token",
        "description": "将当前选中的代币加入 Watchlist。优先用于 spotlight 页面上的收藏语音命令。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


ave_remove_watchlist_desc = {
    "type": "function",
    "function": {
        "name": "ave_remove_current_watchlist_voice",
        "description": "将当前选中的代币从 Watchlist 移除。优先用于 spotlight 页面上的取消收藏语音命令。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


@register_function("ave_list_signals", ave_list_signals_desc, ToolType.SYSTEM_CTL)
def ave_list_signals(conn: "ConnectionHandler", chain: str = ""):
    try:
        state = _ensure_ave_state(conn)
        selected_chain = _normalize_signals_chain(chain or state.get("signals_chain"), "solana")
        state["signals_chain"] = selected_chain

        # Cut over FEED session before REST fetch so pending/stale live pushes
        # cannot repaint the previous feed while Signals is loading.
        feed_session = _invalidate_live_feed_session(conn, clear_tokens=True)

        resp = _data_get(
            "/signals/public/list",
            {"chain": selected_chain, "limit": 20, "pageSize": 20, "pageNO": 1},
        )
        raw = resp.get("data", {})
        if isinstance(raw, dict):
            raw = raw.get("list", raw.get("items", []))
        rows = _build_signals_rows(raw if isinstance(raw, list) else [])

        state["screen"] = "browse"
        state["feed_source"] = "signals"
        state["feed_platform"] = ""
        state["feed_mode"] = "signals"
        state.pop("nav_from", None)
        state.pop("order_list", None)
        _clear_search_state(state)
        _set_feed_navigation_state(state, rows, cursor=0)
        state["feed_session"] = feed_session

        conn.loop.create_task(
            _send_display(
                conn,
                "browse",
                {
                    "tokens": rows or [_empty_feed_row("SIGNALS", "No signals now")],
                    "mode": "signals",
                    "source_label": _browse_source_label("SIGNALS", selected_chain),
                    "cursor": state.get("feed_cursor", 0),
                    "feed_session": feed_session,
                },
            )
        )
        return ActionResponse(action=Action.NONE, result=f"signals:{len(rows)}", response=None)
    except Exception as exc:
        logger.bind(tag=TAG).error(f"ave_list_signals error: {exc}")
        conn.loop.create_task(
            _send_display(
                conn,
                "notify",
                {
                    "level": "error",
                    "title": "Signals unavailable",
                    "body": str(exc)[:60],
                },
            )
        )
        return ActionResponse(action=Action.RESPONSE, result=str(exc), response="Signals 暂时不可用")


@register_function("ave_open_watchlist", ave_open_watchlist_desc, ToolType.SYSTEM_CTL)
def ave_open_watchlist(conn: "ConnectionHandler", cursor=None, chain_filter: str = ""):
    try:
        state = _ensure_ave_state(conn)
        selected_chain = _normalize_surface_chain(
            chain_filter or state.get("watchlist_chain"),
            "all",
            allow_all=True,
        )
        state["watchlist_chain"] = selected_chain
        if cursor is None:
            cursor = state.get("feed_cursor", 0)
        try:
            cursor = int(cursor)
        except (TypeError, ValueError):
            cursor = 0

        saved_rows = list_watchlist_entries(
            _watchlist_store_path(),
            _watchlist_namespace(conn),
        )
        if selected_chain != "all":
            saved_rows = [
                row for row in saved_rows
                if _normalize_chain_name(row.get("chain"), "solana") == selected_chain
            ]
        rows = _build_watchlist_rows(saved_rows)

        state["screen"] = "browse"
        state["feed_source"] = "watchlist"
        state["feed_platform"] = ""
        state["feed_mode"] = "watchlist"
        state.pop("nav_from", None)
        state.pop("order_list", None)
        _clear_search_state(state)
        _set_feed_navigation_state(state, rows, cursor=cursor)
        feed_session = _next_feed_session(state)

        conn.loop.create_task(
            _send_display(
                conn,
                "browse",
                {
                    "tokens": rows or [_empty_feed_row("WATCHLIST", "Watchlist empty")],
                    "mode": "watchlist",
                    "source_label": _browse_source_label("WATCHLIST", selected_chain),
                    "cursor": state.get("feed_cursor", 0),
                    "feed_session": feed_session,
                },
            )
        )
        return ActionResponse(action=Action.NONE, result=f"watchlist:{len(rows)}", response=None)
    except Exception as exc:
        logger.bind(tag=TAG).error(f"ave_open_watchlist error: {exc}")
        conn.loop.create_task(
            _send_display(
                conn,
                "notify",
                {
                    "level": "error",
                    "title": "Watchlist unavailable",
                    "body": str(exc)[:60],
                },
            )
        )
        return ActionResponse(action=Action.RESPONSE, result=str(exc), response="观察列表暂时不可用")


@register_function("ave_add_current_watchlist_token", ave_add_watchlist_desc, ToolType.SYSTEM_CTL)
def ave_add_current_watchlist_token(conn: "ConnectionHandler", token: dict | None = None):
    state = _ensure_ave_state(conn)
    target = _resolve_watchlist_target(state, token)
    if not target:
        return ActionResponse(action=Action.RESPONSE, result="no_token", response="请先选中一个代币")

    state["current_token"] = {
        "addr": target["addr"],
        "chain": target["chain"],
        "symbol": target["symbol"],
        "token_id": f"{target['addr']}-{target['chain']}",
        "contract_tail": target["addr"][-4:] if len(target["addr"]) >= 4 else target["addr"],
        "source_tag": "",
    }
    try:
        add_watchlist_entry(
            _watchlist_store_path(),
            _watchlist_namespace(conn),
            {
                "addr": target["addr"],
                "chain": target["chain"],
                "symbol": target["symbol"] or "?",
                "added_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        return _watchlist_store_error_response(
            conn,
            user_message="观察列表暂时不可用，请稍后重试。",
            exc=exc,
        )
    conn.loop.create_task(
        _send_display(
            conn,
            "notify",
            {"level": "info", "title": "Watchlist", "body": "Added to watchlist"},
        )
    )
    return _refresh_spotlight_for_token(conn, target)


@register_function("ave_remove_current_watchlist_voice", ave_remove_watchlist_desc, ToolType.SYSTEM_CTL)
def ave_remove_current_watchlist_voice(conn: "ConnectionHandler", token: dict | None = None):
    state = _ensure_ave_state(conn)
    target = _resolve_watchlist_target(state, token)
    if not target:
        return ActionResponse(action=Action.RESPONSE, result="no_token", response="请先选中一个代币")

    try:
        removed = remove_watchlist_entry(
            _watchlist_store_path(),
            _watchlist_namespace(conn),
            target["addr"],
            target["chain"],
        )
    except Exception as exc:
        return _watchlist_store_error_response(
            conn,
            user_message="观察列表暂时不可用，请稍后重试。",
            exc=exc,
        )
    conn.loop.create_task(
        _send_display(
            conn,
            "notify",
            {
                "level": "info",
                "title": "Watchlist",
                "body": "Removed from watchlist" if removed else "Token not in watchlist",
            },
        )
    )
    return _refresh_spotlight_for_token(conn, target)


def ave_remove_current_watchlist_token(
    conn: "ConnectionHandler",
    token: dict | None = None,
    cursor=None,
):
    state = _ensure_ave_state(conn)
    target = _resolve_watchlist_target(state, token, cursor=cursor)
    if not target:
        return ActionResponse(action=Action.RESPONSE, result="no_token", response="请先选中一个代币")

    try:
        removed = remove_watchlist_entry(
            _watchlist_store_path(),
            _watchlist_namespace(conn),
            target["addr"],
            target["chain"],
        )
    except Exception as exc:
        return _watchlist_store_error_response(
            conn,
            user_message="观察列表暂时不可用，请稍后重试。",
            exc=exc,
        )
    conn.loop.create_task(
        _send_display(
            conn,
            "notify",
            {
                "level": "info",
                "title": "Watchlist",
                "body": "Removed from watchlist" if removed else "Token not in watchlist",
            },
        )
    )
    return ave_open_watchlist(conn, cursor=cursor)


# ---------------------------------------------------------------------------
# Tool: ave_get_trending
# ---------------------------------------------------------------------------

ave_get_trending_desc = {
    "type": "function",
    "function": {
        "name": "ave_get_trending",
        "description": "获取多链热门代币列表展示到发现流屏幕。默认混合抓取 solana/eth/bsc/base 四链；用户说'看 ETH 热门'时传 chain=eth。topic 参数可切换榜单类型：trending=热门（默认），gainer=涨幅榜，loser=跌幅榜，new=新币，meme=meme榜，ai=AI板块，depin=DePIN板块，gamefi=GameFi板块。platform 参数可指定平台：pump_in_hot=Pump.fun热门，pump_in_new=Pump.fun新币，fourmeme_in_hot=4.meme热门，fourmeme_in_new=4.meme新币。",
        "parameters": {
            "type": "object",
            "properties": {
                "chain": {
                    "type": "string",
                    "description": "区块链名称，all=四链混合（默认），或指定单链",
                    "enum": ["all", "solana", "bsc", "eth", "base"],
                },
                "topic": {
                    "type": "string",
                    "description": "榜单类型：trending=热门（默认），gainer=涨幅榜，loser=跌幅榜，new=新币，meme=meme榜，ai=AI板块，depin=DePIN，gamefi=GameFi",
                    "enum": ["trending", "gainer", "loser", "new", "meme", "ai", "depin", "gamefi"],
                },
                "platform": {
                    "type": "string",
                    "description": "Platform filter. Correct tag values: pump_in_hot (Pump.fun hot), pump_in_new (Pump.fun new), fourmeme_in_hot (4.meme hot), fourmeme_in_new (4.meme new). Leave empty for no platform filter.",
                },
            },
            "required": [],
        },
    },
}


def _build_token_list(tokens_raw, chain_fallback):
    """Convert raw API token list to display-friendly dicts."""
    tokens = []
    for t in tokens_raw:
        token_id = t.get("token", t.get("token_id", t.get("address", "")))
        chain_val = t.get("chain", chain_fallback)
        price_val = t.get("current_price_usd", t.get("price", 0))
        change_val = t.get("token_price_change_24h", t.get("price_change_24h", 0))
        vol_val = t.get("token_tx_volume_usd_24h", t.get("tx_volume_u_24h", 0))
        identity = _asset_identity_fields(
            {
                **t,
                "token_id": token_id,
                "chain": chain_val,
            }
        )
        tokens.append(
            {
                **identity,
                "price": _fmt_price(price_val),
                "price_raw": float(price_val or 0),
                "change_24h": _fmt_change(change_val),
                "change_positive": float(change_val or 0) >= 0,
                "volume_24h": _fmt_volume(
                    _coalesce_numeric_value(
                        vol_val,
                        t.get("tx_volume_u_24h"),
                    )
                ),
                "market_cap": _fmt_volume(
                    _coalesce_numeric_value(
                        t.get("market_cap"),
                        t.get("fdv"),
                    )
                ),
                "source": t.get("issue_platform", t.get("platform", "trending")),
                "risk_level": "UNKNOWN",
            }
        )
    return tokens


def _extract_limit_order_list(resp: dict) -> list:
    data = resp.get("data", resp)
    if isinstance(data, dict):
        for key in ("list", "orders", "items"):
            if isinstance(data.get(key), list):
                return data.get(key)
        return []
    if isinstance(data, list):
        return data
    return []


def _build_limit_order_rows(orders: list, chain: str = "solana") -> list:
    rows = []
    for order in orders:
        order_id = str(order.get("id", ""))
        token_id = order.get("outTokenAddress", order.get("tokenAddress", ""))
        symbol = order.get("symbol", order.get("outTokenSymbol", "???"))
        row_chain = order.get("chain", chain)

        try:
            limit_price = float(order.get("limitPrice", 0) or 0)
        except (TypeError, ValueError):
            limit_price = None
        try:
            create_price = float(order.get("createPrice", 0) or 0)
        except (TypeError, ValueError):
            create_price = None

        dist_pct = None
        change_positive = None
        if limit_price is not None and create_price is not None and create_price > 0:
            dist_pct = (limit_price - create_price) / create_price * 100
            change_positive = dist_pct >= 0

        identity = _asset_identity_fields(
            {
                "token_id": token_id,
                "chain": row_chain,
                "symbol": symbol,
                "source": "orders",
            }
        )
        rows.append(
            {
                **identity,
                "order_id": order_id,
                "price": _fmt_price(limit_price),
                "price_raw": limit_price,
                "change_24h": _fmt_change(dist_pct),
                "change_positive": change_positive,
                "source": "orders",
            }
        )
    return rows


@register_function("ave_get_trending", ave_get_trending_desc, ToolType.SYSTEM_CTL)
def ave_get_trending(conn: "ConnectionHandler", chain: str = "all", topic: str = "", platform: str = ""):
    """获取多链热门代币列表并推送到设备 FEED 屏幕"""
    import concurrent.futures

    # Platform path: single call to /tokens/platform, short-circuits per-chain loop
    use_platform = bool(platform)
    if use_platform:
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                resp = pool.submit(_data_get, "/tokens/platform",
                                   {"tag": platform, "limit": 20}).result()
            raw = resp.get("data", {})
            if isinstance(raw, dict):
                raw = raw.get("tokens", raw.get("list", raw.get("ranks", [])))
            lst = raw if isinstance(raw, list) else []
            tokens = _build_token_list(lst[:20], chain if chain != "all" else "???")
            state = _ensure_ave_state(conn)
            state["screen"] = "feed"
            state["feed_source"] = "trending"
            state["feed_platform"] = platform
            state["feed_mode"] = "standard"
            _remember_home_feed_state(state, source="trending", platform=platform)
            state.pop("nav_from", None)
            _clear_search_state(state)
            _set_feed_navigation_state(state, tokens, cursor=0)
            feed_session = _next_feed_session(state)

            conn.loop.create_task(
                _send_display(
                    conn,
                    "feed",
                    {
                        "tokens": tokens,
                        "chain": chain,
                        "feed_session": feed_session,
                    },
                )
            )
            logger.bind(tag=TAG).info(f"ave_get_trending: platform={platform} → {len(tokens)} tokens")
            if hasattr(conn, "ave_wss"):
                conn.ave_wss.set_feed_tokens(tokens, chain)
            return ActionResponse(action=Action.NONE, result=f"Showing {len(tokens)} tokens from {platform}", response="")
        except Exception as e:
            logger.bind(tag=TAG).error(f"ave_get_trending platform error: {e}")
            try:
                conn.loop.create_task(_send_display(conn, "notify", {
                    "level": "error",
                    "title": "Platform Feed Failed",
                    "body": str(e)[:60],
                }))
            except Exception:
                pass
            return ActionResponse(action=Action.RESPONSE, result=str(e), response="获取平台热门代币失败，请稍后重试")

    # Normalize topic: empty or "trending" → use /tokens/trending endpoint
    use_ranks = topic and topic != "trending"

    CHAINS = ["solana", "eth", "bsc", "base"] if chain == "all" else [chain]
    if use_ranks:
        # `/ranks` behaves like a global board mirrored across chain params.
        # Pull a deeper slice per request, then dedupe globally to fill 20.
        PER_CHAIN = 20
    else:
        PER_CHAIN = max(5, 20 // len(CHAINS))   # ≈ 5 each → 20 total

    def _fetch_chain(ch):
        try:
            if use_ranks:
                resp = _data_get("/ranks", {"topic": topic, "chain": ch, "limit": PER_CHAIN})
            else:
                resp = _data_get("/tokens/trending", {
                    "chain": ch, "current_page": 1, "page_size": PER_CHAIN,
                })
            raw = resp.get("data", {})
            if isinstance(raw, dict):
                raw = raw.get("tokens", raw.get("list", raw.get("ranks", [])))
            lst = raw if isinstance(raw, list) else []
            for item in lst:
                if not item.get("chain"):
                    item["chain"] = ch
            return ch, _filter_supported_feed_items(lst, ch)
        except Exception as e:
            logger.bind(tag=TAG).warning(f"fetch_chain {ch}: {e}")
            return ch, []

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(CHAINS)) as pool:
            results = list(pool.map(_fetch_chain, CHAINS))

        # Interleave: SOL[0], ETH[0], BSC[0], BASE[0], SOL[1], …
        buckets  = {ch: lst for ch, lst in results}
        max_len  = max((len(v) for v in buckets.values()), default=0)
        raw_all, seen = [], set()
        for i in range(max_len):
            for ch in CHAINS:
                lst = buckets.get(ch, [])
                if i < len(lst):
                    t   = lst[i]
                    tid = t.get("token", t.get("token_id", t.get("address", "")))
                    if use_ranks:
                        dedupe_key = str(tid)
                    else:
                        dedupe_key = (str(tid), str(t.get("chain") or ch or ""))
                    if tid and dedupe_key not in seen:
                        seen.add(dedupe_key)
                        raw_all.append(t)

        tokens = _build_token_list(raw_all[:20], chain if chain != "all" else "???")

        # Track state so LLM can reference tokens by symbol in follow-up commands
        state = _ensure_ave_state(conn)
        state["screen"] = "feed"
        state["feed_source"] = topic or "trending"
        state["feed_platform"] = ""
        state["feed_mode"] = "standard"
        _remember_home_feed_state(state, source=topic or "trending", platform="")
        state.pop("nav_from", None)
        _clear_search_state(state)
        _set_feed_navigation_state(state, tokens, cursor=0)
        feed_session = _next_feed_session(state)

        conn.loop.create_task(_send_display(conn, "feed", {
            "tokens": tokens,
            "chain": chain,
            "feed_session": feed_session,
        }))
        logger.bind(tag=TAG).info(f"ave_get_trending: sent {len(tokens)} tokens to FEED")

        if hasattr(conn, "ave_wss"):
            conn.ave_wss.set_feed_tokens(tokens, chain)

        # Include compact token listing in result so LLM knows what's on screen
        summary = ", ".join(f"{t['symbol']}({t['chain'][:3].upper()})" for t in tokens[:8])
        return ActionResponse(action=Action.NONE,
            result=f"已展示{len(tokens)}个热门代币: {summary}等", response=None)

    except Exception as e:
        logger.bind(tag=TAG).error(f"ave_get_trending error: {e}")
        try:
            conn.loop.create_task(_send_display(conn, "notify", {
                "level": "error",
                "title": "Trending Feed Failed",
                "body": str(e)[:60],
            }))
        except Exception:
            pass
        return ActionResponse(action=Action.RESPONSE, result=str(e), response="获取热门代币失败，请稍后重试")


# ---------------------------------------------------------------------------
# Tool: ave_search_token
# ---------------------------------------------------------------------------

ave_search_token_desc = {
    "type": "function",
    "function": {
        "name": "ave_search_token",
        "description": "Search for tokens by keyword/name/symbol. Use when user says 'search X', 'find X', 'look up X token'. Results appear on FEED screen.",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Token symbol or name to search for, e.g. 'TRUMP', 'PEPE', 'WIF'"
                },
                "chain": {
                    "type": "string",
                    "description": "Chain filter: 'all', 'solana', 'eth', 'bsc', 'base'. Default: 'all'",
                    "enum": ["all", "solana", "eth", "bsc", "base"]
                }
            },
            "required": ["keyword"]
        }
    }
}


@register_function("ave_search_token", ave_search_token_desc, ToolType.SYSTEM_CTL)
def ave_search_token(conn: "ConnectionHandler", keyword: str, chain: str = "all"):
    """搜索代币并推送结果到设备 FEED 屏幕"""
    try:
        params = {"keyword": keyword, "limit": 20}
        if chain and chain != "all":
            params["chain"] = chain
        resp = _data_get("/tokens", params)
        raw = resp.get("data", {})
        if isinstance(raw, dict):
            raw = raw.get("tokens", raw.get("list", []))
        lst = raw if isinstance(raw, list) else []

        tokens = _build_token_list(lst[:20], chain if chain != "all" else "???")
        state = _ensure_ave_state(conn)
        normalized_keyword = str(keyword or "").strip().upper()
        disambiguation_items = [
            token for token in tokens
            if normalized_keyword and str(token.get("symbol") or "").strip().upper() == normalized_keyword
        ]
        state["feed_mode"] = "search"
        state.pop("nav_from", None)

        if len(disambiguation_items) > 1:
            payload = _build_disambiguation_payload(disambiguation_items)
            visible_items = list(payload.get("items", []))
            _save_search_session(
                conn,
                query=keyword,
                chain=chain,
                items=visible_items,
                cursor=payload.get("cursor", 0),
            )
            conn.loop.create_task(_send_display(conn, "disambiguation", payload))
            logger.bind(tag=TAG).info(
                f"ave_search_token: '{keyword}' -> disambiguation ({len(disambiguation_items)} matches)"
            )
            state["screen"] = "disambiguation"
            state["nav_from"] = payload.get("nav_from", "feed")
            state["disambiguation_items"] = visible_items
            state["disambiguation_cursor"] = payload.get("cursor", 0)
            _set_feed_navigation_state(
                state,
                visible_items,
                cursor=payload.get("cursor", 0),
            )
            return ActionResponse(
                action=Action.NONE,
                result=f"Need disambiguation for '{keyword}' ({len(disambiguation_items)} matches)",
                response="",
            )

        _save_search_session(
            conn,
            query=keyword,
            chain=chain,
            items=tokens,
            cursor=0,
        )
        feed_session = _next_feed_session(state)
        conn.loop.create_task(_send_display(conn, "feed", {
            "tokens": tokens,
            "chain": chain,
            "source_label": "SEARCH",
            "mode": "search",
            "search_query": state.get("search_query", ""),
            "cursor": state.get("search_cursor", 0),
            "feed_session": feed_session,
        }))
        logger.bind(tag=TAG).info(f"ave_search_token: '{keyword}' \u2192 {len(tokens)} results")

        if hasattr(conn, "ave_wss"):
            conn.ave_wss.set_feed_tokens(tokens, chain)

        state["screen"] = "feed"
        state.pop("disambiguation_items", None)
        state.pop("disambiguation_cursor", None)
        _set_feed_navigation_state(state, tokens, cursor=0)

        return ActionResponse(action=Action.NONE, result=f"Found {len(tokens)} tokens matching '{keyword}'", response="")
    except Exception as e:
        logger.bind(tag=TAG).error(f"ave_search_token error: {e}")
        try:
            conn.loop.create_task(_send_display(conn, "notify", {
                "level": "error",
                "title": "Search Failed",
                "body": str(e)[:60],
            }))
        except Exception:
            pass
        return ActionResponse(action=Action.NONE, result=f"Search failed: {e}", response="")


# ---------------------------------------------------------------------------
# Tool: ave_list_orders
# ---------------------------------------------------------------------------

ave_list_orders_desc = {
    "type": "function",
    "function": {
        "name": "ave_list_orders",
        "description": "查看未完成的限价挂单列表，复用 FEED 屏显示。用户说'查看限价单/我的挂单/open orders/pending orders'时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "chain": {
                    "type": "string",
                    "description": "区块链，默认沿用当前上下文或 solana",
                    "enum": ["solana", "bsc", "eth", "base"]
                }
            },
            "required": []
        }
    }
}


@register_function("ave_list_orders", ave_list_orders_desc, ToolType.SYSTEM_CTL)
def ave_list_orders(conn: "ConnectionHandler", chain: str = "solana"):
    try:
        state = getattr(conn, "ave_state", {})
        if not chain:
            chain = state.get("last_orders_chain") or state.get("current_token", {}).get("chain") or "solana"
        if _get_trade_mode(conn) == _TRADE_MODE_PAPER:
            _try_fill_paper_limit_orders(conn, chain=chain)
            rows = _paper_limit_order_rows(conn, chain)
            source_label = "PAPER ORDERS"
        else:
            assets_id = os.environ.get("AVE_PROXY_WALLET_ID", "SIM_MOCK_WALLET")
            resp = _trade_get("/v1/thirdParty/tx/getLimitOrder", {
                "assetsId": assets_id,
                "chain": chain,
                "pageSize": "20",
                "pageNo": "0",
                "status": "waiting",
            })
            orders = _extract_limit_order_list(resp)
            rows = _build_limit_order_rows(orders, chain=chain)
            source_label = "ORDERS"

        display_rows = rows or [{
            "token_id": "",
            "order_id": "",
            "chain": chain,
            "symbol": "EMPTY",
            "price": "--",
            "change_24h": "--",
            "change_positive": True,
            "source": "orders",
        }]
        state = _ensure_ave_state(conn)
        feed_session = _next_feed_session(state)
        _invalidate_live_feed_session(
            conn,
            session=feed_session,
            chain=chain,
            clear_tokens=True,
        )
        conn.loop.create_task(_send_display(conn, "feed", {
            "tokens": display_rows,
            "chain": chain,
            "mode": "orders",
            "source_label": source_label,
            "feed_session": feed_session,
        }))

        state["screen"] = "feed"
        state["feed_mode"] = "orders"
        state.pop("nav_from", None)
        state["last_orders_chain"] = chain
        state["order_list"] = [{
            "id": row.get("order_id", ""),
            "symbol": row.get("symbol", "???"),
            "token_id": row.get("token_id", ""),
            "chain": row.get("chain", chain),
        } for row in rows if row.get("order_id")]

        if not rows:
            return ActionResponse(action=Action.NONE, result="没有未完成挂单", response=None)

        summary = "; ".join(
            f"{idx + 1}. {row['symbol']} limit {row['price']} (id: {row['order_id']})"
            for idx, row in enumerate(rows[:8])
        )
        return ActionResponse(action=Action.NONE, result=summary, response=None)
    except Exception as e:
        logger.bind(tag=TAG).error(f"ave_list_orders error: {e}")
        return ActionResponse(action=Action.RESPONSE, result=str(e), response="查询挂单失败")


# ---------------------------------------------------------------------------
# Tool: ave_cancel_order
# ---------------------------------------------------------------------------

ave_cancel_order_desc = {
    "type": "function",
    "function": {
        "name": "ave_cancel_order",
        "description": "撤销一个或多个限价挂单。传 order_ids 列表；如用户说撤销全部，可传 ['all']。",
        "parameters": {
            "type": "object",
            "properties": {
                "order_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要撤销的挂单 ID 列表，或 ['all']"
                },
                "chain": {
                    "type": "string",
                    "description": "区块链，默认沿用最近一次挂单列表查询的链",
                    "enum": ["solana", "bsc", "eth", "base"]
                },
                "symbol": {
                    "type": "string",
                    "description": "展示用符号，可省略"
                }
            },
            "required": ["order_ids"]
        }
    }
}


@register_function("ave_cancel_order", ave_cancel_order_desc, ToolType.SYSTEM_CTL)
def ave_cancel_order(conn: "ConnectionHandler", order_ids: list, chain: str = "", symbol: str = ""):
    try:
        if not order_ids:
            return ActionResponse(action=Action.RESPONSE, result="no_order_ids", response="请先告诉我要撤销哪个挂单")

        state = getattr(conn, "ave_state", {})
        chain = chain or state.get("last_orders_chain") or state.get("current_token", {}).get("chain") or "solana"
        resolved_ids = [str(order_id) for order_id in order_ids]
        trade_mode = _get_trade_mode(conn)

        if resolved_ids == ["all"]:
            if trade_mode == _TRADE_MODE_PAPER:
                orders = list_paper_open_orders(_paper_store_path(), _trade_namespace(conn))
                resolved_ids = [
                    str(order.get("id", ""))
                    for order in orders
                    if isinstance(order, dict) and _normalize_chain_name(order.get("chain"), chain) == chain and order.get("id")
                ]
            else:
                assets_id = os.environ.get("AVE_PROXY_WALLET_ID", "SIM_MOCK_WALLET")
                resp = _trade_get("/v1/thirdParty/tx/getLimitOrder", {
                    "assetsId": assets_id,
                    "chain": chain,
                    "pageSize": "20",
                    "pageNo": "0",
                    "status": "waiting",
                })
                orders = _extract_limit_order_list(resp)
                resolved_ids = [str(order.get("id", "")) for order in orders if order.get("id")]
            if not resolved_ids:
                return ActionResponse(action=Action.RESPONSE, result="no_waiting_orders", response="没有可撤销的挂单")

        if not symbol:
            known_orders = {item.get("id"): item for item in state.get("order_list", [])}
            first = known_orders.get(resolved_ids[0], {})
            symbol = first.get("symbol", "ORDER")

        trade_params = {
            "chain": chain,
            "ids": resolved_ids,
        }
        tid = trade_mgr.create("cancel_order", trade_params, conn)

        order_count_label = f"{len(resolved_ids)} order" if len(resolved_ids) == 1 else f"{len(resolved_ids)} orders"
        _set_pending_trade(
            conn=conn,
            trade_id=tid,
            trade_type="cancel_order",
            action="CANCEL",
            symbol=symbol or "ORDER",
            amount_native=order_count_label,
            amount_usd="",
            chain=chain,
            order_ids=resolved_ids,
        )

        conn.loop.create_task(_send_display(conn, "confirm", {
            "trade_id": tid,
            "action": "CANCEL",
            "symbol": symbol,
            "amount_native": order_count_label,
            "amount_usd": "",
            "tp_pct": 0,
            "sl_pct": 0,
            "slippage_pct": 0.0,
            "timeout_sec": TRADE_CONFIRM_TIMEOUT_SEC,
            "mode_label": _trade_mode_marker(conn),
        }))

        return ActionResponse(
            action=Action.NONE,
            result=f"cancel_pending:{tid} ids={','.join(resolved_ids)}",
            response=None,
        )
    except Exception as e:
        logger.bind(tag=TAG).error(f"ave_cancel_order error: {e}")
        return ActionResponse(action=Action.RESPONSE, result=str(e), response="撤销挂单失败")


# ---------------------------------------------------------------------------
# Tool: ave_token_detail
# ---------------------------------------------------------------------------

ave_token_detail_desc = {
    "type": "function",
    "function": {
        "name": "ave_token_detail",
        "description": "查询指定代币的详情、K线图和风险信息，展示到聚焦详情屏幕。用户说'看这个/详情/进入'时调用（addr可省略，自动用当前选中代币）",
        "parameters": {
            "type": "object",
            "properties": {
                "addr": {"type": "string", "description": "代币合约地址（可省略，省略时用当前显示的代币）"},
                "chain": {"type": "string", "description": "区块链名称", "enum": ["solana", "bsc", "eth", "base"]},
                "symbol": {"type": "string", "description": "代币符号，如 BONK（addr省略时按此查找）"},
                "interval": {
                    "type": "string",
                    "description": "K线周期，s1(秒级实时)/1/5/60/240/1440（分钟），默认60（1小时）",
                    "enum": ["s1", "1", "5", "60", "240", "1440"]
                },
            },
            "required": [],
        },
    },
}


@register_function("ave_token_detail", ave_token_detail_desc, ToolType.SYSTEM_CTL)
def ave_token_detail(conn: "ConnectionHandler", addr: str = "", chain: str = "solana",
                     symbol: str = "", interval: str = "60",
                     feed_cursor=None, feed_total=None):
    """查询代币详情并推送到设备 SPOTLIGHT 屏幕"""
    try:
        addr, chain = _split_token_reference(addr, chain)
        # Resolve addr from symbol lookup or current state if not provided
        if not addr:
            state = getattr(conn, "ave_state", {})
            if symbol:
                entry = state.get("feed_tokens", {}).get(symbol.upper())
                if entry:
                    addr, chain = _split_token_reference(entry.get("addr", ""), entry.get("chain", chain))
            if not addr:
                cur = state.get("current_token")
                if cur:
                    addr, chain = _split_token_reference(cur.get("addr", ""), cur.get("chain", chain))
            if not addr:
                return ActionResponse(action=Action.RESPONSE,
                    result="no_token", response="请告诉我你想查看哪个代币的地址或名称")

        if _get_trade_mode(conn) == _TRADE_MODE_PAPER:
            _try_fill_paper_limit_orders(conn, chain=chain, token_addr=addr)

        state = _ensure_ave_state(conn)
        previous_screen = str(state.get("screen") or "")
        if previous_screen == "portfolio":
            state["portfolio_selected_token"] = {"addr": addr, "chain": chain}
            state["portfolio_cursor"] = _coerce_portfolio_cursor(
                _portfolio_holding_index(state.get("portfolio_holdings", []), addr, chain),
                len(state.get("portfolio_holdings", [])) if isinstance(state.get("portfolio_holdings"), list) else 0,
            )
        interval = str(interval or "60").strip().lower() or "60"
        resolved_symbol = _resolve_spotlight_symbol(state, addr, chain, symbol, feed_cursor)
        is_refreshing_current_spotlight = _is_same_spotlight_token(state, addr, chain)
        origin_hint = _resolve_spotlight_origin_hint(
            state,
            addr,
            chain,
            previous_screen=previous_screen,
        )
        is_watchlisted = _is_watchlisted_for_token(conn, addr, chain)
        request_seq = int(state.get("spotlight_request_seq", 0) or 0) + 1
        state["spotlight_request_seq"] = request_seq
        state["spotlight_origin_hint"] = origin_hint
        state["spotlight_is_watchlisted"] = bool(is_watchlisted)
        state["screen"] = "spotlight"
        state["current_token"] = {
            "addr": addr,
            "chain": chain,
            "symbol": resolved_symbol,
            "token_id": f"{addr}-{chain}",
            "contract_tail": addr[-4:] if len(addr) >= 4 else addr,
            "source_tag": "",
            "origin_hint": origin_hint,
        }
        explicit_nav_from = str(state.get("nav_from") or "").strip().lower()
        if explicit_nav_from not in {"feed", "portfolio", "signals", "watchlist"}:
            if previous_screen == "portfolio":
                state["nav_from"] = "portfolio"
            elif previous_screen == "browse":
                if state.get("feed_mode") == "signals" or state.get("feed_source") == "signals":
                    state["nav_from"] = "signals"
                elif state.get("feed_mode") == "watchlist" or state.get("feed_source") == "watchlist":
                    state["nav_from"] = "watchlist"
                else:
                    state["nav_from"] = "feed"
            elif previous_screen in {"feed", "disambiguation"}:
                state["nav_from"] = "feed"
            else:
                state["nav_from"] = "feed"
        loading_payload = _build_spotlight_loading_payload(
            addr,
            chain,
            symbol=resolved_symbol,
            interval=interval,
            feed_cursor=feed_cursor,
            feed_total=feed_total,
            origin_hint=origin_hint,
            is_watchlisted=is_watchlisted,
        )
        if is_refreshing_current_spotlight and hasattr(conn, "ave_wss"):
            transition_payload = {
                "addr": addr,
                "chain": chain,
                "token_id": f"{addr}-{chain}",
                "symbol": resolved_symbol,
                "interval": interval,
            }
            if feed_cursor is not None and feed_total is not None:
                transition_payload["cursor"] = feed_cursor
                transition_payload["total"] = feed_total
            try:
                wss_interval = _to_wss_kline_interval(interval)
                conn.ave_wss.begin_spotlight_transition(
                    addr,
                    chain,
                    transition_payload,
                    interval=wss_interval,
                )
            except Exception:
                pass
        elif previous_screen == "spotlight" and hasattr(conn, "ave_wss"):
            try:
                wss_interval = _to_wss_kline_interval(interval)
                conn.ave_wss.begin_spotlight_transition(
                    addr,
                    chain,
                    loading_payload,
                    interval=wss_interval,
                )
            except Exception:
                pass
            conn.loop.create_task(_send_display(conn, "spotlight", loading_payload))
        else:
            conn.loop.create_task(_send_display(conn, "spotlight", loading_payload))
        conn.loop.create_task(
            _ave_token_detail_async(
                conn,
                addr=addr,
                chain=chain,
                symbol=resolved_symbol,
                interval=interval,
                feed_cursor=feed_cursor,
                feed_total=feed_total,
                request_seq=request_seq,
                previous_screen=previous_screen,
            )
        )

        return ActionResponse(action=Action.NONE,
            result=f"已展示{resolved_symbol}详情 [addr={addr}, chain={chain}]", response=None)

    except Exception as e:
        logger.bind(tag=TAG).error(f"ave_token_detail error: {e}")
        try:
            conn.loop.create_task(_send_display(conn, "notify", {
                "level": "error", "title": "Lookup Failed", "body": str(e)[:60],
            }))
        except Exception:
            pass
        return ActionResponse(action=Action.RESPONSE, result=str(e), response="查询代币详情失败")


# ---------------------------------------------------------------------------
# Tool: ave_risk_check
# ---------------------------------------------------------------------------

ave_risk_check_desc = {
    "type": "function",
    "function": {
        "name": "ave_risk_check",
        "description": "检查合约安全风险，CRITICAL风险直接拦截并告警，不允许交易",
        "parameters": {
            "type": "object",
            "properties": {
                "addr": {"type": "string", "description": "代币合约地址"},
                "chain": {"type": "string", "description": "区块链名称"},
            },
            "required": ["addr", "chain"],
        },
    },
}


@register_function("ave_risk_check", ave_risk_check_desc, ToolType.SYSTEM_CTL)
def ave_risk_check(conn: "ConnectionHandler", addr: str, chain: str = "solana"):
    """检查合约风险，返回风险信息但不阻止后续交易流程。"""
    try:
        risk_resp = _data_get(f"/contracts/{addr}-{chain}")
        flags = _risk_flags(risk_resp)

        logger.bind(tag=TAG).info(f"Risk check passed: {addr}-{chain} level={flags['risk_level']}")
        return ActionResponse(
            action=Action.NONE,
            result=f"risk_level={flags['risk_level']},honeypot={flags['is_honeypot']}",
            response=None,
        )

    except Exception as e:
        logger.bind(tag=TAG).error(f"ave_risk_check error: {e}")
        return ActionResponse(action=Action.NONE, result=f"risk_check_failed: {e}", response=None)


# ---------------------------------------------------------------------------
# Tool: ave_buy_token
# ---------------------------------------------------------------------------

ave_buy_token_desc = {
    "type": "function",
    "function": {
        "name": "ave_buy_token",
        "description": "市价买入代币，先显示确认屏幕，等用户按键或语音确认后执行。addr可省略（自动用当前查看的代币）",
        "parameters": {
            "type": "object",
            "properties": {
                "addr": {"type": "string", "description": "代币合约地址（可省略，省略时用当前代币）"},
                "chain": {"type": "string", "description": "区块链", "enum": ["solana", "bsc", "eth", "base"]},
                "in_amount_sol": {"type": "number", "description": "买入金额（SOL单位），默认0.1"},
                "tp_pct": {"type": "integer", "description": "止盈百分比，默认25"},
                "sl_pct": {"type": "integer", "description": "止损百分比，默认15"},
                "symbol": {"type": "string", "description": "代币符号（展示用）"},
            },
            "required": [],
        },
    },
}


@register_function("ave_buy_token", ave_buy_token_desc, ToolType.SYSTEM_CTL)
def ave_buy_token(
    conn: "ConnectionHandler",
    addr: str = "",
    chain: str = "solana",
    in_amount_sol: float = None,
    tp_pct: int = None,
    sl_pct: int = None,
    symbol: str = "",
):
    """先风控检查，通过后推送 CONFIRM 屏幕"""
    try:
        addr, chain = _split_token_reference(addr, chain)
        # Resolve addr from current token state if omitted
        if not addr:
            cur = getattr(conn, "ave_state", {}).get("current_token")
            if cur:
                addr, chain = _split_token_reference(cur.get("addr", ""), cur.get("chain", chain))
                symbol = symbol or cur.get("symbol", "TOKEN")
            else:
                return ActionResponse(action=Action.RESPONSE,
                    result="no_token", response="请先查看一个代币详情，或告诉我买哪个代币")

        symbol = _resolve_trade_symbol(conn, addr, chain, symbol)

        # 1. Risk check (informational only; do not block buys)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            risk_resp = pool.submit(_data_get, f"/contracts/{addr}-{chain}").result()
        flags = _risk_flags(risk_resp)
        if flags["risk_level"] == "CRITICAL" or flags["is_honeypot"]:
            logger.bind(tag=TAG).warning(
                f"ave_buy_token proceeding despite risk flags: {addr}-{chain} "
                f"level={flags['risk_level']} honeypot={flags['is_honeypot']}"
            )

        # 2. Apply defaults
        trade_amount = in_amount_sol if in_amount_sol is not None else DEFAULT_BUY_NATIVE_AMOUNT
        tp = tp_pct if tp_pct is not None else DEFAULT_TP_PCT
        sl = sl_pct if sl_pct is not None else DEFAULT_SL_PCT
        slippage = DEFAULT_SLIPPAGE

        # 3. Get current price for USD estimate
        native_amount_text = _native_amount_label(chain, trade_amount)
        usd_est = _estimate_native_usd(chain, trade_amount)
        in_amount_lamports = _native_amount_to_base_units(chain, trade_amount)

        # 4. Get assetsId (fall back to SIM_MOCK so CONFIRM screen shows in simulator)
        assets_id = os.environ.get("AVE_PROXY_WALLET_ID", "SIM_MOCK_WALLET")

        # 5. Build trade params
        trade_params = {
            "chain": chain,
            "assetsId": assets_id,
            "inTokenAddress": _native_token_address(chain),
            "outTokenAddress": addr,
            "inAmount": str(in_amount_lamports),
            "swapType": "buy",
            "slippage": str(slippage),
            "useMev": True,
            "autoSlippage": True,
            "autoSellConfig": [
                {
                    "priceChange": str(tp * 100),    # e.g. 2500 = 25%
                    "sellRatio": "10000",
                    "type": "default",
                },
                {
                    "priceChange": str(-sl * 100),   # e.g. -1500 = -15%
                    "sellRatio": "10000",
                    "type": "default",
                },
            ],
            "paper_native_amount": str(trade_amount),
            "paper_symbol": symbol,
        }
        if chain == "solana":
            trade_params["gas"] = DEFAULT_SOLANA_GAS_LAMPORTS
            trade_params["autoGas"] = DEFAULT_SOLANA_AUTO_GAS
        trade_params = _normalize_proxy_trade_payload("market_buy", trade_params)

        # 6. Register pending trade
        tid = trade_mgr.create("market_buy", trade_params, conn)

        # 7. Track state for voice confirm/cancel
        _set_pending_trade(
            conn=conn,
            trade_id=tid,
            trade_type="market_buy",
            action="BUY",
            symbol=symbol,
            amount_native=native_amount_text,
            amount_usd=f"${usd_est:.2f}",
            chain=chain,
            asset_token_address=addr,
        )

        # 8. Try to get exact output amount from quote API (Solana only)
        out_amount_str = ""
        if chain == "solana":
            try:
                from plugins_func.functions.ave_trade_mgr import _trade_post
                in_amount_lamports_quote = _native_amount_to_base_units(chain, trade_amount)
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    quote_resp = pool.submit(_trade_post, "/v1/thirdParty/chainWallet/getAmountOut", {
                        "chain": chain,
                        "inAmount": str(in_amount_lamports_quote),
                        "inTokenAddress": _native_token_address(chain),
                        "outTokenAddress": addr,
                        "swapType": "buy",
                    }).result()
                formatted = _format_quote_out_amount(quote_resp, symbol=symbol)
                if formatted:
                    out_amount_str = str(formatted)
            except Exception as e:
                logger.bind(tag=TAG).warning(f"quote API failed (non-fatal): {e}")
                # out_amount_str stays "" — confirm screen will use USD estimate fallback

        # 9. Push CONFIRM screen
        identity = _asset_identity_fields({"addr": addr, "chain": chain, "symbol": symbol})
        confirm_payload = {
            **identity,
            "trade_id": tid,
            "action": "BUY",
            "amount_native": native_amount_text,
            "amount_usd": f"${usd_est:.2f}",
            "tp_pct": tp,
            "sl_pct": sl,
            "slippage_pct": slippage / 100,
            "timeout_sec": TRADE_CONFIRM_TIMEOUT_SEC,
        }
        if _get_trade_mode(conn) == _TRADE_MODE_PAPER:
            confirm_payload["mode_label"] = "PAPER"
        if out_amount_str:
            confirm_payload["out_amount"] = out_amount_str
        conn.loop.create_task(_send_display(conn, "confirm", confirm_payload))

        return ActionResponse(action=Action.NONE,
            result=f"已展示买入{symbol}确认页，等待用户确认 [trade_id={tid}]。"
                   f"用户说'确认'时调用 ave_confirm_trade，说'取消'时调用 ave_cancel_trade",
            response=None)

    except Exception as e:
        logger.bind(tag=TAG).error(f"ave_buy_token error: {e}")
        try:
            conn.loop.create_task(_send_display(conn, "notify", {
                "level": "error", "title": "Buy Failed", "body": str(e)[:60],
            }))
        except Exception:
            pass
        return ActionResponse(action=Action.RESPONSE, result=str(e), response="准备买入时出错，请重试")


# ---------------------------------------------------------------------------
# Tool: ave_limit_order
# ---------------------------------------------------------------------------

ave_limit_order_desc = {
    "type": "function",
    "function": {
        "name": "ave_limit_order",
        "description": "设置限价买单，等价格达到目标价再自动买入",
        "parameters": {
            "type": "object",
            "properties": {
                "addr": {"type": "string", "description": "代币合约地址"},
                "chain": {"type": "string", "description": "区块链"},
                "in_amount_sol": {"type": "number", "description": "买入金额（SOL）"},
                "limit_price": {"type": "number", "description": "目标价格（USD）"},
                "current_price": {"type": "number", "description": "当前价格（USD，用于展示距离）"},
                "symbol": {"type": "string", "description": "代币符号"},
                "expire_hours": {"type": "integer", "description": "过期时间（小时），默认24"},
            },
            "required": ["addr", "chain", "limit_price"],
        },
    },
}


@register_function("ave_limit_order", ave_limit_order_desc, ToolType.SYSTEM_CTL)
def ave_limit_order(
    conn: "ConnectionHandler",
    addr: str,
    chain: str = "solana",
    in_amount_sol: float = None,
    limit_price: float = 0.0,
    current_price: float = None,
    symbol: str = "TOKEN",
    expire_hours: int = 24,
):
    """推送限价单确认屏幕"""
    try:
        addr, chain = _split_token_reference(addr, chain)
        symbol = _resolve_trade_symbol(conn, addr, chain, symbol)
        try:
            risk_resp = _data_get(f"/contracts/{addr}-{chain}")
            flags = _risk_flags(risk_resp)
            if flags["risk_level"] == "CRITICAL" or flags["is_honeypot"]:
                logger.bind(tag=TAG).warning(
                    f"ave_limit_order proceeding despite risk flags: {addr}-{chain} "
                    f"level={flags['risk_level']} honeypot={flags['is_honeypot']}"
                )
        except Exception as e:
            logger.bind(tag=TAG).warning(f"ave_limit_order risk check skipped: {e}")

        trade_amount = in_amount_sol if in_amount_sol is not None else DEFAULT_BUY_NATIVE_AMOUNT
        native_amount_text = _native_amount_label(chain, trade_amount)
        in_amount_lamports = _native_amount_to_base_units(chain, trade_amount)
        expire_secs = expire_hours * 3600
        # Fall back to SIM_MOCK so LIMIT_CONFIRM screen shows in simulator
        assets_id = os.environ.get("AVE_PROXY_WALLET_ID", "SIM_MOCK_WALLET")

        trade_params = {
            "chain": chain,
            "assetsId": assets_id,
            "inTokenAddress": _native_token_address(chain),
            "outTokenAddress": addr,
            "inAmount": str(in_amount_lamports),
            "swapType": "buy",
            "slippage": str(DEFAULT_SLIPPAGE),
            "useMev": True,
            "limitPrice": str(limit_price),
            "expireTime": str(expire_secs),
            "paper_native_amount": str(trade_amount),
            "paper_current_price": str(current_price if current_price is not None else ""),
            "paper_symbol": symbol,
        }
        if chain == "solana":
            trade_params["gas"] = DEFAULT_SOLANA_GAS_LAMPORTS
            trade_params["autoGas"] = DEFAULT_SOLANA_AUTO_GAS
        trade_params = _normalize_proxy_trade_payload("limit_buy", trade_params)

        tid = trade_mgr.create("limit_buy", trade_params, conn)
        _set_pending_trade(
            conn=conn,
            trade_id=tid,
            trade_type="limit_buy",
            action="LIMIT BUY",
            symbol=symbol,
            amount_native=native_amount_text,
            amount_usd="",
            screen="limit_confirm",
            chain=chain,
            asset_token_address=addr,
        )

        # Calculate distance from current price
        dist_str = "N/A"
        if current_price and current_price > 0:
            dist_pct = (limit_price - current_price) / current_price * 100
            dist_str = f"{dist_pct:+.1f}%"

        identity = _asset_identity_fields({"addr": addr, "chain": chain, "symbol": symbol})
        conn.loop.create_task(_send_display(conn, "limit_confirm", {
            **identity,
            "trade_id": tid,
            "action": "LIMIT BUY",
            "limit_price": _fmt_price(limit_price),
            "limit_price_raw": limit_price,
            "current_price": _fmt_price(current_price),
            "distance": dist_str,
            "amount_native": native_amount_text,
            "expire_hours": expire_hours,
            "timeout_sec": TRADE_CONFIRM_TIMEOUT_SEC,
            "mode_label": _trade_mode_marker(conn),
        }))

        return ActionResponse(action=Action.NONE, result=f"limit_pending:{tid}", response=None)

    except Exception as e:
        logger.bind(tag=TAG).error(f"ave_limit_order error: {e}")
        return ActionResponse(action=Action.RESPONSE, result=str(e), response="设置限价单失败")


# ---------------------------------------------------------------------------
# Tool: ave_sell_token
# ---------------------------------------------------------------------------

ave_sell_token_desc = {
    "type": "function",
    "function": {
        "name": "ave_sell_token",
        "description": "市价卖出代币，显示确认屏幕等待用户确认",
        "parameters": {
            "type": "object",
            "properties": {
                "addr": {"type": "string", "description": "要卖出的代币合约地址"},
                "chain": {"type": "string", "description": "区块链"},
                "sell_ratio": {"type": "number", "description": "卖出比例 0-1，默认1.0（全部卖出）"},
                "symbol": {"type": "string", "description": "代币符号"},
                "holdings_amount": {"type": "string", "description": "当前持仓 raw 机器单位字符串，必须保留精确值"},
            },
            "required": ["addr", "chain"],
        },
    },
}


@register_function("ave_sell_token", ave_sell_token_desc, ToolType.SYSTEM_CTL)
def ave_sell_token(
    conn: "ConnectionHandler",
    addr: str,
    chain: str = "solana",
    sell_ratio: float = 1.0,
    symbol: str = "TOKEN",
    holdings_amount=None,
):
    """市价卖出，推送 CONFIRM 屏幕"""
    try:
        addr, chain = _split_token_reference(addr, chain)
        symbol = _resolve_trade_symbol(conn, addr, chain, symbol)
        assets_id = os.environ.get("AVE_PROXY_WALLET_ID", "SIM_MOCK_WALLET")

        # Calculate in_amount from holdings
        # For sell, inAmount should be the token amount (in raw units)
        # sell_ratio * holdings
        if holdings_amount is not None:
            try:
                in_amount = int(Decimal(str(holdings_amount)) * Decimal(str(sell_ratio)))
            except (ArithmeticError, InvalidOperation, ValueError, TypeError):
                in_amount = 0
        else:
            # Fallback: use 0 and let AVE handle it with sell ratio
            in_amount = 0

        trade_params = {
            "chain": chain,
            "assetsId": assets_id,
            "inTokenAddress": addr,
            "outTokenAddress": _native_token_address(chain),
            "inAmount": str(in_amount) if in_amount > 0 else "0",
            "swapType": "sell",
            "slippage": str(DEFAULT_SLIPPAGE),
            "useMev": True,
            "autoSlippage": True,
            "paper_sell_ratio": str(sell_ratio),
            "paper_position_amount": str(holdings_amount or ""),
            "paper_symbol": symbol,
        }
        if chain == "solana":
            trade_params["gas"] = DEFAULT_SOLANA_GAS_LAMPORTS
            trade_params["autoGas"] = DEFAULT_SOLANA_AUTO_GAS
        trade_params = _normalize_proxy_trade_payload("market_sell", trade_params)

        tid = trade_mgr.create("market_sell", trade_params, conn)

        sell_pct = int(sell_ratio * 100)
        _set_pending_trade(
            conn=conn,
            trade_id=tid,
            trade_type="market_sell",
            action="SELL",
            symbol=symbol,
            amount_native=f"{sell_pct}% holdings",
            amount_usd="",
            chain=chain,
            asset_token_address=addr,
        )
        identity = _asset_identity_fields({"addr": addr, "chain": chain, "symbol": symbol})
        conn.loop.create_task(_send_display(conn, "confirm", {
            **identity,
            "trade_id": tid,
            "action": "SELL",
            "amount_native": f"{sell_pct}% holdings",
            "amount_usd": "",
            "tp_pct": None,
            "sl_pct": None,
            "slippage_pct": DEFAULT_SLIPPAGE / 100,
            "timeout_sec": TRADE_CONFIRM_TIMEOUT_SEC,
            "mode_label": _trade_mode_marker(conn),
        }))

        return ActionResponse(action=Action.NONE, result=f"sell_pending:{tid}", response=None)

    except Exception as e:
        logger.bind(tag=TAG).error(f"ave_sell_token error: {e}")
        return ActionResponse(action=Action.RESPONSE, result=str(e), response="准备卖出时出错")


# ---------------------------------------------------------------------------
# Tool: ave_portfolio
# ---------------------------------------------------------------------------

ave_portfolio_desc = {
    "type": "function",
    "function": {
        "name": "ave_portfolio",
        "description": "查询代理钱包持仓并展示持仓总览屏幕，用户说'我的持仓'或'查资产'时调用",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


@register_function("ave_portfolio", ave_portfolio_desc, ToolType.SYSTEM_CTL)
def ave_portfolio(conn: "ConnectionHandler", chain_filter: str = ""):
    """查询持仓并推送 PORTFOLIO 屏幕"""
    try:
        state = _ensure_ave_state(conn)
        selected_chain = _normalize_surface_chain(
            chain_filter or state.get("portfolio_chain"),
            "solana",
            allow_all=False,
        )
        state["portfolio_chain"] = selected_chain

        if _get_trade_mode(conn) == _TRADE_MODE_PAPER:
            _try_fill_paper_limit_orders(conn)
            selection_hint = state.pop("portfolio_selected_token", None)
            state["screen"] = "portfolio"
            state["portfolio_view"] = "list"
            payload = _build_paper_portfolio_payload(conn, chain_filter=selected_chain)
            holdings = payload.get("holdings", [])
            cursor = payload.get("cursor", 0)
            if isinstance(selection_hint, dict):
                selected_idx = _portfolio_holding_index(
                    holdings,
                    selection_hint.get("addr", ""),
                    selection_hint.get("chain", ""),
                )
                if selected_idx >= 0:
                    cursor = selected_idx
                    payload["cursor"] = cursor
            conn.loop.create_task(_send_display(conn, "portfolio", payload))
            state["portfolio_holdings"] = [
                {
                    "addr": row.get("addr", ""),
                    "chain": row.get("chain", ""),
                    "symbol": row.get("symbol", ""),
                }
                for row in holdings
                if row.get("addr")
            ]
            state["portfolio_cursor"] = cursor
            return ActionResponse(action=Action.NONE, result=f"paper_portfolio:{len(holdings)}tokens", response=None)

        assets_id = os.environ.get("AVE_PROXY_WALLET_ID", "")
        selection_hint = state.pop("portfolio_selected_token", None)
        state["screen"] = "portfolio"
        state["portfolio_view"] = "list"
        state["portfolio_holdings"] = []
        if not assets_id:
            # No wallet configured: show empty portfolio in simulator
            explanation_fields = _portfolio_explanation_fields("N/A")
            conn.loop.create_task(_send_display(conn, "portfolio", {
                "holdings": [],
                "cursor": 0,
                "total_usd": "$0",
                "pnl": "N/A",
                "pnl_pct": "N/A",
                "chain_label": _surface_chain_label(selected_chain),
                **explanation_fields,
            }))
            state["portfolio_cursor"] = 0
            return ActionResponse(action=Action.NONE, result="no_wallet_sim", response=None)

        # Get wallet info (chain addresses)
        wallet_resp = _trade_get(
            "/v1/thirdParty/user/getUserByAssetsId",
            {"assetsIds": assets_id}
        )
        wallets = wallet_resp.get("data", [])
        portfolio_wallets = _normalize_portfolio_wallets(wallets)
        state["portfolio_wallets"] = portfolio_wallets
        if not wallets:
            explanation_fields = _portfolio_explanation_fields("N/A")
            conn.loop.create_task(_send_display(conn, "portfolio", {
                "holdings": [],
                "cursor": 0,
                "wallets": portfolio_wallets,
                "holding_source": "getUserByAssetsId",
                "total_usd": "$0",
                "pnl": "N/A",
                "pnl_pct": "N/A",
                "chain_label": _surface_chain_label(selected_chain),
                **explanation_fields,
            }))
            state["portfolio_holding_source"] = "getUserByAssetsId"
            state["portfolio_cursor"] = 0
            return ActionResponse(action=Action.NONE, result="empty_portfolio", response=None)

        token_ids, holdings_map, holding_sources = _collect_portfolio_holdings(wallets)
        holding_source = ",".join(holding_sources) if holding_sources else "getUserByAssetsId.addressList"
        state["portfolio_holding_source"] = holding_source

        # Batch price query
        prices = _price_map_for_token_ids(token_ids)

        # Build holdings list
        holdings = []
        total_usd = 0.0
        for tid_str, info in holdings_map.items():
            price = prices.get(_normalize_batch_price_token_id(tid_str), 0)
            display_balance = float(info.get("display_balance_decimal", 0) or 0)
            value = display_balance * price
            total_usd += value
            raw_balance_text = ""
            if info.get("has_complete_raw_balance") and info.get("raw_balance_decimal") is not None:
                raw_balance_text = _decimal_to_string(info.get("raw_balance_decimal"))
            # No PnL available without cost basis; show N/A
            holdings.append({
                "symbol": info["symbol"],
                "addr": info["addr"],
                "chain": info["chain"],
                "contract_tail": info.get("contract_tail", ""),
                "token_id": info.get("token_id", tid_str),
                "source_tag": info.get("source_tag", ""),
                "balance": f"{display_balance:.4f}",
                "balance_raw": raw_balance_text,
                "amount_raw": raw_balance_text,
                "value_usd": _fmt_volume(value),
                "_value_raw": value,
                "price": _fmt_price(price),
                "avg_cost_usd": "N/A",
                "pnl": "N/A",
                "pnl_pct": "N/A",  # Would need cost basis; keep deliberate/neutral
                "pnl_positive": None,
            })

        # Sort by value descending using raw float to avoid suffix parsing errors
        holdings.sort(key=lambda h: h.get("_value_raw", 0), reverse=True)
        holdings = [
            row for row in holdings
            if _normalize_chain_name(row.get("chain"), "solana") == selected_chain
        ]
        total_usd = sum(float(row.get("_value_raw", 0) or 0) for row in holdings)
        cursor = _coerce_portfolio_cursor(state.get("portfolio_cursor", 0), len(holdings))
        if isinstance(selection_hint, dict):
            selected_idx = _portfolio_holding_index(
                holdings,
                selection_hint.get("addr", ""),
                selection_hint.get("chain", ""),
            )
            if selected_idx >= 0:
                cursor = selected_idx

        explanation_fields = _portfolio_explanation_fields("N/A")
        conn.loop.create_task(_send_display(conn, "portfolio", {
            "holdings": holdings,
            "cursor": cursor,
            "wallets": portfolio_wallets,
            "holding_source": holding_source,
            "chain_label": _surface_chain_label(selected_chain),
            "total_usd": _fmt_volume(total_usd),
            "pnl": "N/A",
            "pnl_pct": "N/A",
            **explanation_fields,
        }))
        state["portfolio_holdings"] = [
            {
                "addr": row.get("addr", ""),
                "chain": row.get("chain", ""),
                "symbol": row.get("symbol", ""),
            }
            for row in holdings
            if row.get("addr")
        ]
        state["portfolio_cursor"] = cursor

        return ActionResponse(action=Action.NONE, result=f"portfolio:{len(holdings)}tokens", response=None)

    except Exception as e:
        logger.bind(tag=TAG).error(f"ave_portfolio error: {e}")
        try:
            conn.loop.create_task(_send_display(conn, "notify", {
                "level": "error", "title": "Portfolio Lookup Failed", "body": str(e)[:60],
            }))
        except Exception:
            pass
        return ActionResponse(action=Action.RESPONSE, result=str(e), response="查询持仓失败，请稍后重试")


# ---------------------------------------------------------------------------
# Tool: ave_set_trade_mode
# ---------------------------------------------------------------------------

ave_set_trade_mode_desc = {
    "type": "function",
    "function": {
        "name": "ave_set_trade_mode",
        "description": "切换交易模式。real 为真实交易，paper 为模拟交易。切换后 Portfolio、Orders、后续交易确认都会跟随模式。",
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["real", "paper"],
                    "description": "目标交易模式"
                }
            },
            "required": ["mode"]
        }
    }
}


@register_function("ave_set_trade_mode", ave_set_trade_mode_desc, ToolType.SYSTEM_CTL)
def ave_set_trade_mode(conn: "ConnectionHandler", mode: str):
    try:
        normalized = _set_trade_mode(conn, mode)
        label = _trade_mode_label(normalized)
        return ActionResponse(
            action=Action.NONE,
            result=f"trade_mode:{normalized}",
            response=f"Switched to {label}."
        )
    except PaperStoreError as exc:
        logger.bind(tag=TAG).error(f"ave_set_trade_mode error: {exc}")
        return ActionResponse(
            action=Action.RESPONSE,
            result=str(exc),
            response="Failed to switch trading mode"
        )


# ---------------------------------------------------------------------------
# Tool: ave_confirm_trade  (voice "确认" on CONFIRM screen)
# ---------------------------------------------------------------------------

ave_confirm_trade_desc = {
    "type": "function",
    "function": {
        "name": "ave_confirm_trade",
        "description": "用户在确认买入页说'确认'/'确认购买'/'执行'时调用，执行当前待确认的交易",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


@register_function("ave_confirm_trade", ave_confirm_trade_desc, ToolType.SYSTEM_CTL)
def ave_confirm_trade(conn: "ConnectionHandler"):
    """通过 conn.ave_state 找到 pending trade_id 并确认执行"""
    pending = _get_pending_trade(conn)
    trade_id = pending.get("trade_id", "")
    symbol = pending.get("symbol", "TOKEN")
    trade_type = pending.get("trade_type", "")
    if not trade_id:
        return ActionResponse(action=Action.RESPONSE,
            result="no_pending", response="没有待确认的交易，请先发起一个交易")

    async def _do():
        result = await trade_mgr.confirm(trade_id)
        if _is_submit_only_ack(result, pending=pending):
            await _push_submit_ack_transition(conn, result, pending=pending)
            return
        payload = _build_result_payload(result, pending=pending)
        await _present_trade_result_or_defer(
            conn,
            payload,
            current_trade_id=trade_id,
        )
        _clear_pending_trade(conn, trade_id)

    conn.loop.create_task(_do())
    return ActionResponse(action=Action.NONE,
        result=f"正在执行{_label_trade_action(trade_type)}{symbol} [trade_id={trade_id}]", response=None)


# ---------------------------------------------------------------------------
# Tool: ave_cancel_trade  (voice "取消" on CONFIRM screen)
# ---------------------------------------------------------------------------

ave_cancel_trade_desc = {
    "type": "function",
    "function": {
        "name": "ave_cancel_trade",
        "description": "用户在确认买入页说'取消'/'算了'/'不买了'时调用，取消当前待确认的交易并返回",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


@register_function("ave_cancel_trade", ave_cancel_trade_desc, ToolType.SYSTEM_CTL)
def ave_cancel_trade(conn: "ConnectionHandler"):
    """取消 pending trade，并恢复到发起交易前的页面。"""
    pending = _get_pending_trade(conn)
    trade_id = pending.get("trade_id", "")
    symbol = pending.get("symbol", "TOKEN")
    trade_type = pending.get("trade_type", "")
    if trade_id:
        trade_mgr.cancel(trade_id)
    state = _ensure_ave_state(conn)
    state.pop("deferred_result_queue", None)
    _clear_pending_trade(conn, trade_id)
    restore_resp = _restore_cancel_target(conn, pending)
    if isinstance(restore_resp, ActionResponse) and restore_resp.action != Action.NONE:
        return restore_resp
    return ActionResponse(action=Action.NONE,
        result=f"已取消{_label_trade_action(trade_type)}{symbol}，已恢复上一页", response=None)


# ---------------------------------------------------------------------------
# Tool: ave_back_to_feed  (voice "返回"/"回到首页")
# ---------------------------------------------------------------------------

ave_back_to_feed_desc = {
    "type": "function",
    "function": {
        "name": "ave_back_to_feed",
        "description": "用户说'返回'/'回去'/'首页'/'回到热门'时调用，返回热门代币列表",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


@register_function("ave_back_to_feed", ave_back_to_feed_desc, ToolType.SYSTEM_CTL)
def ave_back_to_feed(conn: "ConnectionHandler"):
    """返回 FEED 屏幕"""
    state = _ensure_ave_state(conn)
    pending = _get_pending_trade(conn)
    if pending.get("trade_id") and state.get("screen") in {"confirm", "limit_confirm"}:
        return ave_cancel_trade(conn)

    refresh_resp = _refresh_home_feed(conn)
    if isinstance(refresh_resp, ActionResponse) and refresh_resp.action != Action.NONE:
        return refresh_resp
    return ActionResponse(action=Action.NONE, result="已返回热门列表", response=None)
