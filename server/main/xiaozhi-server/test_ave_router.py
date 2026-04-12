import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from core.connection import ConnectionHandler, TOOL_CALLING_RULES
from core.handle.intentHandler import analyze_intent_with_llm, process_intent_result
from core.handle.receiveAudioHandle import startToChat
from core.handle.textHandler.aveCommandRouter import (
    build_ave_context,
    missing_selection_reply,
    try_route_ave_command,
)
from core.handle.textHandler.keyActionHandler import KeyActionHandler
from core.handle.textHandler.listenMessageHandler import ListenTextMessageHandler
from core.providers.intent.intent_llm.intent_llm import IntentProvider as IntentLLMProvider
from core.providers.asr.dto.dto import InterfaceType
from core.utils.dialogue import Dialogue, Message
from plugins_func.functions import ave_tools
from plugins_func.register import Action, ActionResponse


class _FakeLogger:
    def bind(self, **kwargs):
        return self

    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


class _ImmediateExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args, **kwargs):
        self.calls.append((fn, args, kwargs))
        return fn(*args, **kwargs)


class _QueuedExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args, **kwargs):
        self.calls.append((fn, args, kwargs))
        return None

    def run_next(self):
        fn, args, kwargs = self.calls.pop(0)
        return fn(*args, **kwargs)


class _FakeCacheManager:
    def __init__(self):
        self.values = {}

    def get(self, cache_type, key):
        return self.values.get((cache_type, key))

    def set(self, cache_type, key, value):
        self.values[(cache_type, key)] = value


class _CapturingIntentLLM:
    def __init__(self):
        self.calls = []

    def response_no_stream(self, system_prompt, user_prompt):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )
        return '{"function_call": {"name": "continue_chat"}}'


class _FakeQueue:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


class _FakeTTS:
    def __init__(self):
        self.tts_text_queue = _FakeQueue()

    def tts_one_sentence(self, conn, content_type, content_detail=None):
        return None


class _CompletedFuture:
    def __init__(self, result):
        self._result = result

    def result(self, timeout=None):
        return self._result


class _BlockingLLM:
    def __init__(self):
        self.first_started = threading.Event()
        self.release_first = threading.Event()
        self.second_started = threading.Event()
        self.call_count = 0

    def response(self, session_id, dialogue):
        self.call_count += 1
        if self.call_count == 1:
            self.first_started.set()
            self.release_first.wait(timeout=2)
        else:
            self.second_started.set()
        return iter([f"reply-{self.call_count}"])


