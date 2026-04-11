import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from plugins_func.functions import ave_tools
from plugins_func.register import Action, ActionResponse


class SignalsWatchlistToolTests(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.conn = SimpleNamespace(loop=self.loop, ave_state={})

    def tearDown(self):
        pending = asyncio.all_tasks(self.loop)
        for task in pending:
            task.cancel()
        if pending:
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self.loop.close()

    def test_ave_list_signals_sends_browse_payload_with_signals_mode(self):
        signal_payload = {
            "data": {
                "list": [
                    {
                        "symbol": "PUMP",
                        "token": "Token111",
                        "chain": "solana",
                        "signal_type": "SMART_MONEY",
                        "headline": "Should not be shown in browse row",
                        "action_type": "BUY",
                        "first_signal_time": 9900,
                        "signal_time": 9980,
                        "action_count": 2,
                        "tx_volume_u_24h": 125000,
                        "price_change_24h": 12.34,
                        "mc_cur": 120000,
                        "actions": [
                            {"action_type": "buy", "quote_token_volume": "1.25", "quote_token_symbol": "SOL"},
                            {"action_type": "buy", "quote_token_volume": "2.25", "quote_token_symbol": "SOL"},
                        ],
                    }
                ]
            }
        }

        with patch.object(ave_tools, "_data_get", return_value=signal_payload), patch.object(
            ave_tools.time, "time", return_value=10020
        ), patch.object(
            ave_tools, "_send_display", new=AsyncMock()
        ) as send_display:
            ave_tools.ave_list_signals(self.conn)
            self.loop.run_until_complete(asyncio.sleep(0))

        self.assertEqual(send_display.await_count, 1)
        _, screen, payload = send_display.await_args.args
        self.assertEqual(screen, "browse")
        self.assertEqual(payload["mode"], "signals")
        self.assertEqual(payload["source_label"], "SIGNALS")
        self.assertEqual(payload["tokens"][0]["token_id"], "Token111")
        self.assertEqual(payload["tokens"][0]["signal_label"], "BUY")
        self.assertEqual(payload["tokens"][0]["signal_value"], "BUY 3.5 SOL")
        self.assertEqual(payload["tokens"][0]["signal_first"], "First 2m")
        self.assertEqual(payload["tokens"][0]["signal_last"], "Last 0m")
        self.assertEqual(payload["tokens"][0]["signal_count"], "Count 2")
        self.assertEqual(payload["tokens"][0]["signal_vol"], "Vol $125.0K")
        self.assertEqual(
            payload["tokens"][0]["signal_summary"],
            "First 2m Last 0m Count 2 Vol $125.0K",
        )
        self.assertEqual(self.conn.ave_state["screen"], "browse")
        self.assertEqual(self.conn.ave_state["feed_mode"], "signals")

    def test_ave_list_signals_falls_back_to_action_count_when_actions_missing(self):
        signal_payload = {
            "data": {
                "list": [
                    {
                        "symbol": "MORITZ",
                        "token": "Token222",
                        "chain": "solana",
                        "action_type": "BUY",
                        "first_signal_time": 6400,
                        "signal_time": 8200,
                        "action_count": 3,
                        "tx_volume_u_24h": 13150,
                    }
                ]
            }
        }

        with patch.object(ave_tools, "_data_get", return_value=signal_payload), patch.object(
            ave_tools.time, "time", return_value=10000
        ), patch.object(
            ave_tools, "_send_display", new=AsyncMock()
        ) as send_display:
            ave_tools.ave_list_signals(self.conn)
            self.loop.run_until_complete(asyncio.sleep(0))

        _, _, payload = send_display.await_args.args
        self.assertEqual(payload["tokens"][0]["signal_label"], "BUY")
        self.assertEqual(payload["tokens"][0]["signal_value"], "BUY")
        self.assertEqual(payload["tokens"][0]["signal_first"], "First 1h")
        self.assertEqual(payload["tokens"][0]["signal_last"], "Last 30m")
        self.assertEqual(payload["tokens"][0]["signal_count"], "Count 3")
        self.assertEqual(payload["tokens"][0]["signal_vol"], "Vol $13.2K")
        self.assertEqual(
            payload["tokens"][0]["signal_summary"],
            "First 1h Last 30m Count 3 Vol $13.2K",
        )

    def test_ave_list_signals_invalidates_live_feed_session_before_fetch(self):
        signal_payload = {"data": {"list": []}}
        order = []

        def _invalidate(conn, **kwargs):
            order.append("invalidate")
            conn.ave_state["feed_session"] = 77
            return 77

        def _data_get(*args, **kwargs):
            order.append("data_get")
            return signal_payload

        with patch.object(ave_tools, "_invalidate_live_feed_session", side_effect=_invalidate), patch.object(
            ave_tools, "_data_get", side_effect=_data_get
        ), patch.object(ave_tools, "_send_display", new=AsyncMock()) as send_display:
            ave_tools.ave_list_signals(self.conn)
            self.loop.run_until_complete(asyncio.sleep(0))

        self.assertEqual(order[:2], ["invalidate", "data_get"])
        _, _, payload = send_display.await_args.args
        self.assertEqual(payload["feed_session"], 77)
        self.assertEqual(self.conn.ave_state["feed_session"], 77)

    def test_ave_open_watchlist_renders_watchlist_browse(self):
        with patch.object(
            ave_tools,
            "list_watchlist_entries",
            return_value=[{"addr": "Token111", "chain": "solana", "symbol": "BONK"}],
        ), patch.object(ave_tools, "_send_display", new=AsyncMock()) as send_display:
            ave_tools.ave_open_watchlist(self.conn)
            self.loop.run_until_complete(asyncio.sleep(0))

        self.assertEqual(send_display.await_count, 1)
        _, screen, payload = send_display.await_args.args
        self.assertEqual(screen, "browse")
        self.assertEqual(payload["mode"], "watchlist")
        self.assertEqual(payload["source_label"], "WATCHLIST")
        self.assertEqual(payload["tokens"][0]["symbol"], "BONK")
        self.assertEqual(self.conn.ave_state["screen"], "browse")
        self.assertEqual(self.conn.ave_state["feed_mode"], "watchlist")

    def test_ave_open_watchlist_uses_empty_row_when_no_entries(self):
        with patch.object(ave_tools, "list_watchlist_entries", return_value=[]), patch.object(
            ave_tools, "_send_display", new=AsyncMock()
        ) as send_display:
            ave_tools.ave_open_watchlist(self.conn)
            self.loop.run_until_complete(asyncio.sleep(0))

        self.assertEqual(send_display.await_count, 1)
        _, _, payload = send_display.await_args.args
        self.assertEqual(payload["mode"], "watchlist")
        self.assertEqual(payload["source_label"], "WATCHLIST")
        self.assertEqual(payload["tokens"][0]["symbol"], "WATCHLIST")

    def test_ave_add_current_watchlist_token_refreshes_spotlight(self):
        self.conn.ave_state = {
            "screen": "spotlight",
            "nav_from": "feed",
            "current_token": {"addr": "Token111", "chain": "solana", "symbol": "BONK"},
            "feed_cursor": 1,
            "feed_token_list": [
                {"addr": "Token000", "chain": "solana", "symbol": "OLD"},
                {"addr": "Token111", "chain": "solana", "symbol": "BONK"},
            ],
        }
        sentinel = ActionResponse(action=Action.NONE, result="ok", response=None)

        with patch.object(ave_tools, "add_watchlist_entry") as add_entry, patch.object(
            ave_tools, "ave_token_detail", return_value=sentinel
        ) as token_detail, patch.object(ave_tools, "_send_display", new=AsyncMock()):
            resp = ave_tools.ave_add_current_watchlist_token(self.conn)
            self.loop.run_until_complete(asyncio.sleep(0))

        self.assertIs(resp, sentinel)
        add_entry.assert_called_once()
        token_detail.assert_called_once_with(
            self.conn,
            addr="Token111",
            chain="solana",
            symbol="BONK",
            feed_cursor=1,
            feed_total=2,
        )

    def test_ave_remove_current_watchlist_voice_refreshes_spotlight(self):
        self.conn.ave_state = {
            "screen": "spotlight",
            "nav_from": "feed",
            "current_token": {"addr": "Token111", "chain": "solana", "symbol": "BONK"},
            "feed_cursor": 0,
            "feed_token_list": [{"addr": "Token111", "chain": "solana", "symbol": "BONK"}],
        }
        sentinel = ActionResponse(action=Action.NONE, result="ok", response=None)

        with patch.object(ave_tools, "remove_watchlist_entry", return_value=True) as remove_entry, patch.object(
            ave_tools, "ave_token_detail", return_value=sentinel
        ) as token_detail, patch.object(ave_tools, "_send_display", new=AsyncMock()):
            resp = ave_tools.ave_remove_current_watchlist_voice(self.conn)
            self.loop.run_until_complete(asyncio.sleep(0))

        self.assertIs(resp, sentinel)
        remove_entry.assert_called_once()
        token_detail.assert_called_once_with(
            self.conn,
            addr="Token111",
            chain="solana",
            symbol="BONK",
            feed_cursor=0,
            feed_total=1,
        )

    def test_portfolio_origin_watchlist_refresh_does_not_reuse_stale_feed_cursor(self):
        self.conn.ave_state = {
            "screen": "spotlight",
            "nav_from": "portfolio",
            "current_token": {"addr": "Token111", "chain": "solana", "symbol": "BONK"},
            "feed_cursor": 9,
            "feed_token_list": [
                {"addr": "stale-1", "chain": "solana", "symbol": "OLD"},
                {"addr": "stale-2", "chain": "base", "symbol": "OLD2"},
            ],
        }
        sentinel = ActionResponse(action=Action.NONE, result="ok", response=None)

        with patch.object(ave_tools, "add_watchlist_entry") as add_entry, patch.object(
            ave_tools, "ave_token_detail", return_value=sentinel
        ) as token_detail, patch.object(ave_tools, "_send_display", new=AsyncMock()):
            resp = ave_tools.ave_add_current_watchlist_token(self.conn)
            self.loop.run_until_complete(asyncio.sleep(0))

        self.assertIs(resp, sentinel)
        add_entry.assert_called_once()
        token_detail.assert_called_once_with(
            self.conn,
            addr="Token111",
            chain="solana",
            symbol="BONK",
            feed_cursor=None,
            feed_total=None,
        )

    def test_ave_add_current_watchlist_token_handles_store_failure(self):
        self.conn.ave_state = {
            "screen": "spotlight",
            "current_token": {"addr": "Token111", "chain": "solana", "symbol": "BONK"},
            "feed_cursor": 0,
            "feed_token_list": [{"addr": "Token111", "chain": "solana", "symbol": "BONK"}],
        }

        with patch.object(ave_tools, "add_watchlist_entry", side_effect=RuntimeError("disk full")), patch.object(
            ave_tools, "ave_token_detail"
        ) as token_detail, patch.object(ave_tools, "_send_display", new=AsyncMock()) as send_display:
            resp = ave_tools.ave_add_current_watchlist_token(self.conn)
            self.loop.run_until_complete(asyncio.sleep(0))

        self.assertEqual(resp.action, Action.RESPONSE)
        token_detail.assert_not_called()
        self.assertEqual(send_display.await_count, 1)
        self.assertEqual(send_display.await_args.args[1], "notify")
        self.assertEqual(send_display.await_args.args[2]["level"], "error")

    def test_ave_remove_current_watchlist_token_handles_store_failure(self):
        self.conn.ave_state = {
            "screen": "browse",
            "feed_mode": "watchlist",
            "feed_cursor": 0,
            "feed_token_list": [{"addr": "Token111", "chain": "solana", "symbol": "BONK"}],
            "current_token": {"addr": "Token111", "chain": "solana", "symbol": "BONK"},
        }

        with patch.object(ave_tools, "remove_watchlist_entry", side_effect=RuntimeError("readonly fs")), patch.object(
            ave_tools, "ave_open_watchlist"
        ) as open_watchlist, patch.object(ave_tools, "_send_display", new=AsyncMock()) as send_display:
            resp = ave_tools.ave_remove_current_watchlist_token(self.conn)
            self.loop.run_until_complete(asyncio.sleep(0))

        self.assertEqual(resp.action, Action.RESPONSE)
        open_watchlist.assert_not_called()
        self.assertEqual(send_display.await_count, 1)
        self.assertEqual(send_display.await_args.args[1], "notify")
        self.assertEqual(send_display.await_args.args[2]["level"], "error")

    def test_ave_token_detail_loading_payload_includes_origin_hint_and_watchlist_state(self):
        self.conn.ave_state = {
            "screen": "browse",
            "feed_mode": "signals",
            "feed_token_list": [{"addr": "Token111", "chain": "solana", "symbol": "BONK"}],
        }

        with patch.object(ave_tools, "watchlist_contains", return_value=True), patch.object(
            ave_tools, "_send_display", new=AsyncMock()
        ) as send_display, patch.object(ave_tools, "_ave_token_detail_async", new=AsyncMock()):
            ave_tools.ave_token_detail(
                self.conn,
                addr="Token111",
                chain="solana",
                symbol="BONK",
                feed_cursor=0,
                feed_total=1,
            )
            self.loop.run_until_complete(asyncio.sleep(0))

        loading_payload = send_display.await_args_list[0].args[2]
        self.assertEqual(loading_payload.get("origin_hint"), "From Signal")
        self.assertTrue(loading_payload.get("is_watchlisted"))

    def test_ave_token_detail_from_portfolio_clears_stale_feed_origin_hint(self):
        self.conn.ave_state = {
            "screen": "portfolio",
            "feed_mode": "signals",
            "nav_from": "portfolio",
            "portfolio_holdings": [{"addr": "Token111", "chain": "solana", "symbol": "BONK"}],
            "current_token": {"addr": "stale", "chain": "solana", "symbol": "OLD", "origin_hint": "From Signal"},
        }

        with patch.object(ave_tools, "watchlist_contains", return_value=False), patch.object(
            ave_tools, "_send_display", new=AsyncMock()
        ) as send_display, patch.object(ave_tools, "_ave_token_detail_async", new=AsyncMock()):
            ave_tools.ave_token_detail(
                self.conn,
                addr="Token111",
                chain="solana",
                symbol="BONK",
            )
            self.loop.run_until_complete(asyncio.sleep(0))

        loading_payload = send_display.await_args_list[0].args[2]
        self.assertEqual(loading_payload.get("origin_hint"), "")

    def test_ave_token_detail_same_token_from_portfolio_context_clears_stale_origin(self):
        self.conn.ave_state = {
            "screen": "spotlight",
            "feed_mode": "signals",
            "nav_from": "portfolio",
            "spotlight_origin_hint": "From Signal",
            "current_token": {
                "addr": "Token111",
                "chain": "solana",
                "symbol": "BONK",
                "origin_hint": "From Signal",
            },
        }

        with patch.object(ave_tools, "watchlist_contains", return_value=False), patch.object(
            ave_tools, "_send_display", new=AsyncMock()
        ) as send_display, patch.object(ave_tools, "_ave_token_detail_async", new=AsyncMock()):
            ave_tools.ave_token_detail(
                self.conn,
                addr="Token111",
                chain="solana",
                symbol="BONK",
            )
            self.loop.run_until_complete(asyncio.sleep(0))

        loading_payload = send_display.await_args_list[0].args[2]
        self.assertEqual(loading_payload.get("origin_hint"), "")

    def test_ave_token_detail_async_real_path_uses_provided_previous_screen(self):
        self.conn.ave_state = {
            "screen": "spotlight",
            "feed_mode": "signals",
            "nav_from": "feed",
            "spotlight_request_seq": 7,
            "current_token": {"addr": "Token111", "chain": "solana", "symbol": "BONK"},
        }

        def _data_get_side_effect(path, params=None):
            if path.startswith("/tokens/"):
                return {
                    "data": {
                        "symbol": "BONK",
                        "current_price_usd": 1.5,
                        "token_price_change_24h": 5.2,
                        "holders": 123,
                        "main_pair_tvl": 10000,
                        "token_tx_volume_usd_24h": 20000,
                        "market_cap": 500000,
                    }
                }
            if path.startswith("/klines/token/"):
                return {
                    "data": {
                        "points": [
                            {"close": 1.2, "time": 1710000000},
                            {"close": 1.5, "time": 1710003600},
                        ]
                    }
                }
            if path.startswith("/contracts/"):
                return {"data": {"risk_score": 10, "is_honeypot": False, "has_mint_method": False, "has_black_method": False}}
            raise AssertionError(f"unexpected path {path}")

        with patch.object(ave_tools, "_data_get", side_effect=_data_get_side_effect), patch.object(
            ave_tools, "_safe_top100_summary_get", return_value={}
        ), patch.object(ave_tools, "watchlist_contains", return_value=False), patch.object(
            ave_tools, "_send_display", new=AsyncMock()
        ) as send_display, patch("plugins_func.functions.ave_tools.asyncio.to_thread", new=AsyncMock(side_effect=lambda fn, *a, **k: fn(*a, **k))):
            self.loop.run_until_complete(
                ave_tools._ave_token_detail_async(
                    self.conn,
                    addr="Token111",
                    chain="solana",
                    symbol="BONK",
                    interval="60",
                    feed_cursor=0,
                    feed_total=1,
                    request_seq=7,
                    previous_screen="feed",
                )
            )

        self.assertGreaterEqual(send_display.await_count, 1)
        _, screen, payload = send_display.await_args_list[0].args
        self.assertEqual(screen, "spotlight")
        self.assertEqual(payload.get("origin_hint"), "From Signal")


if __name__ == "__main__":
    unittest.main()
