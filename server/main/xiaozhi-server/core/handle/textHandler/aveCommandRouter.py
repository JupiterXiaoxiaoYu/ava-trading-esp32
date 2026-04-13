import json
import re
from typing import TYPE_CHECKING, Any, Dict, Optional

from config.logger import setup_logging
from core.handle.sendAudioHandle import send_stt_message
from core.utils.util import remove_punctuation_and_length
from plugins_func.register import Action

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

_FEED_COMMANDS = {"看热门", "刷新热门", "热门代币"}
_PORTFOLIO_COMMANDS = {"我的持仓", "持仓"}
_OPEN_WATCHLIST_COMMANDS = {"打开观察列表", "查看观察列表", "观察列表", "watchlist"}
_OPEN_ORDERS_COMMANDS = {
    "查看限价单",
    "查看挂单",
    "我的挂单",
    "挂单",
    "openorders",
    "pendingorders",
}
_WATCH_CURRENT_COMMANDS = {"看这个", "详情", "进入"}
_BUY_CURRENT_COMMANDS = {"买这个"}
_ADD_WATCHLIST_COMMANDS = {"收藏这个币", "加入观察列表", "收藏它"}
_REMOVE_WATCHLIST_COMMANDS = {"取消收藏", "从观察列表移除", "移除这个币"}
_CONFIRM_COMMANDS = {"确认", "确认购买", "执行"}
_CANCEL_COMMANDS = {"取消", "算了", "不买了"}
_BACK_COMMANDS = {"返回", "回去", "首页", "回到热门"}
_CONFIRM_SCREENS = {"confirm", "limit_confirm"}
_DEICTIC_MARKERS = ("这个", "这只", "这币", "它")
_DEICTIC_RISK_KEYWORDS = (
    "买",
    "能买吗",
    "能不能买",
    "分析",
    "详情",
    "介绍",
    "风险",
    "涨",
    "跌",
    "走势",
    "价格",
)
_DEICTIC_RISK_PHRASES = {
    "这个怎么样",
    "帮我分析这个",
    "分析这个",
    "看看这个",
    "看下这个",
    "给我讲讲这个",
    "讲讲这个",
    "说说这个",
    "聊聊这个",
    "这个如何",
    "给我讲讲它",
    "说说它",
    "聊聊它",
}
_OPEN_ENDED_DEICTIC_PATTERN = re.compile(
    r"(?:(?:给我讲讲|讲讲|说说|聊聊|看看|看下|分析)(?:这只币|这币|它)|(?:这只币|这币|它)(?:怎么样|如何))"
)
_SELECTION_GUARDED_SCREENS = {"feed", "browse", "portfolio", "spotlight", "confirm", "limit_confirm"}