class AveRouterTests(unittest.IsolatedAsyncioTestCase):
    def _build_listen_conn(self, ave_state=None):
        conn = SimpleNamespace()
        conn.logger = _FakeLogger()
        conn.config = {"wakeup_words": [], "enable_greeting": True}
        conn.client_listen_mode = "auto"
        conn.client_have_voice = False
        conn.client_voice_stop = False
        conn.last_activity_time = 0
        conn.just_woken_up = False
        conn.asr = SimpleNamespace(interface_type=InterfaceType.NON_STREAM)
        conn.asr_audio = []
        conn.ave_state = ave_state or {}
        conn.reset_audio_states = MagicMock()
        conn.loop = asyncio.get_running_loop()
        return conn

    def _build_chat_conn(self, ave_state=None):
        conn = SimpleNamespace()
        conn.logger = _FakeLogger()
        conn.need_bind = False
        conn.max_output_size = 0
        conn.client_is_speaking = False
        conn.client_listen_mode = "auto"
        conn.headers = {}
        conn.config = {}
        conn.current_speaker = None
        conn.ave_state = ave_state or {}
        conn.executor = _ImmediateExecutor()
        conn.chat_calls = []

        def _chat(query, ave_context=None):
            captured_context = ave_context
            if captured_context is None:
                captured_context = getattr(conn, "ave_context", None)
            conn.chat_calls.append((query, captured_context))

        conn.chat = _chat
        return conn

    async def test_spotlight_buy_this_routes_directly_to_buy(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "current_token": {"addr": "addr-1", "chain": "solana", "symbol": "ROCKET"},
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_buy_token") as mock_buy:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "买这个",
                    "selection": {
                        "screen": "spotlight",
                        "token": {"addr": "addr-1", "chain": "solana", "symbol": "ROCKET"},
                    },
                },
            )

        start_chat.assert_not_awaited()
        mock_buy.assert_called_once()

    async def test_partial_selection_token_fails_closed_for_buy_this(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "current_token": {"addr": "stale-1", "chain": "solana", "symbol": "STALE"},
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("core.handle.textHandler.aveCommandRouter.send_stt_message", new=AsyncMock()) as send_stt, \
             patch("plugins_func.functions.ave_tools.ave_buy_token") as mock_buy:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "买这个",
                    "selection": {
                        "token": {"addr": "fresh-1", "chain": "solana", "symbol": "FRESH"},
                    },
                },
            )

        start_chat.assert_not_awaited()
        mock_buy.assert_not_called()
        send_stt.assert_awaited_once_with(conn, missing_selection_reply("买这个"))

    async def test_partial_selection_token_missing_chain_fails_closed_for_watch_this(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "current_token": {"addr": "stale-1", "chain": "solana", "symbol": "STALE"},
                "feed_token_list": [
                    {"addr": "fresh-1", "chain": "base", "symbol": "FRESH"},
                ],
                "feed_cursor": 0,
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("core.handle.textHandler.aveCommandRouter.send_stt_message", new=AsyncMock()) as send_stt, \
             patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "看这个",
                    "selection": {
                        "screen": "feed",
                        "token": {"addr": "fresh-1", "symbol": "FRESH"},
                    },
                },
            )

        start_chat.assert_not_awaited()
        mock_detail.assert_not_called()
        send_stt.assert_awaited_once_with(conn, missing_selection_reply("看这个"))

    async def test_confirm_confirm_routes_directly_to_confirm_trade(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "confirm",
                "pending_trade": {"trade_id": "trade-1", "symbol": "ROCKET"},
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_confirm_trade") as mock_confirm:
            await handler.handle(conn, {"state": "detect", "text": "确认"})

        start_chat.assert_not_awaited()
        mock_confirm.assert_called_once_with(conn)

    async def test_confirm_cancel_routes_directly_to_cancel_trade(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "confirm",
                "pending_trade": {"trade_id": "trade-1", "symbol": "ROCKET"},
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_cancel_trade") as mock_cancel:
            await handler.handle(conn, {"state": "detect", "text": "取消"})

        start_chat.assert_not_awaited()
        mock_cancel.assert_called_once_with(conn)

    async def test_spotlight_add_to_watchlist_routes_directly(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "current_token": {"addr": "a1", "chain": "solana", "symbol": "BONK"},
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_add_current_watchlist_token") as add_current:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "收藏这个币",
                    "selection": {
                        "screen": "spotlight",
                        "token": {"addr": "a1", "chain": "solana", "symbol": "BONK"},
                    },
                },
            )

        start_chat.assert_not_awaited()
        add_current.assert_called_once_with(
            conn,
            token={"addr": "a1", "chain": "solana", "symbol": "BONK"},
        )

    async def test_add_to_watchlist_without_trusted_selection_fails_closed(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "spotlight"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("core.handle.textHandler.aveCommandRouter.send_stt_message", new=AsyncMock()) as send_stt, \
             patch("plugins_func.functions.ave_tools.ave_add_current_watchlist_token") as add_current:
            await handler.handle(conn, {"state": "detect", "text": "收藏这个币"})

        start_chat.assert_not_awaited()
        add_current.assert_not_called()
        send_stt.assert_awaited_once_with(conn, missing_selection_reply("收藏这个币"))

    async def test_open_watchlist_routes_without_llm(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_open_watchlist") as open_watchlist:
            await handler.handle(conn, {"state": "detect", "text": "打开观察列表"})

        start_chat.assert_not_awaited()
        open_watchlist.assert_called_once_with(conn)

    async def test_open_orders_routes_without_llm(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_list_orders") as list_orders:
            await handler.handle(conn, {"state": "detect", "text": "查看限价单"})

        start_chat.assert_not_awaited()
        list_orders.assert_called_once_with(conn)

    async def test_open_orders_english_routes_without_llm(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_list_orders") as list_orders:
            await handler.handle(conn, {"state": "detect", "text": "open orders"})

        start_chat.assert_not_awaited()
        list_orders.assert_called_once_with(conn)

    async def test_spotlight_remove_watchlist_routes_directly(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "current_token": {"addr": "a1", "chain": "solana", "symbol": "BONK"},
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_remove_current_watchlist_voice") as remove_current:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "取消收藏",
                    "selection": {
                        "screen": "spotlight",
                        "token": {"addr": "a1", "chain": "solana", "symbol": "BONK"},
                    },
                },
            )

        start_chat.assert_not_awaited()
        remove_current.assert_called_once_with(
            conn,
            token={"addr": "a1", "chain": "solana", "symbol": "BONK"},
        )

    async def test_confirm_uses_selection_screen_when_server_state_lags(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "pending_trade": {"trade_id": "trade-1", "symbol": "ROCKET"},
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("core.handle.textHandler.aveCommandRouter.send_stt_message", new=AsyncMock()) as send_stt, \
             patch("plugins_func.functions.ave_tools.ave_confirm_trade") as mock_confirm:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "确认",
                    "selection": {"screen": "confirm"},
                },
            )

        start_chat.assert_not_awaited()
        send_stt.assert_not_awaited()
        mock_confirm.assert_called_once_with(conn)

    async def test_cancel_uses_selection_screen_when_server_state_lags(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "pending_trade": {"trade_id": "trade-2", "symbol": "ROCKET"},
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("core.handle.textHandler.aveCommandRouter.send_stt_message", new=AsyncMock()) as send_stt, \
             patch("plugins_func.functions.ave_tools.ave_cancel_trade") as mock_cancel:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "取消",
                    "selection": {"screen": "confirm"},
                },
            )

        start_chat.assert_not_awaited()
        send_stt.assert_not_awaited()
        mock_cancel.assert_called_once_with(conn)

    async def test_feed_watch_this_routes_directly_to_token_detail(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "feed_token_list": [
                    {"addr": "feed-1", "chain": "solana", "symbol": "ROCKET"},
                ],
                "feed_cursor": 0,
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "看这个",
                    "selection": {
                        "screen": "feed",
                        "cursor": 0,
                        "token": {"addr": "feed-1", "chain": "solana", "symbol": "ROCKET"},
                    },
                },
            )

        start_chat.assert_not_awaited()
        mock_detail.assert_called_once_with(
            conn,
            addr="feed-1",
            chain="solana",
            symbol="ROCKET",
            feed_cursor=0,
            feed_total=1,
        )

    async def test_router_back_from_spotlight_signals_restores_signals_feed(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "feed_mode": "signals",
                "feed_source": "signals",
                "nav_from": "feed",
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_list_signals") as mock_signals, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(conn, {"state": "detect", "text": "返回"})

        start_chat.assert_not_awaited()
        mock_signals.assert_called_once_with(conn)
        mock_trending.assert_not_called()

    async def test_router_back_from_spotlight_watchlist_restores_watchlist_feed(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "feed_mode": "watchlist",
                "feed_source": "watchlist",
                "feed_cursor": 2,
                "nav_from": "feed",
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_open_watchlist") as mock_watchlist, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(conn, {"state": "detect", "text": "返回"})

        start_chat.assert_not_awaited()
        mock_watchlist.assert_called_once_with(conn, cursor=2)
        mock_trending.assert_not_called()

    async def test_router_back_from_search_spotlight_restores_search_payload(self):
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "feed_mode": "search",
                "feed_source": "trending",
                "search_query": "PEPE",
                "search_chain": "all",
                "search_cursor": 1,
                "search_session": {
                    "query": "PEPE",
                    "chain": "all",
                    "cursor": 1,
                    "items": [
                        {"token_id": "So111...", "chain": "solana", "symbol": "PEPE", "price": "$1.23"},
                        {"token_id": "0xabc...", "chain": "base", "symbol": "PEPE", "price": "$1.11"},
                    ],
                },
            }
        )

        with patch("plugins_func.functions.ave_tools._send_display", new=AsyncMock()) as send_display, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            handled = await try_route_ave_command(conn, "返回")

        self.assertTrue(handled)
        mock_trending.assert_not_called()
        send_display.assert_awaited_once()
        _, screen, payload = send_display.await_args.args
        self.assertEqual(screen, "feed")
        self.assertEqual(payload.get("mode"), "search")
        self.assertEqual(payload.get("search_query"), "PEPE")

    async def test_portfolio_watch_this_routes_directly_to_token_detail(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "portfolio",
                "portfolio_holdings": [
                    {"addr": "pf-1", "chain": "solana", "symbol": "ROCKET"},
                ],
                "portfolio_cursor": 0,
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "看这个",
                    "selection": {
                        "screen": "portfolio",
                        "cursor": 0,
                        "token": {"addr": "pf-1", "chain": "solana", "symbol": "ROCKET"},
                    },
                },
            )

        start_chat.assert_not_awaited()
        mock_detail.assert_called_once()
        self.assertEqual(conn.ave_state.get("nav_from"), "portfolio")

    async def test_portfolio_watch_this_rejects_without_portfolio_selection_state(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "portfolio"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("core.handle.textHandler.aveCommandRouter.send_stt_message", new=AsyncMock()) as send_stt, \
             patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(conn, {"state": "detect", "text": "看这个"})

        start_chat.assert_not_awaited()
        mock_detail.assert_not_called()
        send_stt.assert_awaited_once()

    async def test_kankan_symbol_routes_to_deterministic_search(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_search_token") as mock_search:
            await handler.handle(conn, {"state": "detect", "text": "看看ROCKET"})

        start_chat.assert_not_awaited()
        mock_search.assert_called_once_with(conn, keyword="ROCKET")

    async def test_kan_symbol_routes_to_deterministic_search(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_search_token") as mock_search:
            await handler.handle(conn, {"state": "detect", "text": "看ROCKET"})

        start_chat.assert_not_awaited()
        mock_search.assert_called_once_with(conn, keyword="ROCKET")

    async def test_search_symbol_routes_to_deterministic_search(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_search_token") as mock_search:
            await handler.handle(conn, {"state": "detect", "text": "搜索ROCKET"})

        start_chat.assert_not_awaited()
        mock_search.assert_called_once_with(conn, keyword="ROCKET")

    async def test_cha_symbol_routes_to_deterministic_search(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_search_token") as mock_search:
            await handler.handle(conn, {"state": "detect", "text": "查ROCKET"})

        start_chat.assert_not_awaited()
        mock_search.assert_called_once_with(conn, keyword="ROCKET")

    async def test_search_english_symbol_routes_to_deterministic_search(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_search_token") as mock_search:
            await handler.handle(conn, {"state": "detect", "text": "search ROCKET"})

        start_chat.assert_not_awaited()
        mock_search.assert_called_once_with(conn, keyword="ROCKET")

    async def test_sou_symbol_routes_to_deterministic_search(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_search_token") as mock_search:
            await handler.handle(conn, {"state": "detect", "text": "搜ROCKET"})

        start_chat.assert_not_awaited()
        mock_search.assert_called_once_with(conn, keyword="ROCKET")

    async def test_sou_yixia_symbol_routes_to_deterministic_search(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_search_token") as mock_search:
            await handler.handle(conn, {"state": "detect", "text": "搜一下ROCKET"})

        start_chat.assert_not_awaited()
        mock_search.assert_called_once_with(conn, keyword="ROCKET")

    async def test_cha_yixia_symbol_routes_to_deterministic_search(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_search_token") as mock_search:
            await handler.handle(conn, {"state": "detect", "text": "查一下ROCKET"})

        start_chat.assert_not_awaited()
        mock_search.assert_called_once_with(conn, keyword="ROCKET")

    async def test_lookup_symbol_routes_to_deterministic_search(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_search_token") as mock_search:
            await handler.handle(conn, {"state": "detect", "text": "look up ROCKET"})

        start_chat.assert_not_awaited()
        mock_search.assert_called_once_with(conn, keyword="ROCKET")

    async def test_buy_symbol_routes_to_buy_with_symbol_mapping(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "feed_tokens": {"ROCKET": {"addr": "rocket-addr", "chain": "base"}},
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_buy_token") as mock_buy:
            await handler.handle(conn, {"state": "detect", "text": "买ROCKET"})

        start_chat.assert_not_awaited()
        mock_buy.assert_called_once_with(
            conn,
            addr="rocket-addr",
            chain="base",
            symbol="ROCKET",
        )

    async def test_voice_market_buy_amount_uses_token_chain_native_context(self):
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "current_token": {"addr": "bsc-1", "chain": "bsc", "symbol": "CAKE"},
            }
        )

        with patch("plugins_func.functions.ave_tools.ave_buy_token") as mock_buy:
            routed = await try_route_ave_command(
                conn,
                "买这个 0.1",
                {
                    "selection": {
                        "screen": "spotlight",
                        "token": {"addr": "bsc-1", "chain": "bsc", "symbol": "CAKE"},
                    }
                },
            )

        self.assertTrue(routed)
        mock_buy.assert_called_once_with(
            conn,
            addr="bsc-1",
            chain="bsc",
            in_amount_sol=0.1,
            symbol="CAKE",
        )

    async def test_voice_limit_buy_missing_fields_are_filled_by_follow_up_dialogue(self):
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "current_token": {"addr": "base-1", "chain": "base", "symbol": "AERO"},
            }
        )

        with patch("core.handle.textHandler.aveCommandRouter.send_stt_message", new=AsyncMock()) as send_stt, \
             patch("plugins_func.functions.ave_tools.ave_limit_order") as mock_limit:
            routed = await try_route_ave_command(
                conn,
                "限价买这个",
                {
                    "selection": {
                        "screen": "spotlight",
                        "token": {"addr": "base-1", "chain": "base", "symbol": "AERO"},
                    }
                },
            )
            self.assertTrue(routed)
            self.assertEqual(conn.ave_state["voice_trade_draft"]["kind"], "limit_buy")
            self.assertEqual(conn.ave_state["voice_trade_draft"]["chain"], "base")
            send_stt.assert_awaited_with(conn, "目标价是多少美元？比如说 0.00012。")
            mock_limit.assert_not_called()

            await try_route_ave_command(conn, "0.00012")
            send_stt.assert_awaited_with(conn, "你想用多少 ETH 买入？比如说 0.1 ETH。")
            mock_limit.assert_not_called()

            await try_route_ave_command(conn, "0.1")

        self.assertNotIn("voice_trade_draft", conn.ave_state)
        mock_limit.assert_called_once_with(
            conn,
            addr="base-1",
            chain="base",
            in_amount_sol=0.1,
            limit_price=0.00012,
            symbol="AERO",
        )

    async def test_voice_market_buy_rejects_wrong_native_unit_for_chain(self):
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "current_token": {"addr": "bsc-1", "chain": "bsc", "symbol": "CAKE"},
            }
        )

        with patch("core.handle.textHandler.aveCommandRouter.send_stt_message", new=AsyncMock()) as send_stt, \
             patch("plugins_func.functions.ave_tools.ave_buy_token") as mock_buy:
            routed = await try_route_ave_command(
                conn,
                "买这个 0.1 SOL",
                {
                    "selection": {
                        "screen": "spotlight",
                        "token": {"addr": "bsc-1", "chain": "bsc", "symbol": "CAKE"},
                    }
                },
            )

        self.assertTrue(routed)
        send_stt.assert_awaited_once_with(conn, "这条链下单金额请用 BNB 表示。")
        mock_buy.assert_not_called()

    async def test_non_router_utterance_falls_through_to_chat(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})
        message = {
            "state": "detect",
            "text": "最近怎么样",
            "selection": {
                "screen": "feed",
                "cursor": 1,
                "token": {"addr": "feed-2", "chain": "base", "symbol": "NEW"},
            },
        }

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_search_token") as mock_search:
            await handler.handle(conn, message)

        mock_search.assert_not_called()
        start_chat.assert_awaited_once_with(conn, "最近怎么样", message_payload=message)

    async def test_open_ended_chat_path_receives_ave_context(self):
        conn = self._build_chat_conn(
            {
                "screen": "feed",
                "feed_source": "trending",
                "feed_platform": "",
                "feed_cursor": 0,
                "feed_token_list": [
                    {"addr": "a1", "chain": "solana", "symbol": "ROCKET"},
                    {"addr": "a2", "chain": "solana", "symbol": "MOON"},
                ],
            }
        )

        with patch("core.handle.receiveAudioHandle.send_stt_message", new=AsyncMock()) as send_stt, \
             patch("core.handle.receiveAudioHandle.handle_user_intent", new=AsyncMock(return_value=False)):
            await startToChat(conn, "聊聊这个代币")

        send_stt.assert_awaited_once_with(conn, "聊聊这个代币")
        self.assertTrue(hasattr(conn, "ave_context"))
        self.assertEqual(conn.chat_calls[0][0], "聊聊这个代币")
        self.assertIsNotNone(conn.chat_calls[0][1])
        self.assertEqual(conn.chat_calls[0][1]["screen"], "feed")
        self.assertEqual(conn.chat_calls[0][1]["feed_visible_symbols"], ["ROCKET", "MOON"])

    async def test_open_ended_chat_path_preserves_explicit_selection_context(self):
        conn = self._build_chat_conn(
            {
                "screen": "feed",
                "feed_source": "trending",
                "feed_cursor": 0,
                "feed_token_list": [
                    {"addr": "stale-1", "chain": "solana", "symbol": "OLD"},
                    {"addr": "stale-2", "chain": "solana", "symbol": "OLDER"},
                ],
                "current_token": {"addr": "stale-spot", "chain": "solana", "symbol": "STALE"},
            }
        )
        payload = {
            "state": "detect",
            "text": "帮我分析这个",
            "selection": {
                "screen": "feed",
                "cursor": 1,
                "token": {"addr": "fresh-2", "chain": "base", "symbol": "FRESH"},
            },
        }

        with patch("core.handle.receiveAudioHandle.send_stt_message", new=AsyncMock()) as send_stt, \
             patch("core.handle.receiveAudioHandle.handle_user_intent", new=AsyncMock(return_value=False)):
            await startToChat(conn, "帮我分析这个", message_payload=payload)

        send_stt.assert_awaited_once_with(conn, "帮我分析这个")
        self.assertEqual(conn.chat_calls[0][1]["screen"], "feed")
        self.assertEqual(
            conn.chat_calls[0][1]["current_token"],
            {"addr": "fresh-2", "chain": "base", "symbol": "FRESH"},
        )
        self.assertTrue(conn.chat_calls[0][1]["has_trusted_selection"])
        self.assertEqual(conn.chat_calls[0][1]["selection_source"], "explicit")

    async def test_start_to_chat_fail_closes_for_zhege_family_without_trusted_selection(self):
        utterances = [
            "给我讲讲这个",
            "讲讲这个",
            "说说这个",
            "聊聊这个",
            "这个如何",
        ]

        for utterance in utterances:
            with self.subTest(utterance=utterance):
                conn = self._build_chat_conn({"screen": "feed"})

                with patch(
                    "core.handle.receiveAudioHandle.try_route_ave_command",
                    new=AsyncMock(return_value=False),
                ) as try_route, patch(
                    "core.handle.receiveAudioHandle.handle_user_intent",
                    new=AsyncMock(return_value=False),
                ) as handle_intent, patch(
                    "core.handle.receiveAudioHandle.send_stt_message",
                    new=AsyncMock(),
                ) as send_stt:
                    await startToChat(conn, utterance)

                try_route.assert_awaited_once_with(conn, utterance, None)
                send_stt.assert_awaited_once_with(conn, missing_selection_reply(utterance))
                handle_intent.assert_not_awaited()
                self.assertEqual(conn.chat_calls, [])

    async def test_start_to_chat_routes_spoken_commands_before_intent(self):
        conn = self._build_chat_conn(
            {
                "screen": "spotlight",
                "current_token": {"addr": "a1", "chain": "solana", "symbol": "ROCKET"},
            }
        )
        payload = {
            "state": "detect",
            "text": "买这个",
            "selection": {
                "screen": "spotlight",
                "token": {"addr": "a1", "chain": "solana", "symbol": "ROCKET"},
            },
        }

        with patch("core.handle.receiveAudioHandle.try_route_ave_command", new=AsyncMock(return_value=True)) as try_route, \
             patch("core.handle.receiveAudioHandle.handle_user_intent", new=AsyncMock()) as handle_intent, \
             patch("core.handle.receiveAudioHandle.send_stt_message", new=AsyncMock()) as send_stt:
            await startToChat(conn, "买这个", message_payload=payload)

        try_route.assert_awaited_once_with(conn, "买这个", payload)
        handle_intent.assert_not_awaited()
        send_stt.assert_not_awaited()
        self.assertEqual(conn.chat_calls, [])

    async def test_start_to_chat_speaker_json_routes_using_content_not_raw_json(self):
        conn = self._build_chat_conn(
            {
                "screen": "spotlight",
                "current_token": {"addr": "a1", "chain": "solana", "symbol": "ROCKET"},
            }
        )
        payload = (
            '{"speaker":"Alice","language":"zh","content":"买这个",'
            '"selection":{"screen":"spotlight","token":{"addr":"a1","chain":"solana","symbol":"ROCKET"}}}'
        )

        with patch("core.handle.receiveAudioHandle.try_route_ave_command", new=AsyncMock(return_value=True)) as try_route, \
             patch("core.handle.receiveAudioHandle.handle_user_intent", new=AsyncMock()) as handle_intent:
            await startToChat(conn, payload)

        try_route.assert_awaited_once_with(
            conn,
            "买这个",
            {
                "speaker": "Alice",
                "language": "zh",
                "content": "买这个",
                "selection": {
                    "screen": "spotlight",
                    "token": {"addr": "a1", "chain": "solana", "symbol": "ROCKET"},
                },
            },
        )
        handle_intent.assert_not_awaited()
        self.assertEqual(conn.current_speaker, "Alice")

    async def test_feed_watch_uses_feed_selection_not_stale_spotlight_token(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "current_token": {"addr": "stale-spot", "chain": "solana", "symbol": "OLD"},
                "feed_token_list": [
                    {"addr": "feed-2", "chain": "base", "symbol": "NEW"},
                ],
                "feed_cursor": 0,
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "看这个",
                    "selection": {
                        "screen": "feed",
                        "cursor": 0,
                        "token": {"addr": "feed-2", "chain": "base", "symbol": "NEW"},
                    },
                },
            )

        start_chat.assert_not_awaited()
        mock_detail.assert_called_once_with(
            conn,
            addr="feed-2",
            chain="base",
            symbol="NEW",
            feed_cursor=0,
            feed_total=1,
        )

    async def test_feed_watch_route_preserves_turn_selection_context_after_success(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "feed_cursor": 0,
                "feed_token_list": [
                    {"addr": "feed-1", "chain": "solana", "symbol": "OLD"},
                    {"addr": "feed-2", "chain": "base", "symbol": "NEW"},
                ],
            }
        )

        def _detail_side_effect(
            passed_conn,
            addr,
            chain,
            symbol="",
            feed_cursor=None,
            feed_total=None,
        ):
            passed_conn.ave_state["screen"] = "spotlight"
            passed_conn.ave_state["current_token"] = {
                "addr": "stale-spot",
                "chain": "solana",
                "symbol": "STALE",
            }

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_token_detail", side_effect=_detail_side_effect) as mock_detail:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "看这个",
                    "selection": {
                        "screen": "feed",
                        "cursor": 1,
                        "token": {"addr": "feed-2", "chain": "base", "symbol": "NEW"},
                    },
                },
            )

        start_chat.assert_not_awaited()
        mock_detail.assert_called_once_with(
            conn,
            addr="feed-2",
            chain="base",
            symbol="NEW",
            feed_cursor=1,
            feed_total=2,
        )
        self.assertEqual(conn.ave_context["screen"], "feed")
        self.assertEqual(conn.ave_context["feed_cursor"], 1)
        self.assertEqual(
            conn.ave_context["current_token"],
            {"addr": "feed-2", "chain": "base", "symbol": "NEW"},
        )
        self.assertTrue(conn.ave_context["has_trusted_selection"])
        self.assertEqual(conn.ave_context["selection_source"], "explicit")

    async def test_portfolio_watch_uses_portfolio_selection_not_stale_spotlight_token(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "portfolio",
                "current_token": {"addr": "stale-spot", "chain": "solana", "symbol": "OLD"},
                "portfolio_holdings": [
                    {"addr": "pf-2", "chain": "eth", "symbol": "REAL"},
                ],
                "portfolio_cursor": 0,
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "看这个",
                    "selection": {
                        "screen": "portfolio",
                        "cursor": 0,
                        "token": {"addr": "pf-2", "chain": "eth", "symbol": "REAL"},
                    },
                },
            )

        start_chat.assert_not_awaited()
        mock_detail.assert_called_once_with(
            conn,
            addr="pf-2",
            chain="eth",
            symbol="REAL",
            feed_cursor=None,
            feed_total=None,
        )

    async def test_portfolio_voice_watch_then_back_returns_to_portfolio(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "portfolio",
                "portfolio_holdings": [{"addr": "pf-2", "chain": "eth", "symbol": "REAL"}],
                "portfolio_cursor": 0,
            }
        )

        def _detail_side_effect(
            passed_conn,
            addr,
            chain,
            symbol="",
            feed_cursor=None,
            feed_total=None,
        ):
            passed_conn.ave_state["screen"] = "spotlight"

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_token_detail", side_effect=_detail_side_effect), \
             patch("plugins_func.functions.ave_tools.ave_portfolio") as mock_portfolio, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "看这个",
                    "selection": {
                        "screen": "portfolio",
                        "cursor": 0,
                        "token": {"addr": "pf-2", "chain": "eth", "symbol": "REAL"},
                    },
                },
            )
            await handler.handle(conn, {"state": "detect", "text": "返回"})

        start_chat.assert_not_awaited()
        mock_portfolio.assert_called_once_with(conn)
        mock_trending.assert_not_called()

    async def test_confirm_command_rejects_when_not_on_confirm_screen(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "pending_trade": {"trade_id": "trade-1", "symbol": "ROCKET"},
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("core.handle.textHandler.aveCommandRouter.send_stt_message", new=AsyncMock()) as send_stt, \
             patch("plugins_func.functions.ave_tools.ave_confirm_trade") as mock_confirm:
            await handler.handle(conn, {"state": "detect", "text": "确认"})

        start_chat.assert_not_awaited()
        mock_confirm.assert_not_called()
        send_stt.assert_awaited_once()

    async def test_cancel_command_rejects_when_not_on_confirm_screen(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "pending_trade": {"trade_id": "trade-1", "symbol": "ROCKET"},
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("core.handle.textHandler.aveCommandRouter.send_stt_message", new=AsyncMock()) as send_stt, \
             patch("plugins_func.functions.ave_tools.ave_cancel_trade") as mock_cancel:
            await handler.handle(conn, {"state": "detect", "text": "取消"})

        start_chat.assert_not_awaited()
        mock_cancel.assert_not_called()
        send_stt.assert_awaited_once()

    async def test_back_routes_to_portfolio_when_nav_from_portfolio(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "nav_from": "portfolio",
                "feed_source": "gainer",
                "feed_platform": "pump_in_hot",
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_portfolio") as mock_portfolio, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(conn, {"state": "detect", "text": "返回"})

        start_chat.assert_not_awaited()
        mock_portfolio.assert_called_once_with(conn)
        mock_trending.assert_not_called()

    async def test_back_on_confirm_cancels_pending_trade(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "confirm",
                "pending_trade": {"trade_id": "trade-1", "symbol": "ROCKET"},
                "feed_source": "gainer",
                "feed_platform": "pump_in_hot",
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_cancel_trade") as mock_cancel, \
             patch("plugins_func.functions.ave_tools.ave_portfolio") as mock_portfolio, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(conn, {"state": "detect", "text": "返回"})

        start_chat.assert_not_awaited()
        mock_cancel.assert_called_once_with(conn)
        mock_portfolio.assert_not_called()
        mock_trending.assert_not_called()

    async def test_back_uses_selection_screen_when_server_state_lags(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "pending_trade": {"trade_id": "trade-3", "symbol": "ROCKET"},
                "feed_source": "gainer",
                "feed_platform": "pump_in_hot",
            }
        )

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_cancel_trade") as mock_cancel, \
             patch("plugins_func.functions.ave_tools.ave_portfolio") as mock_portfolio, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "返回",
                    "selection": {"screen": "confirm"},
                },
            )

        start_chat.assert_not_awaited()
        mock_cancel.assert_called_once_with(conn)
        mock_portfolio.assert_not_called()
        mock_trending.assert_not_called()

    async def test_feed_command_on_confirm_cancels_pending_trade_before_refresh(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "confirm",
                "pending_trade": {"trade_id": "trade-1", "symbol": "ROCKET"},
            }
        )
        call_order = []

        def _cancel_side_effect(passed_conn):
            call_order.append(("cancel", passed_conn))

        def _feed_side_effect(passed_conn, topic=""):
            call_order.append(("feed", passed_conn, topic))

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_cancel_trade", side_effect=_cancel_side_effect) as mock_cancel, \
             patch("plugins_func.functions.ave_tools.ave_get_trending", side_effect=_feed_side_effect) as mock_trending:
            await handler.handle(conn, {"state": "detect", "text": "看热门"})

        start_chat.assert_not_awaited()
        mock_cancel.assert_called_once_with(conn)
        mock_trending.assert_called_once_with(conn)
        self.assertEqual(call_order, [("cancel", conn), ("feed", conn, "")])

    async def test_feed_command_uses_selection_screen_to_cancel_pending_trade_before_refresh(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "pending_trade": {"trade_id": "trade-4", "symbol": "ROCKET"},
            }
        )
        call_order = []

        def _cancel_side_effect(passed_conn):
            call_order.append(("cancel", passed_conn))

        def _feed_side_effect(passed_conn, topic=""):
            call_order.append(("feed", passed_conn, topic))

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_cancel_trade", side_effect=_cancel_side_effect) as mock_cancel, \
             patch("plugins_func.functions.ave_tools.ave_get_trending", side_effect=_feed_side_effect) as mock_trending:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "看热门",
                    "selection": {"screen": "confirm"},
                },
            )

        start_chat.assert_not_awaited()
        mock_cancel.assert_called_once_with(conn)
        mock_trending.assert_called_once_with(conn)
        self.assertEqual(call_order, [("cancel", conn), ("feed", conn, "")])

    async def test_portfolio_command_on_limit_confirm_cancels_pending_trade_before_opening_portfolio(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "limit_confirm",
                "pending_trade": {"trade_id": "trade-2", "symbol": "ROCKET"},
            }
        )
        call_order = []

        def _cancel_side_effect(passed_conn):
            call_order.append(("cancel", passed_conn))

        def _portfolio_side_effect(passed_conn):
            call_order.append(("portfolio", passed_conn))

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_cancel_trade", side_effect=_cancel_side_effect) as mock_cancel, \
             patch("plugins_func.functions.ave_tools.ave_portfolio", side_effect=_portfolio_side_effect) as mock_portfolio:
            await handler.handle(conn, {"state": "detect", "text": "我的持仓"})

        start_chat.assert_not_awaited()
        mock_cancel.assert_called_once_with(conn)
        mock_portfolio.assert_called_once_with(conn)
        self.assertEqual(call_order, [("cancel", conn), ("portfolio", conn)])

    async def test_open_orders_command_on_limit_confirm_cancels_pending_trade_before_opening_orders(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "limit_confirm",
                "pending_trade": {"trade_id": "trade-2", "symbol": "ROCKET"},
            }
        )
        call_order = []

        def _cancel_side_effect(passed_conn):
            call_order.append(("cancel", passed_conn))

        def _orders_side_effect(passed_conn):
            call_order.append(("orders", passed_conn))

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_cancel_trade", side_effect=_cancel_side_effect) as mock_cancel, \
             patch("plugins_func.functions.ave_tools.ave_list_orders", side_effect=_orders_side_effect) as mock_orders:
            await handler.handle(conn, {"state": "detect", "text": "我的挂单"})

        start_chat.assert_not_awaited()
        mock_cancel.assert_called_once_with(conn)
        mock_orders.assert_called_once_with(conn)
        self.assertEqual(call_order, [("cancel", conn), ("orders", conn)])

    async def test_search_command_uses_selection_screen_to_cancel_pending_trade_before_search(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "pending_trade": {"trade_id": "trade-5", "symbol": "ROCKET"},
            }
        )
        call_order = []

        def _cancel_side_effect(passed_conn):
            call_order.append(("cancel", passed_conn))

        def _search_side_effect(passed_conn, keyword=""):
            call_order.append(("search", passed_conn, keyword))

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_cancel_trade", side_effect=_cancel_side_effect) as mock_cancel, \
             patch("plugins_func.functions.ave_tools.ave_search_token", side_effect=_search_side_effect) as mock_search:
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "看ROCKET",
                    "selection": {"screen": "limit_confirm"},
                },
            )

        start_chat.assert_not_awaited()
        mock_cancel.assert_called_once_with(conn)
        mock_search.assert_called_once_with(conn, keyword="ROCKET")
        self.assertEqual(call_order, [("cancel", conn), ("search", conn, "ROCKET")])

    async def test_search_command_on_limit_confirm_cancels_pending_trade_before_search(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "limit_confirm",
                "pending_trade": {"trade_id": "trade-3", "symbol": "ROCKET"},
            }
        )
        call_order = []

        def _cancel_side_effect(passed_conn):
            call_order.append(("cancel", passed_conn))

        def _search_side_effect(passed_conn, keyword=""):
            call_order.append(("search", passed_conn, keyword))

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_cancel_trade", side_effect=_cancel_side_effect) as mock_cancel, \
             patch("plugins_func.functions.ave_tools.ave_search_token", side_effect=_search_side_effect) as mock_search:
            await handler.handle(conn, {"state": "detect", "text": "看ROCKET"})

        start_chat.assert_not_awaited()
        mock_cancel.assert_called_once_with(conn)
        mock_search.assert_called_once_with(conn, keyword="ROCKET")
        self.assertEqual(call_order, [("cancel", conn), ("search", conn, "ROCKET")])

    def test_context_allowed_actions_exclude_watch_without_trusted_selection(self):
        conn = self._build_chat_conn(
            {
                "screen": "feed",
                "feed_tokens": {"CACHED": {"addr": "a1", "chain": "solana"}},
            }
        )
        ave_context = build_ave_context(conn)
        self.assertNotIn("watch_current", ave_context["allowed_actions"])

    def test_context_allowed_actions_buy_only_on_spotlight_with_trusted_selection(self):
        feed_conn = self._build_chat_conn(
            {
                "screen": "feed",
                "feed_token_list": [{"addr": "a1", "chain": "solana", "symbol": "A"}],
                "feed_cursor": 0,
            }
        )
        spot_conn = self._build_chat_conn(
            {
                "screen": "spotlight",
                "current_token": {"addr": "a2", "chain": "base", "symbol": "B"},
            }
        )
        self.assertNotIn("buy_current", build_ave_context(feed_conn)["allowed_actions"])
        self.assertIn(
            "buy_current",
            build_ave_context(
                spot_conn,
                selection_payload={
                    "screen": "spotlight",
                    "token": {"addr": "a2", "chain": "base", "symbol": "B"},
                },
            )["allowed_actions"],
        )

    def test_context_allowed_actions_watchlist_add_remove_only_on_spotlight_with_trusted_selection(self):
        conn = self._build_chat_conn(
            {
                "screen": "spotlight",
                "current_token": {"addr": "a2", "chain": "base", "symbol": "B"},
            }
        )
        ave_context = build_ave_context(
            conn,
            selection_payload={
                "screen": "spotlight",
                "token": {"addr": "a2", "chain": "base", "symbol": "B"},
            },
        )
        self.assertIn("add_to_watchlist", ave_context["allowed_actions"])
        self.assertIn("remove_from_watchlist", ave_context["allowed_actions"])
        self.assertIn("open_watchlist", ave_context["allowed_actions"])

    def test_context_feed_visible_symbols_prefers_ordered_feed_list(self):
        conn = self._build_chat_conn(
            {
                "screen": "feed",
                "feed_token_list": [{"addr": "a1", "chain": "solana", "symbol": "VISIBLE"}],
                "feed_tokens": {
                    "VISIBLE": {"addr": "a1", "chain": "solana"},
                    "STALE": {"addr": "a2", "chain": "base"},
                },
            }
        )
        ave_context = build_ave_context(conn)
        self.assertEqual(ave_context["feed_visible_symbols"], ["VISIBLE"])

    def test_context_explicit_selection_cursor_overrides_stale_server_feed_cursor(self):
        conn = self._build_chat_conn(
            {
                "screen": "feed",
                "feed_cursor": 0,
                "feed_token_list": [
                    {"addr": "stale-1", "chain": "solana", "symbol": "FIRST"},
                    {"addr": "fresh-2", "chain": "base", "symbol": "SECOND"},
                ],
            }
        )

        ave_context = build_ave_context(
            conn,
            selection_payload={
                "screen": "feed",
                "cursor": 1,
                "token": {"addr": "fresh-2", "chain": "base", "symbol": "SECOND"},
            },
        )

        self.assertEqual(ave_context["feed_cursor"], 1)

    def test_context_browse_selection_cursor_uses_feed_navigation_state(self):
        conn = self._build_chat_conn(
            {
                "screen": "browse",
                "feed_mode": "signals",
                "feed_cursor": 0,
                "feed_token_list": [
                    {"addr": "stale-1", "chain": "solana", "symbol": "FIRST"},
                    {"addr": "fresh-2", "chain": "base", "symbol": "SECOND"},
                ],
            }
        )

        ave_context = build_ave_context(
            conn,
            selection_payload={
                "screen": "browse",
                "cursor": 1,
                "token": {"addr": "fresh-2", "chain": "base", "symbol": "SECOND"},
            },
        )

        self.assertEqual(ave_context["screen"], "browse")
        self.assertEqual(ave_context["feed_cursor"], 1)
        self.assertIn("watch_current", ave_context["allowed_actions"])

    def test_context_non_feed_selection_cursor_does_not_override_feed_cursor(self):
        conn = self._build_chat_conn(
            {
                "screen": "feed",
                "feed_cursor": 0,
            }
        )

        ave_context = build_ave_context(
            conn,
            selection_payload={
                "screen": "portfolio",
                "cursor": 3,
                "token": {"addr": "fresh-2", "chain": "base", "symbol": "SECOND"},
            },
        )

        self.assertEqual(ave_context["screen"], "portfolio")
        self.assertEqual(ave_context["feed_cursor"], 0)

    def test_context_browse_selection_is_trusted(self):
        conn = self._build_chat_conn(
            {
                "screen": "browse",
                "feed_mode": "watchlist",
                "feed_cursor": 0,
                "feed_token_list": [
                    {"addr": "wl-1", "chain": "solana", "symbol": "BONK"},
                ],
            }
        )

        ave_context = build_ave_context(
            conn,
            selection_payload={
                "screen": "browse",
                "cursor": 0,
                "token": {"addr": "wl-1", "chain": "solana", "symbol": "BONK"},
            },
        )

        self.assertTrue(ave_context["has_trusted_selection"])
        self.assertEqual(
            ave_context["current_token"],
            {"addr": "wl-1", "chain": "solana", "symbol": "BONK"},
        )

    def test_context_without_explicit_selection_omits_current_token(self):
        conn = self._build_chat_conn(
            {
                "screen": "feed",
                "feed_cursor": 0,
                "feed_token_list": [
                    {"addr": "feed-1", "chain": "solana", "symbol": "VISIBLE"},
                ],
                "current_token": {"addr": "stale-spot", "chain": "base", "symbol": "OLD"},
            }
        )

        ave_context = build_ave_context(conn)

        self.assertFalse(ave_context["has_trusted_selection"])
        self.assertIsNone(ave_context["current_token"])
        self.assertNotIn("watch_current", ave_context["allowed_actions"])
        self.assertNotIn("buy_current", ave_context["allowed_actions"])

    async def test_open_ended_deictic_chat_fails_closed_without_trusted_selection(self):
        conn = self._build_chat_conn(
            {
                "screen": "feed",
                "feed_cursor": 0,
                "feed_token_list": [
                    {"addr": "stale-1", "chain": "solana", "symbol": "STALE"},
                ],
                "current_token": {"addr": "stale-spot", "chain": "base", "symbol": "OLD"},
            }
        )

        with patch("core.handle.receiveAudioHandle.try_route_ave_command", new=AsyncMock(return_value=False)) as try_route, \
             patch("core.handle.receiveAudioHandle.handle_user_intent", new=AsyncMock()) as handle_intent, \
             patch("core.handle.receiveAudioHandle.send_stt_message", new=AsyncMock()) as send_stt:
            await startToChat(conn, "这个能买吗")

        try_route.assert_awaited_once_with(conn, "这个能买吗", None)
        handle_intent.assert_not_awaited()
        send_stt.assert_awaited_once_with(conn, "请先在界面上选中你要操作的代币，然后再说一次。")
        self.assertEqual(conn.chat_calls, [])

    async def test_common_deictic_variants_fail_closed_without_trusted_selection(self):
        utterances = ("它能买吗", "这币还能涨吗", "给我讲讲它")

        for utterance in utterances:
            conn = self._build_chat_conn(
                {
                    "screen": "feed",
                    "feed_cursor": 0,
                    "feed_token_list": [
                        {"addr": "stale-1", "chain": "solana", "symbol": "STALE"},
                    ],
                }
            )

            with self.subTest(utterance=utterance):
                with patch("core.handle.receiveAudioHandle.try_route_ave_command", new=AsyncMock(return_value=False)) as try_route, \
                     patch("core.handle.receiveAudioHandle.handle_user_intent", new=AsyncMock()) as handle_intent, \
                     patch("core.handle.receiveAudioHandle.send_stt_message", new=AsyncMock()) as send_stt:
                    await startToChat(conn, utterance)

                try_route.assert_awaited_once_with(conn, utterance, None)
                handle_intent.assert_not_awaited()
                send_stt.assert_awaited_once_with(
                    conn,
                    "请先在界面上选中你要操作的代币，然后再说一次。",
                )
                self.assertEqual(conn.chat_calls, [])

    async def test_extended_deictic_variants_fail_closed_without_trusted_selection(self):
        utterances = ("这只币怎么样", "聊聊这只币", "说说这只币", "看看这只币", "看看这币", "说说它")

        for utterance in utterances:
            conn = self._build_chat_conn(
                {
                    "screen": "feed",
                    "feed_cursor": 0,
                    "feed_token_list": [
                        {"addr": "stale-1", "chain": "solana", "symbol": "STALE"},
                    ],
                    "current_token": {"addr": "stale-spot", "chain": "base", "symbol": "OLD"},
                }
            )

            with self.subTest(utterance=utterance):
                with patch("core.handle.receiveAudioHandle.try_route_ave_command", new=AsyncMock(return_value=False)) as try_route, \
                     patch("core.handle.receiveAudioHandle.handle_user_intent", new=AsyncMock()) as handle_intent, \
                     patch("core.handle.receiveAudioHandle.send_stt_message", new=AsyncMock()) as send_stt:
                    await startToChat(conn, utterance)

                try_route.assert_awaited_once_with(conn, utterance, None)
                handle_intent.assert_not_awaited()
                send_stt.assert_awaited_once_with(
                    conn,
                    "请先在界面上选中你要操作的代币，然后再说一次。",
                )
                self.assertEqual(conn.chat_calls, [])

    async def test_open_ended_deictic_chat_fails_closed_on_result_screen_without_selection(self):
        conn = self._build_chat_conn(
            {
                "screen": "result",
                "current_token": {"addr": "stale-spot", "chain": "base", "symbol": "OLD"},
            }
        )

        with patch("core.handle.receiveAudioHandle.try_route_ave_command", new=AsyncMock(return_value=False)) as try_route, \
             patch("core.handle.receiveAudioHandle.handle_user_intent", new=AsyncMock()) as handle_intent, \
             patch("core.handle.receiveAudioHandle.send_stt_message", new=AsyncMock()) as send_stt:
            await startToChat(conn, "帮我分析这个")

        try_route.assert_awaited_once_with(conn, "帮我分析这个", None)
        handle_intent.assert_not_awaited()
        send_stt.assert_awaited_once_with(
            conn,
            "请先在界面上选中你要操作的代币，然后再说一次。",
        )
        self.assertEqual(conn.chat_calls, [])

    async def test_open_ended_deictic_chat_fails_closed_on_unknown_screen_without_selection(self):
        conn = self._build_chat_conn({"screen": "mystery"})

        with patch("core.handle.receiveAudioHandle.try_route_ave_command", new=AsyncMock(return_value=False)) as try_route, \
             patch("core.handle.receiveAudioHandle.handle_user_intent", new=AsyncMock()) as handle_intent, \
             patch("core.handle.receiveAudioHandle.send_stt_message", new=AsyncMock()) as send_stt:
            await startToChat(conn, "这个能买吗")

        try_route.assert_awaited_once_with(conn, "这个能买吗", None)
        handle_intent.assert_not_awaited()
        send_stt.assert_awaited_once_with(
            conn,
            "请先在界面上选中你要操作的代币，然后再说一次。",
        )
        self.assertEqual(conn.chat_calls, [])

    def test_chat_llm_failure_cleans_temporary_context_and_reminder_messages(self):
        dialogue = Dialogue()
        dialogue.put(Message(role="system", content="system"))
        for idx in range(3):
            dialogue.put(Message(role="user", content=f"user-{idx}"))
            dialogue.put(Message(role="assistant", content=f"assistant-{idx}"))

        conn = SimpleNamespace(
            logger=_FakeLogger(),
            ave_context={"screen": "feed", "current_token": {"addr": "fresh-1"}},
            dialogue=dialogue,
            tts=_FakeTTS(),
            memory=None,
            intent_type="function_call",
            func_handler=SimpleNamespace(
                get_functions=lambda: [{"function": {"name": "demo", "description": "demo"}}]
            ),
            llm=SimpleNamespace(response_with_functions=MagicMock(side_effect=RuntimeError("boom"))),
            session_id="session-1",
            config={},
            tool_call_stats={"last_call_turn": -1, "consecutive_no_call": 0},
            client_abort=False,
            loop=None,
        )
        conn._build_ave_context_prompt = ConnectionHandler._build_ave_context_prompt.__get__(
            conn, ConnectionHandler
        )
        conn._clear_temporary_dialogue_messages = ConnectionHandler._clear_temporary_dialogue_messages.__get__(
            conn, ConnectionHandler
        )
        conn._get_tool_summary = ConnectionHandler._get_tool_summary.__get__(
            conn, ConnectionHandler
        )

        result = ConnectionHandler.chat(
            conn,
            "帮我分析这个",
            ave_context={"screen": "feed", "current_token": {"addr": "fresh-1"}},
        )

        self.assertIsNone(result)
        persisted_contents = [msg.content for msg in conn.dialogue.dialogue if msg.content]
        self.assertIn("帮我分析这个", persisted_contents)
        self.assertFalse(
            any(getattr(msg, "is_temporary", False) for msg in conn.dialogue.dialogue)
        )
        self.assertFalse(any("[AVE_CONTEXT]" in content for content in persisted_contents))
        self.assertFalse(any(TOOL_CALLING_RULES in content for content in persisted_contents))

    def test_top_level_chat_serializes_per_connection(self):
        dialogue = Dialogue()
        dialogue.put(Message(role="system", content="system"))
        llm = _BlockingLLM()
        conn = SimpleNamespace(
            logger=_FakeLogger(),
            ave_context={"screen": "feed"},
            dialogue=dialogue,
            tts=_FakeTTS(),
            memory=None,
            intent_type="nointent",
            func_handler=None,
            llm=llm,
            session_id="session-1",
            config={},
            tool_call_stats={"last_call_turn": -1, "consecutive_no_call": 0},
            client_abort=False,
            loop=object(),
        )
        conn._build_ave_context_prompt = ConnectionHandler._build_ave_context_prompt.__get__(
            conn, ConnectionHandler
        )
        conn._clear_temporary_dialogue_messages = ConnectionHandler._clear_temporary_dialogue_messages.__get__(
            conn, ConnectionHandler
        )
        conn._get_tool_summary = ConnectionHandler._get_tool_summary.__get__(
            conn, ConnectionHandler
        )

        def _run_chat(query, addr):
            ConnectionHandler.chat(
                conn,
                query,
                ave_context={"screen": "feed", "current_token": {"addr": addr}},
            )

        with patch("core.connection.textUtils.get_emotion", new=MagicMock(return_value=None)), \
             patch(
                 "core.connection.asyncio.run_coroutine_threadsafe",
                 return_value=_CompletedFuture(None),
             ):
            first = threading.Thread(target=_run_chat, args=("first turn", "token-1"))
            second = threading.Thread(target=_run_chat, args=("second turn", "token-2"))

            first.start()
            self.assertTrue(llm.first_started.wait(timeout=1))

            second.start()
            self.assertFalse(
                llm.second_started.wait(timeout=0.2),
                "second top-level chat started before the first turn finished",
            )

            llm.release_first.set()
            first.join(timeout=1)
            second.join(timeout=1)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(llm.call_count, 2)

    async def test_intent_handler_reqlLM_continuation_preserves_turn_snapshot(self):
        turn_ave_context = {
            "screen": "feed",
            "current_token": {"addr": "fresh-1", "chain": "base", "symbol": "FIRST"},
            "has_trusted_selection": True,
            "selection_source": "explicit",
        }
        conn = SimpleNamespace(
            logger=_FakeLogger(),
            sentence_id="sentence-1",
            executor=_QueuedExecutor(),
            config={"tool_call_timeout": 30},
            func_handler=SimpleNamespace(handle_llm_function_call=MagicMock(return_value=object())),
            loop=object(),
            dialogue=SimpleNamespace(put=MagicMock()),
            intent=SimpleNamespace(replyResult=MagicMock(return_value="带上下文的总结")),
            client_abort=False,
            tts_MessageText="",
            tts=_FakeTTS(),
            ave_context={"screen": "feed", "current_token": {"addr": "stale-2", "symbol": "STALE"}},
        )

        with patch("core.handle.intentHandler.send_stt_message", new=AsyncMock()), \
             patch("core.handle.intentHandler.enqueue_tool_report"), \
             patch(
                 "core.handle.intentHandler.asyncio.run_coroutine_threadsafe",
                 return_value=_CompletedFuture(
                     ActionResponse(action=Action.REQLLM, result="工具输出")
                 ),
             ):
            handled = await process_intent_result(
                conn,
                '{"function_call": {"name": "demo_tool", "arguments": {}}}',
                "帮我分析这个",
                ave_context=turn_ave_context,
            )
            conn.ave_context = {
                "screen": "portfolio",
                "current_token": {"addr": "fresh-2", "chain": "solana", "symbol": "SECOND"},
            }
            conn.executor.run_next()

        self.assertTrue(handled)
        conn.intent.replyResult.assert_called_once_with(
            "工具输出",
            "帮我分析这个",
            ave_context=turn_ave_context,
        )

    async def test_overlapping_intent_reqlLM_continuations_keep_distinct_sentence_ids(self):
        conn = SimpleNamespace(
            logger=_FakeLogger(),
            sentence_id="sentence-1",
            executor=_QueuedExecutor(),
            config={"tool_call_timeout": 30},
            func_handler=SimpleNamespace(handle_llm_function_call=MagicMock(return_value=object())),
            loop=object(),
            dialogue=SimpleNamespace(put=MagicMock()),
            intent=SimpleNamespace(replyResult=MagicMock(side_effect=["第一条总结", "第二条总结"])),
            client_abort=False,
            tts_MessageText="",
            tts=_FakeTTS(),
            ave_context={"screen": "feed"},
        )

        with patch("core.handle.intentHandler.send_stt_message", new=AsyncMock()), \
             patch("core.handle.intentHandler.enqueue_tool_report"), \
             patch(
                 "core.handle.intentHandler.asyncio.run_coroutine_threadsafe",
                 return_value=_CompletedFuture(
                     ActionResponse(action=Action.REQLLM, result="工具输出")
                 ),
             ):
            handled_first = await process_intent_result(
                conn,
                '{"function_call": {"name": "demo_tool", "arguments": {}}}',
                "第一轮",
                ave_context={"screen": "feed"},
            )
            conn.sentence_id = "sentence-2"
            handled_second = await process_intent_result(
                conn,
                '{"function_call": {"name": "demo_tool", "arguments": {}}}',
                "第二轮",
                ave_context={"screen": "portfolio"},
            )

            self.assertTrue(handled_first)
            self.assertTrue(handled_second)
            self.assertEqual(len(conn.executor.calls), 2)

            conn.executor.run_next()
            conn.executor.run_next()

        self.assertEqual(
            [item.sentence_id for item in conn.tts.tts_text_queue.items],
            ["sentence-1", "sentence-1", "sentence-2", "sentence-2"],
        )

    async def test_intent_analysis_forwards_authoritative_ave_context(self):
        ave_context = {
            "screen": "feed",
            "current_token": {"addr": "fresh-2", "chain": "base", "symbol": "FRESH"},
            "has_trusted_selection": True,
            "selection_source": "explicit",
        }
        conn = SimpleNamespace(
            logger=_FakeLogger(),
            dialogue=SimpleNamespace(dialogue=[]),
            intent=SimpleNamespace(
                detect_intent=AsyncMock(
                    return_value='{"function_call": {"name": "continue_chat"}}'
                )
            ),
            ave_context=ave_context,
        )

        result = await analyze_intent_with_llm(conn, "帮我分析这个")

        self.assertEqual(result, '{"function_call": {"name": "continue_chat"}}')
        conn.intent.detect_intent.assert_awaited_once_with(
            conn,
            conn.dialogue.dialogue,
            "帮我分析这个",
            ave_context=ave_context,
        )

    async def test_intent_llm_prompt_and_cache_key_vary_with_ave_context(self):
        provider = IntentLLMProvider({})
        provider.llm = _CapturingIntentLLM()
        provider.cache_manager = _FakeCacheManager()
        provider.CacheType = SimpleNamespace(INTENT="intent")

        conn = SimpleNamespace(
            device_id="device-1",
            func_handler=SimpleNamespace(get_functions=lambda: []),
            config={"plugins": {}},
            dialogue=SimpleNamespace(dialogue=[]),
        )
        first_context = {
            "screen": "feed",
            "current_token": {"addr": "fresh-1", "chain": "base", "symbol": "FIRST"},
            "has_trusted_selection": True,
            "selection_source": "explicit",
        }
        second_context = {
            "screen": "feed",
            "current_token": {"addr": "fresh-2", "chain": "solana", "symbol": "SECOND"},
            "has_trusted_selection": True,
            "selection_source": "explicit",
        }

        with patch(
            "core.providers.intent.intent_llm.intent_llm.initialize_music_handler",
            return_value={"music_file_names": ""},
        ):
            await provider.detect_intent(conn, [], "帮我分析这个", ave_context=first_context)
            await provider.detect_intent(conn, [], "帮我分析这个", ave_context=second_context)

        self.assertEqual(len(provider.llm.calls), 2)
        self.assertIn("[AVE_CONTEXT]", provider.llm.calls[0]["user_prompt"])
        self.assertIn("fresh-1", provider.llm.calls[0]["user_prompt"])
        self.assertIn("FIRST", provider.llm.calls[0]["user_prompt"])
        self.assertIn("fresh-2", provider.llm.calls[1]["user_prompt"])
        self.assertIn("SECOND", provider.llm.calls[1]["user_prompt"])

    async def test_open_ended_chat_uses_per_turn_ave_context_snapshot(self):
        conn = self._build_chat_conn({"screen": "feed"})
        conn.executor = _QueuedExecutor()
        first_payload = {
            "state": "detect",
            "text": "聊聊第一只",
            "selection": {
                "screen": "feed",
                "cursor": 0,
                "token": {"addr": "fresh-1", "chain": "base", "symbol": "FIRST"},
            },
        }
        second_payload = {
            "state": "detect",
            "text": "聊聊第二只",
            "selection": {
                "screen": "portfolio",
                "cursor": 1,
                "token": {"addr": "fresh-2", "chain": "solana", "symbol": "SECOND"},
            },
        }

        with patch("core.handle.receiveAudioHandle.send_stt_message", new=AsyncMock()), \
             patch("core.handle.receiveAudioHandle.handle_user_intent", new=AsyncMock(return_value=False)):
            await startToChat(conn, first_payload["text"], message_payload=first_payload)
            await startToChat(conn, second_payload["text"], message_payload=second_payload)

        self.assertEqual(len(conn.executor.calls), 2)
        conn.executor.run_next()

        self.assertEqual(conn.chat_calls[0][0], "聊聊第一只")
        self.assertEqual(
            conn.chat_calls[0][1],
            {
                "screen": "feed",
                "nav_from": "",
                "current_token": {"addr": "fresh-1", "chain": "base", "symbol": "FIRST"},
                "has_trusted_selection": True,
                "selection_source": "explicit",
                "pending_trade": {},
                "feed_source": "",
                "feed_platform": "",
                "feed_cursor": 0,
                "feed_visible_symbols": [],
                "allowed_actions": [
                    "back_to_feed",
                    "open_feed",
                    "open_portfolio",
                    "open_watchlist",
                    "search_symbol",
                    "watch_current",
                ],
            },
        )

    def test_recursive_tool_continuation_reuses_turn_ave_context_snapshot(self):
        turn_ave_context = {
            "screen": "feed",
            "current_token": {"addr": "fresh-1", "chain": "base", "symbol": "FIRST"},
            "has_trusted_selection": True,
            "selection_source": "explicit",
        }
        conn = SimpleNamespace(
            logger=_FakeLogger(),
            ave_context=turn_ave_context,
            dialogue=SimpleNamespace(put=MagicMock()),
            chat_calls=[],
        )

        def _chat(query, depth=0, ave_context=None):
            conn.chat_calls.append((query, depth, ave_context))

        conn.chat = _chat

        ConnectionHandler._handle_function_result(
            conn,
            [
                (
                    ActionResponse(action=Action.REQLLM, result="工具输出"),
                    {"id": "tool-1", "name": "demo_tool", "arguments": "{}"},
                )
            ],
            depth=0,
        )

        self.assertEqual(conn.chat_calls, [(None, 1, turn_ave_context)])

    async def test_intent_llm_cache_key_varies_with_history_window(self):
        provider = IntentLLMProvider({})
        provider.llm = _CapturingIntentLLM()
        provider.cache_manager = _FakeCacheManager()
        provider.CacheType = SimpleNamespace(INTENT="intent")
        provider.history_count = 4

        conn = SimpleNamespace(
            device_id="device-1",
            func_handler=SimpleNamespace(get_functions=lambda: []),
            config={"plugins": {}},
            dialogue=SimpleNamespace(dialogue=[]),
        )
        ave_context = {
            "screen": "feed",
            "current_token": {"addr": "fresh-1", "chain": "base", "symbol": "FIRST"},
            "has_trusted_selection": True,
            "selection_source": "explicit",
        }
        first_history = [SimpleNamespace(role="user", content="第一段历史")]
        second_history = [SimpleNamespace(role="user", content="第二段历史")]

        with patch(
            "core.providers.intent.intent_llm.intent_llm.initialize_music_handler",
            return_value={"music_file_names": ""},
        ):
            await provider.detect_intent(conn, first_history, "帮我分析这个", ave_context=ave_context)
            await provider.detect_intent(conn, second_history, "帮我分析这个", ave_context=ave_context)

        self.assertEqual(len(provider.llm.calls), 2)
        self.assertIn("第一段历史", provider.llm.calls[0]["user_prompt"])
        self.assertIn("第二段历史", provider.llm.calls[1]["user_prompt"])

    async def test_search_with_duplicate_symbols_routes_to_disambiguation(self):
        conn = self._build_listen_conn({"screen": "feed"})
        sent = []

        ambiguous_items = [
            {"token_id": "So111...", "chain": "solana", "symbol": "PEPE"},
            {"token_id": "0xabc...", "chain": "base", "symbol": "PEPE"},
        ]

        def fake_data_get(path, params=None):
            if path == "/tokens":
                return {"data": {"tokens": ambiguous_items}}
            return {}

        async def fake_send_display(passed_conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=fake_send_display):
            await try_route_ave_command(conn, "看PEPE")
            await asyncio.sleep(0)

        self.assertTrue(
            any(screen == "disambiguation" for screen, _ in sent),
            msg=f"expected a disambiguation display, got {[screen for screen, _ in sent]}",
        )
        self.assertFalse(
            any(screen == "feed" for screen, _ in sent),
            msg="ambiguous search should not fall back to a feed display",
        )

        disambiguation_payloads = [payload for screen, payload in sent if screen == "disambiguation"]
        self.assertTrue(
            disambiguation_payloads,
            msg="disambiguation display never emitted, expected at least one payload",
        )
        expected_token_ids = {item["token_id"] for item in ambiguous_items}
        expected_items = {item["token_id"]: item for item in ambiguous_items}
        for payload in disambiguation_payloads:
            self.assertIn(
                "items",
                payload,
                msg="disambiguation payload should include an 'items' list of candidates",
            )
            items = payload.get("items", [])
            actual_ids = {item.get("token_id") for item in items if item.get("token_id")}
            self.assertEqual(
                expected_token_ids,
                actual_ids,
                msg="disambiguation candidates should mirror the search results",
            )
            for candidate in items:
                token_id = candidate.get("token_id")
                if not token_id:
                    continue
                self.assertIn(
                    token_id,
                    expected_items,
                    msg="disambiguation candidate must match a known ambiguous result",
                )
                expected = expected_items[token_id]
                self.assertEqual(
                    expected["chain"],
                    candidate.get("chain"),
                    msg=f"chain should be preserved for {token_id}",
                )
                self.assertEqual(
                    expected["symbol"],
                    candidate.get("symbol"),
                    msg=f"symbol should be preserved for {token_id}",
                )

    async def test_ave_search_token_persists_search_session_for_restore(self):
        conn = self._build_listen_conn({"screen": "feed"})
        sent = []
        raw_items = [
            {"token_id": "So111...", "chain": "solana", "symbol": "PEPE", "price": 1.23},
            {"token_id": "0xabc...", "chain": "base", "symbol": "PEPE", "price": 1.11},
            {"token_id": "0xdef...", "chain": "eth", "symbol": "NOTPEPE", "price": 0.99},
        ]

        def fake_data_get(path, params=None):
            self.assertEqual(path, "/tokens")
            self.assertEqual(params.get("keyword"), "PEPE")
            return {"data": {"tokens": raw_items}}

        async def fake_send_display(passed_conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=fake_send_display):
            response = ave_tools.ave_search_token(conn, keyword="PEPE")
            await asyncio.sleep(0)

        self.assertEqual(response.action, Action.NONE)
        session = conn.ave_state.get("search_session")
        self.assertIsInstance(session, dict)
        self.assertEqual(session.get("query"), "PEPE")
        self.assertEqual(session.get("chain"), "all")
        self.assertEqual(session.get("cursor"), 0)
        self.assertEqual(
            [item.get("token_id") for item in session.get("items", [])],
            ["So111...", "0xabc..."],
        )
        self.assertTrue(
            any(screen == "disambiguation" for screen, _ in sent),
            msg="ambiguous search should still emit disambiguation while saving the restore session",
        )

    async def test_repeated_duplicate_symbol_watch_researches_instead_of_picking_a_collapsed_winner(self):
        conn = self._build_listen_conn(
            {
                "screen": "disambiguation",
                "feed_mode": "search",
                "search_query": "PEPE",
                "search_chain": "all",
            }
        )
        ambiguous_items = [
            {"token_id": "So111...", "chain": "solana", "symbol": "PEPE", "price": "$1.23"},
            {"token_id": "0xabc...", "chain": "base", "symbol": "PEPE", "price": "$1.11"},
        ]
        ave_tools._save_search_session(
            conn,
            query="PEPE",
            chain="all",
            items=ambiguous_items,
            cursor=0,
        )
        conn.ave_state["disambiguation_items"] = list(ambiguous_items)
        conn.ave_state["disambiguation_cursor"] = 0
        ave_tools._set_feed_navigation_state(conn.ave_state, ambiguous_items, cursor=0)

        with patch(
            "plugins_func.functions.ave_tools.ave_search_token",
            return_value=ActionResponse(action=Action.NONE, result="Need disambiguation", response=""),
        ) as mock_search, patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            routed = await try_route_ave_command(conn, "看PEPE")

        self.assertTrue(routed)
        mock_search.assert_called_once_with(conn, keyword="PEPE")
        mock_detail.assert_not_called()

    async def test_back_from_spotlight_restores_search_query_and_cursor_from_search_session(self):
        handler = KeyActionHandler()
        search_items = [
            {"token_id": "So111...", "chain": "solana", "symbol": "PEPE", "price": "$1.23"},
            {"token_id": "0xabc...", "chain": "base", "symbol": "PEPE", "price": "$1.11"},
            {"token_id": "0xdef...", "chain": "eth", "symbol": "PEPE", "price": "$0.99"},
        ]
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "feed_mode": "search",
                "feed_source": "trending",
                "search_query": "PEPE",
                "search_chain": "all",
                "search_cursor": 1,
                "search_session": {
                    "query": "PEPE",
                    "chain": "all",
                    "cursor": 1,
                    "items": list(search_items),
                },
            }
        )
        sent = []

        async def fake_send_display(passed_conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=fake_send_display), \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(conn, {"type": "key_action", "action": "back"})

        mock_trending.assert_not_called()
        self.assertEqual(conn.ave_state.get("screen"), "feed")
        self.assertEqual(conn.ave_state.get("feed_mode"), "search")
        self.assertEqual(conn.ave_state.get("search_query"), "PEPE")
        self.assertEqual(conn.ave_state.get("feed_cursor"), 1)
        self.assertEqual(conn.ave_state.get("search_session", {}).get("cursor"), 1)

        feed_payload = next((payload for screen, payload in sent if screen == "feed"), None)
        self.assertIsNotNone(feed_payload)
        self.assertEqual(feed_payload.get("source_label"), "SEARCH")
        self.assertEqual(feed_payload.get("mode"), "search")
        self.assertEqual(feed_payload.get("search_query"), "PEPE")
        self.assertEqual(feed_payload.get("cursor"), 1)
        self.assertEqual(
            [item.get("token_id") for item in feed_payload.get("tokens", [])],
            [item.get("token_id") for item in search_items],
        )

    async def test_key_action_signals_routes_to_server_tool(self):
        handler = KeyActionHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("plugins_func.functions.ave_tools.ave_list_signals") as list_signals:
            await handler.handle(conn, {"type": "key_action", "action": "signals"})

        list_signals.assert_called_once_with(conn)

    async def test_key_action_watchlist_routes_to_server_tool(self):
        handler = KeyActionHandler()
        conn = self._build_listen_conn({"screen": "feed"})

        with patch("plugins_func.functions.ave_tools.ave_open_watchlist") as open_watchlist:
            await handler.handle(conn, {"type": "key_action", "action": "watchlist"})

        open_watchlist.assert_called_once_with(conn)

    async def test_key_action_watchlist_remove_uses_selected_token_and_cursor(self):
        handler = KeyActionHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "feed_mode": "watchlist",
                "feed_cursor": 0,
                "feed_token_list": [
                    {"addr": "Token111", "chain": "solana", "symbol": "BONK"},
                    {"addr": "Token222", "chain": "base", "symbol": "WIF"},
                ],
            }
        )

        with patch("plugins_func.functions.ave_tools.ave_remove_current_watchlist_token") as remove_current:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "watchlist_remove",
                    "token_id": "Token222",
                    "chain": "base",
                    "cursor": 1,
                },
            )

        remove_current.assert_called_once_with(
            conn,
            token={"addr": "Token222", "chain": "base", "symbol": "WIF"},
            cursor=1,
        )

    async def test_key_action_watch_without_cursor_uses_existing_server_feed_cursor(self):
        handler = KeyActionHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "feed_mode": "signals",
                "feed_cursor": 1,
                "feed_token_list": [
                    {"addr": "Token111", "chain": "solana", "symbol": "BONK"},
                    {"addr": "Token222", "chain": "base", "symbol": "WIF"},
                ],
            }
        )

        with patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "watch",
                    "token_id": "Token222",
                    "chain": "base",
                },
            )

        mock_detail.assert_called_once_with(
            conn,
            addr="Token222",
            chain="base",
            feed_cursor=1,
            feed_total=2,
        )

    async def test_key_action_back_from_signals_spotlight_restores_signals(self):
        handler = KeyActionHandler()
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "feed_mode": "signals",
                "feed_source": "signals",
                "nav_from": "feed",
            }
        )

        with patch("plugins_func.functions.ave_tools.ave_list_signals") as mock_signals, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(conn, {"type": "key_action", "action": "back"})

        mock_signals.assert_called_once_with(conn)
        mock_trending.assert_not_called()

    async def test_key_action_back_from_watchlist_spotlight_restores_watchlist(self):
        handler = KeyActionHandler()
        conn = self._build_listen_conn(
            {
                "screen": "spotlight",
                "feed_mode": "watchlist",
                "feed_source": "watchlist",
                "feed_cursor": 1,
                "nav_from": "feed",
            }
        )

        with patch("plugins_func.functions.ave_tools.ave_open_watchlist") as mock_watchlist, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(conn, {"type": "key_action", "action": "back"})

        mock_watchlist.assert_called_once_with(conn, cursor=1)
        mock_trending.assert_not_called()


if __name__ == "__main__":
    unittest.main()
