"""
AVE real-time WebSocket manager (per-connection).

Maintains two background asyncio tasks:
  _data_loop  — connects to wss://wss.ave-api.xyz (requires API_PLAN=pro)
                subscribes price for feed tokens + kline-s1 for spotlight token
                pushes FEED / SPOTLIGHT display updates to the device

  _trade_loop — connects to wss://bot-api.ave.ai/thirdws (requires API_PLAN>=normal)
                subscribes botswap topic
                pushes NOTIFY / RESULT on TP/SL/confirmed/error events

Usage
-----
In helloHandle.py after welcome is sent:

    conn.ave_wss = AveWssManager(conn)
    conn.ave_wss.start()
    conn.loop.create_task(_initial_feed_push(conn))

In connection.py _save_and_close():

    if hasattr(conn, 'ave_wss'):
        conn.ave_wss.stop()

In ave_tools.py ave_get_trending():

    if hasattr(conn, 'ave_wss'):
        conn.ave_wss.set_feed_tokens(tokens)

In ave_tools.py ave_token_detail():

    if hasattr(conn, 'ave_wss'):
        conn.ave_wss.set_spotlight(addr, chain, display_data, raw_closes)
"""

import asyncio
import contextlib
import json
import math
import os
import time
from typing import TYPE_CHECKING, List, Optional

import websockets

from config.logger import setup_logging
from plugins_func.functions.ave_trade_mgr import _send_display, _SWAP_TERMINAL_STATUSES
from plugins_func.functions.ave_tools import (
    _build_result_payload,
    _clear_search_state,
    _current_feed_session,
    _build_trade_state_notify_payload,
    _clear_pending_trade,
    _present_trade_result_or_defer,
    _clear_submitted_trade,
    _ensure_ave_state,
    _get_pending_trade,
    _next_feed_session,
    _get_submitted_trades,
    _queue_deferred_result_payload,
    _set_feed_navigation_state,
)

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

DATA_WSS_URL = "wss://wss.ave-api.xyz"
TRADE_WSS_URL = "wss://bot-api.ave.ai/thirdws?ave_access_key={key}"

RECONNECT_DELAY = 5    # seconds between reconnects
MAX_FEED_TOKENS = 20   # cap price subscriptions
MAX_CHART_POINTS = 48  # rolling window for live kline
DATA_SILENCE_WARN_SEC = 12
TRADE_SUBSCRIBE_WARN_SEC = 5


# ---------------------------------------------------------------------------
# Kline normalization (same logic as ave_tools._normalize_kline)
# ---------------------------------------------------------------------------

def _normalize_kline(closes: list) -> list:
    """Log-scale normalize raw closes to int16 range [0, 1000]."""
    if not closes:
        return []
    vals = [float(v) for v in closes if v is not None and float(v) > 0]
    if not vals:
        return [0] * len(closes)

    mn, mx = min(vals), max(vals)
    if mn <= 0:
        offset = abs(mn) + 1e-12
        vals = [v + offset for v in vals]
        mn, mx = min(vals), max(vals)

    log_min = math.log10(mn)
    log_max = math.log10(mx)
    log_range = log_max - log_min if log_max != log_min else 1.0

    result = []
    src = iter(vals)
    for raw in closes:
        if raw is None or float(raw) <= 0:
            result.append(0)
        else:
            v = next(src)
            normalized = (math.log10(v) - log_min) / log_range
            result.append(int(normalized * 1000))
    return result


# ---------------------------------------------------------------------------
# Formatting helpers (inline to avoid circular imports)
# ---------------------------------------------------------------------------

def _fmt_price(price) -> str:
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
    mag = math.floor(math.log10(abs(price)))
    decimals = max(2, -mag + 3)
    return f"${price:.{decimals}f}"


def _fmt_change(pct) -> str:
    if pct is None:
        return "N/A"
    pct = float(pct)
    sign = "+" if pct >= 0 else "-"
    return f"{sign}{abs(pct):.2f}%"


def _trade_subscribe_frame(topic: str = "botswap") -> dict:
    return {
        "jsonrpc": "2.0",
        "method": "subscribe",
        "params": [topic],
        "id": 0,
    }


def _jsonrpc_frame(method: str, params: list, rpc_id: int) -> dict:
    return {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": rpc_id,
    }


def _jsonrpc_error_text(error) -> str:
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message", "")
        data = error.get("data")
        parts = []
        if code is not None:
            parts.append(f"code={code}")
        if message:
            parts.append(str(message))
        if data not in (None, "", {}):
            parts.append(f"data={data}")
        return " | ".join(parts) if parts else str(error)
    return str(error)


def _fmt_volume(vol) -> str:
    if vol is None:
        return "N/A"
    vol = float(vol)
    if vol >= 1_000_000:
        return f"${vol/1_000_000:.1f}M"
    if vol >= 1_000:
        return f"${vol/1_000:.1f}K"
    return f"${vol:.0f}"


def _fmt_chart_time(ts: int) -> str:
    """Format a unix timestamp as 'MM/DD HH:MM' for chart axis labels."""
    if not ts:
        return ""
    from datetime import datetime
    try:
        return datetime.fromtimestamp(ts).strftime("%m/%d %H:%M")
    except Exception:
        return ""


def _fmt_y_label(price) -> str:
    if price is None or float(price) <= 0:
        return "N/A"
    price = float(price)
    if price >= 1000:
        return f"${price:,.0f}"
    if price >= 1:
        return f"${price:.2f}"
    if price >= 0.001:
        return f"${price:.4f}"
    exp = int(math.floor(math.log10(abs(price))))
    mantissa = price / (10 ** exp)
    return f"{mantissa:.2f}e{exp}"


def _normalized_interval(interval: str) -> str:
    value = str(interval or "").strip().lower()
    if value.startswith("k"):
        return value[1:]
    return value


def _is_live_chart_interval(interval: str) -> bool:
    return _normalized_interval(interval) in {"s1", "1"}


def _interval_matches_selected(selected_interval: str, incoming_interval: str) -> bool:
    if not incoming_interval:
        return True
    return _normalized_interval(selected_interval) == _normalized_interval(incoming_interval)


