"""
Handle key_action messages from the device — bypass LLM for instant UI response.

Message format:
  {"type":"key_action","action":"watch","token_id":"<addr>","chain":"solana"}
  {"type":"key_action","action":"buy",  "token_id":"<addr>","chain":"solana"}
  {"type":"key_action","action":"portfolio"}

Actions:
  watch     → call ave_token_detail directly → pushes spotlight display
  buy       → call ave_buy_token directly    → pushes confirm display
  portfolio → call ave_portfolio directly    → pushes portfolio display
"""
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

VALID_FEED_PLATFORMS = {
    "pump_in_hot",
    "pump_in_new",
    "fourmeme_in_hot",
    "fourmeme_in_new",
}
VALID_ACTION_CHAINS = {"solana", "bsc", "eth", "base"}


class KeyActionHandler(TextMessageHandler):

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.KEY_ACTION

    async def handle(self, conn: "ConnectionHandler", msg_json: Dict[str, Any]) -> None:
        # ave_tools functions are synchronous def (not async def).
        # Call them directly on the event loop thread — safe because they use
        # conn.loop.create_task() for display pushes, which requires the event
        # loop thread.  HTTP calls block briefly but that's acceptable here.
        from plugins_func.functions.ave_tools import (
            ave_token_detail, ave_buy_token, ave_portfolio,
            ave_sell_token, ave_get_trending, ave_cancel_trade,
            ave_list_orders, ave_list_signals, ave_open_watchlist,
            ave_portfolio_activity_detail,
            ave_set_trade_mode,
            ave_remove_current_watchlist_token,
            _get_pending_trade, _restore_search_session_payload,
            _set_feed_navigation_state, _build_explorer_payload,
            _send_display, _set_search_session_cursor, _split_token_reference,
        )

        def _resolve_asset_ref(ref_value, chain_value):
            raw_ref = str(ref_value or "").strip()
            raw_chain = str(chain_value or "").strip().lower()
            resolved_addr, resolved_chain = _split_token_reference(raw_ref, raw_chain)
            has_chain = (
                resolved_chain in VALID_ACTION_CHAINS and
                (bool(raw_chain) or (bool(raw_ref) and resolved_addr != raw_ref))
            )
            return raw_ref, resolved_addr, resolved_chain, has_chain

        def _normalize_supported_chain(chain_value):
            normalized = str(chain_value or "").strip().lower()
            if not normalized:
                return ""
            if normalized not in VALID_ACTION_CHAINS:
                return None
            return normalized

        def _cycle_action_chain(current_value, *, allow_all=False):
            order = ["solana", "base", "eth", "bsc"]
            if allow_all:
                order = ["all"] + order
            normalized = str(current_value or "").strip().lower()
            if normalized not in order:
                normalized = order[0]
            next_idx = (order.index(normalized) + 1) % len(order)
            return order[next_idx]

        action = msg_json.get("action", "")
        token_id = msg_json.get("token_id", "")
        raw_chain, token_addr, token_chain, token_has_chain = _resolve_asset_ref(
            token_id,
            msg_json.get("chain", ""),
        )

        if action == "watch":
            if not token_addr:
                logger.bind(tag=TAG).warning("key_action watch missing token_id")
                return
            if not token_has_chain:
                logger.bind(tag=TAG).warning("key_action watch missing chain")
                return
            logger.bind(tag=TAG).info(f"key_action watch {token_addr} chain={token_chain}")
            try:
                state = getattr(conn, "ave_state", {})
                try:
                    raw_cursor = msg_json.get("cursor")
                    cursor = int(raw_cursor) if raw_cursor is not None else None
                except (TypeError, ValueError):
                    cursor = None
                feed_list = state.get("feed_token_list", [])
                feed_total = len(feed_list) if isinstance(feed_list, list) and feed_list else None
                if cursor is None and feed_total:
                    try:
                        cursor = int(state.get("feed_cursor", 0))
                    except (TypeError, ValueError):
                        cursor = 0
                if cursor is not None and feed_total:
                    cursor = max(0, min(cursor, feed_total - 1))
                if cursor is not None:
                    state["feed_cursor"] = cursor
                    if state.get("feed_mode") == "search":
                        state["search_cursor"] = cursor
                        _set_search_session_cursor(state, cursor)
                origin = str(msg_json.get("origin") or "").strip().lower()
                if origin not in {"feed", "signals", "watchlist", "portfolio"}:
                    if state.get("screen") == "portfolio":
                        origin = "portfolio"
                    elif state.get("feed_mode") == "signals" or state.get("feed_source") == "signals":
                        origin = "signals"
                    elif state.get("feed_mode") == "watchlist" or state.get("feed_source") == "watchlist":
                        origin = "watchlist"
                    else:
                        origin = "feed"
                state["nav_from"] = origin
                conn.ave_state = state
                ave_token_detail(
                    conn,
                    addr=token_addr,
                    chain=token_chain,
                    feed_cursor=cursor,
                    feed_total=feed_total,
                )
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action watch error: {e}")

        elif action == "buy":
            if not token_addr:
                logger.bind(tag=TAG).warning("key_action buy missing token_id")
                return
            if not token_has_chain:
                logger.bind(tag=TAG).warning("key_action buy missing chain")
                return
            logger.bind(tag=TAG).info(f"key_action buy {token_addr} chain={token_chain}")
            try:
                ave_buy_token(conn, addr=token_addr, chain=token_chain, in_amount_sol=0.1)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action buy error: {e}")

        elif action == "portfolio":
            logger.bind(tag=TAG).info("key_action portfolio — sending display")
            from plugins_func.functions.ave_trade_mgr import _send_display
            try:
                # Run the sync function which schedules _send_display via create_task.
                # Also await directly in case the task scheduler has latency issues.
                ave_portfolio(conn)
                # Yield so the create_task coroutine can run immediately.
                import asyncio
                await asyncio.sleep(0)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action portfolio error: {e}", exc_info=True)

        elif action == "kline_interval":
            interval = msg_json.get("interval", "60")
            if not token_addr:
                logger.bind(tag=TAG).warning("key_action kline_interval missing token_id")
                return
            if not token_has_chain:
                logger.bind(tag=TAG).warning("key_action kline_interval missing chain")
                return
            logger.bind(tag=TAG).info(f"key_action kline_interval {token_addr} chain={token_chain} interval={interval}")
            try:
                ave_token_detail(conn, addr=token_addr, chain=token_chain, interval=interval)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action kline_interval error: {e}")

        elif action == "quick_sell":
            if not token_addr:
                logger.bind(tag=TAG).warning("key_action quick_sell missing token_id")
                return
            if not token_has_chain:
                logger.bind(tag=TAG).warning("key_action quick_sell missing chain")
                return
            logger.bind(tag=TAG).info(f"key_action quick_sell {token_addr} chain={token_chain}")
            try:
                # Use first 8 chars of the normalized addr as symbol fallback.
                sym_fallback = token_addr[:8] if token_addr else "TOKEN"
                # Check if we have symbol in state
                state = getattr(conn, "ave_state", {})
                sym = str(msg_json.get("symbol") or "").strip()
                if not sym:
                    sym = state.get("current_token", {}).get("symbol", sym_fallback)
                ave_sell_token(conn, addr=token_addr, chain=token_chain,
                               sell_ratio=1.0, symbol=sym)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action quick_sell error: {e}")

        elif action == "cancel_trade":
            logger.bind(tag=TAG).info("key_action cancel_trade")
            try:
                ave_cancel_trade(conn)
                import asyncio
                await asyncio.sleep(0)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action cancel_trade error: {e}")

        elif action == "orders":
            state = getattr(conn, "ave_state", {})
            raw_msg_chain = msg_json.get("chain")
            msg_chain = _normalize_supported_chain(raw_msg_chain)
            if raw_msg_chain and msg_chain is None:
                logger.bind(tag=TAG).warning(f"key_action orders unsupported chain={raw_msg_chain}")
                return

            raw_last_orders_chain = state.get("last_orders_chain")
            last_orders_chain = _normalize_supported_chain(raw_last_orders_chain)
            if raw_last_orders_chain and last_orders_chain is None:
                logger.bind(tag=TAG).warning(
                    f"key_action orders unsupported last_orders_chain={raw_last_orders_chain}"
                )
                return

            current_token = state.get("current_token")
            if current_token is not None and not isinstance(current_token, dict):
                logger.bind(tag=TAG).warning("key_action orders malformed current_token state")
                return

            raw_current_chain = (current_token or {}).get("chain")
            current_chain = _normalize_supported_chain(raw_current_chain)
            if raw_current_chain and current_chain is None:
                logger.bind(tag=TAG).warning(
                    f"key_action orders unsupported current_token chain={raw_current_chain}"
                )
                return

            chain = msg_chain or last_orders_chain or current_chain or "solana"
            logger.bind(tag=TAG).info(f"key_action orders chain={chain}")
            try:
                ave_list_orders(conn, chain=chain)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action orders error: {e}")

        elif action == "feed_source":
            source = msg_json.get("source", "trending")
            VALID_TOPICS = {"trending", "gainer", "loser", "new", "meme", "ai", "depin", "gamefi"}
            if source not in VALID_TOPICS:
                logger.bind(tag=TAG).warning(f"feed_source: unknown source '{source}', falling back to trending")
                source = "trending"
            logger.bind(tag=TAG).info(f"key_action feed_source source={source}")
            try:
                ave_get_trending(conn, topic=source)
                state = getattr(conn, "ave_state", {})
                state["feed_source"] = source
                conn.ave_state = state
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action feed_source error: {e}")

        elif action == "feed_platform":
            platform = msg_json.get("platform", "")
            if platform not in VALID_FEED_PLATFORMS:
                logger.bind(tag=TAG).warning(f"feed_platform: unknown platform '{platform}'")
                return
            logger.bind(tag=TAG).info(f"key_action feed_platform platform={platform}")
            try:
                ave_get_trending(conn, topic="", platform=platform)
                state = getattr(conn, "ave_state", {})
                state["feed_source"] = "trending"
                state["feed_platform"] = platform
                conn.ave_state = state
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action feed_platform error: {e}")

        elif action == "signals":
            logger.bind(tag=TAG).info("key_action signals")
            try:
                ave_list_signals(conn)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action signals error: {e}")

        elif action == "watchlist":
            logger.bind(tag=TAG).info("key_action watchlist")
            try:
                ave_open_watchlist(conn)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action watchlist error: {e}")

        elif action == "signals_chain_cycle":
            state = getattr(conn, "ave_state", {})
            order = ["solana", "bsc"]
            current_chain = str(state.get("signals_chain") or "").strip().lower()
            if current_chain not in order:
                current_chain = order[0]
            next_chain = order[(order.index(current_chain) + 1) % len(order)]
            logger.bind(tag=TAG).info(f"key_action signals_chain_cycle -> {next_chain}")
            try:
                ave_list_signals(conn, chain=next_chain)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action signals_chain_cycle error: {e}")

        elif action == "watchlist_chain_cycle":
            state = getattr(conn, "ave_state", {})
            next_chain = _cycle_action_chain(state.get("watchlist_chain"), allow_all=True)
            logger.bind(tag=TAG).info(f"key_action watchlist_chain_cycle -> {next_chain}")
            try:
                ave_open_watchlist(conn, cursor=0, chain_filter=next_chain)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action watchlist_chain_cycle error: {e}")

        elif action == "portfolio_chain_cycle":
            state = getattr(conn, "ave_state", {})
            next_chain = _cycle_action_chain(state.get("portfolio_chain"), allow_all=False)
            logger.bind(tag=TAG).info(f"key_action portfolio_chain_cycle -> {next_chain}")
            try:
                ave_portfolio(conn, chain_filter=next_chain)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action portfolio_chain_cycle error: {e}")

        elif action == "explorer_sync":
            logger.bind(tag=TAG).info("key_action explorer_sync")
            try:
                await _send_display(conn, "explorer", _build_explorer_payload(conn))
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action explorer_sync error: {e}")

        elif action == "trade_mode_set":
            requested_mode = str(msg_json.get("mode", "") or "").strip().lower()
            logger.bind(tag=TAG).info(f"key_action trade_mode_set mode={requested_mode}")
            try:
                ave_set_trade_mode(conn, mode=requested_mode)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action trade_mode_set error: {e}")

        elif action == "watchlist_remove":
            state = getattr(conn, "ave_state", {})
            feed_rows = state.get("feed_token_list", [])
            try:
                cursor = int(msg_json.get("cursor", state.get("feed_cursor", 0)))
            except (TypeError, ValueError):
                cursor = state.get("feed_cursor", 0)
            if isinstance(feed_rows, list) and feed_rows:
                cursor = max(0, min(cursor, len(feed_rows) - 1))
            else:
                cursor = 0
            state["feed_cursor"] = cursor
            conn.ave_state = state

            selected_token = {}
            if isinstance(feed_rows, list) and 0 <= cursor < len(feed_rows):
                row = feed_rows[cursor]
                if isinstance(row, dict):
                    selected_token = {
                        "addr": row.get("addr", ""),
                        "chain": row.get("chain", ""),
                        "symbol": row.get("symbol", ""),
                    }
            if token_addr and token_has_chain:
                selected_token["addr"] = token_addr
                selected_token["chain"] = token_chain
            if (not selected_token.get("symbol")) and isinstance(feed_rows, list) and 0 <= cursor < len(feed_rows):
                row = feed_rows[cursor]
                if isinstance(row, dict):
                    selected_token["symbol"] = str(row.get("symbol") or "").strip()

            if not selected_token.get("addr") or not selected_token.get("chain"):
                logger.bind(tag=TAG).warning("key_action watchlist_remove missing token context")
                return

            logger.bind(tag=TAG).info(
                f"key_action watchlist_remove cursor={cursor} addr={selected_token['addr']} chain={selected_token['chain']}"
            )
            try:
                ave_remove_current_watchlist_token(conn, token=selected_token, cursor=cursor)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action watchlist_remove error: {e}")

        elif action in ("feed_prev", "feed_next"):
            state = getattr(conn, "ave_state", {})
            lst = state.get("feed_token_list", [])
            if not lst:
                logger.bind(tag=TAG).info(f"key_action {action} ignored: feed_token_list is empty")
                return

            cursor = state.get("feed_cursor", 0)
            is_next = (action == "feed_next")

            if is_next:
                if cursor >= len(lst) - 1:
                    logger.bind(tag=TAG).info(
                        f"key_action {action} ignored at boundary cursor={cursor} size={len(lst)}"
                    )
                    return
                cursor += 1
            else:
                if cursor <= 0:
                    logger.bind(tag=TAG).info(
                        f"key_action {action} ignored at boundary cursor={cursor} size={len(lst)}"
                    )
                    return
                cursor -= 1

            state["feed_cursor"] = cursor
            if state.get("feed_mode") == "search":
                state["search_cursor"] = cursor
                _set_search_session_cursor(state, cursor)
            tok = lst[cursor] if cursor < len(lst) else {}
            tok_addr = str(tok.get("addr") or "").strip() if isinstance(tok, dict) else ""
            tok_chain_raw = tok.get("chain") if isinstance(tok, dict) else ""
            tok_chain = _normalize_supported_chain(tok_chain_raw)
            if not tok_addr:
                logger.bind(tag=TAG).warning(f"key_action {action} missing addr at cursor={cursor}")
                conn.ave_state = state
                return
            if tok_chain is None or not tok_chain:
                logger.bind(tag=TAG).warning(
                    f"key_action {action} invalid chain at cursor={cursor}: {tok_chain_raw}"
                )
                conn.ave_state = state
                return
            logger.bind(tag=TAG).info(
                f"key_action {action} cursor={cursor} addr={tok_addr} chain={tok_chain}"
            )
            conn.ave_state = state
            try:
                ave_token_detail(conn, addr=tok_addr, chain=tok_chain,
                                 feed_cursor=cursor, feed_total=len(lst))
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action {action} error: {e}")

        elif action == "back":
            state = getattr(conn, "ave_state", {})
            pending = _get_pending_trade(conn)
            if pending.get("trade_id") and state.get("screen") in {"confirm", "limit_confirm"}:
                logger.bind(tag=TAG).info("key_action back → cancel pending trade")
                try:
                    ave_cancel_trade(conn)
                except Exception as e:
                    logger.bind(tag=TAG).error(f"key_action back→cancel error: {e}")
                return

            nav_from = state.get("nav_from", "feed")
            # Clear nav_from after use
            state.pop("nav_from", None)

            if nav_from == "portfolio":
                # Re-fetch portfolio to return to it
                logger.bind(tag=TAG).info("key_action back → portfolio")
                try:
                    ave_portfolio(conn)
                except Exception as e:
                    logger.bind(tag=TAG).error(f"key_action back→portfolio error: {e}")
            elif nav_from == "signals":
                logger.bind(tag=TAG).info("key_action back → signals (nav_from)")
                try:
                    ave_list_signals(conn)
                    return
                except Exception as e:
                    logger.bind(tag=TAG).error(f"key_action back→signals(nav_from) error: {e}")
            elif nav_from == "watchlist":
                logger.bind(tag=TAG).info("key_action back → watchlist (nav_from)")
                try:
                    ave_open_watchlist(conn, cursor=state.get("feed_cursor", 0))
                    return
                except Exception as e:
                    logger.bind(tag=TAG).error(f"key_action back→watchlist(nav_from) error: {e}")
            elif state.get("feed_mode") == "search":
                logger.bind(tag=TAG).info("key_action back → restore search feed")
                try:
                    payload = _restore_search_session_payload(state)
                    if payload:
                        conn.ave_state = state
                        await _send_display(conn, "feed", payload)
                        return
                    logger.bind(tag=TAG).info("key_action back → search session unavailable, falling back to feed")
                    source = state.get("feed_source", "trending")
                    platform = state.get("feed_platform", "")
                    if platform:
                        ave_get_trending(conn, topic="", platform=platform)
                    else:
                        ave_get_trending(conn, topic=source)
                    return
                except Exception as e:
                    logger.bind(tag=TAG).error(f"key_action back→search error: {e}")
            elif state.get("feed_mode") == "signals" or state.get("feed_source") == "signals":
                logger.bind(tag=TAG).info("key_action back → signals")
                try:
                    ave_list_signals(conn)
                    return
                except Exception as e:
                    logger.bind(tag=TAG).error(f"key_action back→signals error: {e}")
            elif state.get("feed_mode") == "watchlist" or state.get("feed_source") == "watchlist":
                logger.bind(tag=TAG).info("key_action back → watchlist")
                try:
                    ave_open_watchlist(conn, cursor=state.get("feed_cursor", 0))
                    return
                except Exception as e:
                    logger.bind(tag=TAG).error(f"key_action back→watchlist error: {e}")
            else:
                # Default: return to FEED (re-fetch last source/platform)
                source = state.get("feed_source", "trending")
                platform = state.get("feed_platform", "")
                logger.bind(tag=TAG).info(
                    f"key_action back → feed source={source} platform={platform or '-'}"
                )
                try:
                    if platform:
                        ave_get_trending(conn, topic="", platform=platform)
                    else:
                        ave_get_trending(conn, topic=source)
                except Exception as e:
                    logger.bind(tag=TAG).error(f"key_action back→feed error: {e}")

        elif action == "portfolio_watch":
            if not token_addr:
                logger.bind(tag=TAG).warning("key_action portfolio_watch missing token_id")
                return
            if not token_has_chain:
                logger.bind(tag=TAG).warning("key_action portfolio_watch missing chain")
                return
            logger.bind(tag=TAG).info(f"key_action portfolio_watch {token_addr} chain={token_chain}")
            state = getattr(conn, "ave_state", {})
            state["nav_from"] = "portfolio"
            conn.ave_state = state
            try:
                ave_token_detail(conn, addr=token_addr, chain=token_chain)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action portfolio_watch error: {e}")

        elif action == "portfolio_activity_detail":
            if not token_addr:
                logger.bind(tag=TAG).warning("key_action portfolio_activity_detail missing token_id")
                return
            if not token_has_chain:
                logger.bind(tag=TAG).warning("key_action portfolio_activity_detail missing chain")
                return
            symbol = str(msg_json.get("symbol", "") or "").strip()
            logger.bind(tag=TAG).info(
                f"key_action portfolio_activity_detail {token_addr} chain={token_chain} symbol={symbol}"
            )
            state = getattr(conn, "ave_state", {})
            state["nav_from"] = "portfolio"
            conn.ave_state = state
            try:
                ave_portfolio_activity_detail(conn, addr=token_addr, chain=token_chain, symbol=symbol)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action portfolio_activity_detail error: {e}")

        elif action == "portfolio_sell":
            addr = msg_json.get("addr", "")
            symbol = msg_json.get("symbol", "")
            balance_raw = msg_json.get("balance_raw", "")
            _, addr, chain, has_chain = _resolve_asset_ref(addr, msg_json.get("chain", ""))
            if not addr:
                logger.bind(tag=TAG).warning("key_action portfolio_sell missing addr")
                return
            if not has_chain:
                logger.bind(tag=TAG).warning("key_action portfolio_sell missing chain")
                return
            logger.bind(tag=TAG).info(f"key_action portfolio_sell {addr} chain={chain} symbol={symbol}")
            state = getattr(conn, "ave_state", {})
            state["nav_from"] = "portfolio"
            conn.ave_state = state
            try:
                ave_sell_token(conn, addr=addr, chain=chain, symbol=symbol,
                               holdings_amount=balance_raw or None, sell_ratio=1.0)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action portfolio_sell error: {e}")

        elif action == "disambiguation_select":
            state = getattr(conn, "ave_state", {})
            items = state.get("disambiguation_items", [])
            cursor = msg_json.get("cursor", state.get("disambiguation_cursor", 0))
            try:
                cursor = int(cursor)
            except (TypeError, ValueError):
                cursor = 0

            chosen = None
            if isinstance(items, list) and items:
                cursor = max(0, min(cursor, len(items) - 1))
                chosen = items[cursor]
                state["disambiguation_cursor"] = cursor

            if not isinstance(chosen, dict):
                chosen = {
                    "token_id": msg_json.get("token_id", ""),
                    "chain": msg_json.get("chain", raw_chain),
                    "symbol": msg_json.get("symbol", ""),
                }

            chosen_token_id = str(chosen.get("token_id") or msg_json.get("token_id") or "").strip()
            chosen_chain_value = chosen.get("chain") or msg_json.get("chain", "")
            chosen_symbol = str(chosen.get("symbol") or msg_json.get("symbol") or "").strip()
            _, chosen_addr, chosen_chain, chosen_has_chain = _resolve_asset_ref(
                chosen_token_id,
                chosen_chain_value,
            )
            if not chosen_addr:
                logger.bind(tag=TAG).warning("key_action disambiguation_select missing token_id")
                return
            if not chosen_has_chain:
                logger.bind(tag=TAG).warning("key_action disambiguation_select missing chain")
                return

            if not state.get("nav_from"):
                state["nav_from"] = "feed"
            if state.get("feed_mode") == "search":
                state["search_cursor"] = cursor
                state["feed_cursor"] = cursor
                _set_search_session_cursor(state, cursor)
            _set_feed_navigation_state(state, items, cursor=cursor)
            state["screen"] = "disambiguation"
            conn.ave_state = state
            logger.bind(tag=TAG).info(
                f"key_action disambiguation_select {chosen_addr} chain={chosen_chain} cursor={cursor}"
            )
            try:
                ave_token_detail(conn, addr=chosen_addr, chain=chosen_chain, symbol=chosen_symbol)
            except Exception as e:
                logger.bind(tag=TAG).error(f"key_action disambiguation_select error: {e}")

        else:
            logger.bind(tag=TAG).warning(f"Unknown key action: {action}")
