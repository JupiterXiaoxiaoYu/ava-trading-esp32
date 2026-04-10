import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from core.handle.textHandler.keyActionHandler import KeyActionHandler
from core.handle.textHandler.tradeActionHandler import TradeActionHandler
from plugins_func.functions import ave_tools


class _FakeLoop:
    def __init__(self, loop):
        self._loop = loop

    def create_task(self, coro, name=None):
        return self._loop.create_task(coro, name=name)


class _FakeConn:
    def __init__(self, loop):
        self.loop = _FakeLoop(loop)
        self.ave_state = {}


class TradeContractFixTests(unittest.IsolatedAsyncioTestCase):
    async def test_ave_confirm_trade_submit_ack_pushes_notify_then_feed(self):
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
        conn.ave_state["nav_from"] = "portfolio"

        with patch.object(ave_tools.trade_mgr, "confirm", new=AsyncMock(return_value={
            "trade_type": "market_buy",
            "status": 0,
            "msg": "Success",
            "data": {"id": "doc-order-id"},
        })), patch.object(ave_tools.trade_mgr, "reconcile_swap_order", new=AsyncMock(return_value={})), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_confirm_trade(conn)
            await asyncio.sleep(0)

        self.assertEqual([screen for screen, _ in sent], ["notify", "feed"])
        self.assertEqual(sent[0][1]["title"], "Order Submitted")
        self.assertEqual(sent[0][1]["body"], "Waiting for chain confirmation.")
        self.assertEqual(sent[1][1]["reason"], "trade_submitted")
        self.assertNotIn("pending_trade", conn.ave_state)
        self.assertNotIn("nav_from", conn.ave_state)
        self.assertEqual(conn.ave_state.get("submitted_trades", [])[0]["swap_order_id"], "doc-order-id")
        self.assertEqual(conn.ave_state.get("submitted_trades", [])[0]["trade_type"], "market_buy")
        self.assertEqual(conn.ave_state.get("screen"), "feed")

    async def test_trade_action_confirm_submit_ack_pushes_notify_then_feed(self):
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
        conn.ave_state["nav_from"] = "portfolio"

        with patch.object(ave_tools.trade_mgr, "confirm", new=AsyncMock(return_value={
            "trade_type": "market_sell",
            "status": 0,
            "msg": "Success",
            "data": {"id": "doc-order-id"},
        })), patch.object(ave_tools.trade_mgr, "reconcile_swap_order", new=AsyncMock(return_value={})), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            await handler.handle(conn, {
                "type": "trade_action",
                "action": "confirm",
                "trade_id": "sell-1",
            })

        self.assertEqual([screen for screen, _ in sent], ["notify", "feed"])
        self.assertEqual(sent[0][1]["title"], "Order Submitted")
        self.assertEqual(sent[0][1]["body"], "Waiting for chain confirmation.")
        self.assertEqual(sent[1][1]["reason"], "trade_submitted")
        self.assertNotIn("pending_trade", conn.ave_state)
        self.assertNotIn("nav_from", conn.ave_state)
        self.assertEqual(conn.ave_state.get("submitted_trades", [])[0]["swap_order_id"], "doc-order-id")
        self.assertEqual(conn.ave_state.get("submitted_trades", [])[0]["trade_type"], "market_sell")
        self.assertEqual(conn.ave_state.get("screen"), "feed")

    async def test_trade_action_cancel_rebuilds_home_feed_and_clears_nav_from(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        handler = TradeActionHandler()
        conn.ave_state.update({
            "feed_source": "gainer",
            "feed_mode": "search",
            "search_query": "BONK",
            "screen": "confirm",
            "nav_from": "portfolio",
        })
        ave_tools._set_pending_trade(
            conn,
            trade_id="cancel-1",
            trade_type="market_buy",
            action="BUY",
            symbol="BONK",
            amount_native="0.10 SOL",
        )

        with patch.object(ave_tools.trade_mgr, "cancel") as mock_cancel, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending, \
             patch("plugins_func.functions.ave_trade_mgr._send_display", new=AsyncMock()) as mock_send:
            await handler.handle(conn, {
                "type": "trade_action",
                "action": "cancel",
                "trade_id": "cancel-1",
            })
            await asyncio.sleep(0)

        mock_cancel.assert_called_once_with("cancel-1")
        mock_trending.assert_called_once_with(conn, topic="gainer")
        mock_send.assert_not_awaited()
        self.assertEqual(conn.ave_state.get("screen"), "feed")
        self.assertNotIn("pending_trade", conn.ave_state)
        self.assertNotIn("nav_from", conn.ave_state)

    async def test_key_action_back_on_confirm_uses_trade_cancel_path(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        handler = KeyActionHandler()
        conn.ave_state["screen"] = "confirm"
        ave_tools._set_pending_trade(
            conn,
            trade_id="buy-1",
            trade_type="market_buy",
            action="BUY",
            symbol="BONK",
            amount_native="0.10 SOL",
        )

        with patch("plugins_func.functions.ave_tools.ave_cancel_trade") as mock_cancel, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending, \
             patch("plugins_func.functions.ave_tools.ave_portfolio") as mock_portfolio:
            await handler.handle(conn, {"type": "key_action", "action": "back"})

        mock_cancel.assert_called_once_with(conn)
        mock_trending.assert_not_called()
        mock_portfolio.assert_not_called()

    async def test_ave_back_to_feed_cancels_pending_confirm_trade(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)

        conn.ave_state["screen"] = "confirm"
        ave_tools._set_pending_trade(
            conn,
            trade_id="buy-1",
            trade_type="market_buy",
            action="BUY",
            symbol="BONK",
            amount_native="0.10 SOL",
        )

        with patch.object(ave_tools.trade_mgr, "cancel") as mock_cancel, \
             patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending, \
             patch("plugins_func.functions.ave_tools._send_display", new=AsyncMock()) as mock_send:
            resp = ave_tools.ave_back_to_feed(conn)
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "已取消买入BONK，返回热门列表")
        mock_cancel.assert_called_once_with("buy-1")
        mock_trending.assert_called_once_with(conn, topic="trending")
        mock_send.assert_not_awaited()
        self.assertEqual(conn.ave_state.get("screen"), "feed")
        self.assertNotIn("pending_trade", conn.ave_state)

    async def test_key_action_buy_strips_chain_suffix_from_spotlight_token_id(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools.ave_buy_token") as mock_buy:
            await handler.handle(conn, {
                "type": "key_action",
                "action": "buy",
                "token_id": "token-123-base",
            })

        mock_buy.assert_called_once_with(conn, addr="token-123", chain="base", in_amount_sol=0.1)

    async def test_key_action_kline_interval_strips_chain_suffix_from_spotlight_token_id(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools.ave_token_detail") as mock_detail:
            await handler.handle(conn, {
                "type": "key_action",
                "action": "kline_interval",
                "token_id": "token-123-eth",
                "interval": "5",
            })

        mock_detail.assert_called_once_with(conn, addr="token-123", chain="eth", interval="5")

    async def test_ave_limit_order_blocks_critical_risk_before_create(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._data_get", return_value={
            "data": {"risk_score": 90, "is_honeypot": True}
        }), patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools.trade_mgr.create") as mock_create:
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

        self.assertEqual(resp.result, "BLOCKED")
        mock_create.assert_not_called()
        self.assertEqual(sent[0][0], "notify")
        self.assertEqual(sent[0][1]["level"], "error")
        self.assertEqual(sent[0][1]["title"], "Dangerous Token Blocked")
        self.assertEqual(sent[0][1]["body"], "Honeypot contract detected. Limit order cancelled.")
        self.assertEqual(conn.ave_state.get("screen"), None)


if __name__ == "__main__":
    unittest.main()