def _build_spotlight_chart_patch(raw_closes: list[float], raw_times: list[int]) -> dict:
    valid = [float(v) for v in raw_closes if v is not None and float(v) > 0]
    if not valid:
        return {}

    times = [int(v) for v in raw_times if v]
    n_times = len(times)
    chart_min = min(valid)
    chart_max = max(valid)
    return {
        "chart": _normalize_kline(valid),
        "chart_min": _fmt_price(chart_min),
        "chart_max": _fmt_price(chart_max),
        "chart_min_y": _fmt_y_label(chart_min),
        "chart_max_y": _fmt_y_label(chart_max),
        "chart_t_start": _fmt_chart_time(times[0]) if n_times > 0 else "",
        "chart_t_mid": _fmt_chart_time(times[n_times // 2]) if n_times > 0 else "",
        "chart_t_end": "now",
    }


def _infer_event_trade_type(msg: dict) -> str:
    swap_type = str(msg.get("swapType", msg.get("swap_type", "")) or "").lower()
    order_type = str(msg.get("orderType", msg.get("order_type", "")) or "").lower()

    if swap_type in {"cancel_order", "cancel"}:
        return "cancel_order"
    if order_type == "limit":
        return "limit_buy"
    if swap_type == "buy":
        return "market_buy"
    if swap_type == "sell":
        return "market_sell"
    return ""


def _has_pending_trade(conn) -> bool:
    state = _ensure_ave_state(conn)
    pending = state.get("pending_trade")
    return isinstance(pending, dict) and bool(pending.get("trade_id"))


def _event_trade_ids(msg: dict) -> set[str]:
    ids = set()
    for key in (
        "tradeId",
        "trade_id",
        "id",
        "orderId",
        "order_id",
        "swapOrderId",
        "swap_order_id",
        "orderIds",
        "ids",
    ):
        value = msg.get(key)
        if isinstance(value, list):
            ids.update(str(item) for item in value if item not in (None, ""))
        elif value not in (None, ""):
            ids.add(str(value))
    return ids


def _normalize_match_text(value) -> str:
    return str(value or "").strip().lower()


def _event_trade_chain(msg: dict) -> str:
    return _normalize_match_text(msg.get("chain") or msg.get("network"))


def _event_trade_symbol(msg: dict, trade_type: str) -> str:
    if trade_type in {"market_sell", "limit_buy", "cancel_order"}:
        value = msg.get("inTokenSymbol") or msg.get("outTokenSymbol") or ""
    else:
        value = msg.get("outTokenSymbol") or msg.get("inTokenSymbol") or ""
    return str(value or "").strip().upper()


def _event_trade_asset_address(msg: dict, trade_type: str) -> str:
    if trade_type == "market_sell":
        value = msg.get("inTokenAddress") or msg.get("outTokenAddress") or ""
    elif trade_type in {"market_buy", "limit_buy"}:
        value = msg.get("outTokenAddress") or msg.get("inTokenAddress") or ""
    else:
        value = msg.get("inTokenAddress") or msg.get("outTokenAddress") or ""
    return _normalize_match_text(value)


def _record_trade_asset_address(record: dict) -> str:
    return _normalize_match_text(record.get("asset_token_address"))


def _event_matches_pending_trade_exact(msg: dict, pending: dict) -> bool:
    pending_id = str(pending.get("trade_id", "") or "")
    if not pending_id and not pending.get("order_ids"):
        return False
    explicit_ids = _event_trade_ids(msg)
    if pending_id and pending_id in explicit_ids:
        return True
    order_ids = {str(item) for item in pending.get("order_ids", []) if item not in (None, "")}
    return bool(order_ids and explicit_ids and order_ids.intersection(explicit_ids))


def _event_matches_trade_fallback(
    msg: dict,
    record: dict,
    *,
    allow_direction_fallback: bool = True,
) -> bool:
    if not allow_direction_fallback:
        return False

    pending_type = str(record.get("trade_type", "") or "").lower()
    event_type = _infer_event_trade_type(msg)
    if not (pending_type and event_type and pending_type == event_type):
        return False

    pending_chain = _normalize_match_text(record.get("chain"))
    event_chain = _event_trade_chain(msg)
    if pending_chain and event_chain and pending_chain != event_chain:
        return False

    pending_asset = _record_trade_asset_address(record)
    event_asset = _event_trade_asset_address(msg, event_type)
    if pending_asset and event_asset:
        return pending_asset == event_asset

    pending_symbol = str(record.get("symbol", "") or "").strip().upper()
    event_symbol = _event_trade_symbol(msg, event_type)
    if not pending_symbol or not event_symbol:
        return False
    return pending_symbol == event_symbol


def _event_matches_submitted_trade_exact(msg: dict, submitted: dict) -> bool:
    submitted_order_id = str(submitted.get("swap_order_id", "") or "")
    return bool(submitted_order_id and submitted_order_id in _event_trade_ids(msg))


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class AveWssManager:
    """
    Per-connection AVE real-time WebSocket manager.

    Thread-safe: all state mutations and WSS tasks run in the same asyncio loop
    as the connection (conn.loop), so no locking is needed.
    """

    def __init__(self, conn: "ConnectionHandler"):
        self.conn = conn
        self._stopped = False
        self._rpc_id = 0

        # Feed state
        self._feed_token_ids: List[str] = []      # ["addr-chain", ...]
        self._feed_display: dict = {}              # token_id → display dict
        self._feed_chain: str = "solana"
        self._feed_session: int = 0

        # Spotlight state
        self._spotlight_id: Optional[str] = None
        self._spotlight_pair: Optional[str] = None
        self._spotlight_chain: Optional[str] = None
        self._spotlight_interval: str = "k60"
        self._spotlight_data: dict = {}
        self._spotlight_raw_closes: List[float] = []   # live 1s closes only
        self._spotlight_raw_times: List[int] = []
        self._spotlight_raw_owner_token_id: str = ""
        self._spotlight_raw_owner_chain: str = ""
        self._spotlight_raw_owner_interval: str = ""
        self._spotlight_initial_times: List[int] = []

        # Resubscribe signal (set when feed/spotlight changes)
        self._resubscribe = asyncio.Event()

        # Feed push throttle: batch rapid per-token price events into one push
        # Fires at most once per FEED_THROTTLE_SEC to avoid flooding the device
        self._feed_dirty: bool = False
        self._last_feed_push: float = 0.0
        self._feed_flush_task: Optional[asyncio.Task] = None

        self._data_task: Optional[asyncio.Task] = None
        self._trade_task: Optional[asyncio.Task] = None
        self._spotlight_poll_task: Optional[asyncio.Task] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Spawn background tasks on conn.loop."""
        api_plan = os.environ.get("API_PLAN", "free").lower()
        if api_plan == "pro":
            self._data_task = self.conn.loop.create_task(
                self._data_loop(), name="ave_data_wss"
            )
            logger.bind(tag=TAG).info("AveWssManager: data WSS task started (pro plan)")
        else:
            logger.bind(tag=TAG).info(
                f"AveWssManager: data WSS skipped (API_PLAN={api_plan}, requires pro)"
            )

        self._trade_task = self.conn.loop.create_task(
            self._trade_loop(), name="ave_trade_wss"
        )
        logger.bind(tag=TAG).info("AveWssManager: trade WSS task started")

    def stop(self):
        """Cancel background tasks gracefully."""
        self._stopped = True
        if self._data_task and not self._data_task.done():
            self._data_task.cancel()
        if self._trade_task and not self._trade_task.done():
            self._trade_task.cancel()
        if self._spotlight_poll_task and not self._spotlight_poll_task.done():
            self._spotlight_poll_task.cancel()
        logger.bind(tag=TAG).info("AveWssManager: stopped")

    def set_feed_tokens(self, tokens: list, chain: str = "solana"):
        """
        Called by ave_get_trending after REST fetch.
        tokens: list of display dicts containing token_id, chain, price_raw, etc.
        """
        ids = []
        display = {}
        for t in tokens[:MAX_FEED_TOKENS]:
            tid = t.get("token_id", "")
            ch = t.get("chain", chain)
            # Ensure "addr-chain" format for the subscription key
            if tid and "-" not in tid:
                sub_id = f"{tid}-{ch}"
            else:
                sub_id = tid
            if sub_id:
                ids.append(sub_id)
                display[sub_id] = dict(t)

        self._feed_token_ids = ids
        self._feed_display = display
        self._feed_chain = chain
        self._feed_session = _current_feed_session(_ensure_ave_state(self.conn))
        self._resubscribe.set()
        logger.bind(tag=TAG).debug(f"set_feed_tokens: {len(ids)} tokens, chain={chain}")

    def invalidate_feed_session(
        self,
        session: Optional[int] = None,
        *,
        chain: Optional[str] = None,
        clear_tokens: bool = True,
    ) -> int:
        """
        Drop pending live FEED flush state before a screen/session transition.

        Clearing cached tokens prevents late price events or deferred flushes from repainting
        the old FEED context while a slower REST-driven rebuild is still in flight.
        """
        state = _ensure_ave_state(self.conn)
        if session is None:
            session = _next_feed_session(state)
        else:
            try:
                session = int(session)
            except (TypeError, ValueError):
                session = _next_feed_session(state)
            else:
                state["feed_session"] = session

        self._feed_session = session
        if chain is not None:
            self._feed_chain = chain

        self._feed_dirty = False
        flush_task = self._feed_flush_task
        self._feed_flush_task = None
        if flush_task is not None and not flush_task.done():
            flush_task.cancel()

        if clear_tokens:
            self._feed_token_ids = []
            self._feed_display = {}

        self._resubscribe.set()
        logger.bind(tag=TAG).debug(
            f"invalidate_feed_session: session={session}, clear_tokens={clear_tokens}"
        )
        return session

    def begin_spotlight_transition(
        self,
        pair_addr: str,
        chain: str,
        display_data: dict,
        *,
        interval: str = "k60",
    ):
        """
        Prime spotlight state for an interval/token refresh without repainting a loading shell.

        Keeps the current visible snapshot on screen, but updates internal selection state so
        live price/poll pushes stop using the old interval while fresh REST data is in flight.
        """
        next_data = dict(self._spotlight_data or {})
        next_data.update(dict(display_data or {}))
        token_id = next_data.get(
            "token_id",
            f"{next_data.get('addr', pair_addr)}-{chain}",
        )
        prev_token_id = str(self._spotlight_id or "")
        prev_chain = str(self._spotlight_chain or "").strip().lower()
        prev_interval = _normalized_interval(getattr(self, "_spotlight_interval", "k60"))
        next_interval = _normalized_interval(interval)

        self._spotlight_id = token_id
        self._spotlight_pair = pair_addr
        self._spotlight_chain = chain
        self._spotlight_interval = interval
        next_data["interval"] = str(next_data.get("interval", "60"))
        self._spotlight_data = next_data

        # When token/chain/interval identity changes, old live raw buffers become stale.
        if (
            prev_token_id != token_id
            or prev_chain != str(chain or "").strip().lower()
            or prev_interval != next_interval
        ):
            self._spotlight_raw_closes = []
            self._spotlight_raw_times = []
            self._spotlight_raw_owner_token_id = token_id
            self._spotlight_raw_owner_chain = str(chain or "").strip().lower()
            self._spotlight_raw_owner_interval = next_interval

        self._resubscribe.set()
        logger.bind(tag=TAG).debug(f"begin_spotlight_transition: {token_id} interval={interval}")

    def set_spotlight(
        self,
        pair_addr: str,
        chain: str,
        display_data: dict,
        raw_closes: list = None,
        raw_times: list = None,
        interval: str = "k60",
    ):
        """
        Called by ave_token_detail after REST fetch.
        pair_addr : pair/pool address used for kline WSS subscription.
        display_data: full SPOTLIGHT payload dict (will be mutated for live updates).
        raw_closes : list of raw close prices for renormalization.
        interval   : WSS kline interval (e.g. "k60", "k5", "k240", "k1440").
        """
        token_id = display_data.get(
            "token_id",
            f"{display_data.get('addr', pair_addr)}-{chain}",
        )
        self._spotlight_id = token_id
        self._spotlight_pair = pair_addr
        self._spotlight_chain = chain
        self._spotlight_interval = interval
        self._spotlight_data = dict(display_data)
        # Live kline window starts EMPTY — historical hourly closes from REST
        # are only used for the initial display (already in display_data["chart"]).
        # Mixing them with 1s live closes causes bimodal distribution in
        # normalization (new token: historical high ≈1000, current low ≈0).
        self._spotlight_raw_closes: List[float] = []
        self._spotlight_raw_times: List[int] = []
        self._spotlight_raw_owner_token_id = token_id
        self._spotlight_raw_owner_chain = str(chain or "").strip().lower()
        self._spotlight_raw_owner_interval = _normalized_interval(interval)
        self._spotlight_initial_times = list(raw_times or [])
        self._resubscribe.set()
        logger.bind(tag=TAG).debug(f"set_spotlight: {token_id}")

        # Cancel previous poll task and start a new one for this token
        if self._spotlight_poll_task and not self._spotlight_poll_task.done():
            self._spotlight_poll_task.cancel()
        addr = display_data.get("addr", pair_addr)
        self._spotlight_poll_task = self.conn.loop.create_task(
            self._spotlight_poll_loop(addr, chain), name="ave_spotlight_poll"
        )

    def _next_rpc_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    def _data_subscription_snapshot(self) -> dict:
        return {
            "price_tokens": list(self._feed_token_ids[:MAX_FEED_TOKENS]),
            "spotlight_pair": self._spotlight_pair or "",
            "spotlight_chain": self._spotlight_chain or "",
            "spotlight_interval": getattr(self, "_spotlight_interval", "k60"),
        }

    def _has_data_subscription(self) -> bool:
        return bool(self._feed_token_ids or (self._spotlight_pair and self._spotlight_chain))

    def _handle_data_control_frame(self, msg: dict) -> bool:
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return False

        if "error" in msg:
            logger.bind(tag=TAG).warning(
                f"AVE data WSS protocol error: {_jsonrpc_error_text(msg.get('error'))}"
            )
            return True

        if "result" not in msg:
            return False

        result = msg.get("result")
        if not isinstance(result, dict):
            logger.bind(tag=TAG).info(
                f"AVE data WSS ack: id={msg.get('id')} result={result!r}"
            )
            return True

        if any(key in result for key in ("prices", "klines", "kline", "type", "topic")):
            return False

        logger.bind(tag=TAG).info(
            f"AVE data WSS control frame: id={msg.get('id')} result={result}"
        )
        return True

    def _handle_trade_control_frame(self, msg: dict) -> bool:
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return False

        if "error" in msg:
            logger.bind(tag=TAG).warning(
                f"AVE trade WSS protocol error: {_jsonrpc_error_text(msg.get('error'))}"
            )
            return True

        if "result" not in msg:
            return False

        result = msg.get("result")
        if not isinstance(result, dict):
            logger.bind(tag=TAG).info(
                f"AVE trade WSS ack: id={msg.get('id')} result={result!r}"
            )
            return True

        if any(key in result for key in ("topic", "msg", "status")):
            return False

        logger.bind(tag=TAG).info(
            f"AVE trade WSS control frame: id={msg.get('id')} result={result}"
        )
        return True

    # ── Data WSS loop ─────────────────────────────────────────────────────────

    async def _data_loop(self):
        """Connect → subscribe → handle events → reconnect on error."""
        api_key = os.environ.get("AVE_API_KEY", "")
        if not api_key:
            logger.bind(tag=TAG).error("AVE_API_KEY not set, data WSS will not start")
            return

        while not self._stopped:
            try:
                logger.bind(tag=TAG).info("Connecting to AVE data WSS…")
                async with websockets.connect(
                    DATA_WSS_URL,
                    additional_headers={"X-API-KEY": api_key},
                    ping_interval=30,
                    ping_timeout=30,
                ) as ws:
                    logger.bind(tag=TAG).info("AVE data WSS connected")
                    self._resubscribe.clear()
                    await self._subscribe_data(ws)
                    silence_warned = False

                    # Use asyncio.wait so we react to _resubscribe even when
                    # no price events arrive (e.g. initial subscription was
                    # empty because initial_feed_push hadn't finished yet).
                    recv_task   = asyncio.ensure_future(ws.recv())
                    resub_task  = asyncio.ensure_future(self._resubscribe.wait())

                    try:
                        while not self._stopped:
                            timeout = DATA_SILENCE_WARN_SEC if self._has_data_subscription() and not silence_warned else None
                            done, _ = await asyncio.wait(
                                [recv_task, resub_task],
                                return_when=asyncio.FIRST_COMPLETED,
                                timeout=timeout,
                            )

                            if not done:
                                logger.bind(tag=TAG).warning(
                                    f"AVE data WSS subscribed but no ack/frame within {DATA_SILENCE_WARN_SEC}s: "
                                    f"{self._data_subscription_snapshot()}"
                                )
                                silence_warned = True
                                continue

                            if resub_task in done:
                                self._resubscribe.clear()
                                await self._subscribe_data(ws)
                                resub_task = asyncio.ensure_future(self._resubscribe.wait())
                                silence_warned = False

                            if recv_task in done:
                                try:
                                    raw = recv_task.result()
                                except Exception:
                                    # Connection closed
                                    raise
                                await self._handle_data_event(raw)
                                recv_task = asyncio.ensure_future(ws.recv())
                                silence_warned = False
                    finally:
                        # Cancel dangling futures so their exceptions are
                        # retrieved here and don't produce "never retrieved" warnings.
                        for t in (recv_task, resub_task):
                            if t is None:
                                continue
                            t.cancel()
                            with contextlib.suppress(BaseException):
                                await t

            except asyncio.CancelledError:
                return
            except Exception as e:
                if self._stopped:
                    return
                logger.bind(tag=TAG).warning(
                    f"AVE data WSS disconnected: {e!r}, retry in {RECONNECT_DELAY}s"
                )
                await asyncio.sleep(RECONNECT_DELAY)

    async def _subscribe_data(self, ws):
        """Send subscribe messages for current feed tokens and spotlight kline."""
        # Always unsubscribe first before re-subscribing
        unsubscribe_frame = _jsonrpc_frame("unsubscribe", [], self._next_rpc_id())
        await ws.send(json.dumps(unsubscribe_frame))
        logger.bind(tag=TAG).debug(f"AVE data WSS -> {unsubscribe_frame}")

        if self._feed_token_ids:
            price_frame = _jsonrpc_frame(
                "subscribe",
                ["price", self._feed_token_ids[:MAX_FEED_TOKENS]],
                self._next_rpc_id(),
            )
            await ws.send(json.dumps(price_frame))
            logger.bind(tag=TAG).info(
                f"Subscribed price: {len(self._feed_token_ids)} tokens"
            )
            logger.bind(tag=TAG).debug(f"AVE data WSS -> {price_frame}")

        if self._spotlight_pair and self._spotlight_chain:
            interval = getattr(self, "_spotlight_interval", "k60")
            kline_frame = _jsonrpc_frame(
                "subscribe",
                ["kline", self._spotlight_pair, interval, self._spotlight_chain],
                self._next_rpc_id(),
            )
            await ws.send(json.dumps(kline_frame))
            logger.bind(tag=TAG).info(
                f"Subscribed kline: {self._spotlight_pair}-{self._spotlight_chain} {interval}"
            )
            logger.bind(tag=TAG).debug(f"AVE data WSS -> {kline_frame}")

    async def _handle_data_event(self, raw: str):
        """Route an incoming data WSS frame to the correct handler."""
        try:
            msg = json.loads(raw)
        except Exception:
            return

        if self._handle_data_control_frame(msg):
            return

        result = msg.get("result")
        if isinstance(result, dict):
            # Actual AVE format: result.prices[] — per-pair price push
            prices = result.get("prices")
            if isinstance(prices, list):
                for item in prices:
                    if item.get("is_main_pair"):
                        await self._on_price_event(item)
                return

            # Actual AVE format: result.klines[] — kline push (format TBD)
            klines = result.get("klines")
            if isinstance(klines, list):
                for item in klines:
                    await self._on_kline_event(item)
                return

            # Actual AVE kline format: result = {"id":"pair-chain","interval":"s1","kline":{"eth":{close,...}},"topic":...}
            kline_data = result.get("kline")
            if isinstance(kline_data, dict):
                id_str = result.get("id", "")
                pair = id_str.rsplit("-", 1)[0] if "-" in id_str else ""
                incoming_interval = result.get("interval", "")
                for denom_val in kline_data.values():
                    if isinstance(denom_val, dict) and "close" in denom_val:
                        normalized = dict(denom_val)
                        if pair:
                            normalized["pair"] = pair
                        if incoming_interval:
                            normalized["interval"] = incoming_interval
                        await self._on_kline_event(normalized)
                        break
                return

            # Flat kline push: result itself has close/pair fields
            if "close" in result or "c" in result:
                await self._on_kline_event(result)
                return

            # Unknown result format — log for debugging
            keys = list(result.keys())[:8]
            logger.bind(tag=TAG).debug(f"[data WSS unhandled] keys={keys} val={str(result)[:200]}")

            # Fallback: result.type field
            if "type" in result:
                evt_type = result.get("type", "")
                if evt_type == "price":
                    await self._on_price_event(result)
                elif evt_type == "kline":
                    await self._on_kline_event(result)
                return

        # Top-level kline push (actual AVE format):
        # {"id":"pair-chain","interval":"s1","kline":{"eth":{"close":"...","high":"...","low":"...","open":"...","time":...}},"topic":"..."}
        kline_data = msg.get("kline")
        if isinstance(kline_data, dict):
            incoming_interval = msg.get("interval", "")
            for denom_val in kline_data.values():
                if isinstance(denom_val, dict) and "close" in denom_val:
                    normalized = dict(denom_val)
                    # Extract pair address from "id" field ("pair-chain" format)
                    id_str = msg.get("id", "")
                    if "-" in id_str:
                        normalized["pair"] = id_str.rsplit("-", 1)[0]
                    if incoming_interval:
                        normalized["interval"] = incoming_interval
                    await self._on_kline_event(normalized)
                    break
            return

        # Flat format: type at top level
        if "type" in msg:
            evt_type = msg.get("type", "")
            if evt_type == "price":
                await self._on_price_event(msg)
            elif evt_type == "kline":
                await self._on_kline_event(msg)

    # Minimum seconds between consecutive FEED pushes to the device.
    # Batches all price events that arrive within the window into one paint.
    FEED_THROTTLE_SEC = 0.5

    async def _on_price_event(self, evt: dict):
        """Update a feed token's cached price and schedule a throttled FEED push."""
        # Official format uses token_id; fallback to target_token / id
        chain   = evt.get("chain", self._feed_chain)
        tid_raw = evt.get("token_id", evt.get("target_token", evt.get("id", "")))
        if not tid_raw:
            return

        # Match against display dict (keys are "addr-chain" format)
        tid = tid_raw
        if tid not in self._feed_display:
            candidate = f"{tid_raw}-{chain}"
            if candidate in self._feed_display:
                tid = candidate
            else:
                for key in self._feed_token_ids:
                    if key.startswith(tid_raw + "-") or key == tid_raw:
                        tid = key
                        break
        if tid not in self._feed_display:
            return

        entry = self._feed_display[tid]
        new_price  = evt.get("price", evt.get("uprice"))
        new_change = evt.get("price_change_1h", evt.get("price_change_5m", evt.get("price_change")))
        new_vol    = evt.get("volume_24_u", evt.get("volume_24h"))

        if new_price is not None:
            entry["price"] = _fmt_price(new_price)
            entry["price_raw"] = float(new_price)
        if new_change is not None:
            entry["change_24h"] = _fmt_change(new_change)
            entry["change_positive"] = float(new_change) >= 0
        if new_vol is not None:
            entry["volume_24h"] = _fmt_volume(new_vol)

        self._feed_dirty = True
        await self._schedule_feed_flush()

        # ── Spotlight kline subscription fix ──────────────────────────────────
        # Kline subscription requires the pool (pair) address, not the token address.
        # The price event carries the correct pair address.  When a price event
        # matches the current spotlight token, update _spotlight_pair to the real
        # pool address and trigger a resubscription so kline events start flowing.
        if self._spotlight_id and tid == self._spotlight_id:
            pair_from_evt = evt.get("pair", "")
            if pair_from_evt and pair_from_evt != self._spotlight_pair:
                logger.bind(tag=TAG).info(
                    f"Resolved spotlight pair: {self._spotlight_pair!r} → {pair_from_evt!r}"
                )
                self._spotlight_pair = pair_from_evt
                self._resubscribe.set()

        # Push live price/change update to spotlight (price only — no chart redraw)
        if self._spotlight_id and tid == self._spotlight_id and self._spotlight_data:
            changed = False
            if new_price is not None:
                fmt = _fmt_price(new_price)
                if self._spotlight_data.get("price") != fmt:
                    self._spotlight_data["price"] = fmt
                    self._spotlight_data["price_raw"] = float(new_price)
                    changed = True
            if new_change is not None:
                fmt_c = _fmt_change(new_change)
                if self._spotlight_data.get("change_24h") != fmt_c:
                    self._spotlight_data["change_24h"] = fmt_c
                    self._spotlight_data["change_positive"] = float(new_change) >= 0
                    changed = True
            if changed:
                await _send_display(self.conn, "spotlight", {
                    **self._spotlight_data,
                    "live": True,
                })

    async def _schedule_feed_flush(self):
        """Push FEED to device, respecting the throttle window."""
        now = time.monotonic()
        remaining = self.FEED_THROTTLE_SEC - (now - self._last_feed_push)

        if remaining <= 0:
            # Due now — push immediately
            await self._flush_feed()
        elif self._feed_flush_task is None or self._feed_flush_task.done():
            # Schedule a deferred push after the remaining window
            self._feed_flush_task = self.conn.loop.create_task(
                self._deferred_feed_flush(remaining)
            )

    async def _deferred_feed_flush(self, delay: float):
        await asyncio.sleep(delay)
        await self._flush_feed()

    async def _flush_feed(self):
        if not self._feed_dirty:
            return
        self._feed_dirty = False
        self._last_feed_push = time.monotonic()
        feed_session = self._feed_session or _current_feed_session(_ensure_ave_state(self.conn))
        await _send_display(self.conn, "feed", {
            "tokens": list(self._feed_display.values()),
            "chain": self._feed_chain,
            "live": True,
            "feed_session": feed_session,
        })

    async def _on_kline_event(self, evt: dict):
        """Buffer kline points; only s1 live interval redraws spotlight chart."""
        if not self._spotlight_data:
            return

        # Ignore if not our pair
        pair = evt.get("pair", "")
        if pair and self._spotlight_pair and pair != self._spotlight_pair:
            return

        close_price = evt.get("close", evt.get("c"))
        if close_price is not None:
            close_f = float(close_price)
            ts = int(evt.get("time", 0))

            # Append to live-only rolling window (no historical hourly data)
            self._spotlight_raw_closes.append(close_f)
            if len(self._spotlight_raw_closes) > MAX_CHART_POINTS:
                self._spotlight_raw_closes = self._spotlight_raw_closes[-MAX_CHART_POINTS:]
            if ts:
                self._spotlight_raw_times.append(ts)
                if len(self._spotlight_raw_times) > MAX_CHART_POINTS:
                    self._spotlight_raw_times = self._spotlight_raw_times[-MAX_CHART_POINTS:]
            self._spotlight_raw_owner_token_id = str(
                self._spotlight_id or self._spotlight_data.get("token_id", "")
            )
            self._spotlight_raw_owner_chain = str(
                self._spotlight_chain or self._spotlight_data.get("chain", "")
            ).strip().lower()
            self._spotlight_raw_owner_interval = _normalized_interval(
                evt.get("interval", "") or self._spotlight_interval
            )

            # Do NOT update price from kline close — kline uses "eth" denomination
            # and may lag by 1-2s. Price is kept current by _on_price_event only.
            #
            selected_interval = getattr(self, "_spotlight_interval", "k60")
            incoming_interval = evt.get("interval", "")
            selected_normalized = _normalized_interval(selected_interval)
            if selected_normalized != "s1":
                return
            if not _interval_matches_selected(selected_interval, incoming_interval):
                return

            chart_patch = _build_spotlight_chart_patch(
                self._spotlight_raw_closes,
                self._spotlight_raw_times,
            )
            if not chart_patch:
                return

            self._spotlight_data.update(chart_patch)
            await _send_display(self.conn, "spotlight", {
                **self._spotlight_data,
                "live": True,
            })
        return

    # ── Spotlight holders/liq poll ────────────────────────────────────────────

    async def _spotlight_poll_loop(self, addr: str, chain: str):
        """Poll holders + liquidity every 5 s and push a live SPOTLIGHT update."""
        import asyncio as _asyncio
        from plugins_func.functions.ave_tools import _data_get, _fmt_volume
        loop = _asyncio.get_event_loop()
        chain_norm = str(chain or "").strip().lower()

        def _identity_matches() -> bool:
            if not isinstance(self._spotlight_data, dict):
                return False
            current_addr = str(self._spotlight_data.get("addr", "") or "")
            current_chain = str(self._spotlight_data.get("chain", chain_norm) or chain_norm).strip().lower()
            return current_addr == addr and current_chain == chain_norm

        while not self._stopped and self._spotlight_data:
            await _asyncio.sleep(5)
            if self._stopped or not self._spotlight_data:
                break
            # Spotlight may have changed while we were sleeping
            if not _identity_matches():
                break
            try:
                resp = await loop.run_in_executor(
                    None, lambda: _data_get(f"/tokens/{addr}-{chain}")
                )
                if self._stopped or not self._spotlight_data or not _identity_matches():
                    break
                token_data = resp.get("data", resp)
                token = token_data.get("token", token_data) if isinstance(token_data, dict) else token_data
                if isinstance(token, list) and token:
                    token = token[0]
                if not isinstance(token, dict):
                    continue

                holders_raw = token.get("holders")
                liq_raw = token.get("main_pair_tvl", token.get("tvl"))
                # Always update both fields if present; push regardless of change
                # so holders and liq always stay in sync on screen.
                if holders_raw is not None:
                    try:
                        # API may return int, float, or float-string ("12345.0")
                        self._spotlight_data["holders"] = f"{int(float(holders_raw)):,}"
                    except (ValueError, TypeError):
                        pass
                if liq_raw is not None:
                    self._spotlight_data["liquidity"] = _fmt_volume(liq_raw)

                # L1M should keep moving even when upstream k1 pushes are sparse.
                # Refresh 1-minute chart from REST on each spotlight poll tick.
                selected_interval = _normalized_interval(
                    str(self._spotlight_data.get("interval", self._spotlight_interval))
                )
                if selected_interval == "1":
                    kline_resp = await loop.run_in_executor(
                        None,
                        lambda: _data_get(
                            f"/klines/token/{addr}-{chain}",
                            {"interval": "1", "limit": MAX_CHART_POINTS},
                        ),
                    )
                    if self._stopped or not self._spotlight_data or not _identity_matches():
                        break
                    points = kline_resp.get("data", {}).get("points", [])
                    closes = []
                    times = []
                    for point in points:
                        close_value = point.get("close", point.get("c"))
                        if close_value is None:
                            continue
                        close_float = float(close_value)
                        if close_float <= 0:
                            continue
                        closes.append(close_float)
                        times.append(int(point.get("time", point.get("t", 0)) or 0))
                    chart_patch = _build_spotlight_chart_patch(closes, times)
                    if chart_patch:
                        self._spotlight_data.update(chart_patch)
                # Push on every successful poll so both labels refresh together
                if self._stopped or not self._spotlight_data or not _identity_matches():
                    break
                await _send_display(self.conn, "spotlight", {
                    **self._spotlight_data,
                    "live": True,
                })
            except _asyncio.CancelledError:
                raise
            except Exception as e:
                err_str = str(e)
                # Connection reset / rate-limit: back off 15 s before next poll
                if "104" in err_str or "reset" in err_str.lower() or "rate" in err_str.lower():
                    logger.bind(tag=TAG).debug(f"spotlight poll back-off: {e}")
                    await _asyncio.sleep(15)
                else:
                    logger.bind(tag=TAG).warning(f"spotlight poll error: {e}")

    # ── Trade WSS loop ────────────────────────────────────────────────────────

    async def _trade_loop(self):
        """Connect → subscribe botswap → handle order events → reconnect on error."""
        api_key = os.environ.get("AVE_API_KEY", "")
        if not api_key:
            logger.bind(tag=TAG).error("AVE_API_KEY not set, trade WSS will not start")
            return

        url = TRADE_WSS_URL.format(key=api_key)

        while not self._stopped:
            try:
                logger.bind(tag=TAG).info("Connecting to AVE trade WSS…")
                async with websockets.connect(
                    url,
                    ping_interval=30,
                    ping_timeout=30,
                ) as ws:
                    logger.bind(tag=TAG).info("AVE trade WSS connected")
                    await ws.send(json.dumps(_trade_subscribe_frame("botswap")))
                    try:
                        first_raw = await asyncio.wait_for(
                            ws.recv(),
                            timeout=TRADE_SUBSCRIBE_WARN_SEC,
                        )
                    except asyncio.TimeoutError:
                        logger.bind(tag=TAG).warning(
                            "AVE trade WSS subscribe sent but no ack/frame within "
                            f"{TRADE_SUBSCRIBE_WARN_SEC}s for topic=botswap; waiting for live pushes"
                        )
                    else:
                        await self._handle_trade_event(first_raw)

                    async for raw in ws:
                        if self._stopped:
                            return
                        await self._handle_trade_event(raw)

            except asyncio.CancelledError:
                return
            except Exception as e:
                if self._stopped:
                    return
                logger.bind(tag=TAG).warning(
                    f"AVE trade WSS disconnected: {e!r}, retry in {RECONNECT_DELAY}s"
                )
                await asyncio.sleep(RECONNECT_DELAY)

    async def _handle_trade_event(self, raw: str):
        """Handle a botswap push event → push NOTIFY or RESULT to device."""
        try:
            msg = json.loads(raw)
        except Exception:
            return

        if self._handle_trade_control_frame(msg):
            return

        # Log non-ack frames so we can verify the actual format
        logger.bind(tag=TAG).debug(f"[trade WSS] {raw[:300]}")

        # Support flat format (official spec) and nested result.msg format (legacy)
        if "status" in msg:
            m = msg
        else:
            result = msg.get("result", msg)
            if not isinstance(result, dict):
                return
            m = result.get("msg", result)
        if not isinstance(m, dict):
            return
        # Verify it's a botswap event
        result_obj = msg.get("result", {})
        topic = msg.get("topic", result_obj.get("topic", "") if isinstance(result_obj, dict) else "")
        if topic and topic != "botswap":
            return

        # Skip frames that have no status (e.g. subscription ack)
        status = str(m.get("status", "") or "").lower()
        if not status:
            return

        swap_type = str(m.get("swapType", m.get("swap_type", "")) or "").lower()
        order_type = str(m.get("orderType", m.get("order_type", "")) or "").lower()
        trade_type = _infer_event_trade_type(m)
        symbol = (
            m.get("outTokenSymbol")
            if trade_type in {"market_buy", "limit_buy"}
            else m.get("inTokenSymbol")
        ) or m.get("inTokenSymbol") or m.get("outTokenSymbol") or "TOKEN"
        tx_hash   = m.get("txHash", "")
        amount_usd = m.get("outAmountUsd", m.get("amountUsd", ""))

        logger.bind(tag=TAG).info(
            f"Trade event: status={status} swapType={swap_type} orderType={order_type} symbol={symbol}"
        )

        pending = _get_pending_trade(self.conn)
        has_pending = bool(pending.get("trade_id"))
        explicit_ids = _event_trade_ids(m)
        submitted_trades = [
            item for item in _get_submitted_trades(self.conn)
            if isinstance(item, dict)
        ]

        if explicit_ids:
            matches_pending = has_pending and _event_matches_pending_trade_exact(m, pending)
            submitted_matches = [
                item for item in submitted_trades
                if _event_matches_submitted_trade_exact(m, item)
            ]
        else:
            allow_fallback = status in _SWAP_TERMINAL_STATUSES
            matches_pending = has_pending and _event_matches_trade_fallback(
                m,
                pending,
                allow_direction_fallback=allow_fallback,
            )
            submitted_matches = [
                item for item in submitted_trades
                if _event_matches_trade_fallback(
                    m,
                    item,
                    allow_direction_fallback=allow_fallback,
                )
            ]
            candidate_count = (1 if matches_pending else 0) + len(submitted_matches)
            if candidate_count > 1:
                logger.bind(tag=TAG).warning(
                    f"Ignoring ambiguous under-keyed trade event status={status} symbol={symbol} candidates={candidate_count}"
                )
                return

        matched_submitted = submitted_matches[0] if submitted_matches else {}
        resolved_trade_type = (
            trade_type
            or str(matched_submitted.get("trade_type", "") or "")
            or str(pending.get("trade_type", "") or "")
        )

        def _terminal_failure_payload(*, cancel_state: bool = False) -> dict:
            error_text = (
                m.get("errorMessage")
                or m.get("errorMsg")
                or ("Order was cancelled before execution." if cancel_state else "交易失败")
            )
            payload = _build_result_payload(
                {
                    "status": status,
                    "trade_type": resolved_trade_type,
                    "title": "Trade Cancelled" if cancel_state and resolved_trade_type != "cancel_order" else "",
                    "data": {
                        "inTokenSymbol": m.get("inTokenSymbol", ""),
                        "outTokenSymbol": m.get("outTokenSymbol", ""),
                        "txHash": tx_hash,
                    },
                    "error": error_text,
                    "errorMessage": m.get("errorMessage", ""),
                    "subtitle": error_text if cancel_state else "",
                    "explain_state": "",
                },
                pending=matched_submitted or pending,
            )
            if cancel_state:
                payload["title"] = "Order Cancelled" if resolved_trade_type == "cancel_order" else "Trade Cancelled"
            return payload

        if status == "confirmed":
            if swap_type == "takeprofit":
                await _send_display(self.conn, "notify", {
                    "level": "success",
                    "title": f"🎉 止盈成功 {symbol}",
                    "body": f"${amount_usd}" if amount_usd else (tx_hash[:16] or "已执行"),
                })
            elif swap_type == "stoploss":
                await _send_display(self.conn, "notify", {
                    "level": "warning",
                    "title": f"⚠️ 止损触发 {symbol}",
                    "body": f"${amount_usd}" if amount_usd else (tx_hash[:16] or "已执行"),
                })
            elif swap_type == "trailing":
                await _send_display(self.conn, "notify", {
                    "level": "success",
                    "title": f"📈 追踪止盈 {symbol}",
                    "body": f"${amount_usd}" if amount_usd else "已执行",
                })
            elif resolved_trade_type in {"market_buy", "market_sell", "limit_buy", "cancel_order"}:
                payload = _build_result_payload({
                    "status": status,
                    "trade_type": resolved_trade_type,
                    "data": {
                        "inTokenSymbol": m.get("inTokenSymbol", ""),
                        "outTokenSymbol": m.get("outTokenSymbol", ""),
                        "outAmount": m.get("outAmount", m.get("out_amount", "")),
                        "outAmountUsd": m.get("outAmountUsd", m.get("amountUsd", "")),
                        "txHash": tx_hash,
                        "orderIds": m.get("orderIds", m.get("ids", [])),
                    },
                }, pending=matched_submitted or pending)
                if matched_submitted:
                    await _present_trade_result_or_defer(
                        self.conn,
                        payload,
                        current_trade_id=str(matched_submitted.get("trade_id", "") or ""),
                    )
                    _clear_submitted_trade(
                        self.conn,
                        trade_id=str(matched_submitted.get("trade_id", "") or ""),
                        swap_order_id=str(matched_submitted.get("swap_order_id", "") or ""),
                    )
                    return
                if has_pending and not matches_pending:
                    _queue_deferred_result_payload(self.conn, payload)
                    await _send_display(self.conn, "notify", _build_trade_state_notify_payload("deferred_result"))
                    return
                await _present_trade_result_or_defer(
                    self.conn,
                    payload,
                    current_trade_id=pending.get("trade_id", "") if matches_pending else "",
                )
                if matches_pending:
                    _clear_pending_trade(self.conn, pending.get("trade_id", ""))

        elif status in {"error", "failed"}:
            payload = _terminal_failure_payload(cancel_state=False)
            if matched_submitted:
                await _present_trade_result_or_defer(
                    self.conn,
                    payload,
                    current_trade_id=str(matched_submitted.get("trade_id", "") or ""),
                )
                _clear_submitted_trade(
                    self.conn,
                    trade_id=str(matched_submitted.get("trade_id", "") or ""),
                    swap_order_id=str(matched_submitted.get("swap_order_id", "") or ""),
                )
                return
            if trade_type in {"market_buy", "market_sell", "limit_buy", "cancel_order"} and has_pending and not matches_pending:
                _queue_deferred_result_payload(self.conn, payload)
                await _send_display(self.conn, "notify", _build_trade_state_notify_payload("deferred_result"))
                return
            await _present_trade_result_or_defer(
                self.conn,
                payload,
                current_trade_id=pending.get("trade_id", "") if matches_pending else "",
            )
            if matches_pending:
                _clear_pending_trade(self.conn, pending.get("trade_id", ""))

        elif status in {"cancelled", "canceled", "auto_cancelled"}:
            if resolved_trade_type in {"market_buy", "market_sell", "limit_buy", "cancel_order"} or matched_submitted or matches_pending:
                payload = _terminal_failure_payload(cancel_state=True)
                if matched_submitted:
                    await _present_trade_result_or_defer(
                        self.conn,
                        payload,
                        current_trade_id=str(matched_submitted.get("trade_id", "") or ""),
                    )
                    _clear_submitted_trade(
                        self.conn,
                        trade_id=str(matched_submitted.get("trade_id", "") or ""),
                        swap_order_id=str(matched_submitted.get("swap_order_id", "") or ""),
                    )
                    return
                if has_pending and not matches_pending:
                    _queue_deferred_result_payload(self.conn, payload)
                    await _send_display(self.conn, "notify", _build_trade_state_notify_payload("deferred_result"))
                    return
                await _present_trade_result_or_defer(
                    self.conn,
                    payload,
                    current_trade_id=pending.get("trade_id", "") if matches_pending else "",
                )
                if matches_pending:
                    _clear_pending_trade(self.conn, pending.get("trade_id", ""))
            else:
                await _send_display(self.conn, "notify", {
                    "level": "warning",
                    "title": f"订单已取消 {symbol}",
                    "body": "已自动取消",
                })


# ---------------------------------------------------------------------------
# Initial feed push helper (called on device connect)
# ---------------------------------------------------------------------------

async def initial_feed_push(conn: "ConnectionHandler"):
    """
    Fetch multi-chain trending tokens via REST and push FEED on device connect.
    Uses aiohttp so the event loop is never blocked.
    """
    api_key = os.environ.get("AVE_API_KEY", "")
    if not api_key:
        return

    CHAINS    = ["solana", "eth", "bsc", "base"]
    PER_CHAIN = 5
    data_base = "https://data.ave-api.xyz/v2"

    async def _fetch(session, ch):
        try:
            url = (f"{data_base}/tokens/trending"
                   f"?chain={ch}&current_page=1&page_size={PER_CHAIN}")
            async with session.get(
                url,
                headers={"X-API-KEY": api_key},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                raw = await resp.json()
            lst = raw.get("data", {})
            if isinstance(lst, dict):
                lst = lst.get("tokens", lst.get("list", []))
            lst = lst if isinstance(lst, list) else []
            for item in lst:
                if not item.get("chain"):
                    item["chain"] = ch
            return ch, lst
        except Exception as e:
            logger.bind(tag=TAG).warning(f"initial_feed_push {ch}: {e}")
            return ch, []

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            results = await asyncio.gather(*[_fetch(session, ch) for ch in CHAINS])

        # Interleave across chains
        buckets = {ch: lst for ch, lst in results}
        max_len = max((len(v) for v in buckets.values()), default=0)
        raw_all, seen = [], set()
        for i in range(max_len):
            for ch in CHAINS:
                lst = buckets.get(ch, [])
                if i < len(lst):
                    t   = lst[i]
                    tid = t.get("token", t.get("token_id", t.get("address", "")))
                    dedupe_key = (str(tid), str(t.get("chain") or ch or ""))
                    if tid and dedupe_key not in seen:
                        seen.add(dedupe_key)
                        raw_all.append(t)

        tokens = []
        for t in raw_all[:20]:
            price_val  = t.get("current_price_usd", t.get("price", 0))
            change_val = t.get("token_price_change_24h", t.get("price_change_24h", 0))
            vol_val    = t.get("token_tx_volume_usd_24h", t.get("tx_volume_u_24h", 0))
            tokens.append({
                "token_id":        t.get("token", t.get("token_id", t.get("address", ""))),
                "chain":           t.get("chain", "???"),
                "symbol":          t.get("symbol", "???"),
                "price":           _fmt_price(price_val),
                "price_raw":       float(price_val or 0),
                "change_24h":      _fmt_change(change_val),
                "change_positive": float(change_val or 0) >= 0,
                "volume_24h":      _fmt_volume(vol_val),
                "market_cap":      _fmt_volume(t.get("market_cap", t.get("fdv"))),
                "source":          t.get("issue_platform", t.get("platform", "trending")),
                "risk_level":      "UNKNOWN",
            })

        if not tokens:
            return

        state = _ensure_ave_state(conn)
        feed_session = _next_feed_session(state)
        state["screen"] = "feed"
        state["feed_source"] = "trending"
        state["feed_platform"] = ""
        state["feed_mode"] = "standard"
        state.pop("nav_from", None)
        _clear_search_state(state)
        _set_feed_navigation_state(state, tokens, cursor=0)
        await _send_display(conn, "feed", {"tokens": tokens, "chain": "all", "feed_session": feed_session})

        if hasattr(conn, "ave_wss"):
            conn.ave_wss.set_feed_tokens(tokens, "all")

        logger.bind(tag=TAG).info(
            f"initial_feed_push: pushed {len(tokens)} tokens across {CHAINS}"
        )

    except Exception as e:
        logger.bind(tag=TAG).warning(f"initial_feed_push failed: {e}")
