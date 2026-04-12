import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.handle.textHandler.keyActionHandler import KeyActionHandler
from plugins_func.functions import ave_tools
from plugins_func.functions.ave_paper_store import get_paper_account, mutate_account


class _FakeLoop:
    def __init__(self, loop):
        self._loop = loop

    def create_task(self, coro, name=None):
        return self._loop.create_task(coro, name=name)


class _FakeConn:
    def __init__(self, loop):
        self.loop = _FakeLoop(loop)
        self.ave_state = {}


class PaperModeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.paper_store = Path(self._tmpdir.name) / "paper_store.json"
        self.env_patch = patch.dict(
            os.environ,
            {
                "AVE_PAPER_STORE_PATH": str(self.paper_store),
            },
            clear=False,
        )
        self.env_patch.start()
        self.trade_timeout_patches = [
            patch("plugins_func.functions.ave_trade_mgr.TRADE_CONFIRM_TIMEOUT_SEC", 0.01),
            patch("plugins_func.functions.ave_tools.TRADE_CONFIRM_TIMEOUT_SEC", 0.01),
        ]
        for patcher in self.trade_timeout_patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.trade_timeout_patches):
            patcher.stop()
        self.env_patch.stop()
        self._tmpdir.cleanup()
        super().tearDown()

    def _conn(self):
        return _FakeConn(asyncio.get_running_loop())

    @staticmethod
    def _drop_pending_trade(conn):
        conn.ave_state.pop("pending_trade", None)
        conn.ave_state.pop("pending_trade_id", None)
        conn.ave_state.pop("pending_symbol", None)
        conn.ave_state["screen"] = "feed"

    async def test_set_trade_mode_persists_and_builds_explorer_payload(self):
        conn = self._conn()

        result = ave_tools.ave_set_trade_mode(conn, "paper")

        self.assertEqual(result.result, "trade_mode:paper")
        self.assertEqual(conn.ave_state["trade_mode"], "paper")

        payload = ave_tools._build_explorer_payload(conn)
        self.assertEqual(payload["trade_mode"], "paper")
        self.assertEqual(payload["trade_mode_label"], "Paper Trading")

    async def test_paper_portfolio_uses_seed_balances(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")
        sent = []

        async def _fake_send_display(conn_obj, screen, data):
            sent.append((screen, data))

        def _fake_data_post(path, payload):
            self.assertEqual(path, "/tokens/price")
            return {
                "data": {
                    token_id: {"current_price_usd": 1}
                    for token_id in payload.get("token_ids", [])
                }
            }

        with patch("plugins_func.functions.ave_tools._send_display", new=_fake_send_display), patch(
            "plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post
        ):
            result = ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        self.assertEqual(result.result, "paper_portfolio:1tokens")
        self.assertTrue(sent)
        screen, payload = sent[-1]
        self.assertEqual(screen, "portfolio")
        self.assertEqual(payload["pnl_reason"], "Paper account")
        self.assertEqual(payload["mode_label"], "PAPER")
        self.assertEqual(payload["chain_label"], "SOL")
        self.assertEqual(len(payload["holdings"]), 1)
        self.assertEqual(payload["holdings"][0]["symbol"], "SOL")

    async def test_paper_orders_feed_uses_paper_label(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")
        sent = []

        async def _fake_send_display(conn_obj, screen, data):
            sent.append((screen, data))

        with patch("plugins_func.functions.ave_tools._send_display", new=_fake_send_display):
            result = ave_tools.ave_list_orders(conn, chain="solana")
            await asyncio.sleep(0)

        self.assertEqual(result.result, "没有未完成挂单")
        self.assertTrue(sent)
        screen, payload = sent[-1]
        self.assertEqual(screen, "feed")
        self.assertEqual(payload["mode"], "orders")
        self.assertEqual(payload["source_label"], "PAPER ORDERS")
        self.assertEqual(conn.ave_state["feed_mode"], "orders")

    async def test_paper_portfolio_activity_detail_uses_real_aligned_fields(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")
        sent = []

        def _mutate(account):
            account["fills"] = [
                {
                    "id": "buy-1",
                    "trade_type": "market_buy",
                    "chain": "solana",
                    "addr": "token-1",
                    "symbol": "BONK",
                    "token_amount": "100",
                    "amount_usd": "100",
                    "created_at": 1000,
                },
                {
                    "id": "buy-2",
                    "trade_type": "limit_buy",
                    "chain": "solana",
                    "addr": "token-1",
                    "symbol": "BONK",
                    "token_amount": "50",
                    "amount_usd": "50",
                    "created_at": 2000,
                },
                {
                    "id": "sell-1",
                    "trade_type": "market_sell",
                    "chain": "solana",
                    "addr": "token-1",
                    "symbol": "BONK",
                    "token_amount": "40",
                    "amount_usd": "80",
                    "created_at": 3000,
                },
            ]
            account["open_orders"] = [
                {"id": "ord-1", "addr": "token-1", "chain": "solana", "status": "waiting"},
                {"id": "ord-2", "addr": "other", "chain": "solana", "status": "waiting"},
            ]

        mutate_account(self.paper_store, "default", _mutate)

        async def _fake_send_display(conn_obj, screen, data):
            sent.append((screen, data))

        with patch("plugins_func.functions.ave_tools._send_display", new=_fake_send_display):
            result = ave_tools.ave_portfolio_activity_detail(
                conn,
                addr="token-1",
                chain="solana",
                symbol="BONK",
            )
            await asyncio.sleep(0)

        self.assertEqual(result.result, "portfolio_activity_detail")
        self.assertTrue(sent)
        screen, payload = sent[-1]
        self.assertEqual(screen, "portfolio")
        self.assertEqual(payload["view"], "detail")
        self.assertEqual(payload["mode_label"], "PAPER")
        self.assertEqual(payload["symbol"], "BONK")
        self.assertEqual(payload["buy_avg"], "$1.0000")
        self.assertEqual(payload["buy_total"], "$150")
        self.assertEqual(payload["sell_avg"], "$2.0000")
        self.assertEqual(payload["sell_total"], "$80")
        self.assertEqual(payload["realized_pnl"], "+$40")
        self.assertEqual(payload["open_orders"], "1")
        self.assertNotEqual(payload["first_buy"], "N/A")
        self.assertNotEqual(payload["last_sell"], "N/A")

    async def test_key_action_explorer_sync_pushes_current_trade_mode(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")
        sent = []

        async def _fake_send_display(conn_obj, screen, data):
            sent.append((screen, data))

        handler = KeyActionHandler()
        with patch("plugins_func.functions.ave_tools._send_display", new=_fake_send_display):
            await handler.handle(conn, {"type": "key_action", "action": "explorer_sync"})

        self.assertEqual(len(sent), 1)
        screen, payload = sent[0]
        self.assertEqual(screen, "explorer")
        self.assertEqual(payload["trade_mode"], "paper")

    async def test_paper_buy_confirm_updates_account_and_shows_result(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")

        def _fake_data_post(path, payload):
            self.assertEqual(path, "/tokens/price")
            data = {}
            for token_id in payload.get("token_ids", []):
                if token_id == f"{ave_tools.NATIVE_SOL}-solana":
                    data[token_id] = {"current_price_usd": 100}
                else:
                    data[token_id] = {"current_price_usd": 2}
            return {"data": data}

        with patch("plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post):
            result = ave_tools._execute_paper_trade(
                conn,
                "market_buy",
                {
                    "chain": "solana",
                    "outTokenAddress": "token-1",
                    "paper_native_amount": "1",
                    "paper_symbol": "BONK",
                },
            )
        pending = {
            "trade_type": "market_buy",
            "symbol": "BONK",
            "amount_native": "1 SOL",
            "amount_usd": "≈ $100.00",
        }
        result_payload = ave_tools._build_result_payload(result, pending=pending)
        self.assertTrue(result_payload["success"])
        self.assertEqual(result_payload["title"], "Paper Bought!")
        self.assertEqual(result_payload["symbol"], "BONK")
        self.assertEqual(result_payload["mode_label"], "PAPER")

        account = get_paper_account(self.paper_store, "default")
        self.assertEqual(account["balances"]["solana"]["amount"], "0")
        position = account["positions"]["token-1-solana"]
        self.assertEqual(position["symbol"], "BONK")
        self.assertEqual(position["amount"], "50")

    async def test_paper_buy_without_symbol_uses_current_token_symbol(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")
        conn.ave_state["current_token"] = {
            "addr": "token-9",
            "chain": "solana",
            "symbol": "WIF",
        }

        def _fake_data_post(path, payload):
            self.assertEqual(path, "/tokens/price")
            data = {}
            for token_id in payload.get("token_ids", []):
                if token_id == f"{ave_tools.NATIVE_SOL}-solana":
                    data[token_id] = {"current_price_usd": 100}
                else:
                    data[token_id] = {"current_price_usd": 2}
            return {"data": data}

        with patch("plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post):
            result = ave_tools._execute_paper_trade(
                conn,
                "market_buy",
                {
                    "chain": "solana",
                    "outTokenAddress": "token-9",
                    "paper_native_amount": "1",
                },
            )

        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["data"]["outTokenSymbol"], "WIF")

        account = get_paper_account(self.paper_store, "default")
        position = account["positions"]["token-9-solana"]
        self.assertEqual(position["symbol"], "WIF")

    async def test_paper_portfolio_shows_position_symbol_and_pnl(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")
        sent = []
        price_call = {"count": 0}

        async def _fake_send_display(conn_obj, screen, data):
            sent.append((screen, data))

        def _fake_data_post(path, payload):
            self.assertEqual(path, "/tokens/price")
            price_call["count"] += 1
            token_price = 2.0 if price_call["count"] == 1 else 3.0
            data = {}
            for token_id in payload.get("token_ids", []):
                if token_id == f"{ave_tools.NATIVE_SOL}-solana":
                    data[token_id] = {"current_price_usd": 100}
                elif token_id == "token-1-solana":
                    data[token_id] = {"current_price_usd": token_price}
                else:
                    data[token_id] = {"current_price_usd": 1}
            return {"data": data}

        with patch("plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post):
            buy_result = ave_tools._execute_paper_trade(
                conn,
                "market_buy",
                {
                    "chain": "solana",
                    "outTokenAddress": "token-1",
                    "paper_native_amount": "1",
                    "paper_symbol": "BONK",
                },
            )
        self.assertEqual(buy_result["status"], "confirmed")

        with patch("plugins_func.functions.ave_tools._send_display", new=_fake_send_display), patch(
            "plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post
        ):
            result = ave_tools.ave_portfolio(conn, chain_filter="solana")
            await asyncio.sleep(0)

        self.assertEqual(result.result, "paper_portfolio:2tokens")
        self.assertTrue(sent)
        screen, payload = sent[-1]
        self.assertEqual(screen, "portfolio")
        target = next(row for row in payload["holdings"] if row.get("addr") == "token-1")
        self.assertEqual(target["symbol"], "BONK")
        self.assertEqual(target["avg_cost_usd"], "$2.0000")
        self.assertEqual(target["pnl"], "+$50")
        self.assertEqual(payload["pnl"], "+$50")
        self.assertEqual(payload["pnl_pct"], "+50.00%")
        self.assertEqual(payload["pnl_reason"], "")

    async def test_paper_portfolio_repairs_historical_symbol_and_cost_basis(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")
        self.paper_store.write_text(
            json.dumps(
                {
                    "default": {
                        "selected_mode": "paper",
                        "seeded": True,
                        "updated_at": 1,
                        "realized_pnl_usd": "0",
                        "balances": {
                            "solana": {"symbol": "SOL", "amount": "1"},
                            "eth": {"symbol": "ETH", "amount": "1"},
                            "base": {"symbol": "ETH", "amount": "1"},
                            "bsc": {"symbol": "BNB", "amount": "1"},
                        },
                        "open_orders": [],
                        "fills": [
                            {
                                "id": "paper-old-buy",
                                "trade_type": "market_buy",
                                "chain": "eth",
                                "addr": "0xoldtoken",
                                "symbol": "TOKEN",
                                "token_amount": "200",
                                "amount_usd": "100",
                                "price_usd": "0.5",
                                "created_at": 1,
                            }
                        ],
                        "positions": {
                            "0xoldtoken-eth": {
                                "addr": "0xoldtoken",
                                "chain": "eth",
                                "symbol": "TOKEN",
                                "token_id": "0xoldtoken-eth",
                                "amount": "200",
                                "amount_raw": "200",
                            }
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        sent = []

        async def _fake_send_display(conn_obj, screen, data):
            sent.append((screen, data))

        def _fake_data_get(path, params=None):
            if path == "/tokens/0xoldtoken-eth":
                return {"data": {"token": {"symbol": "LDO"}}}
            raise AssertionError(path)

        def _fake_data_post(path, payload):
            self.assertEqual(path, "/tokens/price")
            data = {}
            for token_id in payload.get("token_ids", []):
                if token_id == f"{ave_tools.NATIVE_SOL}-solana":
                    data[token_id] = {"current_price_usd": 100}
                elif token_id == "0xoldtoken-eth":
                    data[token_id] = {"current_price_usd": 0.75}
                else:
                    data[token_id] = {"current_price_usd": 1}
            return {"data": data}

        with patch("plugins_func.functions.ave_tools._send_display", new=_fake_send_display), patch(
            "plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get
        ), patch("plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post):
            result = ave_tools.ave_portfolio(conn, chain_filter="eth")
            await asyncio.sleep(0)

        self.assertEqual(result.result, "paper_portfolio:2tokens")
        screen, payload = sent[-1]
        self.assertEqual(screen, "portfolio")
        row = next(item for item in payload["holdings"] if item.get("addr") == "0xoldtoken")
        self.assertEqual(row["symbol"], "LDO")
        self.assertEqual(row["avg_cost_usd"], "$0.500000")
        self.assertEqual(row["pnl"], "+$50")
        self.assertEqual(payload["pnl"], "+$50")

        account = get_paper_account(self.paper_store, "default")
        repaired = account["positions"]["0xoldtoken-eth"]
        self.assertEqual(repaired["symbol"], "LDO")
        self.assertEqual(repaired["avg_cost_usd"], "0.5")
        self.assertEqual(repaired["cost_basis_usd"], "100")

    async def test_paper_sell_confirm_reduces_position_and_returns_native_balance(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")

        def _fake_data_post(path, payload):
            self.assertEqual(path, "/tokens/price")
            data = {}
            for token_id in payload.get("token_ids", []):
                if token_id == f"{ave_tools.NATIVE_SOL}-solana":
                    data[token_id] = {"current_price_usd": 100}
                else:
                    data[token_id] = {"current_price_usd": 2}
            return {"data": data}

        with patch("plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post):
            buy_result = ave_tools._execute_paper_trade(
                conn,
                "market_buy",
                {
                    "chain": "solana",
                    "outTokenAddress": "token-1",
                    "paper_native_amount": "1",
                    "paper_symbol": "BONK",
                },
            )
            self.assertEqual(buy_result["status"], "confirmed")

            result = ave_tools._execute_paper_trade(
                conn,
                "market_sell",
                {
                    "chain": "solana",
                    "inTokenAddress": "token-1",
                    "paper_sell_ratio": "0.5",
                    "paper_position_amount": "50",
                    "paper_symbol": "BONK",
                },
            )
        sell_pending = {
            "trade_type": "market_sell",
            "symbol": "BONK",
            "amount_native": "50% holdings",
            "amount_usd": "",
        }
        result_payload = ave_tools._build_result_payload(result, pending=sell_pending)
        self.assertTrue(result_payload["success"])
        self.assertEqual(result_payload["title"], "Paper Sold!")
        self.assertEqual(result_payload["symbol"], "BONK")
        self.assertEqual(result_payload["mode_label"], "PAPER")

        account = get_paper_account(self.paper_store, "default")
        self.assertEqual(account["balances"]["solana"]["amount"], "0.5")
        position = account["positions"]["token-1-solana"]
        self.assertEqual(position["amount"], "25")

    async def test_paper_portfolio_top_pnl_includes_realized_and_unrealized(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")
        sent = []
        price_call = {"count": 0}

        async def _fake_send_display(conn_obj, screen, data):
            sent.append((screen, data))

        def _fake_data_post(path, payload):
            self.assertEqual(path, "/tokens/price")
            price_call["count"] += 1
            if price_call["count"] == 1:
                token_price = 2.0
            elif price_call["count"] == 2:
                token_price = 4.0
            else:
                token_price = 6.0
            data = {}
            for token_id in payload.get("token_ids", []):
                if token_id == f"{ave_tools.NATIVE_SOL}-solana":
                    data[token_id] = {"current_price_usd": 100}
                elif token_id == "token-1-solana":
                    data[token_id] = {"current_price_usd": token_price}
                else:
                    data[token_id] = {"current_price_usd": 1}
            return {"data": data}

        with patch("plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post):
            ave_tools._execute_paper_trade(
                conn,
                "market_buy",
                {
                    "chain": "solana",
                    "outTokenAddress": "token-1",
                    "paper_native_amount": "1",
                    "paper_symbol": "BONK",
                },
            )
            ave_tools._execute_paper_trade(
                conn,
                "market_sell",
                {
                    "chain": "solana",
                    "inTokenAddress": "token-1",
                    "paper_sell_ratio": "0.5",
                    "paper_position_amount": "50",
                    "paper_symbol": "BONK",
                },
            )

        with patch("plugins_func.functions.ave_tools._send_display", new=_fake_send_display), patch(
            "plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post
        ):
            result = ave_tools.ave_portfolio(conn, chain_filter="solana")
            await asyncio.sleep(0)

        self.assertEqual(result.result, "paper_portfolio:2tokens")
        _, payload = sent[-1]
        target = next(row for row in payload["holdings"] if row.get("addr") == "token-1")
        self.assertEqual(target["pnl"], "+$100")
        self.assertEqual(payload["pnl"], "+$150")

    async def test_paper_limit_order_create_list_cancel_restores_balance(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")
        sent = []

        async def _fake_send_display(conn_obj, screen, data):
            sent.append((screen, data))

        def _fake_data_get(path, params=None):
            return {"data": {"risk_score": 1, "is_honeypot": 0}}

        def _fake_data_post_no_fill(path, payload):
            self.assertEqual(path, "/tokens/price")
            data = {}
            for token_id in payload.get("token_ids", []):
                if token_id == f"{ave_tools.NATIVE_SOL}-solana":
                    data[token_id] = {"current_price_usd": 100}
                else:
                    data[token_id] = {"current_price_usd": 2.0}
            return {"data": data}

        with patch("plugins_func.functions.ave_tools._send_display", new=_fake_send_display), patch(
            "plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get
        ), patch("plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post_no_fill):
            start = ave_tools.ave_limit_order(
                conn,
                addr="token-2",
                chain="solana",
                in_amount_sol=0.5,
                limit_price=1.5,
                current_price=2.0,
                symbol="PEPE",
            )
            self.assertTrue(start.result.startswith("limit_pending:"))
            pending = ave_tools._get_pending_trade(conn)
            result = await ave_tools.trade_mgr.confirm(pending["trade_id"])
            self._drop_pending_trade(conn)

            payload = ave_tools._build_result_payload(result, pending=pending)
            self.assertTrue(payload["success"])
            self.assertEqual(payload["title"], "Paper Limit Order Placed")

            list_result = ave_tools.ave_list_orders(conn, chain="solana")
            await asyncio.sleep(0)
            self.assertIn("PEPE limit", list_result.result)

            account = get_paper_account(self.paper_store, "default")
            self.assertEqual(account["balances"]["solana"]["amount"], "0.5")
            self.assertEqual(len(account["open_orders"]), 1)
            order_id = account["open_orders"][0]["id"]

            sent.clear()
            cancel_start = ave_tools.ave_cancel_order(conn, [order_id], chain="solana", symbol="PEPE")
            self.assertTrue(cancel_start.result.startswith("cancel_pending:"))
            cancel_pending = ave_tools._get_pending_trade(conn)
            cancel_result = await ave_tools.trade_mgr.confirm(cancel_pending["trade_id"])
            self._drop_pending_trade(conn)

        cancel_payload = ave_tools._build_result_payload(cancel_result, pending=cancel_pending)
        self.assertTrue(cancel_payload["success"])
        self.assertEqual(cancel_payload["title"], "Paper Order Cancelled")

        account = get_paper_account(self.paper_store, "default")
        self.assertEqual(account["balances"]["solana"]["amount"], "1")
        self.assertEqual(account["open_orders"], [])

    async def test_paper_limit_order_matches_when_orders_refresh_hits_price(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")
        sent = []

        async def _fake_send_display(conn_obj, screen, data):
            sent.append((screen, data))

        def _fake_data_get(path, params=None):
            return {"data": {"risk_score": 1, "is_honeypot": 0}}

        def _fake_data_post_fill(path, payload):
            self.assertEqual(path, "/tokens/price")
            data = {}
            for token_id in payload.get("token_ids", []):
                if token_id == f"{ave_tools.NATIVE_SOL}-solana":
                    data[token_id] = {"current_price_usd": 100}
                else:
                    data[token_id] = {"current_price_usd": 1.0}
            return {"data": data}

        with patch("plugins_func.functions.ave_tools._send_display", new=_fake_send_display), patch(
            "plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get
        ):
            start = ave_tools.ave_limit_order(
                conn,
                addr="token-3",
                chain="solana",
                in_amount_sol=0.5,
                limit_price=1.5,
                current_price=2.0,
                symbol="DOGE",
            )
            self.assertTrue(start.result.startswith("limit_pending:"))
            pending = ave_tools._get_pending_trade(conn)
            await ave_tools.trade_mgr.confirm(pending["trade_id"])
            self._drop_pending_trade(conn)

        with patch("plugins_func.functions.ave_tools._send_display", new=_fake_send_display), patch(
            "plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post_fill
        ):
            result = ave_tools.ave_list_orders(conn, chain="solana")
            await asyncio.sleep(0)

        self.assertEqual(result.result, "没有未完成挂单")
        account = get_paper_account(self.paper_store, "default")
        self.assertEqual(account["open_orders"], [])
        self.assertEqual(account["positions"]["token-3-solana"]["amount"], "50")
        notify_payloads = [data for screen, data in sent if screen == "notify"]
        self.assertTrue(notify_payloads)
        self.assertEqual(notify_payloads[-1]["title"], "Paper Order Filled")

    async def test_paper_spotlight_detail_checks_current_token_limit_orders(self):
        conn = self._conn()
        ave_tools.ave_set_trade_mode(conn, "paper")
        observed = []

        async def _fake_send_display(conn_obj, screen, data):
            return None

        async def _fake_detail_async(*args, **kwargs):
            return None

        def _fake_try_fill(conn_obj, **kwargs):
            observed.append(kwargs)
            return []

        with patch("plugins_func.functions.ave_tools._send_display", new=_fake_send_display), patch(
            "plugins_func.functions.ave_tools._ave_token_detail_async", new=_fake_detail_async
        ), patch(
            "plugins_func.functions.ave_tools._try_fill_paper_limit_orders", side_effect=_fake_try_fill
        ):
            result = ave_tools.ave_token_detail(conn, addr="token-spot", chain="solana", symbol="SPOT")
            await asyncio.sleep(0)

        self.assertIn("已展示SPOT详情", result.result)
        self.assertEqual(observed, [{"chain": "solana", "token_addr": "token-spot"}])
