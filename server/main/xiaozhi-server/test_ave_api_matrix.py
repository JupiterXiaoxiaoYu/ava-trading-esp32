import asyncio
import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from plugins_func.functions import ave_tools, ave_wss, ave_trade_mgr
from plugins_func.functions.ave_trade_mgr import trade_mgr

DOC_SUCCESS_FIXTURES = {
    "send_swap_order": {
        "status": 0,
        "msg": "Success",
        "data": {"id": "swap-doc-1234567890abcdef"},
    },
    "send_limit_order": {
        "status": 0,
        "msg": "Success",
        "data": {"id": "limit-doc-abcdef1234567890"},
    },
    "cancel_limit_order": {
        "status": 0,
        "msg": "Success",
        "data": ["id1", "id2"],
    },
}

REAL_FAILURE_FIXTURES = {
    "swap_too_small": {
        "status": 3001,
        "msg": "failed to send transaction: swap value too small",
    },
    "swap_missing_gas": {
        "status": 2001,
        "msg": "Invalid swap order parameters: gas is required for Solana chain",
    },
    "limit_too_small": {
        "status": 3001,
        "msg": "failed to send transaction: swap value too small",
    },
    "limit_invalid_auto_gas": {
        "status": 2001,
        "msg": "invalid auto gas price",
    },
    "limit_missing_gas": {
        "status": 2001,
        "msg": "Invalid limit order parameters: gas is required for Solana chain",
    },
    "cancel_real_success_empty": {
        "status": 200,
        "msg": "Success",
        "data": [],
    },
}


class _FakeLoop:
    def __init__(self, loop):
        self._loop = loop

    def create_task(self, coro, name=None):
        return self._loop.create_task(coro, name=name)


class _FakeWss:
    def __init__(self):
        self.feed_calls = []
        self.spotlight_calls = []

    def set_feed_tokens(self, tokens, chain):
        self.feed_calls.append((tokens, chain))

    def set_spotlight(self, *args, **kwargs):
        self.spotlight_calls.append((args, kwargs))


class _FakeConn:
    def __init__(self, loop):
        self.loop = _FakeLoop(loop)
        self.ave_state = {}
        self.ave_wss = _FakeWss()
        self.websocket = MagicMock()


class AveApiMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        trade_mgr._pending.clear()

    async def test_initial_feed_push_seeds_feed_navigation_state(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        class _FakeResp:
            def __init__(self, payload):
                self._payload = payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def json(self):
                return self._payload

        class _FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def get(self, url, headers=None, timeout=None):
                del headers, timeout
                chain = url.split("chain=")[1].split("&", 1)[0]
                return _FakeResp(
                    {
                        "data": {
                            "tokens": [
                                {
                                    "token": f"{chain}-token",
                                    "chain": chain,
                                    "symbol": chain.upper(),
                                    "current_price_usd": "1.23",
                                    "token_price_change_24h": "4.5",
                                }
                            ]
                        }
                    }
                )

        fake_aiohttp = types.SimpleNamespace(
            ClientSession=lambda: _FakeSession(),
            ClientTimeout=lambda total=10: total,
        )

        with patch.dict(os.environ, {"AVE_API_KEY": "test-key"}, clear=False), \
             patch.dict(sys.modules, {"aiohttp": fake_aiohttp}), \
             patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await ave_wss.initial_feed_push(conn)

        self.assertEqual(sent[0][0], "feed")
        self.assertEqual(sent[0][1]["chain"], "all")
        self.assertEqual(conn.ave_wss.feed_calls[0][1], "all")
        self.assertEqual(conn.ave_state["screen"], "feed")
        self.assertEqual(conn.ave_state["feed_source"], "trending")
        self.assertEqual(conn.ave_state["feed_platform"], "")
        self.assertEqual(conn.ave_state["feed_mode"], "standard")
        self.assertEqual(conn.ave_state["feed_cursor"], 0)
        self.assertEqual(
            [item["addr"] for item in conn.ave_state["feed_token_list"]],
            ["solana", "eth", "bsc", "base"],
        )

    async def test_ave_get_trending_platform_uses_platform_endpoint_mapping(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        requests = []
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _fake_data_get(path, params=None):
            requests.append((path, params))
            return {
                "data": {
                    "tokens": [
                        {
                            "token": "pump-token",
                            "chain": "solana",
                            "symbol": "PUMP",
                            "current_price_usd": "0.12",
                            "token_price_change_24h": "5.5",
                        }
                    ]
                }
            }

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            resp = ave_tools.ave_get_trending(conn, chain="all", platform="pump_in_hot")
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "Showing 1 tokens from pump_in_hot")
        self.assertEqual(requests, [("/tokens/platform", {"tag": "pump_in_hot", "limit": 20})])
        self.assertEqual(sent[0][0], "feed")
        self.assertEqual(sent[0][1]["chain"], "all")
        self.assertEqual(conn.ave_wss.feed_calls[0][1], "all")
        self.assertEqual(conn.ave_state["screen"], "feed")
        self.assertEqual(conn.ave_state["feed_platform"], "pump_in_hot")
        self.assertEqual(conn.ave_state["feed_source"], "trending")

    async def test_ave_get_trending_topic_uses_ranks_endpoint_mapping(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        requests = []

        async def _fake_send_display(conn, screen, payload):
            return None

        def _fake_data_get(path, params=None):
            requests.append((path, params))
            return {
                "data": {
                    "ranks": [
                        {
                            "token": "gainer-1",
                            "symbol": "GAIN",
                            "current_price_usd": "1.5",
                            "token_price_change_24h": "25",
                        }
                    ]
                }
            }

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_get_trending(conn, chain="bsc", topic="gainer")
            await asyncio.sleep(0)

        self.assertEqual(requests, [("/ranks", {"topic": "gainer", "chain": "bsc", "limit": 20})])
        self.assertEqual(conn.ave_state["feed_source"], "gainer")
        self.assertEqual(conn.ave_state["feed_platform"], "")

    async def test_ave_get_trending_topic_keeps_cross_chain_rank_rows_even_when_token_ids_repeat(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []
        requests = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _fake_data_get(path, params=None):
            requests.append((path, params))
            chain = params["chain"]
            return {
                "data": {
                    "ranks": [
                        {
                            "token": f"shared-rank-{idx}",
                            "chain": chain,
                            "symbol": f"R{idx}",
                            "current_price_usd": str(idx + 1),
                            "token_price_change_24h": str(idx + 10),
                        }
                        for idx in range(5)
                    ]
                }
            }

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_get_trending(conn, chain="all", topic="gainer")
            await asyncio.sleep(0)

        self.assertEqual(
            requests,
            [
                ("/ranks", {"topic": "gainer", "chain": "solana", "limit": 5}),
                ("/ranks", {"topic": "gainer", "chain": "eth", "limit": 5}),
                ("/ranks", {"topic": "gainer", "chain": "bsc", "limit": 5}),
                ("/ranks", {"topic": "gainer", "chain": "base", "limit": 5}),
            ],
        )
        self.assertEqual(sent[0][0], "feed")
        self.assertEqual(len(sent[0][1]["tokens"]), 20)
        self.assertEqual(
            [item["chain"] for item in sent[0][1]["tokens"][:8]],
            ["solana", "eth", "bsc", "base", "solana", "eth", "bsc", "base"],
        )
        self.assertEqual(len(conn.ave_state["feed_token_list"]), 20)

    async def test_ave_get_trending_topic_prefers_requested_chain_over_incorrect_rank_payload_chain(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _fake_data_get(path, params=None):
            chain = params["chain"]
            return {
                "data": {
                    "ranks": [
                        {
                            "token": f"shared-rank-{idx}",
                            "chain": "solana",
                            "symbol": f"{chain.upper()}-{idx}",
                            "current_price_usd": str(idx + 1),
                            "token_price_change_24h": str(idx + 10),
                        }
                        for idx in range(5)
                    ]
                }
            }

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_get_trending(conn, chain="all", topic="gainer")
            await asyncio.sleep(0)

        self.assertEqual(len(sent[0][1]["tokens"]), 20)
        self.assertEqual(
            [item["chain"] for item in sent[0][1]["tokens"][:8]],
            ["solana", "eth", "bsc", "base", "solana", "eth", "bsc", "base"],
        )

    async def test_ave_get_trending_default_topic_uses_tokens_trending_endpoint(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        requests = []
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _fake_data_get(path, params=None):
            requests.append((path, params))
            return {
                "data": {
                    "tokens": [
                        {
                            "token": "trend-1",
                            "symbol": "WIF",
                            "current_price_usd": "1.5",
                            "token_price_change_24h": "12.3",
                        }
                    ]
                }
            }

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            resp = ave_tools.ave_get_trending(conn, chain="solana", topic="")
            await asyncio.sleep(0)

        self.assertEqual(
            requests,
            [("/tokens/trending", {"chain": "solana", "current_page": 1, "page_size": 20})],
        )
        self.assertEqual(resp.action, ave_tools.Action.NONE)
        self.assertEqual(conn.ave_state["feed_source"], "trending")
        self.assertEqual(sent[0][0], "feed")
        self.assertEqual(sent[0][1]["tokens"][0]["chain"], "solana")

    async def test_ave_search_token_uses_tokens_endpoint_mapping(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        requests = []
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _fake_data_get(path, params=None):
            requests.append((path, params))
            return {
                "data": {
                    "tokens": [
                        {
                            "token": "pepe-sol",
                            "chain": "solana",
                            "symbol": "PEPE",
                            "current_price_usd": "0.001",
                            "token_price_change_24h": "-2.5",
                        }
                    ]
                }
            }

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            resp = ave_tools.ave_search_token(conn, keyword="PEPE", chain="solana")
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "Found 1 tokens matching 'PEPE'")
        self.assertEqual(requests, [("/tokens", {"keyword": "PEPE", "chain": "solana", "limit": 20})])
        self.assertEqual(sent[0][1]["source_label"], "SEARCH")
        self.assertEqual(conn.ave_wss.feed_calls[0][1], "solana")

    async def test_ave_token_detail_maps_token_kline_and_contract_endpoints(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        requests = []
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _fake_data_get(path, params=None):
            requests.append((path, params))
            if path == "/tokens/token-123-solana":
                return {
                    "data": {
                        "token": {
                            "symbol": "BONK",
                            "current_price_usd": "0.00002",
                            "token_price_change_24h": "4.5",
                            "holders": 123456,
                            "main_pair_tvl": 250000,
                        }
                    }
                }
            if path == "/klines/token/token-123-solana":
                return {
                    "data": {
                        "points": [
                            {"close": 1.0, "time": 1710000000},
                            {"close": 2.0, "time": 1710003600},
                        ]
                    }
                }
            if path == "/contracts/token-123-solana":
                return {
                    "data": {
                        "risk_score": 65,
                        "has_mint_method": True,
                        "has_black_method": False,
                    }
                }
            raise AssertionError(f"unexpected path: {path}")

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_token_detail(conn, addr="token-123", chain="solana", interval="5")
            await asyncio.sleep(0)

        self.assertEqual(
            requests,
            [
                ("/tokens/token-123-solana", None),
                ("/klines/token/token-123-solana", {"interval": "5", "limit": 48}),
                ("/contracts/token-123-solana", None),
            ],
        )
        self.assertEqual(sent[0][0], "spotlight")
        self.assertEqual(sent[0][1]["interval"], "5")
        self.assertEqual(sent[0][1]["risk_level"], "HIGH")
        self.assertTrue(sent[0][1]["is_mintable"])
        self.assertEqual(conn.ave_wss.spotlight_calls[0][1]["interval"], "k5")

    async def test_ave_token_detail_interval_1_maps_to_rest_1m_and_wss_k1(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        requests = []
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _fake_data_get(path, params=None):
            requests.append((path, params))
            if path == "/tokens/token-123-solana":
                return {
                    "data": {
                        "token": {
                            "symbol": "BONK",
                            "current_price_usd": "0.00002",
                            "token_price_change_24h": "4.5",
                            "holders": 123456,
                            "main_pair_tvl": 250000,
                        }
                    }
                }
            if path == "/klines/token/token-123-solana":
                return {
                    "data": {
                        "points": [
                            {"close": 1.0, "time": 1710000000},
                            {"close": 2.0, "time": 1710003600},
                        ]
                    }
                }
            if path == "/contracts/token-123-solana":
                return {
                    "data": {
                        "risk_score": 65,
                        "has_mint_method": True,
                        "has_black_method": False,
                    }
                }
            raise AssertionError(f"unexpected path: {path}")

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_token_detail(conn, addr="token-123", chain="solana", interval="1")
            await asyncio.sleep(0)

        normalized_requests = [
            (path, json.dumps(params, sort_keys=True) if params is not None else None)
            for path, params in requests
        ]
        self.assertCountEqual(
            normalized_requests,
            [
                ("/tokens/token-123-solana", None),
                ("/klines/token/token-123-solana", "{\"interval\": \"1\", \"limit\": 48}"),
                ("/contracts/token-123-solana", None),
            ],
        )
        self.assertEqual(sent[0][0], "spotlight")
        self.assertEqual(sent[0][1]["interval"], "1")
        self.assertEqual(conn.ave_wss.spotlight_calls[0][1]["interval"], "k1")

    async def test_ave_token_detail_interval_s1_skips_rest_kline_and_seeds_live_chart(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        requests = []
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _fake_data_get(path, params=None):
            requests.append((path, params))
            if path == "/tokens/token-123-solana":
                return {
                    "data": {
                        "token": {
                            "symbol": "BONK",
                            "current_price_usd": "0.00002",
                            "token_price_change_24h": "4.5",
                            "holders": 123456,
                            "main_pair_tvl": 250000,
                        }
                    }
                }
            if path == "/contracts/token-123-solana":
                return {
                    "data": {
                        "risk_score": 65,
                        "has_mint_method": True,
                        "has_black_method": False,
                    }
                }
            if path.startswith("/klines/token/"):
                raise AssertionError("interval=s1 must not call REST kline endpoint")
            raise AssertionError(f"unexpected path: {path}")

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_token_detail(conn, addr="token-123", chain="solana", interval="s1")
            await asyncio.sleep(0)

        normalized_requests = [
            (path, json.dumps(params, sort_keys=True) if params is not None else None)
            for path, params in requests
        ]
        self.assertCountEqual(
            normalized_requests,
            [
                ("/tokens/token-123-solana", None),
                ("/contracts/token-123-solana", None),
            ],
        )
        self.assertEqual(sent[0][0], "spotlight")
        self.assertEqual(sent[0][1]["interval"], "s1")
        self.assertGreaterEqual(len(sent[0][1]["chart"]), 8)
        self.assertTrue(any(v > 0 for v in sent[0][1]["chart"]))
        self.assertEqual(sent[0][1]["chart_t_end"], "now")
        self.assertEqual(conn.ave_wss.spotlight_calls[0][1]["interval"], "s1")

    async def test_ave_buy_token_maps_contract_price_quote_and_trade_payloads(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        data_get_requests = []
        data_post_requests = []
        quote_requests = []
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _fake_data_get(path, params=None):
            data_get_requests.append((path, params))
            return {"data": {"risk_score": 5}}

        def _fake_data_post(path, payload):
            data_post_requests.append((path, payload))
            return {
                "data": {
                    f"{ave_tools.NATIVE_SOL}-solana": {"current_price_usd": "150"}
                }
            }

        def _fake_quote_post(path, payload):
            quote_requests.append((path, payload))
            return {"data": {"estimateOut": "50000000000", "decimals": 6}}

        def _env_get(key, default=None):
            if key == "AVE_PROXY_WALLET_ID":
                return "wallet-1"
            return default

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post), \
             patch("plugins_func.functions.ave_trade_mgr._trade_post", side_effect=_fake_quote_post), \
             patch("plugins_func.functions.ave_trade_mgr._trade_get", return_value={"data": {}}) as mock_quote_get, \
             patch("plugins_func.functions.ave_tools.trade_mgr.create", return_value="buy123") as mock_create, \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools.os.environ.get", side_effect=_env_get):
            resp = ave_tools.ave_buy_token(
                conn,
                addr="token-1",
                chain="solana",
                in_amount_sol=0.2,
                tp_pct=30,
                sl_pct=10,
                symbol="BONK",
            )
            await asyncio.sleep(0)

        self.assertIn("trade_id=buy123", resp.result)
        self.assertEqual(data_get_requests, [("/contracts/token-1-solana", None)])
        self.assertEqual(
            data_post_requests,
            [("/tokens/price", {"token_ids": [f"{ave_tools.NATIVE_SOL}-solana"]})],
        )
        self.assertEqual(
            quote_requests,
            [(
                "/v1/thirdParty/chainWallet/getAmountOut",
                {
                    "chain": "solana",
                    "inAmount": "200000000",
                    "inTokenAddress": "sol",
                    "outTokenAddress": "token-1",
                    "swapType": "buy",
                },
            )],
        )
        mock_quote_get.assert_not_called()
        trade_type, trade_params, passed_conn = mock_create.call_args[0]
        self.assertEqual(trade_type, "market_buy")
        self.assertIs(passed_conn, conn)
        self.assertEqual(trade_params["assetsId"], "wallet-1")
        self.assertEqual(trade_params["inTokenAddress"], "sol")
        self.assertEqual(trade_params["outTokenAddress"], "token-1")
        self.assertEqual(trade_params["inAmount"], "200000000")
        self.assertEqual(trade_params["swapType"], "buy")
        self.assertEqual(trade_params["slippage"], "100")
        self.assertEqual(trade_params["gas"], "1000000")
        self.assertEqual(trade_params["autoGas"], "average")
        self.assertEqual(trade_params["autoSellConfig"][0]["priceChange"], "3000")
        self.assertEqual(trade_params["autoSellConfig"][1]["priceChange"], "-1000")
        self.assertEqual(sent[0][0], "confirm")
        self.assertEqual(sent[0][1]["out_amount"], "50000 BONK")

    async def test_ave_buy_token_uses_price_and_quote_fallbacks_non_fatally(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _env_get(key, default=None):
            if key == "AVE_PROXY_WALLET_ID":
                return "wallet-fallback"
            return default

        with patch("plugins_func.functions.ave_tools._data_get", return_value={"data": {"risk_score": 5}}), \
             patch("plugins_func.functions.ave_tools._data_post", side_effect=RuntimeError("price down")), \
             patch("plugins_func.functions.ave_trade_mgr._trade_post", side_effect=RuntimeError("quote down")), \
             patch("plugins_func.functions.ave_tools.trade_mgr.create", return_value="buy-fallback"), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools.os.environ.get", side_effect=_env_get):
            resp = ave_tools.ave_buy_token(
                conn,
                addr="token-fallback",
                chain="solana",
                in_amount_sol=0.2,
                symbol="BONK",
            )
            await asyncio.sleep(0)

        self.assertIn("trade_id=buy-fallback", resp.result)
        self.assertEqual(sent[0][0], "confirm")
        self.assertEqual(sent[0][1]["amount_usd"], "≈ $30.00")
        self.assertNotIn("out_amount", sent[0][1])

    async def test_ave_risk_check_blocks_honeypot_and_pushes_notify(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._data_get", return_value={"data": {"risk_score": 99}}), \
             patch("plugins_func.functions.ave_tools._risk_flags", return_value={
                 "risk_level": "CRITICAL",
                 "is_honeypot": True,
                 "is_mintable": True,
                 "is_freezable": True,
             }), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            resp = ave_tools.ave_risk_check(conn, addr="bad-token", chain="solana")
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "CRITICAL_BLOCKED")
        self.assertIn("已拦截交易", resp.response)
        self.assertEqual(sent[0][0], "notify")
        self.assertEqual(sent[0][1]["level"], "error")

    def test_ave_risk_check_non_critical_returns_pass_signal(self):
        loop = asyncio.new_event_loop()
        try:
            conn = _FakeConn(loop)
            with patch("plugins_func.functions.ave_tools._data_get", return_value={"data": {"risk_score": 5}}), \
                 patch("plugins_func.functions.ave_tools._risk_flags", return_value={
                     "risk_level": "LOW",
                     "is_honeypot": False,
                     "is_mintable": False,
                     "is_freezable": False,
                 }), \
                 patch("plugins_func.functions.ave_tools._send_display") as send_mock:
                resp = ave_tools.ave_risk_check(conn, addr="ok-token", chain="solana")
        finally:
            loop.close()

        send_mock.assert_not_called()
        self.assertIn("risk_level=LOW", resp.result)
        self.assertEqual(resp.action, ave_tools.Action.NONE)

    async def test_ave_limit_order_uses_stringified_proxy_payload_and_solana_gas(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _env_get(key, default=None):
            if key == "AVE_PROXY_WALLET_ID":
                return "wallet-limit"
            return default

        with patch("plugins_func.functions.ave_tools.trade_mgr.create", return_value="limit123") as mock_create, \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools.os.environ.get", side_effect=_env_get):
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

        self.assertEqual(resp.result, "limit_pending:limit123")
        trade_type, trade_params, passed_conn = mock_create.call_args[0]
        self.assertEqual(trade_type, "limit_buy")
        self.assertIs(passed_conn, conn)
        self.assertEqual(trade_params["chain"], "solana")
        self.assertEqual(trade_params["assetsId"], "wallet-limit")
        self.assertEqual(trade_params["inTokenAddress"], "sol")
        self.assertEqual(trade_params["outTokenAddress"], "token-limit")
        self.assertEqual(trade_params["inAmount"], "250000000")
        self.assertEqual(trade_params["swapType"], "buy")
        self.assertEqual(trade_params["slippage"], "100")
        self.assertEqual(trade_params["useMev"], True)
        self.assertEqual(trade_params["limitPrice"], "0.1234")
        self.assertEqual(trade_params["expireTime"], "86400")
        self.assertEqual(trade_params["gas"], "1000000")
        self.assertNotIn("autoGas", trade_params)
        self.assertEqual(sent[0][0], "limit_confirm")
        self.assertEqual(sent[0][1]["trade_id"], "limit123")

    async def test_ave_list_orders_uses_get_limit_order_contract(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        requests = []

        async def _fake_send_display(conn, screen, payload):
            return None

        def _fake_trade_get(path, params=None):
            requests.append((path, params))
            return {"data": {"list": []}}

        def _env_get(key, default=None):
            if key == "AVE_PROXY_WALLET_ID":
                return "wallet-7"
            return default

        with patch("plugins_func.functions.ave_tools._trade_get", side_effect=_fake_trade_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools.os.environ.get", side_effect=_env_get):
            resp = ave_tools.ave_list_orders(conn, chain="base")
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "没有未完成挂单")
        self.assertEqual(
            requests,
            [(
                "/v1/thirdParty/tx/getLimitOrder",
                {"assetsId": "wallet-7", "chain": "base", "pageSize": "20", "pageNo": "0", "status": "waiting"},
            )],
        )

    async def test_ave_cancel_order_all_maps_lookup_then_cancel_payload(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        requests = []

        async def _fake_send_display(conn, screen, payload):
            return None

        def _fake_trade_get(path, params=None):
            requests.append((path, params))
            return {
                "data": {
                    "list": [
                        {"id": "ord-1", "symbol": "BONK"},
                        {"id": "ord-2", "symbol": "BONK"},
                    ]
                }
            }

        def _env_get(key, default=None):
            if key == "AVE_PROXY_WALLET_ID":
                return "wallet-9"
            return default

        with patch("plugins_func.functions.ave_tools._trade_get", side_effect=_fake_trade_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools.trade_mgr.create", return_value="cancel-all") as mock_create, \
             patch("plugins_func.functions.ave_tools.os.environ.get", side_effect=_env_get):
            resp = ave_tools.ave_cancel_order(conn, order_ids=["all"], chain="solana")
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "cancel_pending:cancel-all ids=ord-1,ord-2")
        self.assertEqual(
            requests,
            [(
                "/v1/thirdParty/tx/getLimitOrder",
                {"assetsId": "wallet-9", "chain": "solana", "pageSize": "20", "pageNo": "0", "status": "waiting"},
            )],
        )
        trade_type, trade_params, passed_conn = mock_create.call_args[0]
        self.assertEqual(trade_type, "cancel_order")
        self.assertIs(passed_conn, conn)
        self.assertEqual(trade_params, {"chain": "solana", "ids": ["ord-1", "ord-2"]})

    async def test_ave_portfolio_reads_real_wallet_schema_without_faking_holdings(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        trade_requests = []
        data_post_requests = []
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _fake_trade_get(path, params=None):
            trade_requests.append((path, params))
            return {
                "data": [
                    {
                        "assetsId": "wallet-portfolio",
                        "assetsName": "Primary",
                        "status": "enabled",
                        "addressList": [
                            {"chain": "solana", "address": "So11111111111111111111111111111111111111112"},
                            {"chain": "base", "address": "0xABcDEF1234"},
                        ],
                    }
                ]
            }

        def _fake_data_post(path, payload):
            data_post_requests.append((path, payload))
            return {"data": {}}

        def _env_get(key, default=None):
            if key == "AVE_PROXY_WALLET_ID":
                return "wallet-portfolio"
            return default

        with patch("plugins_func.functions.ave_tools._trade_get", side_effect=_fake_trade_get), \
             patch("plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools.os.environ.get", side_effect=_env_get):
            resp = ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "portfolio:0tokens")
        self.assertEqual(
            trade_requests,
            [("/v1/thirdParty/user/getUserByAssetsId", {"assetsIds": "wallet-portfolio"})],
        )
        self.assertEqual(
            data_post_requests,
            [],
        )
        self.assertEqual(sent[0][0], "portfolio")
        self.assertEqual(sent[0][1]["holdings"], [])
        self.assertEqual(sent[0][1]["holding_source"], "getUserByAssetsId.addressList")
        self.assertEqual(
            sent[0][1]["wallets"],
            [
                {
                    "assets_id": "wallet-portfolio",
                    "assets_name": "Primary",
                    "status": "enabled",
                    "addresses": [
                        {
                            "chain": "solana",
                            "address": "So11111111111111111111111111111111111111112",
                        },
                        {
                            "chain": "base",
                            "address": "0xABcDEF1234",
                        },
                    ],
                }
            ],
        )
        self.assertEqual(conn.ave_state["portfolio_holding_source"], "getUserByAssetsId.addressList")

    async def test_trade_wss_uses_jsonrpc_subscribe_contract(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        sent = []

        class _FakeWs:
            async def send(self, raw):
                sent.append(json.loads(raw))
                manager._stopped = True

            def __aiter__(self):
                async def _iter():
                    if False:
                        yield None
                return _iter()

        class _FakeConnect:
            async def __aenter__(self):
                return _FakeWs()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        def _env_get(key, default=None):
            if key == "AVE_API_KEY":
                return "api-key-1"
            return default

        with patch("plugins_func.functions.ave_wss.os.environ.get", side_effect=_env_get), \
             patch("plugins_func.functions.ave_wss.websockets.connect", return_value=_FakeConnect()):
            await manager._trade_loop()

        self.assertEqual(
            sent,
            [{
                "jsonrpc": "2.0",
                "method": "subscribe",
                "params": ["botswap"],
                "id": 0,
            }],
        )

    async def test_wss_ignores_jsonrpc_subscription_ack_frames(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)

        await ave_wss.AveWssManager(conn)._handle_trade_event(json.dumps({
            "jsonrpc": "2.0",
            "result": 0,
            "id": 0,
        }))

    async def test_wss_trade_error_uses_official_errorMessage_field(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        raw = json.dumps({
            "jsonrpc": "2.0",
            "id": 0,
            "result": {
                "topic": "botswap",
                "msg": {
                    "status": "error",
                    "swapType": "buy",
                    "inTokenSymbol": "SOL",
                    "outTokenSymbol": "BONK",
                    "errorMessage": "route not found",
                },
            },
        })

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await ave_wss.AveWssManager(conn)._handle_trade_event(raw)

        self.assertEqual(sent[0][0], "result")
        self.assertEqual(sent[0][1]["title"], "Trade Failed")
        self.assertEqual(sent[0][1]["error"], "route not found")

    async def test_wss_trade_jsonrpc_error_frames_are_logged_for_diagnostics(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        fake_logger = MagicMock()
        fake_logger.bind.return_value = fake_logger

        with patch("plugins_func.functions.ave_wss.logger", fake_logger):
            await ave_wss.AveWssManager(conn)._handle_trade_event(json.dumps({
                "jsonrpc": "2.0",
                "id": 0,
                "error": {
                    "code": -32000,
                    "message": "unknown topic",
                },
            }))

        fake_logger.warning.assert_called()

    def test_trade_mgr_execute_sync_maps_trade_types_to_endpoints(self):
        cases = [
            ("market_buy", "/v1/thirdParty/tx/sendSwapOrder"),
            ("market_sell", "/v1/thirdParty/tx/sendSwapOrder"),
            ("limit_buy", "/v1/thirdParty/tx/sendLimitOrder"),
            ("cancel_order", "/v1/thirdParty/tx/cancelLimitOrder"),
        ]

        for trade_type, expected_path in cases:
            with self.subTest(trade_type=trade_type):
                with patch("plugins_func.functions.ave_trade_mgr._trade_post", return_value={"status": 0, "data": {}}) as mock_post:
                    result = trade_mgr._execute_sync({"type": trade_type, "params": {"foo": "bar"}})
                mock_post.assert_called_once_with(expected_path, {"foo": "bar"})
                self.assertEqual(result["trade_type"], trade_type)

    def test_trade_mgr_execute_sync_normalizes_proxy_payload_shape_and_types(self):
        trade = {
            "type": "limit_buy",
            "params": {
                "chain": "solana",
                "assetsId": "wallet-1",
                "inToken": ave_tools.NATIVE_SOL,
                "outToken": "token-1",
                "inAmount": 200000000,
                "swapType": "buy",
                "slippage": 100,
                "useMev": True,
                "limitPrice": 0.5,
                "expireTime": 3600,
                "gas": 1000000,
            },
        }

        with patch("plugins_func.functions.ave_trade_mgr._trade_post", return_value={"status": 0, "data": {}}) as mock_post:
            result = trade_mgr._execute_sync(trade)

        mock_post.assert_called_once_with(
            "/v1/thirdParty/tx/sendLimitOrder",
            {
                "chain": "solana",
                "assetsId": "wallet-1",
                "inTokenAddress": "sol",
                "outTokenAddress": "token-1",
                "inAmount": "200000000",
                "swapType": "buy",
                "slippage": "100",
                "useMev": True,
                "limitPrice": "0.5",
                "expireTime": "3600",
                "gas": "1000000",
            },
        )
        self.assertEqual(result["trade_type"], "limit_buy")

    def test_trade_mgr_execute_sync_solana_limit_drops_invalid_auto_gas(self):
        trade = {
            "type": "limit_buy",
            "params": {
                "chain": "solana",
                "assetsId": "wallet-1",
                "inToken": ave_tools.NATIVE_SOL,
                "outToken": "token-1",
                "inAmount": 200000000,
                "swapType": "buy",
                "slippage": 100,
                "gas": 1000000,
                "autoGas": "average",
            },
        }

        with patch("plugins_func.functions.ave_trade_mgr._trade_post", return_value={"status": 0, "data": {}}) as mock_post:
            trade_mgr._execute_sync(trade)

        posted_payload = mock_post.call_args[0][1]
        self.assertEqual(posted_payload["gas"], "1000000")
        self.assertNotIn("autoGas", posted_payload)

    def test_trade_mgr_execute_sync_accepts_doc_success_and_live_cancel_success_samples(self):
        endpoint_by_type = {
            "market_buy": "/v1/thirdParty/tx/sendSwapOrder",
            "limit_buy": "/v1/thirdParty/tx/sendLimitOrder",
            "cancel_order": "/v1/thirdParty/tx/cancelLimitOrder",
        }
        fixtures = [
            ("market_buy", DOC_SUCCESS_FIXTURES["send_swap_order"]),
            ("limit_buy", DOC_SUCCESS_FIXTURES["send_limit_order"]),
            ("cancel_order", DOC_SUCCESS_FIXTURES["cancel_limit_order"]),
            ("cancel_order", REAL_FAILURE_FIXTURES["cancel_real_success_empty"]),
        ]

        for trade_type, fixture in fixtures:
            with self.subTest(trade_type=trade_type, fixture=fixture):
                with patch("plugins_func.functions.ave_trade_mgr._trade_post", return_value=fixture) as mock_post:
                    result = trade_mgr._execute_sync({"type": trade_type, "params": {"foo": "bar"}})
                mock_post.assert_called_once_with(endpoint_by_type[trade_type], {"foo": "bar"})
                self.assertEqual(result["trade_type"], trade_type)
                self.assertEqual(result["status"], fixture["status"])

    async def test_trade_mgr_confirm_reconciles_submit_only_swap_ack_via_get_swap_order(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        trade_mgr._pending["swap-ack-1"] = {
            "type": "market_buy",
            "params": {
                "chain": "solana",
                "assetsId": "wallet-1",
                "inTokenAddress": "sol",
                "outTokenAddress": "token-1",
                "inAmount": "1000000",
                "swapType": "buy",
                "slippage": "100",
                "gas": "1000000",
                "autoGas": "average",
            },
            "conn": conn,
            "ts": 0,
        }

        with patch("plugins_func.functions.ave_trade_mgr._trade_post", return_value={
            "status": 0,
            "msg": "Success",
            "data": {"id": "swap-order-123"},
        }) as mock_post, patch("plugins_func.functions.ave_trade_mgr._trade_get", return_value={
            "status": 0,
            "msg": "Success",
            "data": [
                {
                    "id": "swap-order-123",
                    "status": "confirmed",
                    "chain": "solana",
                    "swapType": "buy",
                    "txHash": "feedfacecafebeef00112233",
                    "outAmount": "52752 BONK",
                    "errorMessage": "",
                }
            ],
        }) as mock_get:
            result = await trade_mgr.confirm("swap-ack-1")

        mock_post.assert_called_once_with(
            "/v1/thirdParty/tx/sendSwapOrder",
            {
                "chain": "solana",
                "assetsId": "wallet-1",
                "inTokenAddress": "sol",
                "outTokenAddress": "token-1",
                "inAmount": "1000000",
                "swapType": "buy",
                "slippage": "100",
                "gas": "1000000",
                "autoGas": "average",
            },
        )
        mock_get.assert_called_once_with(
            "/v1/thirdParty/tx/getSwapOrder",
            {"chain": "solana", "ids": "swap-order-123"},
        )
        self.assertEqual(result["trade_type"], "market_buy")
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["swap_order_id"], "swap-order-123")
        self.assertEqual(result["data"]["txHash"], "feedfacecafebeef00112233")
        self.assertEqual(result["data"]["outAmount"], "52752 BONK")

    def test_trade_mgr_execute_sync_rejects_real_failure_like_samples(self):
        cases = [
            ("market_buy", REAL_FAILURE_FIXTURES["swap_too_small"]),
            ("market_buy", REAL_FAILURE_FIXTURES["swap_missing_gas"]),
            ("limit_buy", REAL_FAILURE_FIXTURES["limit_too_small"]),
            ("limit_buy", REAL_FAILURE_FIXTURES["limit_invalid_auto_gas"]),
            ("limit_buy", REAL_FAILURE_FIXTURES["limit_missing_gas"]),
        ]

        for trade_type, fixture in cases:
            with self.subTest(trade_type=trade_type, fixture=fixture):
                with patch("plugins_func.functions.ave_trade_mgr._trade_post", return_value=fixture):
                    with self.assertRaises(RuntimeError) as ctx:
                        trade_mgr._execute_sync({"type": trade_type, "params": {}})
                self.assertIn(f"status={fixture['status']}", str(ctx.exception))
                self.assertIn(fixture["msg"], str(ctx.exception))

    def test_trade_mgr_execute_sync_rejects_missing_or_malformed_status(self):
        cases = [
            {"msg": "Success"},
            {"status": None, "msg": "Success"},
            {"status": "ok", "msg": "Success"},
            {"status": True, "msg": "Success"},
        ]

        for fixture in cases:
            with self.subTest(fixture=fixture):
                with patch("plugins_func.functions.ave_trade_mgr._trade_post", return_value=fixture):
                    with self.assertRaises(RuntimeError) as ctx:
                        trade_mgr._execute_sync({"type": "market_buy", "params": {}})
                self.assertIn("status=", str(ctx.exception))

    def test_build_result_payload_handles_doc_success_and_list_data_shapes(self):
        cases = [
            (
                "market_buy",
                DOC_SUCCESS_FIXTURES["send_swap_order"],
                {"symbol": "BONK", "amount_native": "0.10 SOL"},
                "Order Submitted",
                "0.10 SOL",
            ),
            (
                "limit_buy",
                DOC_SUCCESS_FIXTURES["send_limit_order"],
                {"symbol": "BONK", "amount_native": "0.10 SOL"},
                "Limit Order Submitted",
                "0.10 SOL",
            ),
            (
                "cancel_order",
                DOC_SUCCESS_FIXTURES["cancel_limit_order"],
                {"symbol": "BONK", "amount_native": "2 orders"},
                "Order Cancelled",
                "2 orders",
            ),
            (
                "cancel_order",
                REAL_FAILURE_FIXTURES["cancel_real_success_empty"],
                {"symbol": "BONK", "amount_native": "all orders"},
                "Order Cancelled",
                "0 orders",
            ),
        ]

        for trade_type, fixture, pending_extra, expected_title, expected_out_amount in cases:
            pending = {
                "trade_type": trade_type,
                "symbol": pending_extra["symbol"],
                "amount_native": pending_extra["amount_native"],
                "amount_usd": "$150.00",
            }
            payload = ave_tools._build_result_payload(
                {"trade_type": trade_type, **fixture},
                pending=pending,
            )
            with self.subTest(trade_type=trade_type, fixture=fixture):
                self.assertTrue(payload["success"])
                self.assertEqual(payload["title"], expected_title)
                self.assertEqual(payload["out_amount"], expected_out_amount)
                # REST submit `data.id` is an order id, not a chain tx hash.
                self.assertEqual(payload["tx_id"], "")

    def test_build_result_payload_rest_submit_ack_is_not_terminal_trade_result(self):
        payload = ave_tools._build_result_payload(
            {
                "trade_type": "market_sell",
                **DOC_SUCCESS_FIXTURES["send_swap_order"],
            },
            pending={
                "trade_type": "market_sell",
                "symbol": "BONK",
                "amount_native": "100% holdings",
            },
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["title"], "Order Submitted")
        self.assertNotEqual(payload["title"], "Sold!")
        self.assertEqual(payload["tx_id"], "")

    def test_build_result_payload_treats_tx_hash_as_terminal_execution_evidence(self):
        payload = ave_tools._build_result_payload(
            {
                "trade_type": "market_sell",
                "status": 0,
                "msg": "Success",
                "data": {
                    "outAmount": "1.5 SOL",
                    "amountUsd": "225.00",
                    "txHash": "deadbeefcafebabe1234",
                },
            },
            pending={
                "trade_type": "market_sell",
                "symbol": "BONK",
                "amount_native": "100% holdings",
            },
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["title"], "Sold!")
        self.assertEqual(payload["tx_id"], "deadbeefcafe")
        self.assertNotEqual(payload["title"], "Order Submitted")

    def test_build_result_payload_marks_missing_status_as_failure(self):
        payload = ave_tools._build_result_payload(
            {
                "trade_type": "market_buy",
                "data": {"outAmount": "50000 BONK"},
            },
            pending={"trade_type": "market_buy", "symbol": "BONK"},
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["title"], "Trade Failed")
        self.assertIn("status", payload["error"].lower())

    def test_build_result_payload_handles_real_failure_like_and_malformed_data(self):
        failure_payload = ave_tools._build_result_payload(
            {
                "trade_type": "market_buy",
                **REAL_FAILURE_FIXTURES["swap_too_small"],
                "data": None,
            },
            pending={"trade_type": "market_buy", "symbol": "BONK"},
        )
        malformed_success_payload = ave_tools._build_result_payload(
            {
                "trade_type": "market_buy",
                "status": 0,
                "msg": "Success",
                "data": "not-a-dict",
            },
            pending={"trade_type": "market_buy", "symbol": "BONK", "amount_native": "0.10 SOL"},
        )

        self.assertFalse(failure_payload["success"])
        self.assertIn("swap value too small", failure_payload["error"])
        self.assertTrue(malformed_success_payload["success"])
        self.assertEqual(malformed_success_payload["out_amount"], "0.10 SOL")

    def test_build_result_payload_uses_tx_hash_and_hides_raw_numeric_out_amount(self):
        payload = ave_tools._build_result_payload(
            {
                "trade_type": "market_buy",
                "status": 0,
                "msg": "Success",
                "data": {
                    "outAmount": "52752",
                    "txHash": "feedfacecafebeef00112233",
                },
            },
            pending={
                "trade_type": "market_buy",
                "symbol": "BONK",
                "amount_native": "0.10 SOL",
            },
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["out_amount"], "0.10 SOL")
        self.assertEqual(payload["tx_id"], "feedfacecafe")

    def test_trade_status_copy_distinguishes_timeout_submitted_and_deferred_states(self):
        self.assertEqual(
            ave_tools._trade_status_copy("confirm_timeout"),
            ("Trade Cancelled", "Confirmation timed out. Nothing was executed."),
        )
        self.assertEqual(
            ave_tools._trade_status_copy("ack_timeout"),
            ("Still Pending", "We did not receive a final confirmation yet."),
        )
        self.assertEqual(
            ave_tools._trade_status_copy("deferred_result"),
            ("Result Deferred", "Another confirmation flow is active. Result will appear next."),
        )
        self.assertEqual(
            ave_tools._trade_status_copy("trade_submitted", trade_type="limit_buy"),
            ("Limit Order Submitted", "Waiting for chain confirmation."),
        )

    def test_terminal_status_helpers_include_failed_and_cancelled_variants(self):
        for status in ("failed", "cancelled", "canceled", "auto_cancelled"):
            with self.subTest(status=status):
                self.assertIn(status, ave_trade_mgr._SWAP_TERMINAL_STATUSES)
                self.assertTrue(ave_tools._is_terminal_trade_result({"status": status}))

    async def test_wss_confirmed_buy_event_maps_to_result_contract(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        raw = json.dumps({
            "topic": "botswap",
            "status": "confirmed",
            "swapType": "buy",
            "inTokenSymbol": "SOL",
            "outTokenSymbol": "BONK",
            "outAmount": "50000 BONK",
            "outAmountUsd": "$150.00",
            "txHash": "0123456789abcdef",
        })

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await ave_wss.AveWssManager(conn)._handle_trade_event(raw)

        self.assertEqual(sent[0][0], "result")
        self.assertEqual(sent[0][1]["title"], "Bought!")
        self.assertEqual(sent[0][1]["symbol"], "BONK")
        self.assertEqual(sent[0][1]["out_amount"], "50000 BONK")
        self.assertEqual(sent[0][1]["tx_id"], "0123456789ab")

    async def test_wss_confirmed_limit_event_uses_limit_result_contract(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        raw = json.dumps({
            "topic": "botswap",
            "status": "confirmed",
            "orderType": "limit",
            "swapType": "buy",
            "txHash": "abc12345def67890",
        })

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await ave_wss.AveWssManager(conn)._handle_trade_event(raw)

        self.assertEqual(sent[0][0], "result")
        self.assertEqual(sent[0][1]["title"], "Limit Order Placed")
        self.assertEqual(sent[0][1]["action"], "LIMIT_BUY")
        self.assertEqual(sent[0][1]["symbol"], "TOKEN")

    async def test_wss_confirmed_cancel_order_event_maps_to_result_contract(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        raw = json.dumps({
            "topic": "botswap",
            "status": "confirmed",
            "swapType": "cancel_order",
            "inTokenSymbol": "BONK",
            "orderIds": ["ord-1", "ord-2"],
        })

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await ave_wss.AveWssManager(conn)._handle_trade_event(raw)

        self.assertEqual(sent[0][0], "result")
        self.assertEqual(sent[0][1]["title"], "Order Cancelled")
        self.assertEqual(sent[0][1]["action"], "CANCEL_ORDER")
        self.assertEqual(sent[0][1]["out_amount"], "2 orders")

    async def test_wss_error_cancel_order_event_maps_to_result_contract(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        raw = json.dumps({
            "topic": "botswap",
            "status": "error",
            "swapType": "cancel_order",
            "inTokenSymbol": "BONK",
            "errorMsg": "already filled",
        })

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await ave_wss.AveWssManager(conn)._handle_trade_event(raw)

        self.assertEqual(sent[0][0], "result")
        self.assertEqual(sent[0][1]["title"], "Cancel Failed")
        self.assertEqual(sent[0][1]["error"], "already filled")

    async def test_wss_trade_notify_branches_cover_tp_sl_trailing_and_auto_cancelled(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)

        cases = [
            (
                {
                    "topic": "botswap",
                    "status": "confirmed",
                    "swapType": "takeprofit",
                    "inTokenSymbol": "BONK",
                    "amountUsd": "225.00",
                },
                "🎉 止盈成功 BONK",
            ),
            (
                {
                    "topic": "botswap",
                    "status": "confirmed",
                    "swapType": "stoploss",
                    "inTokenSymbol": "BONK",
                    "amountUsd": "80.00",
                },
                "⚠️ 止损触发 BONK",
            ),
            (
                {
                    "topic": "botswap",
                    "status": "confirmed",
                    "swapType": "trailing",
                    "inTokenSymbol": "BONK",
                    "amountUsd": "140.00",
                },
                "📈 追踪止盈 BONK",
            ),
            (
                {
                    "topic": "botswap",
                    "status": "auto_cancelled",
                    "inTokenSymbol": "BONK",
                },
                "订单已取消 BONK",
            ),
        ]

        for raw_msg, expected_title in cases:
            sent = []

            async def _fake_send_display(conn, screen, payload):
                sent.append((screen, payload))

            with self.subTest(status=raw_msg["status"], swap_type=raw_msg.get("swapType", "")):
                with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
                    await manager._handle_trade_event(json.dumps(raw_msg))
                self.assertEqual(sent[0][0], "notify")
                self.assertEqual(sent[0][1]["title"], expected_title)

    async def test_wss_failed_terminal_event_clears_pending_with_result_payload(self):
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
            chain="solana",
            asset_token_address="bonk-sol",
        )

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await ave_wss.AveWssManager(conn)._handle_trade_event(json.dumps({
                "topic": "botswap",
                "status": "failed",
                "tradeId": "sell-1",
                "swapType": "sell",
                "chain": "solana",
                "inTokenSymbol": "BONK",
                "inTokenAddress": "bonk-sol",
                "errorMessage": "slippage exceeded",
            }))

        self.assertEqual(sent[0][0], "result")
        self.assertFalse(sent[0][1]["success"])
        self.assertEqual(sent[0][1]["title"], "Trade Failed")
        self.assertIn("slippage exceeded", sent[0][1]["error"])
        self.assertNotIn("pending_trade", conn.ave_state)
        self.assertEqual(conn.ave_state.get("screen"), "result")

    async def test_wss_cancelled_terminal_event_clears_submitted_trade_with_result_payload(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        conn.ave_state["submitted_trades"] = [{
            "trade_id": "buy-1",
            "swap_order_id": "swap-1",
            "trade_type": "market_buy",
            "symbol": "BONK",
            "chain": "solana",
            "asset_token_address": "bonk-sol",
        }]

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await ave_wss.AveWssManager(conn)._handle_trade_event(json.dumps({
                "topic": "botswap",
                "status": "cancelled",
                "swapOrderId": "swap-1",
                "swapType": "buy",
                "chain": "solana",
                "outTokenSymbol": "BONK",
                "outTokenAddress": "bonk-sol",
                "errorMessage": "order expired",
            }))

        self.assertEqual(sent[0][0], "result")
        self.assertFalse(sent[0][1]["success"])
        self.assertEqual(sent[0][1]["title"], "Trade Cancelled")
        self.assertIn("order expired", sent[0][1]["error"])
        self.assertEqual(conn.ave_state.get("submitted_trades", []), [])
        self.assertEqual(conn.ave_state.get("screen"), "result")

    async def test_wss_supports_nested_legacy_result_msg_trade_frames(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        raw = json.dumps({
            "result": {
                "topic": "botswap",
                "msg": {
                    "status": "confirmed",
                    "swapType": "buy",
                    "inTokenSymbol": "SOL",
                    "outTokenSymbol": "WIF",
                    "outAmount": "1200 WIF",
                    "outAmountUsd": "$180.00",
                    "txHash": "feedfacecafebeef",
                },
            }
        })

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await ave_wss.AveWssManager(conn)._handle_trade_event(raw)

        self.assertEqual(sent[0][0], "result")
        self.assertEqual(sent[0][1]["title"], "Bought!")
        self.assertEqual(sent[0][1]["symbol"], "WIF")


if __name__ == "__main__":
    unittest.main()
