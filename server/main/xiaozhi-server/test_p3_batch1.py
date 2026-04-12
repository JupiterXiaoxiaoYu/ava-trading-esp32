import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from core.handle.textHandler.keyActionHandler import KeyActionHandler
from plugins_func.functions import ave_tools, ave_wss


class _FakeWss:
    def __init__(self):
        self.calls = []

    def set_spotlight(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    def set_feed_tokens(self, *args, **kwargs):
        self.calls.append(("feed_tokens", args, kwargs))


class _FakeConn:
    def __init__(self, loop):
        self.loop = loop
        self.ave_wss = _FakeWss()
        self.ave_state = {}


def make_fake_conn_with_search_state():
    loop = asyncio.get_running_loop()
    conn = _FakeConn(loop)
    conn.ave_state.update(
        {
            "screen": "feed",
            "feed_mode": "search",
            "search_query": "PEPE",
            "search_cursor": 2,
            "search_results": [{"symbol": "PEPE"} for _ in range(5)],
        }
    )
    return conn


def build_disambiguation_payload():
    # This is the external payload for `_send_display(..., "disambiguation", payload)`.
    # Router and surface tests pin how it is emitted; the lifecycle test consumes it.
    return {
        "items": [
            {"token_id": "So111...", "chain": "solana", "symbol": "PEPE"},
            {"token_id": "0xabc...", "chain": "base", "symbol": "PEPE"},
        ],
        "cursor": 0,
        "nav_from": "feed",
    }


def seed_disambiguation_state(conn, payload):
    conn.ave_state.update(
        {
            "screen": "disambiguation",
            "nav_from": payload.get("nav_from", "feed"),
            "disambiguation_items": payload.get("items", []),
            "disambiguation_cursor": payload.get("cursor", 0),
        }
    )
    return payload.get("items", [])



async def dispatch_key(conn, key, *, selection_candidates=None, cursor=0, payload=None):
    handler = KeyActionHandler()
    action_payload: dict[str, str] = {"type": "key_action"}
    if key == "right":
        items = selection_candidates or []
        if not items:
            raise AssertionError("dispatch_key right requires disambiguation candidates")
        token = items[cursor % len(items)]
        token_id = token.get("token_id")
        chain = token.get("chain", "solana")
        if not token_id:
            raise AssertionError("ambiguous search result missing token_id")
        action_payload.update(
            {
                # Intentional RED seam: Task 1 must pin a dedicated selected-candidate path
                # that stays distinct from generic `watch`, otherwise the lifecycle would
                # false-green on today's existing watch -> spotlight behavior.
                "action": "disambiguation_select",
                "token_id": token_id,
                "chain": chain,
                "cursor": str(cursor),
                "symbol": token.get("symbol", ""),
            }
        )
    elif key == "back":
        action_payload["action"] = "back"
    else:
        raise ValueError(f"unsupported key {key}")

    def fake_data_get(path, params=None):
        restored_tokens = payload.get("items", []) if payload else []
        if not restored_tokens:
            restored_tokens = conn.ave_state.get("disambiguation_items", [])
        if not restored_tokens:
            restored_tokens = conn.ave_state.get("search_results", [])
        # Keep the harness intentionally narrow so legacy generic trending/ranks flows
        # cannot accidentally satisfy the restore-search assertions.
        if path == "/tokens":
            return {"data": {"tokens": restored_tokens}}
        if path.startswith("/tokens/"):
            lead = restored_tokens[0] if restored_tokens else {}
            return {
                "data": {
                    "token": {
                        "symbol": lead.get("symbol", "PEPE"),
                        "current_price_usd": 1.23,
                        "price": 1.23,
                        "price_change_24h": 0.5,
                        "token_price_change_24h": 0.5,
                        "holders": 1000,
                        "main_pair_tvl": 1000000,
                    }
                }
            }
        if path.startswith("/klines/token/"):
            return {
                "data": {
                    "points": [
                        {"close": 1.0, "time": 1710000000},
                        {"close": 2.0, "time": 1710003600},
                    ]
                }
            }
        if path.startswith("/contracts/"):
            return {"data": {"risk_score": 10}}
        raise AssertionError(f"unexpected path: {path}")

    safe_flags = {
        "is_honeypot": False,
        "is_mintable": False,
        "is_freezable": False,
        "risk_level": "LOW",
    }
    sent = []

    async def fake_send_display(_, screen, payload):
        sent.append((screen, payload))

    with patch("plugins_func.functions.ave_tools._send_display", side_effect=fake_send_display), \
         patch("plugins_func.functions.ave_tools._data_get", side_effect=fake_data_get), \
         patch("plugins_func.functions.ave_tools._risk_flags", return_value=safe_flags):
        await handler.handle(conn, action_payload)
        await asyncio.sleep(0)

    return sent


class Batch1PythonTests(unittest.IsolatedAsyncioTestCase):
    def test_build_disambiguation_payload_reports_overflow_explicitly(self):
        items = [
            {
                "token_id": f"token-{idx}-solana",
                "chain": "solana",
                "symbol": "PEPE",
            }
            for idx in range(15)
        ]

        payload = ave_tools._build_disambiguation_payload(items)

        self.assertEqual(len(payload.get("items", [])), 12)
        self.assertEqual(payload.get("total_candidates"), 15)
        self.assertEqual(payload.get("overflow_count"), 3)

    def test_kline_limit_mapping(self):
        self.assertEqual(ave_tools._kline_limit_for_interval("5"), 48)
        self.assertEqual(ave_tools._kline_limit_for_interval("60"), 48)
        self.assertEqual(ave_tools._kline_limit_for_interval("240"), 42)
        self.assertEqual(ave_tools._kline_limit_for_interval("1440"), 30)
        self.assertEqual(ave_tools._kline_limit_for_interval("unknown"), 48)

    async def test_ave_token_detail_uses_interval_specific_kline_size_and_wss_interval(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        requests = []

        async def _fake_send_display(conn, screen, payload):
            return None

        def _fake_data_get(path, params=None):
            requests.append((path, params))
            if path.startswith("/tokens/"):
                return {
                    "data": {
                        "token": {
                            "symbol": "BONK",
                            "price": 1.23,
                            "price_change_24h": 4.56,
                            "holders": 1234,
                            "tvl": 98765,
                        }
                    }
                }
            if path.startswith("/klines/token/"):
                return {
                    "data": {
                        "points": [
                            {"close": 1.0, "time": 1710000000},
                            {"close": 2.0, "time": 1710003600},
                        ]
                    }
                }
            if path.startswith("/contracts/"):
                return {"data": {}}
            raise AssertionError(f"unexpected path: {path}")

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._risk_flags", return_value={
                 "is_honeypot": False,
                 "is_mintable": False,
                 "is_freezable": False,
                 "risk_level": "LOW",
             }), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_token_detail(conn, addr="token-123", chain="solana", interval="240")
            await asyncio.sleep(0)

        kline_requests = [item for item in requests if item[0].startswith("/klines/token/")]
        self.assertEqual(len(kline_requests), 1)
        self.assertEqual(kline_requests[0][1]["limit"], 42)

        self.assertEqual(len(conn.ave_wss.calls), 1)
        args, kwargs = conn.ave_wss.calls[0]
        self.assertEqual(args[0], "token-123")
        self.assertEqual(args[1], "solana")
        self.assertEqual(kwargs["interval"], "k240")

    async def test_ave_token_detail_trims_oversized_kline_payload_to_requested_window(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        oversized_points = [
            {"close": index + 1, "time": 1710000000 + index * 300}
            for index in range(301)
        ]

        def _fake_data_get(path, params=None):
            if path.startswith("/tokens/"):
                return {
                    "data": {
                        "token": {
                            "symbol": "BONK",
                            "price": 1.23,
                            "price_change_24h": 4.56,
                            "holders": 1234,
                            "tvl": 98765,
                        }
                    }
                }
            if path.startswith("/klines/token/"):
                return {"data": {"points": oversized_points}}
            if path.startswith("/contracts/"):
                return {"data": {}}
            raise AssertionError(f"unexpected path: {path}")

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._risk_flags", return_value={
                 "is_honeypot": False,
                 "is_mintable": False,
                 "is_freezable": False,
                 "risk_level": "LOW",
             }), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_token_detail(conn, addr="token-123", chain="solana", interval="5")
            await asyncio.sleep(0)

        payload = sent[0][1]
        self.assertEqual(len(payload["chart"]), 48)
        args, _ = conn.ave_wss.calls[0]
        self.assertEqual(len(args[2]["chart"]), 48)
        self.assertEqual(args[3][0], 254.0)
        self.assertEqual(args[3][-1], 301.0)

    async def test_data_subscribe_uses_jsonrpc_frames_with_documented_param_shapes(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        manager._feed_token_ids = ["token-1-solana", "token-2-bsc"]
        manager._spotlight_pair = "pair-1"
        manager._spotlight_chain = "solana"
        manager._spotlight_interval = "k60"
        sent = []

        class _FakeWs:
            async def send(self, raw):
                sent.append(json.loads(raw))

        await manager._subscribe_data(_FakeWs())

        self.assertEqual(
            sent,
            [
                {
                    "jsonrpc": "2.0",
                    "method": "unsubscribe",
                    "params": [],
                    "id": 1,
                },
                {
                    "jsonrpc": "2.0",
                    "method": "subscribe",
                    "params": ["price", ["token-1-solana", "token-2-bsc"]],
                    "id": 2,
                },
                {
                    "jsonrpc": "2.0",
                    "method": "subscribe",
                    "params": ["kline", "pair-1", "k60", "solana"],
                    "id": 3,
                },
            ],
        )

    async def test_data_event_price_batch_updates_feed_cache_and_pushes_live_feed(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        manager.set_feed_tokens(
            [
                {
                    "token_id": "token-1-solana",
                    "chain": "solana",
                    "symbol": "BONK",
                    "price": "$1.0000",
                    "price_raw": 1.0,
                    "change_24h": "+0.00%",
                    "change_positive": True,
                }
            ],
            chain="solana",
        )

        raw = json.dumps({
            "result": {
                "prices": [
                    {"token_id": "token-1", "chain": "solana", "is_main_pair": False, "price": "1.1"},
                    {"token_id": "token-1", "chain": "solana", "is_main_pair": True, "price": "2.5", "price_change_1h": "4.2"},
                ]
            }
        })

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await manager._handle_data_event(raw)

        self.assertEqual(manager._feed_display["token-1-solana"]["price_raw"], 2.5)
        self.assertEqual(manager._feed_display["token-1-solana"]["change_24h"], "+4.20%")
        self.assertEqual(sent[0][0], "feed")
        self.assertTrue(sent[0][1]["live"])

    async def test_data_event_kline_result_format_updates_spotlight_runtime_state(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        manager._spotlight_pair = "pair-1"
        manager._spotlight_data = {
            "token_id": "token-1-solana",
            "symbol": "BONK",
            "chart": [100, 200],
            "chart_t_end": "old",
        }

        raw = json.dumps({
            "result": {
                "id": "pair-1-solana",
                "interval": "s1",
                "kline": {
                    "eth": {
                        "close": "0.1234",
                        "time": 1710000000,
                    }
                },
            }
        })

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await manager._handle_data_event(raw)

        self.assertEqual(manager._spotlight_raw_closes[-1], 0.1234)
        self.assertEqual(manager._spotlight_raw_times[-1], 1710000000)
        self.assertEqual(sent[0][0], "spotlight")
        self.assertEqual(sent[0][1]["chart_t_end"], "now")
        self.assertTrue(sent[0][1]["live"])

    async def test_disambiguation_select_enters_spotlight_and_back_restores_search(self):
        conn = make_fake_conn_with_search_state()
        self.assertEqual(conn.ave_state["feed_mode"], "search")
        payload = build_disambiguation_payload()
        ambiguous_items = seed_disambiguation_state(conn, payload)
        await dispatch_key(conn, "right", selection_candidates=ambiguous_items, cursor=payload.get("cursor", 0))
        self.assertEqual(conn.ave_state["screen"], "spotlight")
        sent_back = await dispatch_key(conn, "back", payload=payload)
        self.assertEqual(conn.ave_state["screen"], "feed")
        self.assertEqual(conn.ave_state["feed_mode"], "search")
        feed_payload = next((p for screen, p in sent_back if screen == "feed"), None)
        self.assertIsNotNone(feed_payload)
        self.assertEqual(feed_payload.get("source_label"), "SEARCH")
        token_ids = {token.get("token_id") for token in feed_payload.get("tokens", []) if token.get("token_id")}
        expected_ids = {item.get("token_id") for item in payload.get("items", []) if item.get("token_id")}
        self.assertTrue(expected_ids & token_ids, msg=f"{expected_ids} should intersect with restored tokens")

    async def test_disambiguation_select_updates_search_cursor_for_restore(self):
        conn = make_fake_conn_with_search_state()
        payload = build_disambiguation_payload()
        conn.ave_state["search_results"] = list(payload["items"])
        conn.ave_state["search_cursor"] = 0
        ambiguous_items = seed_disambiguation_state(conn, payload)

        await dispatch_key(conn, "right", selection_candidates=ambiguous_items, cursor=1)

        self.assertEqual(conn.ave_state["search_cursor"], 1)

    async def test_disambiguation_select_keeps_spotlight_prev_next_navigation_context(self):
        handler = KeyActionHandler()
        conn = make_fake_conn_with_search_state()
        payload = build_disambiguation_payload()
        search_items = list(payload["items"])
        conn.ave_state["search_results"] = list(search_items)
        conn.ave_state["search_session"] = {
            "query": "PEPE",
            "chain": "all",
            "cursor": 0,
            "items": list(search_items),
        }
        seed_disambiguation_state(conn, payload)

        detail_calls = []

        def fake_detail(passed_conn, addr, chain, symbol="", feed_cursor=None, feed_total=None, **kwargs):
            detail_calls.append(
                {
                    "addr": addr,
                    "chain": chain,
                    "symbol": symbol,
                    "feed_cursor": feed_cursor,
                    "feed_total": feed_total,
                }
            )
            passed_conn.ave_state["screen"] = "spotlight"
            passed_conn.ave_state["current_token"] = {
                "addr": addr,
                "chain": chain,
                "symbol": symbol or "PEPE",
            }

        with patch("plugins_func.functions.ave_tools.ave_token_detail", side_effect=fake_detail):
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "disambiguation_select",
                    "token_id": search_items[0]["token_id"],
                    "chain": search_items[0]["chain"],
                    "cursor": "0",
                    "symbol": search_items[0]["symbol"],
                },
            )
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "feed_next",
                },
            )

        self.assertEqual(len(detail_calls), 2)
        self.assertEqual(detail_calls[0]["addr"], "So111...")
        self.assertEqual(detail_calls[1]["addr"], "0xabc...")
        self.assertEqual(detail_calls[1]["chain"], "base")
        self.assertEqual(detail_calls[1]["feed_cursor"], 1)
        self.assertEqual(detail_calls[1]["feed_total"], 2)
        self.assertEqual(conn.ave_state["feed_cursor"], 1)
        self.assertEqual(
            [item.get("addr") for item in conn.ave_state["feed_token_list"]],
            ["So111...", "0xabc..."],
        )

    async def test_back_restore_search_feed_includes_cursor(self):
        conn = make_fake_conn_with_search_state()
        conn.ave_state.update(
            {
                "screen": "spotlight",
                "search_results": [
                    {"token_id": "token-0-solana", "chain": "solana", "symbol": "PEPE"},
                    {"token_id": "token-1-base", "chain": "base", "symbol": "PEPE"},
                    {"token_id": "token-2-eth", "chain": "eth", "symbol": "PEPE"},
                ],
                "search_cursor": 2,
            }
        )

        sent_back = await dispatch_key(conn, "back")

        feed_payload = next((p for screen, p in sent_back if screen == "feed"), None)
        self.assertIsNotNone(feed_payload)
        self.assertEqual(feed_payload.get("cursor"), 2)
        self.assertEqual(conn.ave_state["feed_cursor"], 2)

    async def test_watch_missing_chain_fails_closed(self):
        handler = KeyActionHandler()
        conn = _FakeConn(asyncio.get_running_loop())

        with patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "watch",
                    "token_id": "token-no-chain",
                },
            )

        mock_detail.assert_not_called()

    async def test_watch_invalid_chain_fails_closed(self):
        handler = KeyActionHandler()
        conn = _FakeConn(asyncio.get_running_loop())

        with patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "watch",
                    "token_id": "token-1",
                    "chain": "doge",
                },
            )

        mock_detail.assert_not_called()

    async def test_portfolio_sell_missing_chain_fails_closed(self):
        handler = KeyActionHandler()
        conn = _FakeConn(asyncio.get_running_loop())

        with patch("plugins_func.functions.ave_tools.ave_sell_token") as mock_sell:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "portfolio_sell",
                    "addr": "token-no-chain",
                    "symbol": "PEPE",
                    "balance_raw": "123",
                },
            )

        mock_sell.assert_not_called()

    async def test_feed_next_missing_chain_in_cached_feed_state_fails_closed(self):
        handler = KeyActionHandler()
        conn = _FakeConn(asyncio.get_running_loop())
        conn.ave_state.update(
            {
                "feed_token_list": [
                    {"addr": "token-0", "chain": "solana", "symbol": "AAA"},
                    {"addr": "token-1", "symbol": "BROKEN"},
                ],
                "feed_cursor": 0,
            }
        )

        with patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "feed_next",
                },
            )

        self.assertEqual(conn.ave_state["feed_cursor"], 1)
        mock_detail.assert_not_called()

    async def test_feed_next_invalid_chain_in_cached_feed_state_fails_closed(self):
        handler = KeyActionHandler()
        conn = _FakeConn(asyncio.get_running_loop())
        conn.ave_state.update(
            {
                "feed_token_list": [
                    {"addr": "token-0", "chain": "solana", "symbol": "AAA"},
                    {"addr": "token-1", "chain": "doge", "symbol": "BROKEN"},
                ],
                "feed_cursor": 0,
            }
        )

        with patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "feed_next",
                },
            )

        self.assertEqual(conn.ave_state["feed_cursor"], 1)
        mock_detail.assert_not_called()

    async def test_orders_invalid_chain_from_payload_fails_closed(self):
        handler = KeyActionHandler()
        conn = _FakeConn(asyncio.get_running_loop())

        with patch("plugins_func.functions.ave_tools.ave_list_orders") as mock_orders:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "orders",
                    "chain": "doge",
                },
            )

        mock_orders.assert_not_called()

    async def test_orders_invalid_chain_from_state_fails_closed(self):
        handler = KeyActionHandler()
        conn = _FakeConn(asyncio.get_running_loop())
        conn.ave_state.update(
            {
                "last_orders_chain": "doge",
                "current_token": {"addr": "token-1", "chain": "doge", "symbol": "PEPE"},
            }
        )

        with patch("plugins_func.functions.ave_tools.ave_list_orders") as mock_orders:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "orders",
                },
            )

        mock_orders.assert_not_called()

    async def test_orders_malformed_current_token_state_fails_closed(self):
        handler = KeyActionHandler()
        conn = _FakeConn(asyncio.get_running_loop())
        conn.ave_state.update(
            {
                "current_token": "broken-state",
            }
        )

        with patch("plugins_func.functions.ave_tools.ave_list_orders") as mock_orders:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "orders",
                },
            )

        mock_orders.assert_not_called()

    async def test_disambiguation_select_missing_chain_fails_closed(self):
        handler = KeyActionHandler()
        conn = _FakeConn(asyncio.get_running_loop())
        conn.ave_state.update(
            {
                "screen": "disambiguation",
                "disambiguation_items": [
                    {"token_id": "token-no-chain", "symbol": "PEPE"},
                ],
                "disambiguation_cursor": 0,
            }
        )

        with patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "disambiguation_select",
                    "token_id": "token-no-chain",
                    "cursor": "0",
                    "symbol": "PEPE",
                },
            )

        mock_detail.assert_not_called()

    async def test_disambiguation_select_invalid_chain_fails_closed(self):
        handler = KeyActionHandler()
        conn = _FakeConn(asyncio.get_running_loop())
        conn.ave_state.update(
            {
                "screen": "disambiguation",
                "disambiguation_items": [
                    {"token_id": "token-1", "chain": "doge", "symbol": "PEPE"},
                ],
                "disambiguation_cursor": 0,
            }
        )

        with patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "disambiguation_select",
                    "token_id": "token-1",
                    "chain": "doge",
                    "cursor": "0",
                    "symbol": "PEPE",
                },
            )

        mock_detail.assert_not_called()


if __name__ == "__main__":
    unittest.main()