_WATCH_SYMBOL_PATTERN = re.compile(r"^(?:看|看看)([A-Za-z][A-Za-z0-9._-]{1,15})$")
_SEARCH_SYMBOL_PATTERN = re.compile(
    r"^(?:搜索|搜一下|搜|查找|查一下|查|search|find|lookup)([A-Za-z][A-Za-z0-9._-]{1,63})$",
    re.IGNORECASE,
)
_BUY_SYMBOL_PATTERN = re.compile(r"^买([A-Za-z][A-Za-z0-9._-]{1,15})$")
_BUY_SYMBOL_FUZZY_PATTERN = re.compile(
    r"(?:买|买入|购买|buy|purchase)\s*([A-Za-z][A-Za-z0-9._-]{1,15})",
    re.IGNORECASE,
)
_LIMIT_SYMBOL_FUZZY_PATTERN = re.compile(
    r"(?:限价买|限价|挂单买|挂买单|limit\s*buy)\s*([A-Za-z][A-Za-z0-9._-]{1,15})",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(r"(\d+(?:\.\d+)?)")
_PRICE_PATTERNS = (
    re.compile(r"(?:价格|价位|price)\s*(?:到|是|为|=)?\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"(?:跌到|到价|到|低于|小于|below)\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
)
_AMOUNT_PATTERNS = (
    re.compile(r"(?:用|拿|花|投入|买入金额|金额)\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:买|买入|购买|buy|purchase)", re.IGNORECASE),
    re.compile(r"(?:买|买入|购买|buy|purchase)\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
)
_LIMIT_INTENT_MARKERS = ("限价", "挂单", "limit")
_BUY_INTENT_MARKERS = ("买", "买入", "购买", "buy", "purchase")
_PRICE_MARKERS = ("价格", "价位", "price", "跌到", "到价", "低于", "小于", "below")
_CHAIN_NATIVE_SYMBOLS = {
    "solana": "SOL",
    "eth": "ETH",
    "base": "ETH",
    "bsc": "BNB",
}
_CHAIN_NATIVE_ALIASES = {
    "solana": ("sol",),
    "eth": ("eth",),
    "base": ("eth",),
    "bsc": ("bnb",),
}


def _extract_utterance_text(raw_text: str) -> str:
    if not isinstance(raw_text, str):
        return ""

    text = raw_text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            payload = json.loads(text)
            if isinstance(payload, dict) and isinstance(payload.get("content"), str):
                return payload["content"].strip()
        except (json.JSONDecodeError, TypeError):
            pass
    return text


def _normalize_utterance(raw_text: str) -> str:
    _, normalized = remove_punctuation_and_length(raw_text or "")
    return normalized.strip()


def _normalize_token(entry: Any, *, require_chain: bool = False) -> Optional[Dict[str, str]]:
    if not isinstance(entry, dict):
        return None

    addr = str(entry.get("addr") or "").strip()
    if not addr:
        return None

    chain = str(entry.get("chain") or "").strip()
    if require_chain and not chain:
        return None
    if not chain:
        chain = "solana"
    symbol = str(entry.get("symbol") or "").strip()
    return {"addr": addr, "chain": chain, "symbol": symbol}


def _extract_selection_payload(message_payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(message_payload, dict):
        return None
    selection = message_payload.get("selection")
    return selection if isinstance(selection, dict) else None


def _normalize_token_with_alias(
    entry: Any,
    *,
    require_chain: bool = False,
) -> Optional[Dict[str, str]]:
    if not isinstance(entry, dict):
        return None

    normalized_entry = dict(entry)
    if not normalized_entry.get("addr"):
        token_id = normalized_entry.get("token_id")
        if token_id:
            normalized_entry["addr"] = token_id
    return _normalize_token(normalized_entry, require_chain=require_chain)


def _resolve_selection_token(selection_payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    if not isinstance(selection_payload, dict):
        return None

    for key in ("token", "holding", "current"):
        token = _normalize_token_with_alias(
            selection_payload.get(key),
            require_chain=True,
        )
        if token:
            return token

    return _normalize_token_with_alias(selection_payload, require_chain=True)


def _extract_selection_screen(selection_payload: Optional[Dict[str, Any]]) -> str:
    if not isinstance(selection_payload, dict):
        return ""
    return str(selection_payload.get("screen") or "").strip()


def _resolve_effective_screen(
    state_screen: str, selection_payload: Optional[Dict[str, Any]]
) -> str:
    selection_screen = _extract_selection_screen(selection_payload)
    if selection_screen:
        return selection_screen
    return state_screen


def _screen_uses_feed_selection(screen: str) -> bool:
    return screen in {"feed", "browse"}


def _resolve_effective_feed_cursor(
    state_cursor: Any, selection_payload: Optional[Dict[str, Any]]
) -> Any:
    if not _screen_uses_feed_selection(_extract_selection_screen(selection_payload)):
        return state_cursor

    if isinstance(selection_payload, dict) and "cursor" in selection_payload:
        cursor = selection_payload.get("cursor")
        if cursor is not None:
            return cursor
    return state_cursor


def _resolve_selection_feed_nav(
    state: Dict[str, Any],
    selection_payload: Optional[Dict[str, Any]],
    token: Optional[Dict[str, str]],
) -> tuple[Optional[int], Optional[int]]:
    if not _screen_uses_feed_selection(_extract_selection_screen(selection_payload)):
        return None, None

    feed_rows = state.get("feed_token_list")
    if not isinstance(feed_rows, list) or not feed_rows:
        return None, None
    feed_total = len(feed_rows)

    cursor = None
    if isinstance(selection_payload, dict) and selection_payload.get("cursor") is not None:
        try:
            cursor = int(selection_payload.get("cursor"))
        except (TypeError, ValueError):
            cursor = None
    if cursor is None:
        try:
            cursor = int(state.get("feed_cursor", 0))
        except (TypeError, ValueError):
            cursor = 0
    cursor = max(0, min(cursor, feed_total - 1))

    if token:
        try:
            row = feed_rows[cursor]
        except IndexError:
            row = None
        row_addr = str(row.get("addr") or "").strip() if isinstance(row, dict) else ""
        row_chain = str(row.get("chain") or "").strip() if isinstance(row, dict) else ""
        if row_addr != token.get("addr") or row_chain != token.get("chain"):
            for idx, entry in enumerate(feed_rows):
                if not isinstance(entry, dict):
                    continue
                if (
                    str(entry.get("addr") or "").strip() == token.get("addr")
                    and str(entry.get("chain") or "").strip() == token.get("chain")
                ):
                    cursor = idx
                    break

    state["feed_cursor"] = cursor
    if str(state.get("feed_mode") or "") == "search":
        state["search_cursor"] = cursor
    return cursor, feed_total


def has_trusted_selection(selection_payload: Optional[Dict[str, Any]]) -> bool:
    return bool(_extract_selection_screen(selection_payload)) and _resolve_selection_token(
        selection_payload
    ) is not None


def missing_selection_reply(_: str = "") -> str:
    return "请先在界面上选中你要操作的代币，然后再说一次。"


def requires_trusted_selection(
    raw_text: str, ave_context: Optional[Dict[str, Any]] = None
) -> bool:
    utterance = _extract_utterance_text(raw_text)
    normalized = _normalize_utterance(utterance)

    if (
        normalized in _WATCH_CURRENT_COMMANDS
        or normalized in _BUY_CURRENT_COMMANDS
        or normalized in _ADD_WATCHLIST_COMMANDS
        or normalized in _REMOVE_WATCHLIST_COMMANDS
    ):
        return True
    if normalized in _DEICTIC_RISK_PHRASES:
        return True

    if not any(marker in utterance for marker in _DEICTIC_MARKERS):
        return False

    if _OPEN_ENDED_DEICTIC_PATTERN.search(utterance):
        return True

    return any(keyword in utterance or keyword in normalized for keyword in _DEICTIC_RISK_KEYWORDS)


def _resolve_pending_trade(state: Dict[str, Any]) -> Dict[str, Any]:
    pending_trade = state.get("pending_trade")
    if isinstance(pending_trade, dict) and pending_trade.get("trade_id"):
        return dict(pending_trade)

    trade_id = state.get("pending_trade_id")
    if not trade_id:
        return {}

    return {
        "trade_id": str(trade_id),
        "trade_type": "",
        "action": "TRADE",
        "symbol": state.get("pending_symbol", "TOKEN"),
        "amount_native": "",
        "amount_usd": "",
    }


def _resolve_symbol_entry(state: Dict[str, Any], symbol: str) -> Optional[Dict[str, str]]:
    normalized_symbol = symbol.upper()

    symbol_entries = state.get("feed_symbol_entries")
    if isinstance(symbol_entries, dict):
        normalized_matches = []
        seen = set()
        for entry in symbol_entries.get(normalized_symbol, []):
            token = _normalize_token(entry)
            if not token:
                continue
            token_key = (token["addr"], token["chain"])
            if token_key in seen:
                continue
            seen.add(token_key)
            normalized_matches.append(token)
        if len(normalized_matches) == 1:
            token = normalized_matches[0]
            token["symbol"] = normalized_symbol
            return token
        if len(normalized_matches) > 1:
            return None

    feed_tokens = state.get("feed_tokens")
    if not isinstance(feed_tokens, dict):
        return None

    entry = feed_tokens.get(normalized_symbol)
    token = _normalize_token(entry)
    if token:
        token["symbol"] = normalized_symbol
    return token


def _chain_native_symbol(chain: str) -> str:
    return _CHAIN_NATIVE_SYMBOLS.get(str(chain or "").strip().lower(), "NATIVE")


def _parse_numeric_text(raw_value: str) -> Optional[float]:
    try:
        return float(str(raw_value).strip())
    except (TypeError, ValueError):
        return None


def _extract_symbol_hint(utterance: str, state: Dict[str, Any]) -> str:
    for pattern in (_LIMIT_SYMBOL_FUZZY_PATTERN, _BUY_SYMBOL_FUZZY_PATTERN):
        match = pattern.search(utterance or "")
        if match:
            return str(match.group(1) or "").strip().upper()

    current_token = state.get("current_token")
    current_symbol = ""
    if isinstance(current_token, dict):
        current_symbol = str(current_token.get("symbol") or "").strip().upper()

    candidate_symbols = []
    if current_symbol:
        candidate_symbols.append(current_symbol)
    candidate_symbols.extend(_collect_feed_symbols(state))

    seen = set()
    for symbol in candidate_symbols:
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol or normalized_symbol in seen:
            continue
        seen.add(normalized_symbol)
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(normalized_symbol)}(?![A-Za-z0-9])", utterance or "", re.IGNORECASE):
            return normalized_symbol

    return ""


def _resolve_voice_trade_token(
    state: Dict[str, Any],
    selection_payload: Optional[Dict[str, Any]],
    effective_screen: str,
    symbol_hint: str = "",
) -> Optional[Dict[str, str]]:
    token = _resolve_selection_token(selection_payload) if has_trusted_selection(selection_payload) else None
    if token:
        if symbol_hint and not token.get("symbol"):
            token["symbol"] = symbol_hint
        return token

    if symbol_hint:
        symbol_token = _resolve_symbol_entry(state, symbol_hint)
        if symbol_token:
            symbol_token["symbol"] = symbol_hint
            return symbol_token

    if effective_screen in {"spotlight", "confirm", "limit_confirm"}:
        current_token = _normalize_token(state.get("current_token"))
        if current_token:
            if symbol_hint and not current_token.get("symbol"):
                current_token["symbol"] = symbol_hint
            return current_token

    return None


def _extract_amount_value(utterance: str, chain: str, *, follow_up_only: bool = False) -> tuple[Optional[float], Optional[str]]:
    lowered = str(utterance or "").lower()
    aliases = _CHAIN_NATIVE_ALIASES.get(str(chain or "").strip().lower(), ())
    alias_match = re.search(r"(\d+(?:\.\d+)?)\s*([A-Za-z]{2,4})", lowered)
    if alias_match:
        amount = _parse_numeric_text(alias_match.group(1))
        unit = alias_match.group(2)
        if amount is not None:
            if unit in aliases:
                return amount, None
            if unit in {"sol", "eth", "bnb"}:
                return None, f"这条链下单金额请用 {_chain_native_symbol(chain)} 表示。"

    for pattern in _AMOUNT_PATTERNS:
        match = pattern.search(utterance or "")
        if match:
            amount = _parse_numeric_text(match.group(1))
            if amount is not None:
                return amount, None

    if follow_up_only and not any(marker in lowered for marker in _PRICE_MARKERS):
        numbers = _NUMBER_PATTERN.findall(utterance or "")
        if len(numbers) == 1:
            amount = _parse_numeric_text(numbers[0])
            if amount is not None:
                return amount, None

    return None, None


def _extract_limit_price_value(utterance: str, *, follow_up_only: bool = False) -> Optional[float]:
    for pattern in _PRICE_PATTERNS:
        match = pattern.search(utterance or "")
        if match:
            price = _parse_numeric_text(match.group(1))
            if price is not None:
                return price

    if follow_up_only:
        numbers = _NUMBER_PATTERN.findall(utterance or "")
        if len(numbers) == 1:
            return _parse_numeric_text(numbers[0])

    return None


def _voice_trade_missing_field(draft: Dict[str, Any]) -> str:
    token_known = bool(str(draft.get("addr") or "").strip())
    if not token_known:
        return "token"
    if draft.get("kind") == "limit_buy":
        if draft.get("limit_price") is None:
            return "limit_price"
        if draft.get("in_amount_sol") is None:
            return "amount"
    return ""


def _build_voice_trade_prompt(draft: Dict[str, Any]) -> str:
    chain = str(draft.get("chain") or "solana")
    native_symbol = _chain_native_symbol(chain)
    missing_field = _voice_trade_missing_field(draft)
    if missing_field == "token":
        return "你想买哪个币？先说代币名，或者先进入详情页再说买这个。"
    if missing_field == "limit_price":
        return "目标价是多少美元？比如说 0.00012。"
    if missing_field == "amount":
        return f"你想用多少 {native_symbol} 买入？比如说 0.1 {native_symbol}。"
    return ""


def _build_voice_trade_draft(
    *,
    kind: str,
    token: Optional[Dict[str, str]],
    in_amount_sol: Optional[float] = None,
    limit_price: Optional[float] = None,
) -> Dict[str, Any]:
    token = token or {}
    return {
        "kind": kind,
        "addr": str(token.get("addr") or "").strip(),
        "chain": str(token.get("chain") or "solana").strip() or "solana",
        "symbol": str(token.get("symbol") or "").strip(),
        "in_amount_sol": in_amount_sol,
        "limit_price": limit_price,
    }


async def _continue_voice_trade_draft(
    conn: "ConnectionHandler",
    utterance: str,
    normalized: str,
    state: Dict[str, Any],
    selection_payload: Optional[Dict[str, Any]],
    effective_screen: str,
    ave_tools: Any,
) -> bool:
    draft = state.get("voice_trade_draft")
    if not isinstance(draft, dict) or not draft.get("kind"):
        return False

    if normalized in (
        _FEED_COMMANDS
        | _PORTFOLIO_COMMANDS
        | _OPEN_WATCHLIST_COMMANDS
        | _OPEN_ORDERS_COMMANDS
        | _WATCH_CURRENT_COMMANDS
    ):
        state.pop("voice_trade_draft", None)
        return False

    if normalized in _CANCEL_COMMANDS or normalized in _BACK_COMMANDS:
        state.pop("voice_trade_draft", None)
        await _send_router_reply(conn, "已取消这次语音下单。")
        return True

    current_missing = _voice_trade_missing_field(draft)
    symbol_hint = _extract_symbol_hint(utterance, state)
    token = _resolve_voice_trade_token(state, selection_payload, effective_screen, symbol_hint)
    if token:
        draft["addr"] = token.get("addr", "")
        draft["chain"] = token.get("chain", draft.get("chain", "solana"))
        draft["symbol"] = token.get("symbol") or draft.get("symbol", "")

    next_missing = _voice_trade_missing_field(draft)

    if next_missing == "limit_price":
        draft["limit_price"] = _extract_limit_price_value(utterance, follow_up_only=True)

    should_parse_amount = (
        next_missing == "amount"
        or (draft.get("kind") == "market_buy" and current_missing in {"token", "amount"})
    )
    if should_parse_amount and draft.get("in_amount_sol") is None:
        amount_value, amount_error = _extract_amount_value(
            utterance,
            draft.get("chain", "solana"),
            follow_up_only=True,
        )
        if amount_error:
            await _send_router_reply(conn, amount_error)
            return True
        if amount_value is not None:
            draft["in_amount_sol"] = amount_value

    missing_field = _voice_trade_missing_field(draft)
    if missing_field:
        state["voice_trade_draft"] = draft
        await _send_router_reply(conn, _build_voice_trade_prompt(draft))
        return True

    state.pop("voice_trade_draft", None)
    symbol = draft.get("symbol", "")
    if draft.get("kind") == "limit_buy":
        await _handle_tool_response(
            conn,
            ave_tools.ave_limit_order(
                conn,
                addr=draft["addr"],
                chain=draft["chain"],
                in_amount_sol=draft["in_amount_sol"],
                limit_price=draft["limit_price"],
                symbol=symbol,
            ),
        )
        return True

    buy_kwargs = {
        "addr": draft["addr"],
        "chain": draft["chain"],
        "symbol": symbol,
    }
    if draft.get("in_amount_sol") is not None:
        buy_kwargs["in_amount_sol"] = draft.get("in_amount_sol")
    await _handle_tool_response(conn, ave_tools.ave_buy_token(conn, **buy_kwargs))
    return True


async def _try_route_voice_trade_intent(
    conn: "ConnectionHandler",
    utterance: str,
    normalized: str,
    state: Dict[str, Any],
    selection_payload: Optional[Dict[str, Any]],
    effective_screen: str,
    ave_tools: Any,
) -> bool:
    lowered = str(utterance or "").lower()
    has_limit_intent = any(marker in lowered for marker in _LIMIT_INTENT_MARKERS)
    has_buy_intent = any(marker in lowered for marker in _BUY_INTENT_MARKERS)
    if not has_buy_intent:
        return False

    symbol_hint = _extract_symbol_hint(utterance, state)
    token = _resolve_voice_trade_token(state, selection_payload, effective_screen, symbol_hint)
    chain = token.get("chain", "solana") if token else "solana"

    if has_limit_intent:
        limit_price = _extract_limit_price_value(utterance)
        amount_value, amount_error = _extract_amount_value(utterance, chain)
        if amount_error:
            await _send_router_reply(conn, amount_error)
            return True
        draft = _build_voice_trade_draft(
            kind="limit_buy",
            token=token,
            in_amount_sol=amount_value,
            limit_price=limit_price,
        )
        missing_field = _voice_trade_missing_field(draft)
        if missing_field:
            state["voice_trade_draft"] = draft
            await _send_router_reply(conn, _build_voice_trade_prompt(draft))
            return True

        await _handle_tool_response(
            conn,
            ave_tools.ave_limit_order(
                conn,
                addr=draft["addr"],
                chain=draft["chain"],
                in_amount_sol=draft["in_amount_sol"],
                limit_price=draft["limit_price"],
                symbol=draft.get("symbol", ""),
            ),
        )
        return True

    amount_value, amount_error = _extract_amount_value(utterance, chain)
    if amount_error:
        await _send_router_reply(conn, amount_error)
        return True
    if amount_value is None and not any(marker in lowered for marker in _PRICE_MARKERS):
        numbers = _NUMBER_PATTERN.findall(utterance or "")
        if len(numbers) == 1:
            amount_value = _parse_numeric_text(numbers[0])

    if not token:
        draft = _build_voice_trade_draft(
            kind="market_buy",
            token=None,
            in_amount_sol=amount_value,
        )
        state["voice_trade_draft"] = draft
        await _send_router_reply(conn, _build_voice_trade_prompt(draft))
        return True

    buy_kwargs = {
        "addr": token["addr"],
        "chain": token["chain"],
        "symbol": token.get("symbol", ""),
    }
    if amount_value is not None:
        buy_kwargs["in_amount_sol"] = amount_value
    await _handle_tool_response(conn, ave_tools.ave_buy_token(conn, **buy_kwargs))
    return True


def _collect_feed_symbols(state: Dict[str, Any]) -> list[str]:
    token_list = state.get("feed_token_list")
    if isinstance(token_list, list):
        symbols: list[str] = []
        for token in token_list:
            if isinstance(token, dict):
                symbol = str(token.get("symbol") or "").strip().upper()
                if symbol and symbol not in symbols:
                    symbols.append(symbol)
        return symbols

    feed_tokens = state.get("feed_tokens")
    symbols = []
    if isinstance(feed_tokens, dict):
        for symbol in feed_tokens.keys():
            sym = str(symbol).strip().upper()
            if sym and sym not in symbols:
                symbols.append(sym)

    return symbols


def _compact_surface_row(row: Dict[str, Any]) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    for key in (
        "addr",
        "chain",
        "symbol",
        "price",
        "change_24h",
        "headline",
        "value_usd",
        "pnl",
        "amount",
        "signal_summary",
    ):
        value = row.get(key)
        if value not in (None, "", []):
            compact[key] = value
    return compact


def _build_screen_snapshot(
    state: Dict[str, Any],
    screen: str,
    selection_payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {"screen": screen}

    if screen in {"feed", "browse", "disambiguation"}:
        rows = state.get("feed_token_list")
        if isinstance(rows, list):
            cursor = _resolve_effective_feed_cursor(
                state.get("feed_cursor", 0), selection_payload
            )
            total = len(rows)
            if total:
                cursor = max(0, min(cursor, total - 1))
                snapshot["cursor"] = cursor
                snapshot["total"] = total
                snapshot["selected_row"] = _compact_surface_row(rows[cursor])
                snapshot["visible_rows"] = [
                    _compact_surface_row(row)
                    for row in rows[:12]
                    if isinstance(row, dict)
                ]
        feed_mode = str(state.get("feed_mode") or "").strip()
        feed_source = str(state.get("feed_source") or "").strip()
        feed_platform = str(state.get("feed_platform") or "").strip()
        if feed_mode:
            snapshot["mode"] = feed_mode
        if feed_source:
            snapshot["source"] = feed_source
        if feed_platform:
            snapshot["platform"] = feed_platform
        search_query = str(state.get("search_query") or "").strip()
        if search_query:
            snapshot["search_query"] = search_query
        return snapshot

    if screen == "portfolio":
        holdings = state.get("portfolio_holdings")
        if isinstance(holdings, list):
            cursor = state.get("portfolio_cursor", 0)
            if isinstance(selection_payload, dict) and selection_payload.get("screen") == "portfolio":
                cursor = selection_payload.get("cursor", cursor)
            try:
                cursor = int(cursor)
            except (TypeError, ValueError):
                cursor = 0
            total = len(holdings)
            if total:
                cursor = max(0, min(cursor, total - 1))
                snapshot["cursor"] = cursor
                snapshot["total"] = total
                snapshot["selected_row"] = _compact_surface_row(holdings[cursor])
                snapshot["visible_rows"] = [
                    _compact_surface_row(row)
                    for row in holdings[:12]
                    if isinstance(row, dict)
                ]
        return snapshot

    if screen == "spotlight":
        spotlight = state.get("spotlight_snapshot")
        if isinstance(spotlight, dict):
            for key in (
                "symbol",
                "chain",
                "addr",
                "pair",
                "price",
                "change_24h",
                "market_cap",
                "volume_24h",
                "liquidity",
                "holders",
                "top100_concentration",
                "risk_level",
                "is_watchlisted",
                "origin_hint",
                "cursor",
                "total",
            ):
                value = spotlight.get(key)
                if value not in (None, "", []):
                    snapshot[key] = value
        current = state.get("current_token")
        if isinstance(current, dict):
            for key in ("addr", "chain", "symbol"):
                value = current.get(key)
                if value not in (None, "") and key not in snapshot:
                    snapshot[key] = value
        return snapshot

    if screen in {"confirm", "limit_confirm", "result"}:
        pending = _resolve_pending_trade(state)
        if pending:
            snapshot["pending_trade"] = pending
        return snapshot

    return snapshot


def _build_allowed_actions(
    screen: str,
    current_token: Optional[Dict[str, str]],
    pending_trade: Dict[str, Any],
    has_trusted_selection: bool,
) -> list[str]:
    actions = {"search_symbol"}

    actions.add("open_watchlist")
    if screen in {"feed", "browse", "portfolio", "spotlight"} and current_token and has_trusted_selection:
        actions.add("watch_current")
    if screen == "spotlight" and current_token and has_trusted_selection:
        actions.add("buy_current")
        actions.add("add_to_watchlist")
        actions.add("remove_from_watchlist")
    if screen in {"confirm", "limit_confirm"} and pending_trade.get("trade_id"):
        actions.add("confirm_trade")
        actions.add("cancel_trade")

    actions.add("back_to_feed")
    actions.add("open_feed")
    actions.add("open_portfolio")

    return sorted(actions)


def build_ave_context(
    conn: "ConnectionHandler",
    selection_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    state = getattr(conn, "ave_state", {})
    if not isinstance(state, dict):
        state = {}

    screen = _resolve_effective_screen(str(state.get("screen") or ""), selection_payload)
    trusted_selection = has_trusted_selection(selection_payload)
    explicit_token = _resolve_selection_token(selection_payload) if trusted_selection else None
    current_token = explicit_token
    pending_trade = _resolve_pending_trade(state)
    feed_visible_symbols = _collect_feed_symbols(state)
    feed_cursor = _resolve_effective_feed_cursor(state.get("feed_cursor", 0), selection_payload)
    screen_snapshot = _build_screen_snapshot(state, screen, selection_payload)

    return {
        "screen": screen,
        "nav_from": str(state.get("nav_from") or ""),
        "current_token": current_token,
        "has_trusted_selection": trusted_selection,
        "selection_source": "explicit" if trusted_selection else "",
        "pending_trade": pending_trade,
        "feed_source": str(state.get("feed_source") or ""),
        "feed_platform": str(state.get("feed_platform") or ""),
        "feed_cursor": feed_cursor,
        "feed_visible_symbols": feed_visible_symbols,
        "screen_snapshot": screen_snapshot,
        "allowed_actions": _build_allowed_actions(
            screen,
            current_token,
            pending_trade,
            trusted_selection,
        ),
    }


async def _send_router_reply(conn: "ConnectionHandler", text: str) -> None:
    if text:
        await send_stt_message(conn, text)


async def _handle_tool_response(conn: "ConnectionHandler", response: Any) -> None:
    if not response:
        return

    if response.action == Action.RESPONSE and response.response:
        await _send_router_reply(conn, response.response)


async def _cancel_pending_trade_for_exit(
    conn: "ConnectionHandler",
    state: Dict[str, Any],
    screen: str,
    ave_tools: Any,
) -> None:
    if screen not in _CONFIRM_SCREENS:
        return

    pending_trade = _resolve_pending_trade(state)
    if not pending_trade.get("trade_id"):
        return

    await _handle_tool_response(conn, ave_tools.ave_cancel_trade(conn))


async def try_route_ave_command(
    conn: "ConnectionHandler",
    raw_text: str,
    message_payload: Optional[Dict[str, Any]] = None,
) -> bool:
    utterance = _extract_utterance_text(raw_text)
    normalized = _normalize_utterance(utterance)
    selection_payload = _extract_selection_payload(message_payload)

    # Always refresh context so open-ended LLM handoff can reuse the same schema.
    conn.ave_context = build_ave_context(conn, selection_payload=selection_payload)

    def _refresh_turn_context() -> None:
        conn.ave_context = build_ave_context(conn, selection_payload=selection_payload)

    if not normalized:
        return False

    from plugins_func.functions import ave_tools

    state = getattr(conn, "ave_state", {})
    if not isinstance(state, dict):
        state = {}

    state_screen = str(state.get("screen") or "")
    effective_screen = _resolve_effective_screen(state_screen, selection_payload)

    if await _continue_voice_trade_draft(
        conn,
        utterance,
        normalized,
        state,
        selection_payload,
        effective_screen,
        ave_tools,
    ):
        _refresh_turn_context()
        return True

    if normalized in _FEED_COMMANDS:
        await _cancel_pending_trade_for_exit(conn, state, effective_screen, ave_tools)
        await _handle_tool_response(conn, ave_tools.ave_get_trending(conn))
        _refresh_turn_context()
        return True

    if normalized in _PORTFOLIO_COMMANDS:
        await _cancel_pending_trade_for_exit(conn, state, effective_screen, ave_tools)
        await _handle_tool_response(conn, ave_tools.ave_portfolio(conn))
        _refresh_turn_context()
        return True

    if normalized in _OPEN_WATCHLIST_COMMANDS:
        await _cancel_pending_trade_for_exit(conn, state, effective_screen, ave_tools)
        await _handle_tool_response(conn, ave_tools.ave_open_watchlist(conn))
        _refresh_turn_context()
        return True

    if normalized in _OPEN_ORDERS_COMMANDS:
        await _cancel_pending_trade_for_exit(conn, state, effective_screen, ave_tools)
        await _handle_tool_response(conn, ave_tools.ave_list_orders(conn))
        _refresh_turn_context()
        return True

    if normalized in _WATCH_CURRENT_COMMANDS:
        token = _resolve_selection_token(selection_payload) if has_trusted_selection(selection_payload) else None
        if not token:
            await _send_router_reply(conn, missing_selection_reply(utterance))
            return True
        if effective_screen == "portfolio":
            state["nav_from"] = "portfolio"
        elif (
            effective_screen == "browse"
            and (str(state.get("feed_mode") or "") == "signals" or str(state.get("feed_source") or "") == "signals")
        ):
            state["nav_from"] = "signals"
        elif (
            effective_screen == "browse"
            and (str(state.get("feed_mode") or "") == "watchlist" or str(state.get("feed_source") or "") == "watchlist")
        ):
            state["nav_from"] = "watchlist"
        elif effective_screen in {"feed", "browse", "disambiguation"}:
            state["nav_from"] = "feed"
        feed_cursor, feed_total = _resolve_selection_feed_nav(state, selection_payload, token)
        await _handle_tool_response(
            conn,
            ave_tools.ave_token_detail(
                conn,
                addr=token["addr"],
                chain=token["chain"],
                symbol=token.get("symbol", ""),
                feed_cursor=feed_cursor,
                feed_total=feed_total,
            ),
        )
        _refresh_turn_context()
        return True

    if normalized in _BUY_CURRENT_COMMANDS:
        token = _resolve_selection_token(selection_payload) if has_trusted_selection(selection_payload) else None
        if not token:
            await _send_router_reply(conn, missing_selection_reply(utterance))
            return True
        if effective_screen != "spotlight":
            await _send_router_reply(conn, "请先进入代币详情页，再说买这个。")
            return True
        await _handle_tool_response(
            conn,
            ave_tools.ave_buy_token(
                conn,
                addr=token["addr"],
                chain=token["chain"],
                symbol=token.get("symbol", ""),
            ),
        )
        _refresh_turn_context()
        return True

    if normalized in _ADD_WATCHLIST_COMMANDS:
        token = _resolve_selection_token(selection_payload) if has_trusted_selection(selection_payload) else None
        if not token:
            await _send_router_reply(conn, missing_selection_reply(utterance))
            return True
        if effective_screen != "spotlight":
            await _send_router_reply(conn, "请先进入代币详情页，再说收藏这个币。")
            return True
        await _handle_tool_response(conn, ave_tools.ave_add_current_watchlist_token(conn, token=token))
        _refresh_turn_context()
        return True

    if normalized in _REMOVE_WATCHLIST_COMMANDS:
        token = _resolve_selection_token(selection_payload) if has_trusted_selection(selection_payload) else None
        if not token:
            await _send_router_reply(conn, missing_selection_reply(utterance))
            return True
        if effective_screen != "spotlight":
            await _send_router_reply(conn, "请先进入代币详情页，再说取消收藏。")
            return True
        await _handle_tool_response(conn, ave_tools.ave_remove_current_watchlist_voice(conn, token=token))
        _refresh_turn_context()
        return True

    if normalized in _CONFIRM_COMMANDS:
        if effective_screen not in _CONFIRM_SCREENS:
            await _send_router_reply(conn, "当前不在交易确认页。")
            return True
        pending_trade = _resolve_pending_trade(state)
        if not pending_trade.get("trade_id"):
            await _send_router_reply(conn, "当前没有待确认的交易。")
            return True
        await _handle_tool_response(conn, ave_tools.ave_confirm_trade(conn))
        _refresh_turn_context()
        return True

    if normalized in _CANCEL_COMMANDS:
        if effective_screen not in _CONFIRM_SCREENS:
            await _send_router_reply(conn, "当前不在交易确认页。")
            return True
        pending_trade = _resolve_pending_trade(state)
        if not pending_trade.get("trade_id"):
            await _send_router_reply(conn, "当前没有待取消的交易。")
            return True
        await _handle_tool_response(conn, ave_tools.ave_cancel_trade(conn))
        _refresh_turn_context()
        return True

    if normalized in _BACK_COMMANDS:
        if effective_screen in _CONFIRM_SCREENS:
            await _handle_tool_response(conn, ave_tools.ave_cancel_trade(conn))
            _refresh_turn_context()
            return True

        nav_from = str(state.pop("nav_from", "") or "")
        if nav_from == "portfolio":
            await _handle_tool_response(conn, ave_tools.ave_portfolio(conn))
        elif nav_from == "signals":
            await _handle_tool_response(conn, ave_tools.ave_list_signals(conn))
        elif nav_from == "watchlist":
            await _handle_tool_response(
                conn,
                ave_tools.ave_open_watchlist(conn, cursor=state.get("feed_cursor", 0)),
            )
        elif str(state.get("feed_mode") or "") == "search":
            payload = ave_tools._restore_search_session_payload(state)
            if payload:
                conn.ave_state = state
                await ave_tools._send_display(conn, "feed", payload)
            else:
                source = str(state.get("feed_source") or "trending") or "trending"
                platform = str(state.get("feed_platform") or "")
                if platform:
                    await _handle_tool_response(
                        conn, ave_tools.ave_get_trending(conn, topic="", platform=platform)
                    )
                else:
                    await _handle_tool_response(conn, ave_tools.ave_get_trending(conn, topic=source))
        elif str(state.get("feed_mode") or "") == "signals" or str(state.get("feed_source") or "") == "signals":
            await _handle_tool_response(conn, ave_tools.ave_list_signals(conn))
        elif str(state.get("feed_mode") or "") == "watchlist" or str(state.get("feed_source") or "") == "watchlist":
            await _handle_tool_response(
                conn,
                ave_tools.ave_open_watchlist(conn, cursor=state.get("feed_cursor", 0)),
            )
        else:
            source = str(state.get("feed_source") or "trending") or "trending"
            platform = str(state.get("feed_platform") or "")
            if platform:
                await _handle_tool_response(
                    conn, ave_tools.ave_get_trending(conn, topic="", platform=platform)
                )
            else:
                await _handle_tool_response(conn, ave_tools.ave_get_trending(conn, topic=source))
        _refresh_turn_context()
        return True

    if await _try_route_voice_trade_intent(
        conn,
        utterance,
        normalized,
        state,
        selection_payload,
        effective_screen,
        ave_tools,
    ):
        _refresh_turn_context()
        return True

    watch_symbol_match = _WATCH_SYMBOL_PATTERN.match(normalized)
    if watch_symbol_match:
        symbol = watch_symbol_match.group(1).upper()
        await _cancel_pending_trade_for_exit(conn, state, effective_screen, ave_tools)
        token = _resolve_symbol_entry(state, symbol)
        if token:
            await _handle_tool_response(
                conn,
                ave_tools.ave_token_detail(
                    conn,
                    addr=token["addr"],
                    chain=token["chain"],
                    symbol=symbol,
                ),
            )
        else:
            await _handle_tool_response(conn, ave_tools.ave_search_token(conn, keyword=symbol))
        _refresh_turn_context()
        return True

    search_symbol_match = _SEARCH_SYMBOL_PATTERN.match(normalized)
    if search_symbol_match:
        keyword = search_symbol_match.group(1).upper()
        await _cancel_pending_trade_for_exit(conn, state, effective_screen, ave_tools)
        await _handle_tool_response(conn, ave_tools.ave_search_token(conn, keyword=keyword))
        _refresh_turn_context()
        return True

    buy_symbol_match = _BUY_SYMBOL_PATTERN.match(normalized)
    if buy_symbol_match:
        symbol = buy_symbol_match.group(1).upper()
        await _cancel_pending_trade_for_exit(conn, state, effective_screen, ave_tools)
        token = _resolve_symbol_entry(state, symbol)
        if token:
            await _handle_tool_response(
                conn,
                ave_tools.ave_buy_token(
                    conn,
                    addr=token["addr"],
                    chain=token["chain"],
                    symbol=symbol,
                ),
            )
        else:
            await _handle_tool_response(conn, ave_tools.ave_search_token(conn, keyword=symbol))
        _refresh_turn_context()
        return True

    return False
