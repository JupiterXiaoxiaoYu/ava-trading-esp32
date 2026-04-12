import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.handle.textHandler.keyActionHandler import KeyActionHandler
from core.handle.textHandler.tradeActionHandler import TradeActionHandler
from plugins_func.functions import ave_tools, ave_wss
from plugins_func.functions.ave_trade_mgr import trade_mgr


class _FakeLoop:
    def __init__(self, loop):
        self._loop = loop

    def create_task(self, coro, name=None):
        return self._loop.create_task(coro, name=name)


class _FakeConn:
    def __init__(self, loop):
        self.loop = _FakeLoop(loop)
        self.ave_state = {}
        self.websocket = MagicMock()


class TradeFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        trade_mgr._pending.clear()

    async def test_trade_action_confirm_rejects_mismatched_pending_trade_id(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        handler = TradeActionHandler()

        ave_tools._set_pending_trade(
            conn,
            trade_id="sell-1",
            trade_type="market_sell",
            action="SELL",
            symbol="BONK",
            amount_native="100% holdings",
        )

        confirm_mock = AsyncMock(return_value={"trade_type": "market_sell", "data": {}})
        send_mock = AsyncMock()
        with patch.object(trade_mgr, "confirm", new=confirm_mock), \
             patch("plugins_func.functions.ave_trade_mgr._send_display", new=send_mock):
            await handler.handle(conn, {
                "type": "trade_action",
                "action": "confirm",
                "trade_id": "sell-2",
            })

        confirm_mock.assert_not_awaited()
        send_mock.assert_not_awaited()
        self.assertEqual(conn.ave_state["pending_trade"]["trade_id"], "sell-1")
        self.assertEqual(conn.ave_state["screen"], "confirm")

    async def test_ave_confirm_trade_result_text_matches_sell_action(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="sell-1",
            trade_type="market_sell",
            action="SELL",
            symbol="BONK",
            amount_native="100% holdings",
        )

        with patch.object(ave_tools.trade_mgr, "confirm", new=AsyncMock(return_value={
            "trade_type": "market_sell",
            "status": 0,
            "data": {
                "outAmount": "1.5 SOL",
                "outAmountUsd": "$225.00",
                "txId": "abcd1234efgh5678",
            },
        })), patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            resp = ave_tools.ave_confirm_trade(conn)
            await asyncio.sleep(0)

        self.assertIn("卖出", resp.result)
        self.assertEqual(sent[0][0], "result")
        self.assertEqual(sent[0][1]["title"], "Sold!")
        self.assertEqual(sent[0][1]["tx_id"], "abcd1234efgh")

    async def test_ave_confirm_trade_without_pending_returns_no_pending(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)

        with patch.object(ave_tools.trade_mgr, "confirm", new=AsyncMock()) as confirm_mock:
            resp = ave_tools.ave_confirm_trade(conn)

        confirm_mock.assert_not_awaited()
        self.assertEqual(resp.result, "no_pending")
        self.assertIn("没有待确认的交易", resp.response)

    async def test_trade_timeout_pushes_explicit_auto_cancel_explanation(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        trade_mgr._pending["timeout-1"] = {
            "type": "market_sell",
            "params": {},
            "conn": conn,
            "ts": 0,
        }
        ave_tools._set_pending_trade(
            conn,
            trade_id="timeout-1",
            trade_type="market_sell",
            action="SELL",
            symbol="BONK",
            amount_native="100% holdings",
        )

        with patch("plugins_func.functions.ave_trade_mgr._send_display", side_effect=_fake_send_display):
            await trade_mgr._timeout("timeout-1", 0)

        self.assertEqual(sent[0][0], "result")
        self.assertFalse(sent[0][1]["success"])
        self.assertEqual(sent[0][1]["title"], "Trade Cancelled")
        self.assertIn("timed out", sent[0][1]["subtitle"].lower())
        self.assertEqual(sent[0][1]["explain_state"], "confirm_timeout")
        self.assertNotIn("pending_trade", conn.ave_state)
        self.assertEqual(conn.ave_state.get("screen"), "result")

    async def test_wss_confirmed_sell_event_uses_result_contract(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        manager = ave_wss.AveWssManager(conn)
        raw = json.dumps({
            "topic": "botswap",
            "status": "confirmed",
            "swapType": "sell",
            "inTokenSymbol": "BONK",
            "outTokenSymbol": "SOL",
            "outAmount": "1.5 SOL",
            "amountUsd": "225.00",
            "txHash": "deadbeefcafebabe1234",
        })

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await manager._handle_trade_event(raw)

        self.assertEqual(sent[0][0], "result")
        payload = sent[0][1]
        self.assertTrue(payload["success"])
        self.assertEqual(payload["title"], "Sold!")
        self.assertEqual(payload["out_amount"], "1.5 SOL")
        self.assertEqual(payload["amount_usd"], "225.00")
        self.assertEqual(payload["tx_id"], "deadbeefcafe")
        self.assertNotIn("tx_hash", payload)
        self.assertEqual(conn.ave_state.get("screen"), "result")

    async def test_wss_terminal_trade_events_do_not_hijack_confirm_screen_without_correlation(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []
        manager = ave_wss.AveWssManager(conn)

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="sell-1",
            trade_type="market_sell",
            action="SELL",
            symbol="BONK",
            amount_native="100% holdings",
        )

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await manager._handle_trade_event(json.dumps({
                "topic": "botswap",
                "status": "error",
                "swapType": "sell",
                "errorMessage": "simulated failure",
            }))

        self.assertEqual(sent[0][0], "notify")
        self.assertEqual(conn.ave_state.get("pending_trade", {}).get("trade_id"), "sell-1")
        self.assertEqual(conn.ave_state.get("pending_trade_id"), "sell-1")
        self.assertEqual(conn.ave_state.get("screen"), "confirm")
        self.assertEqual(len(conn.ave_state.get("deferred_result_queue", [])), 1)

    async def test_wss_terminal_trade_events_keep_mismatched_pending_state(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)

        ave_tools._set_pending_trade(
            conn,
            trade_id="buy-1",
            trade_type="market_buy",
            action="BUY",
            symbol="BONK",
            amount_native="0.10 SOL",
        )

        with patch("plugins_func.functions.ave_wss._send_display", new=AsyncMock()):
            await manager._handle_trade_event(json.dumps({
                "topic": "botswap",
                "status": "confirmed",
                "swapType": "sell",
                "inTokenSymbol": "BONK",
                "outAmount": "1.5 SOL",
            }))

        self.assertEqual(conn.ave_state.get("pending_trade", {}).get("trade_id"), "buy-1")
        self.assertEqual(conn.ave_state.get("pending_trade_id"), "buy-1")

    async def test_wss_terminal_trade_event_matches_active_pending_by_direction_when_ids_absent(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="sell-1",
            trade_type="market_sell",
            action="SELL",
            symbol="BONK",
            amount_native="100% holdings",
        )

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await manager._handle_trade_event(json.dumps({
                "topic": "botswap",
                "status": "confirmed",
                "swapType": "sell",
                "inTokenSymbol": "BONK",
                "outAmount": "1.5 SOL",
                "amountUsd": "225.00",
                "txHash": "deadbeefcafebabe1234",
            }))

        self.assertEqual(sent[0][0], "result")
        self.assertEqual(sent[0][1]["title"], "Sold!")
        self.assertNotIn("pending_trade", conn.ave_state)
        self.assertEqual(conn.ave_state.get("screen"), "result")
        self.assertEqual(conn.ave_state.get("deferred_result_queue", []), [])

    async def test_wss_terminal_trade_event_does_not_fallback_when_explicit_id_mismatches(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="sell-1",
            trade_type="market_sell",
            action="SELL",
            symbol="BONK",
            amount_native="100% holdings",
        )

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await manager._handle_trade_event(json.dumps({
                "topic": "botswap",
                "status": "confirmed",
                "tradeId": "sell-2",
                "swapType": "sell",
                "inTokenSymbol": "BONK",
                "outAmount": "1.5 SOL",
                "amountUsd": "225.00",
                "txHash": "deadbeefcafebabe1234",
            }))

        self.assertEqual(sent[0][0], "notify")
        self.assertEqual(sent[0][1]["title"], "Result Deferred")
        self.assertEqual(
            sent[0][1]["body"],
            "Another confirmation flow is active. Result will appear next.",
        )
        self.assertEqual(conn.ave_state.get("pending_trade", {}).get("trade_id"), "sell-1")
        self.assertEqual(conn.ave_state.get("screen"), "confirm")
        self.assertEqual(len(conn.ave_state.get("deferred_result_queue", [])), 1)

    async def test_wss_event_without_ids_prefers_unique_chain_matched_submitted_trade_over_pending(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="sell-sol-1",
            trade_type="market_sell",
            action="SELL",
            symbol="BONK",
            amount_native="100% holdings",
            chain="solana",
            asset_token_address="bonk-sol",
        )
        conn.ave_state["submitted_trades"] = [{
            "trade_id": "sell-base-1",
            "swap_order_id": "swap-base-1",
            "trade_type": "market_sell",
            "symbol": "BONK",
            "chain": "base",
            "asset_token_address": "bonk-base",
        }]

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            await manager._handle_trade_event(json.dumps({
                "topic": "botswap",
                "status": "confirmed",
                "swapType": "sell",
                "chain": "base",
                "inTokenSymbol": "BONK",
                "inTokenAddress": "bonk-base",
                "outAmount": "1.5 SOL",
                "txHash": "deadbeefcafebabe1234",
            }))

        self.assertEqual(sent[0][0], "notify")
        self.assertEqual(sent[0][1]["title"], "Result Deferred")
        self.assertEqual(conn.ave_state.get("pending_trade", {}).get("trade_id"), "sell-sol-1")
        self.assertEqual(conn.ave_state.get("submitted_trades", []), [])
        self.assertEqual(len(conn.ave_state.get("deferred_result_queue", [])), 1)
        self.assertEqual(conn.ave_state.get("screen"), "confirm")

    async def test_wss_event_without_ids_ignores_ambiguous_submitted_trade_candidates(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        conn.ave_state["submitted_trades"] = [
            {
                "trade_id": "sell-1",
                "swap_order_id": "swap-1",
                "trade_type": "market_sell",
                "symbol": "BONK",
                "chain": "solana",
                "asset_token_address": "bonk-sol",
            },
            {
                "trade_id": "sell-2",
                "swap_order_id": "swap-2",
                "trade_type": "market_sell",
                "symbol": "BONK",
                "chain": "solana",
                "asset_token_address": "bonk-sol",
            },
        ]

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await manager._handle_trade_event(json.dumps({
                "topic": "botswap",
                "status": "confirmed",
                "swapType": "sell",
                "chain": "solana",
                "inTokenSymbol": "BONK",
                "inTokenAddress": "bonk-sol",
                "outAmount": "1.5 SOL",
                "txHash": "deadbeefcafebabe1234",
            }))

        self.assertEqual(sent, [])
        self.assertEqual(len(conn.ave_state.get("submitted_trades", [])), 2)

    async def test_deferred_wss_terminal_result_flushes_after_pending_clears(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        # Trade B is currently awaiting confirm on this connection.
        ave_tools._set_pending_trade(
            conn,
            trade_id="buy-2",
            trade_type="market_buy",
            action="BUY",
            symbol="WIF",
            amount_native="0.10 SOL",
        )

        # Trade A terminal event arrives while B is pending: must defer, not drop.
        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            await manager._handle_trade_event(json.dumps({
                "topic": "botswap",
                "status": "confirmed",
                "swapType": "sell",
                "inTokenSymbol": "BONK",
                "outAmount": "1.5 SOL",
                "amountUsd": "225.00",
                "txHash": "deadbeefcafebabe1234",
            }))

            self.assertEqual(sent[0][0], "notify")
            self.assertEqual(conn.ave_state.get("screen"), "confirm")
            self.assertEqual(len(conn.ave_state.get("deferred_result_queue", [])), 1)

            # Now B is resolved/cleared and UI leaves confirm; deferred A result should flush.
            ave_tools._clear_pending_trade(conn, "buy-2")
            conn.ave_state["screen"] = "feed"
            await asyncio.sleep(0.2)

        self.assertEqual(sent[1][0], "result")
        self.assertEqual(sent[1][1]["title"], "Sold!")
        self.assertEqual(sent[1][1]["tx_id"], "deadbeefcafe")
        self.assertEqual(conn.ave_state.get("screen"), "result")
        self.assertEqual(conn.ave_state.get("deferred_result_queue", []), [])

    async def test_ave_confirm_trade_submit_ack_uses_submission_title(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="buy-1",
            trade_type="market_buy",
            action="BUY",
            symbol="BONK",
            amount_native="0.10 SOL",
        )

        with patch.object(ave_tools.trade_mgr, "confirm", new=AsyncMock(return_value={
            "trade_type": "market_buy",
            "status": 0,
            "msg": "Success",
            "data": {"id": "doc-order-id"},
        })), patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_confirm_trade(conn)
            await asyncio.sleep(0)

        self.assertEqual(sent[0][0], "notify")
        self.assertIn("Submitted", sent[0][1]["title"])
        self.assertNotIn("pending_trade", conn.ave_state)
        self.assertEqual(conn.ave_state.get("screen"), "feed")

    async def test_submit_only_swap_ack_background_reconcile_pushes_terminal_result(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="buy-1",
            trade_type="market_buy",
            action="BUY",
            symbol="BONK",
            amount_native="0.10 SOL",
        )

        with patch.object(ave_tools.trade_mgr, "confirm", new=AsyncMock(return_value={
            "trade_type": "market_buy",
            "status": 0,
            "msg": "Success",
            "chain": "solana",
            "data": {"id": "swap-order-123"},
        })), patch.object(ave_tools.trade_mgr, "reconcile_swap_order", new=AsyncMock(return_value={
            "trade_type": "market_buy",
            "status": "confirmed",
            "swap_order_id": "swap-order-123",
            "chain": "solana",
            "data": {
                "outAmount": "52752 BONK",
                "txHash": "feedfacecafebeef00112233",
            },
        })), patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_confirm_trade(conn)
            await asyncio.sleep(0.1)

        self.assertEqual([screen for screen, _ in sent], ["notify", "feed", "result"])
        self.assertEqual(sent[2][1]["title"], "Bought!")
        self.assertEqual(sent[2][1]["tx_id"], "feedfacecafe")
        self.assertEqual(conn.ave_state.get("submitted_trades", []), [])
        self.assertEqual(conn.ave_state.get("screen"), "result")

    async def test_trade_action_confirm_submit_ack_uses_non_terminal_notify(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        handler = TradeActionHandler()
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="sell-1",
            trade_type="market_sell",
            action="SELL",
            symbol="BONK",
            amount_native="100% holdings",
        )

        with patch.object(trade_mgr, "confirm", new=AsyncMock(return_value={
            "trade_type": "market_sell",
            "status": 0,
            "msg": "Success",
            "data": {"id": "doc-order-id"},
        })), patch.object(trade_mgr, "reconcile_swap_order", new=AsyncMock(return_value={})), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            await handler.handle(conn, {
                "type": "trade_action",
                "action": "confirm",
                "trade_id": "sell-1",
            })

        self.assertEqual(sent[0][0], "notify")
        self.assertIn("Submitted", sent[0][1]["title"])
        self.assertNotIn("pending_trade", conn.ave_state)
        self.assertEqual(conn.ave_state.get("screen"), "feed")

    async def test_ave_sell_token_uses_proxy_payload_shape_and_solana_gas(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _env_get(key, default=None):
            if key == "AVE_PROXY_WALLET_ID":
                return "wallet-sell"
            return default

        with patch("plugins_func.functions.ave_tools.trade_mgr.create", return_value="sell123") as mock_create, \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools.os.environ.get", side_effect=_env_get):
            resp = ave_tools.ave_sell_token(
                conn,
                addr="token-1",
                chain="solana",
                sell_ratio=0.5,
                symbol="BONK",
                holdings_amount="2000",
            )
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "sell_pending:sell123")
        trade_type, trade_params, passed_conn = mock_create.call_args[0]
        self.assertEqual(trade_type, "market_sell")
        self.assertIs(passed_conn, conn)
        self.assertEqual(trade_params["chain"], "solana")
        self.assertEqual(trade_params["assetsId"], "wallet-sell")
        self.assertEqual(trade_params["inTokenAddress"], "token-1")
        self.assertEqual(trade_params["outTokenAddress"], "sol")
        self.assertEqual(trade_params["inAmount"], "1000")
        self.assertEqual(trade_params["swapType"], "sell")
        self.assertEqual(trade_params["slippage"], "100")
        self.assertEqual(trade_params["gas"], "1000000")
        self.assertEqual(trade_params["autoGas"], "average")
        self.assertEqual(sent[0][0], "confirm")
        confirm_payload = sent[0][1]
        self.assertEqual(confirm_payload["trade_id"], "sell123")
        self.assertIsNone(confirm_payload["tp_pct"])
        self.assertIsNone(confirm_payload["sl_pct"])
        self.assertEqual(confirm_payload["slippage_pct"], ave_tools.DEFAULT_SLIPPAGE / 100)
        self.assertEqual(confirm_payload["timeout_sec"], ave_tools.TRADE_CONFIRM_TIMEOUT_SEC)

    async def test_ave_limit_order_tracks_limit_confirm_screen_state(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools.trade_mgr.create", return_value="limit-1"), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools._data_get", side_effect=RuntimeError("skip risk lookup")):
            resp = ave_tools.ave_limit_order(
                conn,
                addr="token-limit",
                chain="solana",
                in_amount_sol=0.25,
                limit_price=0.1234,
                current_price=0.2,
                symbol="BONK",
                expire_hours=24,
            )
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "limit_pending:limit-1")
        self.assertEqual(conn.ave_state.get("screen"), "limit_confirm")
        self.assertEqual(conn.ave_state.get("pending_trade", {}).get("trade_id"), "limit-1")
        self.assertEqual(sent[0][0], "limit_confirm")

    async def test_deferred_result_flush_waits_until_limit_confirm_screen_exits(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="limit-2",
            trade_type="limit_buy",
            action="LIMIT BUY",
            symbol="BONK",
            amount_native="0.25 SOL",
        )
        conn.ave_state["screen"] = "limit_confirm"
        ave_tools._queue_deferred_result_payload(conn, {
            "title": "Bought!",
            "tx_id": "deadbeefcafe",
        })

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools._clear_pending_trade(conn, "limit-2")
            await asyncio.sleep(0.1)
            self.assertEqual(sent, [])

            conn.ave_state["screen"] = "feed"
            await asyncio.sleep(0.2)

        self.assertEqual(sent, [("result", {
            "title": "Bought!",
            "tx_id": "deadbeefcafe",
            "explain_state": "deferred_result",
        })])
        self.assertEqual(conn.ave_state.get("screen"), "result")

    async def test_deferred_result_flush_preserves_explanation_text(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="buy-9",
            trade_type="market_buy",
            action="BUY",
            symbol="BONK",
            amount_native="0.10 SOL",
        )
        conn.ave_state["screen"] = "confirm"
        ave_tools._queue_deferred_result_payload(conn, {
            "success": False,
            "title": "Trade Cancelled",
            "error": "Confirmation timed out.",
            "subtitle": "Confirmation timed out. Nothing was executed.",
        })

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools._clear_pending_trade(conn, "buy-9")
            conn.ave_state["screen"] = "feed"
            await asyncio.sleep(0.2)

        self.assertEqual(sent[0][0], "result")
        self.assertEqual(sent[0][1]["title"], "Trade Cancelled")
        self.assertEqual(
            sent[0][1]["subtitle"],
            "Confirmation timed out. Nothing was executed.",
        )
        self.assertEqual(sent[0][1]["explain_state"], "deferred_result")

    async def test_deferred_result_flush_shows_one_result_per_exit(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="buy-10",
            trade_type="market_buy",
            action="BUY",
            symbol="BONK",
            amount_native="0.10 SOL",
        )
        conn.ave_state["screen"] = "confirm"
        ave_tools._queue_deferred_result_payload(conn, {"title": "First Result"})
        ave_tools._queue_deferred_result_payload(conn, {"title": "Second Result"})

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools._clear_pending_trade(conn, "buy-10")
            conn.ave_state["screen"] = "feed"
            await asyncio.sleep(0.2)

            self.assertEqual(sent, [("result", {"title": "First Result", "explain_state": "deferred_result"})])
            self.assertEqual(conn.ave_state.get("screen"), "result")
            self.assertEqual(
                conn.ave_state.get("deferred_result_queue", []),
                [{"title": "Second Result", "explain_state": "deferred_result"}],
            )

            await asyncio.sleep(0.2)
            self.assertEqual(len(sent), 1)

            conn.ave_state["screen"] = "feed"
            await asyncio.sleep(0.2)

        self.assertEqual(
            sent,
            [
                ("result", {"title": "First Result", "explain_state": "deferred_result"}),
                ("result", {"title": "Second Result", "explain_state": "deferred_result"}),
            ],
        )
        self.assertEqual(conn.ave_state.get("deferred_result_queue", []), [])

    async def test_deferred_result_flush_reschedules_after_blocked_poll_window_expires(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="buy-11",
            trade_type="market_buy",
            action="BUY",
            symbol="BONK",
            amount_native="0.10 SOL",
        )
        conn.ave_state["screen"] = "confirm"
        ave_tools._queue_deferred_result_payload(conn, {"title": "Late Result"})

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch.object(ave_tools, "_DEFERRED_RESULT_FLUSH_POLL_ATTEMPTS", 1), \
             patch.object(ave_tools, "_DEFERRED_RESULT_FLUSH_BLOCKED_DELAY_SEC", 0.01):
            ave_tools._clear_pending_trade(conn, "buy-11")
            conn.ave_state["screen"] = "result"
            await asyncio.sleep(0.05)

            self.assertEqual(sent, [])
            self.assertEqual(
                conn.ave_state.get("deferred_result_queue", []),
                [{"title": "Late Result", "explain_state": "deferred_result"}],
            )

            conn.ave_state["screen"] = "feed"
            await asyncio.sleep(0.05)

        self.assertEqual(
            sent,
            [("result", {"title": "Late Result", "explain_state": "deferred_result"})],
        )
        self.assertEqual(conn.ave_state.get("deferred_result_queue", []), [])

    async def test_key_action_cancel_trade_invokes_cancel_helper(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools.ave_cancel_trade") as mock_cancel:
            await handler.handle(conn, {"type": "key_action", "action": "cancel_trade"})

        mock_cancel.assert_called_once_with(conn)

    async def test_ave_cancel_trade_clears_pending_and_returns_feed(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        ave_tools._set_pending_trade(
            conn,
            trade_id="cancel-1",
            trade_type="market_buy",
            action="BUY",
            symbol="BONK",
            amount_native="0.1 SOL",
        )

        with patch.object(ave_tools.trade_mgr, "cancel") as mock_cancel, \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            resp = ave_tools.ave_cancel_trade(conn)
            await asyncio.sleep(0)

        mock_cancel.assert_called_once_with("cancel-1")
        self.assertNotIn("pending_trade", conn.ave_state)
        self.assertEqual(conn.ave_state.get("screen"), "feed")
        self.assertEqual(sent[0], ("feed", {"reason": "user_cancel"}))
        self.assertIn("返回热门列表", resp.result)

    async def test_ave_back_to_feed_pushes_feed_navigation_event(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state["screen"] = "spotlight"
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            resp = ave_tools.ave_back_to_feed(conn)
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "已返回热门列表")
        self.assertEqual(conn.ave_state["screen"], "feed")
        self.assertEqual(sent[0], ("feed", {"reason": "navigate_back"}))

    def test_ave_buy_token_without_addr_or_current_token_returns_no_token(self):
        loop = asyncio.new_event_loop()
        try:
            conn = _FakeConn(loop)
            with patch("plugins_func.functions.ave_tools._data_get") as mock_data_get:
                resp = ave_tools.ave_buy_token(conn)
        finally:
            loop.close()

        mock_data_get.assert_not_called()
        self.assertEqual(resp.result, "no_token")
        self.assertIn("请先查看一个代币详情", resp.response)

    async def test_key_action_portfolio_sell_preserves_balance_raw_string(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        handler = KeyActionHandler()
        balance_raw = "12345678901234567890.123456789"

        with patch("plugins_func.functions.ave_tools.ave_sell_token") as mock_sell:
            await handler.handle(conn, {
                "type": "key_action",
                "action": "portfolio_sell",
                "addr": "token-1",
                "chain": "solana",
                "symbol": "BONK",
                "balance_raw": balance_raw,
            })

        mock_sell.assert_called_once_with(
            conn,
            addr="token-1",
            chain="solana",
            symbol="BONK",
            holdings_amount=balance_raw,
            sell_ratio=1.0,
        )

    async def test_portfolio_watch_back_returns_portfolio(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(conn, {
                "type": "key_action",
                "action": "portfolio_watch",
                "token_id": "token-1",
                "chain": "solana",
            })

        self.assertEqual(conn.ave_state.get("nav_from"), "portfolio")
        mock_detail.assert_called_once_with(conn, addr="token-1", chain="solana")

        with patch("plugins_func.functions.ave_tools.ave_portfolio") as mock_portfolio, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_feed:
            await handler.handle(conn, {"type": "key_action", "action": "back"})

        mock_portfolio.assert_called_once_with(conn)
        mock_feed.assert_not_called()
        self.assertNotIn("nav_from", conn.ave_state)

    async def test_trade_result_back_returns_portfolio_when_nav_from_portfolio(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        key_handler = KeyActionHandler()
        trade_handler = TradeActionHandler()
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        conn.ave_state["nav_from"] = "portfolio"
        ave_tools._set_pending_trade(
            conn,
            trade_id="sell-1",
            trade_type="market_sell",
            action="SELL",
            symbol="BONK",
            amount_native="100% holdings",
        )

        with patch.object(trade_mgr, "confirm", new=AsyncMock(return_value={
            "trade_type": "market_sell",
            "status": 0,
            "data": {"outAmount": "0 SOL", "txId": "tx-portfolio-123"},
        })), patch("plugins_func.functions.ave_trade_mgr._send_display", side_effect=_fake_send_display):
            await trade_handler.handle(conn, {
                "type": "trade_action",
                "action": "confirm",
                "trade_id": "sell-1",
            })

        self.assertEqual(conn.ave_state.get("screen"), "result")
        self.assertEqual(conn.ave_state.get("nav_from"), "portfolio")
        self.assertEqual(sent[0][0], "result")

        with patch("plugins_func.functions.ave_tools.ave_portfolio") as mock_portfolio, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_feed:
            await key_handler.handle(conn, {"type": "key_action", "action": "back"})

        mock_portfolio.assert_called_once_with(conn)
        mock_feed.assert_not_called()
        self.assertNotIn("nav_from", conn.ave_state)

    async def test_key_action_back_returns_to_portfolio_and_clears_nav_from(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {"nav_from": "portfolio", "screen": "spotlight"}
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools.ave_portfolio") as mock_portfolio, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(conn, {"type": "key_action", "action": "back"})

        mock_portfolio.assert_called_once_with(conn)
        mock_trending.assert_not_called()
        self.assertNotIn("nav_from", conn.ave_state)

    async def test_search_reentry_clears_stale_nav_from_before_spotlight_back(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {
            "screen": "spotlight",
            "nav_from": "portfolio",
            "feed_source": "trending",
        }
        search_items = [
            {"token_id": "token-1", "chain": "solana", "symbol": "BONK", "price": 1.0},
            {"token_id": "token-2", "chain": "base", "symbol": "ROCKET", "price": 2.0},
        ]
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _fake_data_get(path, params=None):
            if path == "/tokens":
                return {"data": {"tokens": search_items}}
            raise AssertionError(f"unexpected path: {path}")

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_search_token(conn, keyword="BONK")
            await asyncio.sleep(0)

        self.assertNotIn("nav_from", conn.ave_state)
        conn.ave_state["screen"] = "spotlight"
        conn.ave_state["current_token"] = {
            "addr": "token-1",
            "chain": "solana",
            "symbol": "BONK",
            "token_id": "token-1-solana",
        }
        sent.clear()
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools.ave_portfolio") as mock_portfolio, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(conn, {"type": "key_action", "action": "back"})

        mock_portfolio.assert_not_called()
        mock_trending.assert_not_called()
        feed_payload = next((payload for screen, payload in sent if screen == "feed"), None)
        self.assertIsNotNone(feed_payload)
        self.assertEqual(feed_payload.get("mode"), "search")
        self.assertEqual(feed_payload.get("search_query"), "BONK")

    async def test_key_action_back_restores_platform_feed_context(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {
            "screen": "spotlight",
            "feed_source": "trending",
            "feed_platform": "pump_in_hot",
        }
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools.ave_portfolio") as mock_portfolio, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(conn, {"type": "key_action", "action": "back"})

        mock_portfolio.assert_not_called()
        mock_trending.assert_called_once_with(conn, topic="", platform="pump_in_hot")

    async def test_key_action_feed_platform_reuses_existing_platform_feed(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(
                conn,
                {"type": "key_action", "action": "feed_platform", "platform": "pump_in_hot"},
            )

        mock_trending.assert_called_once_with(conn, topic="", platform="pump_in_hot")
        self.assertEqual(conn.ave_state["feed_source"], "trending")
        self.assertEqual(conn.ave_state["feed_platform"], "pump_in_hot")

    async def test_key_action_feed_platform_rejects_unknown_platform_without_mutating_state(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {
            "feed_source": "gainer",
            "feed_platform": "pump_in_hot",
        }
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending:
            await handler.handle(
                conn,
                {"type": "key_action", "action": "feed_platform", "platform": "definitely_unknown"},
            )

        mock_trending.assert_not_called()
        self.assertEqual(conn.ave_state["feed_source"], "gainer")
        self.assertEqual(conn.ave_state["feed_platform"], "pump_in_hot")

    async def test_key_action_portfolio_watch_marks_portfolio_nav_origin(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(conn, {
                "type": "key_action",
                "action": "portfolio_watch",
                "token_id": "token-1",
                "chain": "solana",
            })

        mock_detail.assert_called_once_with(conn, addr="token-1", chain="solana")
        self.assertEqual(conn.ave_state.get("nav_from"), "portfolio")


if __name__ == "__main__":
    unittest.main()
