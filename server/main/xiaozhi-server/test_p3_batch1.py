import asyncio
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core.handle.textHandler.keyActionHandler import KeyActionHandler
from plugins_func.functions import ave_tools, ave_wss


class _FakeWss:
    def __init__(self):
        self.calls = []
        self.transitions = []
        self._spotlight_data = {}
        self._spotlight_id = ""
        self._spotlight_pair = ""
        self._spotlight_chain = ""
        self._spotlight_interval = "k60"

    def set_spotlight(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    def begin_spotlight_transition(self, pair_addr, chain, display_data, *, interval="k60"):
        self.transitions.append(
            {
                "pair_addr": pair_addr,
                "chain": chain,
                "interval": interval,
                "display_data": dict(display_data),
            }
        )
        self._spotlight_pair = pair_addr
        self._spotlight_chain = chain
        self._spotlight_interval = interval
        next_payload = dict(self._spotlight_data or {})
        next_payload.update(dict(display_data or {}))
        if "interval" in next_payload:
            next_payload["interval"] = str(display_data.get("interval", next_payload["interval"]))
        self._spotlight_data = next_payload
        self._spotlight_id = next_payload.get("token_id", self._spotlight_id)

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
    def _compile_and_run_feed_c_harness(self, harness_source: str, binary_name: str):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        json_utils_src = repo_root / "shared/ave_screens/ave_json_utils.c"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / f"{binary_name}.c"
            binary = tmpdir_path / binary_name
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(json_utils_src),
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                compile_result.returncode,
                0,
                msg=compile_result.stdout + compile_result.stderr,
            )

            run_result = subprocess.run(
                [str(binary)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                run_result.returncode,
                0,
                msg=run_result.stdout + run_result.stderr,
            )

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
            for _ in range(20):
                if any(path.startswith("/klines/token/") for path, _ in requests) and conn.ave_wss.calls:
                    break
                await asyncio.sleep(0.01)

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
            for _ in range(20):
                if len(sent) >= 2 and conn.ave_wss.calls:
                    break
                await asyncio.sleep(0.01)

        payload = sent[-1][1]
        self.assertEqual(len(payload["chart"]), 48)
        args, _ = conn.ave_wss.calls[0]
        self.assertEqual(len(args[2]["chart"]), 48)
        self.assertEqual(args[3][0], 254.0)
        self.assertEqual(args[3][-1], 301.0)

    async def test_ave_token_detail_async_skips_stale_state_commit_after_display_await(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {
            "spotlight_request_seq": 1,
            "screen": "spotlight",
            "current_token": {
                "addr": "fresh-token",
                "chain": "solana",
                "symbol": "FRESH",
                "token_id": "fresh-token-solana",
            },
        }
        sent = []

        def _fake_data_get(path, params=None):
            del params
            if path.startswith("/tokens/"):
                return {
                    "data": {
                        "token": {
                            "symbol": "STALE",
                            "current_price_usd": 1.23,
                            "token_price_change_24h": 0.12,
                            "holders": 1234,
                            "main_pair_tvl": 45678,
                        }
                    }
                }
            if path.startswith("/klines/token/"):
                return {
                    "data": {
                        "points": [
                            {"close": 1.1, "time": 1710000000},
                            {"close": 1.2, "time": 1710003600},
                        ]
                    }
                }
            if path.startswith("/contracts/"):
                return {"data": {}}
            raise AssertionError(f"unexpected path: {path}")

        async def _fake_send_display(_, screen, payload):
            sent.append((screen, dict(payload)))
            # Simulate a newer spotlight request being issued while the stale
            # request is awaiting display transport.
            conn.ave_state["spotlight_request_seq"] = 2
            conn.ave_state["current_token"] = {
                "addr": "fresh-token",
                "chain": "solana",
                "symbol": "FRESH",
                "token_id": "fresh-token-solana",
            }
            await asyncio.sleep(0)

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._risk_flags", return_value={
                 "is_honeypot": False,
                 "is_mintable": False,
                 "is_freezable": False,
                 "risk_level": "LOW",
             }), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            await ave_tools._ave_token_detail_async(
                conn,
                addr="stale-token",
                chain="solana",
                symbol="STALE",
                interval="60",
                request_seq=1,
            )

        self.assertEqual(len(sent), 1)
        self.assertEqual(conn.ave_state["current_token"]["addr"], "fresh-token")
        self.assertEqual(conn.ave_state["current_token"]["token_id"], "fresh-token-solana")
        self.assertEqual(conn.ave_wss.calls, [])

    async def test_ave_token_detail_async_s1_ignores_raw_buffer_from_mismatched_owner(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {"spotlight_request_seq": 7}
        conn.ave_wss._spotlight_id = "new-token-solana"
        conn.ave_wss._spotlight_raw_closes = [9.0, 8.0]
        conn.ave_wss._spotlight_raw_times = [1710000000, 1710000060]
        conn.ave_wss._spotlight_raw_owner_token_id = "old-token-solana"
        conn.ave_wss._spotlight_raw_owner_chain = "solana"
        conn.ave_wss._spotlight_raw_owner_interval = "k1"
        sent = []

        def _fake_data_get(path, params=None):
            del params
            if path.startswith("/tokens/"):
                return {
                    "data": {
                        "token": {
                            "symbol": "NEW",
                            "current_price_usd": 1.23,
                            "token_price_change_24h": 0.01,
                            "holders": 123,
                            "main_pair_tvl": 55555,
                        }
                    }
                }
            if path.startswith("/contracts/"):
                return {"data": {}}
            raise AssertionError(f"unexpected path: {path}")

        async def _fake_send_display(_, screen, payload):
            sent.append((screen, dict(payload)))

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._risk_flags", return_value={
                 "is_honeypot": False,
                 "is_mintable": False,
                 "is_freezable": False,
                 "risk_level": "LOW",
             }), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            await ave_tools._ave_token_detail_async(
                conn,
                addr="new-token",
                chain="solana",
                symbol="NEW",
                interval="s1",
                request_seq=7,
            )

        self.assertTrue(sent)
        spotlight_payload = sent[-1][1]
        self.assertEqual(spotlight_payload["chart_min"], "$1.2300")
        self.assertEqual(spotlight_payload["chart_max"], "$1.2300")
        self.assertEqual(len(conn.ave_wss.calls), 1)
        raw_closes = conn.ave_wss.calls[0][0][3]
        self.assertTrue(raw_closes)
        self.assertTrue(all(abs(value - 1.23) < 1e-9 for value in raw_closes))

    async def test_ave_token_detail_async_includes_rich_spotlight_fields(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {"spotlight_request_seq": 3}
        sent = []

        def _fake_data_get(path, params=None):
            del params
            if path.startswith("/tokens/top100/"):
                return {
                    "data": [
                        {"balance_ratio": 0.1},
                        {"balance_ratio": "0.05"},
                        {"balance_ratio": 0.1234},
                    ]
                }
            if path.startswith("/tokens/"):
                return {
                    "data": {
                        "token": {
                            "symbol": "BONK",
                            "current_price_usd": 1.23,
                            "token_price_change_24h": 4.56,
                            "holders": 1234,
                            "main_pair_tvl": 98765,
                            "token_tx_volume_usd_24h": 7654321,
                            "fdv": 223456789,
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
                return {"data": {"risk_score": 20}}
            raise AssertionError(path)

        async def _fake_send_display(_, screen, payload):
            sent.append((screen, dict(payload)))

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            await ave_tools._ave_token_detail_async(
                conn,
                addr="0x1234567890abcdef",
                chain="solana",
                symbol="BONK",
                interval="60",
                request_seq=3,
            )

        payload = sent[-1][1]
        self.assertEqual(payload["volume_24h"], "$7.7M")
        self.assertEqual(payload["market_cap"], "$223.5M")
        self.assertEqual(payload["top100_concentration"], "27.3%")
        self.assertEqual(payload["contract_short"], "0x12...cdef")

    async def test_ave_token_detail_async_falls_back_to_na_for_missing_rich_fields(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {"spotlight_request_seq": 4}
        sent = []

        def _fake_data_get(path, params=None):
            del params
            if path.startswith("/tokens/top100/"):
                return {"data": {}}
            if path.startswith("/tokens/"):
                return {
                    "data": {
                        "token": {
                            "symbol": "BONK",
                            "current_price_usd": 1.23,
                            "token_price_change_24h": 0,
                            "holders": 0,
                            "main_pair_tvl": 0,
                        }
                    }
                }
            if path.startswith("/klines/token/"):
                return {"data": {"points": [{"close": 1.23, "time": 1710000000}]}}
            if path.startswith("/contracts/"):
                return {"data": {"risk_score": 5}}
            raise AssertionError(path)

        async def _fake_send_display(_, screen, payload):
            sent.append((screen, dict(payload)))

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            await ave_tools._ave_token_detail_async(
                conn,
                addr="0x1234567890abcdef",
                chain="solana",
                symbol="BONK",
                interval="60",
                request_seq=4,
            )

        payload = sent[-1][1]
        self.assertEqual(payload["volume_24h"], "N/A")
        self.assertEqual(payload["market_cap"], "N/A")
        self.assertEqual(payload["top100_concentration"], "N/A")
        self.assertEqual(payload["contract_short"], "0x12...cdef")

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

    async def test_data_event_price_batch_live_feed_includes_feed_session_identity(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        conn.ave_state["feed_session"] = 17
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

        raw = json.dumps(
            {
                "result": {
                    "prices": [
                        {
                            "token_id": "token-1",
                            "chain": "solana",
                            "is_main_pair": True,
                            "price": "2.5",
                            "price_change_1h": "4.2",
                        }
                    ]
                }
            }
        )

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await manager._handle_data_event(raw)

        self.assertTrue(sent)
        self.assertEqual(sent[0][0], "feed")
        self.assertEqual(sent[0][1].get("feed_session"), 17)
        self.assertTrue(sent[0][1]["live"])

    def test_feed_surface_ignores_stale_live_payload_when_feed_session_mismatches(self):
        repo_root = Path(__file__).resolve().parents[3]
        verifier_prefix = (repo_root / "simulator/mock/verify_ave_json_payloads.c").read_text(
            encoding="utf-8"
        ).split("#if defined(VERIFY_FEED)", 1)[0]
        screen_source = repo_root / "shared/ave_screens/screen_feed.c"

        harness_source = f"""
#define VERIFY_FEED
{verifier_prefix}

#ifndef LV_OPA_TRANSP
#define LV_OPA_TRANSP 0
#endif
#ifndef LV_TEXT_ALIGN_LEFT
#define LV_TEXT_ALIGN_LEFT 0
#define LV_TEXT_ALIGN_CENTER 1
#define LV_TEXT_ALIGN_RIGHT 2
#endif
void lv_obj_set_style_text_align(lv_obj_t *obj, int align, int part)
{{
    (void)obj;
    (void)align;
    (void)part;
}}
int lv_font_get_line_height(const lv_font_t *font)
{{
    (void)font;
    return 14;
}}
void ave_fmt_price_text(char *out, size_t out_n, const char *price)
{{
    if (!out || out_n == 0) return;
    snprintf(out, out_n, "%s", price ? price : "");
}}
const lv_font_t *ave_font_cjk_14(void) {{ return &lv_font_montserrat_14; }}
const lv_font_t *ave_font_cjk_16(void) {{ return &lv_font_montserrat_14; }}
void ave_sm_go_to_feed(void) {{ }}
int ave_sm_json_escape_string(const char *src, char *out, size_t out_n)
{{
    if (!out || out_n == 0) return 0;
    snprintf(out, out_n, "%s", src ? src : "");
    return 1;
}}
int ave_sm_build_key_action_json(
    const char *action,
    const ave_sm_json_field_t *fields,
    size_t field_count,
    char *out,
    size_t out_n
)
{{
    (void)fields;
    (void)field_count;
    if (!out || out_n == 0) return 0;
    snprintf(out, out_n, "{{\\\"type\\\":\\\"key_action\\\",\\\"action\\\":\\\"%s\\\"}}", action ? action : "");
    return 1;
}}

#include "{screen_source}"

int main(void)
{{
    screen_feed_show(
        "{{\\"screen\\":\\"feed\\",\\"data\\":{{\\"feed_session\\":11,\\"mode\\":\\"search\\","
        "\\"source_label\\":\\"SEARCH\\",\\"tokens\\":[{{\\"token_id\\":\\"token-old-solana\\","
        "\\"chain\\":\\"solana\\",\\"symbol\\":\\"OLD\\",\\"price\\":\\"$1\\"}}]}}}}"
    );
    screen_feed_show(
        "{{\\"screen\\":\\"feed\\",\\"data\\":{{\\"feed_session\\":12,\\"source_label\\":\\"TRENDING\\","
        "\\"tokens\\":[{{\\"token_id\\":\\"token-new-solana\\",\\"chain\\":\\"solana\\","
        "\\"symbol\\":\\"NEW\\",\\"price\\":\\"$2\\"}}]}}}}"
    );
    screen_feed_show(
        "{{\\"screen\\":\\"feed\\",\\"data\\":{{\\"feed_session\\":11,\\"live\\":true,\\"tokens\\":["
        "{{\\"token_id\\":\\"token-old-solana\\",\\"chain\\":\\"solana\\",\\"symbol\\":\\"OLD\\","
        "\\"price\\":\\"$9\\"}}]}}}}"
    );

    if (strcmp(s_tokens[0].token_id, "token-new-solana") != 0) {{
        fprintf(stderr, "stale live payload replaced newer feed context: %s\\n", s_tokens[0].token_id);
        return 2;
    }}
    if (s_is_search_mode != 0) {{
        fprintf(stderr, "stale live payload resurrected search mode\\n");
        return 3;
    }}
    return 0;
}}
"""

        self._compile_and_run_feed_c_harness(
            harness_source,
            "verify_feed_session_blocks_stale_live_payload",
        )

    async def test_data_event_kline_result_format_buffers_live_points_without_replacing_spotlight_chart(self):
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
            "chart_min": "$1",
            "chart_max": "$2",
            "interval": "60",
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
        self.assertEqual(manager._spotlight_data["chart"], [100, 200])
        self.assertEqual(manager._spotlight_data["chart_min"], "$1")
        self.assertEqual(manager._spotlight_data["chart_max"], "$2")
        self.assertEqual(manager._spotlight_data["chart_t_end"], "old")
        self.assertEqual(sent, [])

    async def test_data_event_kline_refreshes_spotlight_chart_when_live_s1_selected(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        manager._spotlight_pair = "pair-1"
        manager._spotlight_interval = "s1"
        manager._spotlight_data = {
            "token_id": "token-1-solana",
            "symbol": "BONK",
            "interval": "s1",
            "chart": [100, 200],
            "chart_min": "$1",
            "chart_max": "$2",
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

        self.assertEqual(sent[0][0], "spotlight")
        self.assertTrue(sent[0][1]["live"])
        self.assertEqual(sent[0][1]["interval"], "s1")
        self.assertEqual(sent[0][1]["chart_t_end"], "now")
        self.assertGreaterEqual(len(sent[0][1]["chart"]), 1)
        self.assertEqual(manager._spotlight_data["chart_t_end"], "now")

    async def test_data_event_kline_does_not_refresh_spotlight_chart_when_live_k1_selected(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        manager._spotlight_pair = "pair-1"
        manager._spotlight_interval = "k1"
        manager._spotlight_data = {
            "token_id": "token-1-solana",
            "symbol": "BONK",
            "interval": "1",
            "chart": [100, 200],
            "chart_min": "$1",
            "chart_max": "$2",
            "chart_t_end": "old",
        }

        raw = json.dumps({
            "result": {
                "id": "pair-1-solana",
                "interval": "k1",
                "kline": {
                    "eth": {
                        "close": "0.2234",
                        "time": 1710000010,
                    }
                },
            }
        })

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display):
            await manager._handle_data_event(raw)

        self.assertEqual(manager._spotlight_raw_closes[-1], 0.2234)
        self.assertEqual(manager._spotlight_raw_times[-1], 1710000010)
        self.assertEqual(manager._spotlight_data["chart"], [100, 200])
        self.assertEqual(manager._spotlight_data["chart_min"], "$1")
        self.assertEqual(manager._spotlight_data["chart_max"], "$2")
        self.assertEqual(manager._spotlight_data["chart_t_end"], "old")
        self.assertEqual(sent, [])

    async def test_spotlight_poll_loop_refreshes_chart_for_live_minute_interval(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        sleep_calls = {"count": 0}

        async def _fake_sleep(_seconds):
            sleep_calls["count"] += 1
            if sleep_calls["count"] > 1:
                raise asyncio.CancelledError()
            return None

        def _fake_data_get(path, params=None):
            if path == "/tokens/token-1-solana":
                return {
                    "data": {
                        "token": {
                            "symbol": "BONK",
                            "holders": 4321,
                            "main_pair_tvl": 2500000,
                        }
                    }
                }
            if path == "/klines/token/token-1-solana":
                self.assertEqual(params, {"interval": "1", "limit": 48})
                return {
                    "data": {
                        "points": [
                            {"close": 1.0, "time": 1710000000},
                            {"close": 1.2, "time": 1710000060},
                            {"close": 1.1, "time": 1710000120},
                        ]
                    }
                }
            raise AssertionError(f"unexpected path: {path}")

        manager._spotlight_data = {
            "addr": "token-1",
            "chain": "solana",
            "interval": "1",
            "chart": [0, 0, 0],
            "chart_min": "$0",
            "chart_max": "$0",
            "chart_t_end": "old",
        }

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("asyncio.sleep", side_effect=_fake_sleep):
            with self.assertRaises(asyncio.CancelledError):
                await manager._spotlight_poll_loop("token-1", "solana")

        self.assertGreaterEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "spotlight")
        self.assertEqual(sent[0][1]["interval"], "1")
        self.assertNotEqual(sent[0][1]["chart"], [0, 0, 0])
        self.assertEqual(sent[0][1]["chart_t_end"], "now")

    async def test_spotlight_poll_loop_drops_results_if_identity_changes_after_token_await(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        manager = ave_wss.AveWssManager(conn)
        sent = []
        requests = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        async def _fake_sleep(_seconds):
            return None

        manager._spotlight_data = {
            "addr": "token-1",
            "chain": "solana",
            "interval": "1",
            "holders": "BASE-HOLDERS",
            "liquidity": "BASE-LIQ",
            "chart": [9, 9, 9],
            "chart_t_end": "base-old",
        }

        def _fake_data_get(path, params=None):
            requests.append((path, params))
            if path == "/tokens/token-1-solana":
                # Simulate user switching to same addr on another chain while
                # this poll request is in flight.
                manager._spotlight_data.update(
                    {
                        "chain": "base",
                        "holders": "BASE-HOLDERS",
                        "liquidity": "BASE-LIQ",
                        "chart": [9, 9, 9],
                        "chart_t_end": "base-old",
                    }
                )
                manager._stopped = True
                return {
                    "data": {
                        "token": {
                            "holders": 4321,
                            "main_pair_tvl": 2500000,
                        }
                    }
                }
            if path == "/klines/token/token-1-solana":
                return {
                    "data": {
                        "points": [
                            {"close": 1.0, "time": 1710000000},
                            {"close": 1.2, "time": 1710000060},
                        ]
                    }
                }
            raise AssertionError(f"unexpected path: {path}")

        with patch("plugins_func.functions.ave_wss._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("asyncio.sleep", side_effect=_fake_sleep):
            await manager._spotlight_poll_loop("token-1", "solana")

        self.assertEqual(sent, [])
        self.assertEqual(requests, [("/tokens/token-1-solana", None)])
        self.assertEqual(manager._spotlight_data.get("chain"), "base")
        self.assertEqual(manager._spotlight_data.get("holders"), "BASE-HOLDERS")

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

    async def test_disambiguation_overflow_restore_keeps_visible_slice_consistent(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        disambiguation_pool = [
            {
                "token_id": f"token-{idx}-solana",
                "chain": "solana",
                "symbol": "PEPE",
            }
            for idx in range(15)
        ]

        def _fake_data_get(path, params=None):
            if path == "/tokens":
                return {"data": {"tokens": list(disambiguation_pool)}}
            raise AssertionError(f"unexpected path: {path}")

        async def _fake_send_display(_, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_search_token(conn, keyword="PEPE", chain="all")
            await asyncio.sleep(0)

        disambiguation_payload = next((payload for screen, payload in sent if screen == "disambiguation"), None)
        self.assertIsNotNone(disambiguation_payload)
        visible_items = list(disambiguation_payload.get("items", []))
        self.assertEqual(len(visible_items), 12)
        self.assertEqual(disambiguation_payload.get("total_candidates"), 15)
        self.assertEqual(len(conn.ave_state.get("disambiguation_items", [])), 12)
        self.assertEqual(len(conn.ave_state.get("search_session", {}).get("items", [])), 12)

        await dispatch_key(conn, "right", selection_candidates=visible_items, cursor=11)
        sent_back = await dispatch_key(conn, "back")

        restored_payload = next((payload for screen, payload in sent_back if screen == "feed"), None)
        self.assertIsNotNone(restored_payload)
        self.assertEqual(restored_payload.get("cursor"), 11)
        restored_ids = [item.get("token_id") for item in restored_payload.get("tokens", [])]
        visible_ids = [item.get("token_id") for item in visible_items]
        self.assertEqual(restored_ids, visible_ids)

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

    async def test_watch_enters_spotlight_before_slow_detail_fetch_completes(self):
        handler = KeyActionHandler()
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state.update(
            {
                "feed_token_list": [
                    {"addr": "token-1", "chain": "solana", "symbol": "BONK"},
                ],
            }
        )

        release_fetch = threading.Event()
        sent = []

        def fake_data_get(path, params=None):
            del params
            release_fetch.wait(timeout=0.15)
            if path.startswith("/tokens/"):
                return {
                    "data": {
                        "token": {
                            "symbol": "BONK",
                            "current_price_usd": 1.23,
                            "token_price_change_24h": 4.56,
                            "holders": 1234,
                            "main_pair_tvl": 98765,
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

        async def fake_send_display(_, screen, payload):
            sent.append((screen, dict(payload)))

        timer = threading.Timer(0.05, release_fetch.set)
        timer.start()
        try:
            with patch("plugins_func.functions.ave_tools._data_get", side_effect=fake_data_get), \
                 patch("plugins_func.functions.ave_tools._risk_flags", return_value={
                     "is_honeypot": False,
                     "is_mintable": False,
                     "is_freezable": False,
                     "risk_level": "LOW",
                 }), \
                 patch("plugins_func.functions.ave_tools._send_display", side_effect=fake_send_display):
                task = asyncio.create_task(
                    handler.handle(
                        conn,
                        {
                            "type": "key_action",
                            "action": "watch",
                            "token_id": "token-1",
                            "chain": "solana",
                            "cursor": "0",
                        },
                    )
                )
                await asyncio.sleep(0.01)
                self.assertTrue(sent)
                self.assertEqual(sent[0][0], "spotlight")
                self.assertEqual(sent[0][1].get("symbol"), "BONK")
                self.assertEqual(sent[0][1].get("price"), "--")
                self.assertEqual(sent[0][1].get("chain"), "solana")
                self.assertEqual(sent[0][1].get("token_id"), "token-1-solana")

                await task
                for _ in range(20):
                    if len(sent) >= 2:
                        break
                    await asyncio.sleep(0.01)
        finally:
            release_fetch.set()
            timer.cancel()

        self.assertGreaterEqual(len(sent), 2)
        self.assertEqual(sent[-1][0], "spotlight")
        self.assertEqual(sent[-1][1].get("symbol"), "BONK")
        self.assertEqual(sent[-1][1].get("price"), "$1.2300")

    async def test_kline_interval_refresh_keeps_existing_spotlight_visible_until_new_data_arrives(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state.update(
            {
                "screen": "spotlight",
                "current_token": {
                    "addr": "token-1",
                    "chain": "solana",
                    "symbol": "BONK",
                    "token_id": "token-1-solana",
                },
            }
        )
        conn.ave_wss._spotlight_data = {
            "addr": "token-1",
            "chain": "solana",
            "token_id": "token-1-solana",
            "symbol": "BONK",
            "price": "$9.9900",
            "interval": "60",
            "chart": [100, 200, 300],
            "chart_min": "$1",
            "chart_max": "$3",
            "chart_t_end": "now",
        }

        release_fetch = threading.Event()
        sent = []

        def fake_data_get(path, params=None):
            del params
            release_fetch.wait(timeout=0.15)
            if path.startswith("/tokens/"):
                return {
                    "data": {
                        "token": {
                            "symbol": "BONK",
                            "current_price_usd": 1.23,
                            "token_price_change_24h": 4.56,
                            "holders": 1234,
                            "main_pair_tvl": 98765,
                        }
                    }
                }
            if path.startswith("/klines/token/"):
                return {
                    "data": {
                        "points": [
                            {"close": 3.0, "time": 1710000000},
                            {"close": 4.0, "time": 1710003600},
                        ]
                    }
                }
            if path.startswith("/contracts/"):
                return {"data": {}}
            raise AssertionError(f"unexpected path: {path}")

        async def fake_send_display(_, screen, payload):
            sent.append((screen, dict(payload)))

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=fake_data_get), \
             patch("plugins_func.functions.ave_tools._risk_flags", return_value={
                 "is_honeypot": False,
                 "is_mintable": False,
                 "is_freezable": False,
                 "risk_level": "LOW",
             }), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=fake_send_display):
            ave_tools.ave_token_detail(conn, addr="token-1", chain="solana", interval="240")
            await asyncio.sleep(0.01)

            self.assertFalse(sent)
            self.assertEqual(len(conn.ave_wss.transitions), 1)
            self.assertEqual(conn.ave_wss.transitions[0]["interval"], "k240")
            self.assertEqual(conn.ave_wss._spotlight_data.get("interval"), "240")
            self.assertEqual(conn.ave_wss._spotlight_data.get("price"), "$9.9900")

            release_fetch.set()
            for _ in range(20):
                if sent:
                    break
                await asyncio.sleep(0.01)

        self.assertTrue(sent)
        self.assertEqual(sent[-1][0], "spotlight")
        self.assertEqual(sent[-1][1].get("interval"), "240")
        self.assertEqual(sent[-1][1].get("price"), "$1.2300")

    async def test_spotlight_next_switches_wss_identity_immediately_so_old_live_updates_do_not_revert_screen(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_wss = ave_wss.AveWssManager(conn)
        conn.ave_state.update(
            {
                "screen": "spotlight",
                "current_token": {
                    "addr": "old-token",
                    "chain": "solana",
                    "symbol": "OLD",
                    "token_id": "old-token-solana",
                },
            }
        )
        conn.ave_wss._spotlight_id = "old-token-solana"
        conn.ave_wss._spotlight_pair = "old-token"
        conn.ave_wss._spotlight_chain = "solana"
        conn.ave_wss._spotlight_interval = "k60"
        conn.ave_wss._spotlight_data = {
            "addr": "old-token",
            "chain": "solana",
            "token_id": "old-token-solana",
            "symbol": "OLD",
            "price": "$9.9900",
            "interval": "60",
            "chart": [100, 200],
        }

        release_fetch = threading.Event()
        sent = []

        def fake_data_get(path, params=None):
            del params
            release_fetch.wait(timeout=0.15)
            if path.startswith("/tokens/"):
                return {
                    "data": {
                        "token": {
                            "symbol": "NEW",
                            "current_price_usd": 1.23,
                            "token_price_change_24h": 4.56,
                            "holders": 1234,
                            "main_pair_tvl": 98765,
                        }
                    }
                }
            if path.startswith("/klines/token/"):
                return {
                    "data": {
                        "points": [
                            {"close": 3.0, "time": 1710000000},
                            {"close": 4.0, "time": 1710003600},
                        ]
                    }
                }
            if path.startswith("/contracts/"):
                return {"data": {}}
            raise AssertionError(f"unexpected path: {path}")

        async def fake_send_display(_, screen, payload):
            sent.append((screen, dict(payload)))

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=fake_data_get), \
             patch("plugins_func.functions.ave_tools._risk_flags", return_value={
                 "is_honeypot": False,
                 "is_mintable": False,
                 "is_freezable": False,
                 "risk_level": "LOW",
             }), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=fake_send_display), \
             patch("plugins_func.functions.ave_wss._send_display", side_effect=fake_send_display):
            ave_tools.ave_token_detail(conn, addr="new-token", chain="solana")
            await asyncio.sleep(0.01)

            self.assertEqual(conn.ave_wss._spotlight_id, "new-token-solana")
            self.assertEqual(conn.ave_wss._spotlight_data.get("token_id"), "new-token-solana")

            await conn.ave_wss._on_price_event({
                "token_id": "old-token",
                "chain": "solana",
                "price": "8.88",
                "price_change_1h": "1.2",
            })
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0][1].get("token_id"), "new-token-solana")

            release_fetch.set()
            for _ in range(20):
                if len(sent) >= 2:
                    break
                await asyncio.sleep(0.01)

        self.assertEqual(sent[-1][1].get("token_id"), "new-token-solana")
        self.assertEqual(sent[-1][1].get("price"), "$1.2300")

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

    def test_risk_flags_normalize_numeric_and_string_sentinels(self):
        numeric_sentinel_resp = {"data": {"is_honeypot": -1, "risk_score": 20}}
        numeric_flags = ave_tools._risk_flags(numeric_sentinel_resp)
        self.assertFalse(numeric_flags["is_honeypot"])
        self.assertEqual(numeric_flags["risk_level"], "MEDIUM")

        string_resp = {
            "data": {
                "is_honeypot": "1",
                "has_mint_method": "1",
                "has_black_method": "TRUE",
            }
        }
        string_flags = ave_tools._risk_flags(string_resp)
        self.assertTrue(string_flags["is_honeypot"])
        self.assertTrue(string_flags["is_mintable"])
        self.assertTrue(string_flags["is_freezable"])
        self.assertEqual(string_flags["risk_level"], "CRITICAL")

        false_string_resp = {"data": {"is_honeypot": "false"}}
        false_string_flags = ave_tools._risk_flags(false_string_resp)
        self.assertFalse(false_string_flags["is_honeypot"])
        self.assertEqual(false_string_flags["risk_level"], "UNKNOWN")

        rejected_truthy_forms = {
            "data": {
                "is_honeypot": 1.0,
                "has_mint_method": 1.0,
                "has_black_method": 1.0,
            }
        }
        rejected_numeric_float_flags = ave_tools._risk_flags(rejected_truthy_forms)
        self.assertFalse(rejected_numeric_float_flags["is_honeypot"])
        self.assertFalse(rejected_numeric_float_flags["is_mintable"])
        self.assertFalse(rejected_numeric_float_flags["is_freezable"])

        rejected_truthy_strings = {
            "data": {
                "is_honeypot": "1.0",
                "has_mint_method": "on",
                "has_black_method": "t",
            }
        }
        rejected_truthy_string_flags = ave_tools._risk_flags(rejected_truthy_strings)
        self.assertFalse(rejected_truthy_string_flags["is_honeypot"])
        self.assertFalse(rejected_truthy_string_flags["is_mintable"])
        self.assertFalse(rejected_truthy_string_flags["is_freezable"])

    def test_risk_flags_treat_missing_values_as_false(self):
        flags = ave_tools._risk_flags({"data": {}})
        self.assertFalse(flags["is_honeypot"])
        self.assertFalse(flags["is_mintable"])
        self.assertFalse(flags["is_freezable"])
        self.assertEqual(flags["risk_level"], "UNKNOWN")

        list_payload_flags = ave_tools._risk_flags({"data": [{"risk_score": None}]})
        self.assertFalse(list_payload_flags["is_honeypot"])
        self.assertFalse(list_payload_flags["is_mintable"])
        self.assertFalse(list_payload_flags["is_freezable"])
        self.assertEqual(list_payload_flags["risk_level"], "UNKNOWN")

    def test_risk_flags_malformed_payloads_default_safe(self):
        empty_list_flags = ave_tools._risk_flags({"data": []})
        self.assertFalse(empty_list_flags["is_honeypot"])
        self.assertFalse(empty_list_flags["is_mintable"])
        self.assertFalse(empty_list_flags["is_freezable"])
        self.assertEqual(empty_list_flags["risk_level"], "UNKNOWN")

        bad_type_flags = ave_tools._risk_flags({"data": "bad"})
        self.assertFalse(bad_type_flags["is_honeypot"])
        self.assertFalse(bad_type_flags["is_mintable"])
        self.assertFalse(bad_type_flags["is_freezable"])
        self.assertEqual(bad_type_flags["risk_level"], "UNKNOWN")

    def test_risk_level_malformed_score_falls_back_unknown(self):
        for malformed_score in ("20.5", "N/A", "", "   "):
            flags = ave_tools._risk_flags({"data": {"risk_score": malformed_score}})
            self.assertEqual(flags["risk_level"], "UNKNOWN")

    def test_risk_level_out_of_range_score_falls_back_unknown(self):
        for out_of_range_score in (-1, 101):
            flags = ave_tools._risk_flags({"data": {"risk_score": out_of_range_score}})
            self.assertEqual(flags["risk_level"], "UNKNOWN")

    def test_risk_helpers_non_dict_roots_fail_closed(self):
        for root in (None, [], "bad"):
            flags = ave_tools._risk_flags(root)
            self.assertFalse(flags["is_honeypot"])
            self.assertFalse(flags["is_mintable"])
            self.assertFalse(flags["is_freezable"])
            self.assertEqual(flags["risk_level"], "UNKNOWN")
            self.assertEqual(ave_tools._risk_level_from_response(root), "UNKNOWN")

    def test_extract_top100_concentration_sums_first_100_balance_ratio_entries(self):
        top100_resp = {
            "data": {
                "items": [{"balance_ratio": 0.001}] * 100 + [{"balance_ratio": 0.5}]
            }
        }
        self.assertEqual(
            ave_tools._extract_top100_concentration(top100_resp),
            "10.0%",
        )

    def test_extract_top100_concentration_accepts_percent_string(self):
        top100_resp = {"data": {"top100_concentration": "2.6%"}}
        self.assertEqual(
            ave_tools._extract_top100_concentration(top100_resp),
            "2.6%",
        )
        half_percent = {"data": {"top100_concentration": "0.5%"}}
        self.assertEqual(
            ave_tools._extract_top100_concentration(half_percent),
            "0.5%",
        )

    def test_extract_top100_concentration_treats_balance_ratio_as_fraction_of_one(self):
        top100_resp = {
            "data": {
                "items": [
                    {"balance_ratio": 0.025928},
                    {"balance_ratio": "0.334417"},
                ]
            }
        }
        self.assertEqual(
            ave_tools._extract_top100_concentration(top100_resp),
            "36.0%",
        )

    def test_extract_top100_concentration_skips_out_of_range_balance_ratios(self):
        top100_resp = {
            "data": {
                "items": [
                    {"balance_ratio": -0.01},
                    {"balance_ratio": 0.5},
                    {"balance_ratio": 120},
                    {"balance_ratio": "abc"},
                ]
            }
        }
        self.assertEqual(
            ave_tools._extract_top100_concentration(top100_resp),
            "50.0%",
        )

    async def test_ave_token_detail_async_handles_stringy_volume_and_market_cap_fail_soft(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {"spotlight_request_seq": 9}
        sent = []

        def _fake_data_get(path, params=None):
            del params
            if path.startswith("/tokens/top100/"):
                return {
                    "data": [
                        {"balance_ratio": "2.6%"},
                        {"balance_ratio": "1.4%"},
                    ]
                }
            if path.startswith("/tokens/"):
                return {
                    "data": {
                        "token": {
                            "symbol": "BONK",
                            "current_price_usd": "1.23",
                            "token_price_change_24h": "0.5",
                            "holders": 10,
                            "main_pair_tvl": "1,234",
                            "token_tx_volume_usd_24h": "",
                            "market_cap": "",
                            "fdv": "N/A",
                        }
                    }
                }
            if path.startswith("/klines/token/"):
                return {"data": {"points": [{"close": 1.23, "time": 1710000000}]}}
            if path.startswith("/contracts/"):
                return {"data": {"risk_score": 5}}
            raise AssertionError(path)

        async def _fake_send_display(_, screen, payload):
            sent.append((screen, dict(payload)))

        with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            await ave_tools._ave_token_detail_async(
                conn,
                addr="0x1234567890abcdef",
                chain="solana",
                symbol="BONK",
                interval="60",
                request_seq=9,
            )

        payload = sent[-1][1]
        self.assertEqual(payload["volume_24h"], "N/A")
        self.assertEqual(payload["market_cap"], "N/A")
        self.assertEqual(payload["liquidity"], "$1.2K")
        self.assertEqual(payload["top100_concentration"], "4.0%")

    def test_safe_top100_summary_get_fails_soft_for_assertion_error(self):
        with patch("plugins_func.functions.ave_tools._data_get", side_effect=AssertionError("fixture mismatch")):
            self.assertEqual(
                ave_tools._safe_top100_summary_get("token-1", "solana"),
                {},
            )

    def test_safe_top100_summary_get_calls_expected_top100_endpoint(self):
        with patch("plugins_func.functions.ave_tools._data_get", return_value={"data": []}) as mock_data_get:
            self.assertEqual(
                ave_tools._safe_top100_summary_get("token-1", "solana"),
                {"data": []},
            )
        mock_data_get.assert_called_once_with("/tokens/top100/token-1-solana")

    def test_safe_top100_summary_get_fails_soft_for_runtime_errors(self):
        with patch("plugins_func.functions.ave_tools._data_get", side_effect=RuntimeError("network down")):
            self.assertEqual(
                ave_tools._safe_top100_summary_get("token-1", "solana"),
                {},
            )


if __name__ == "__main__":
    unittest.main()
