import asyncio
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.handle.textHandler.keyActionHandler import KeyActionHandler
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


class OrdersTests(unittest.IsolatedAsyncioTestCase):
    def _compile_and_run_c_harness(self, harness_source: str, binary_name: str):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"

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
                    str(manager_src),
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

    def test_build_limit_order_rows_formats_distance(self):
        rows = ave_tools._build_limit_order_rows([
            {
                "id": "ord-1",
                "outTokenAddress": "token-1",
                "symbol": "BONK",
                "limitPrice": "0.003",
                "createPrice": "0.002",
            }
        ], chain="solana")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["token_id"], "token-1")
        self.assertEqual(rows[0]["order_id"], "ord-1")
        self.assertEqual(rows[0]["symbol"], "BONK")
        self.assertEqual(rows[0]["price"], "$0.003000")
        self.assertEqual(rows[0]["change_24h"], "+50.00%")
        self.assertTrue(rows[0]["change_positive"])

    def test_build_limit_order_rows_with_missing_create_price_degrades_to_na(self):
        rows = ave_tools._build_limit_order_rows([
            {
                "id": "ord-1",
                "outTokenAddress": "token-1",
                "symbol": "BONK",
                "limitPrice": "0.003",
                "createPrice": "not-a-number",
            }
        ], chain="solana")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["change_24h"], "N/A")
        self.assertIsNone(rows[0]["change_positive"])

    def test_orders_feed_surface_preserves_null_change_positive_as_neutral(self):
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

int screen_confirm_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

int screen_limit_confirm_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

int screen_result_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_disambiguation_show(const char *json_data) {{ (void)json_data; }}
void screen_disambiguation_key(int key) {{ (void)key; }}
void screen_disambiguation_cancel_timers(void) {{ }}
int screen_disambiguation_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

#include "{screen_source}"

int main(void)
{{
    screen_feed_show("{{\\"screen\\":\\"feed\\",\\"data\\":{{\\"mode\\":\\"orders\\",\\"source_label\\":\\"ORDERS\\",\\"tokens\\":[{{\\"token_id\\":\\"token-1\\",\\"chain\\":\\"solana\\",\\"symbol\\":\\"BONK\\",\\"price\\":\\"$1\\",\\"change_24h\\":\\"N/A\\",\\"change_positive\\":null}}]}}}}");

    if (s_tokens[0].change_positive != -1) {{
        fprintf(stderr, "null change_positive should stay neutral, got %d\\n", s_tokens[0].change_positive);
        return 2;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(harness_source, "verify_orders_null_change_positive")

    def test_ave_sell_token_schema_requires_string_holdings_amount(self):
        holdings_amount = (
            ave_tools.ave_sell_token_desc["function"]["parameters"]["properties"]["holdings_amount"]
        )

        self.assertEqual(holdings_amount["type"], "string")
        self.assertIn("raw", holdings_amount["description"].lower())

    async def test_ave_list_orders_pushes_feed_and_stores_order_state(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._trade_get", return_value={
            "data": {
                "list": [
                    {
                        "id": "ord-1",
                        "outTokenAddress": "token-1",
                        "symbol": "BONK",
                        "limitPrice": "0.003",
                        "createPrice": "0.002",
                    }
                ]
            }
        }), patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            resp = ave_tools.ave_list_orders(conn, chain="solana")
            await asyncio.sleep(0)

        self.assertIn("ord-1", resp.result)
        self.assertEqual(sent[0][0], "feed")
        self.assertEqual(sent[0][1]["mode"], "orders")
        self.assertEqual(sent[0][1]["source_label"], "ORDERS")
        self.assertEqual(conn.ave_state["order_list"][0]["id"], "ord-1")

    def test_orders_result_payload_uses_order_state_explanation_copy(self):
        payload = ave_tools._build_result_payload(
            {
                "status": 1,
                "trade_type": "cancel_order",
                "data": {"ids": ["ord-1"]},
            },
            pending={"trade_type": "cancel_order", "symbol": "BONK"},
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["title"], "Order Cancelled")
        self.assertEqual(
            payload["subtitle"],
            "This changed an order state, not your wallet balance.",
        )

    def test_orders_feed_surface_shows_browse_only_chrome(self):
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

int screen_confirm_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

int screen_limit_confirm_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

int screen_result_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_disambiguation_show(const char *json_data) {{ (void)json_data; }}
void screen_disambiguation_key(int key) {{ (void)key; }}
void screen_disambiguation_cancel_timers(void) {{ }}
int screen_disambiguation_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

#include "{screen_source}"

int main(void)
{{
    screen_feed_show("{{\\"screen\\":\\"feed\\",\\"data\\":{{\\"mode\\":\\"orders\\",\\"source_label\\":\\"ORDERS\\",\\"tokens\\":[{{\\"token_id\\":\\"token-1\\",\\"chain\\":\\"solana\\",\\"symbol\\":\\"BONK\\",\\"price\\":\\"$1\\",\\"change_24h\\":\\"+1%\\"}}]}}}}");

    if (strstr(s_lbl_src_hint->text, "view only") == NULL) {{
        fprintf(stderr, "orders chrome missing browse-only hint: %s\\n", s_lbl_src_hint ? s_lbl_src_hint->text : "<null>");
        return 2;
    }}
    if (strstr(s_lbl_action_hint->text, "DETAIL") != NULL) {{
        fprintf(stderr, "orders action hint still suggests detail: %s\\n", s_lbl_action_hint->text);
        return 3;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(harness_source, "verify_orders_browse_only_chrome")

    async def test_key_action_orders_falls_back_to_current_token_chain_before_default(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {
            "current_token": {"chain": "eth"},
        }
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools.ave_list_orders") as mock_orders:
            await handler.handle(conn, {"type": "key_action", "action": "orders"})

        mock_orders.assert_called_once_with(conn, chain="eth")

    async def test_key_action_orders_prefers_last_orders_chain_over_current_token(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {
            "last_orders_chain": "base",
            "current_token": {"chain": "eth"},
        }
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools.ave_list_orders") as mock_orders:
            await handler.handle(conn, {"type": "key_action", "action": "orders"})

        mock_orders.assert_called_once_with(conn, chain="base")

    async def test_search_orders_back_exits_orders_to_standard_feed(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {
            "screen": "feed",
            "feed_mode": "search",
            "feed_source": "trending",
            "search_query": "BONK",
            "search_chain": "all",
            "search_cursor": 0,
            "search_results": [
                {"token_id": "token-1", "chain": "solana", "symbol": "BONK", "price": "$1.00"},
            ],
            "search_session": {
                "query": "BONK",
                "chain": "all",
                "cursor": 0,
                "items": [
                    {"token_id": "token-1", "chain": "solana", "symbol": "BONK", "price": "$1.00"},
                ],
            },
        }
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._trade_get", return_value={
            "data": {
                "list": [
                    {
                        "id": "ord-1",
                        "outTokenAddress": "token-1",
                        "symbol": "BONK",
                        "limitPrice": "0.003",
                        "createPrice": "0.002",
                    }
                ]
            }
        }), patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_list_orders(conn, chain="solana")
            await asyncio.sleep(0)

        self.assertEqual(conn.ave_state.get("feed_mode"), "orders")
        handler = KeyActionHandler()

        with patch("plugins_func.functions.ave_tools.ave_get_trending") as mock_trending, \
             patch("plugins_func.functions.ave_tools.ave_portfolio") as mock_portfolio, \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            await handler.handle(conn, {"type": "key_action", "action": "back"})

        mock_portfolio.assert_not_called()
        mock_trending.assert_called_once_with(conn, topic="trending")
        self.assertFalse(
            any(screen == "feed" and payload.get("mode") == "search" for screen, payload in sent[1:]),
            msg="orders back should not resurrect the previous search feed",
        )

    async def test_ave_cancel_order_creates_pending_cancel_trade_and_pushes_confirm(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools.trade_mgr.create", return_value="cancel123") as mock_create:
            resp = ave_tools.ave_cancel_order(conn, order_ids=["ord-1"], chain="solana", symbol="BONK")
            await asyncio.sleep(0)

        self.assertIn("cancel123", resp.result)
        mock_create.assert_called_once()
        trade_type, params, passed_conn = mock_create.call_args[0]
        self.assertEqual(trade_type, "cancel_order")
        self.assertEqual(params["chain"], "solana")
        self.assertEqual(params["ids"], ["ord-1"])
        self.assertIs(passed_conn, conn)
        self.assertEqual(sent[0][0], "confirm")
        self.assertEqual(sent[0][1]["trade_id"], "cancel123")
        self.assertEqual(sent[0][1]["action"], "CANCEL")
        self.assertEqual(sent[0][1]["timeout_sec"], 15)

    def test_ave_cancel_order_requires_order_ids(self):
        loop = asyncio.new_event_loop()
        try:
            conn = _FakeConn(loop)
            resp = ave_tools.ave_cancel_order(conn, order_ids=[])
        finally:
            loop.close()

        self.assertEqual(resp.result, "no_order_ids")
        self.assertIn("撤销哪个挂单", resp.response)

    async def test_ave_cancel_order_all_returns_no_waiting_orders_when_lookup_is_empty(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)

        with patch("plugins_func.functions.ave_tools._trade_get", return_value={"data": {"list": []}}):
            resp = ave_tools.ave_cancel_order(conn, order_ids=["all"], chain="solana")

        self.assertEqual(resp.result, "no_waiting_orders")
        self.assertIn("没有可撤销的挂单", resp.response)

    async def test_ave_portfolio_keeps_addr_chain_and_missing_machine_raw_fails_closed(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools._trade_get", return_value={
                 "data": [
                     {
                        "chain": "solana",
                         "tokens": [
                             {
                                 "address": "token-1",
                                 "balance": "123",
                                 "symbol": "BONK",
                             }
                         ],
                     }
                 ]
             }), \
             patch("plugins_func.functions.ave_tools._data_post", return_value={
                 "data": {
                     "token-1-solana": {"current_price_usd": "0.5"}
                 }
             }), \
             patch("plugins_func.functions.ave_tools.os.environ.get", return_value="wallet-1"):
            resp = ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "portfolio:1tokens")
        self.assertEqual(sent[0][0], "portfolio")
        holding = sent[0][1]["holdings"][0]
        self.assertEqual(holding["addr"], "token-1")
        self.assertEqual(holding["chain"], "solana")
        self.assertEqual(holding["balance_raw"], "")
        self.assertEqual(sent[0][1]["holding_source"], "getUserByAssetsId.tokens")
        self.assertEqual(
            sent[0][1]["wallets"],
            [
                {
                    "assets_id": "",
                    "assets_name": "",
                    "status": "",
                    "addresses": [],
                }
            ],
        )
        self.assertEqual(conn.ave_state["screen"], "portfolio")

    async def test_ave_portfolio_prefers_machine_raw_balance_for_sell_amount(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools._trade_get", return_value={
                 "data": [
                     {
                        "chain": "solana",
                         "tokens": [
                             {
                                 "address": "token-1",
                                 "balance": "1.5",
                                 "rawBalance": "1500000",
                                 "decimals": 6,
                                 "symbol": "BONK",
                             }
                         ],
                     }
                 ]
             }), \
             patch("plugins_func.functions.ave_tools._data_post", return_value={
                 "data": {
                     "token-1-solana": {"current_price_usd": "0.5"}
                 }
             }), \
             patch("plugins_func.functions.ave_tools.os.environ.get", return_value="wallet-1"):
            ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        holding = sent[0][1]["holdings"][0]
        self.assertEqual(holding["balance"], "1.5000")
        self.assertEqual(holding["balance_raw"], "1500000")

    async def test_ave_portfolio_scales_raw_balance_with_decimals_when_display_missing(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools._trade_get", return_value={
                 "data": [
                     {
                        "chain": "solana",
                         "tokens": [
                             {
                                 "address": "token-1",
                                 "rawBalance": "1500000",
                                 "decimals": 6,
                                 "symbol": "BONK",
                             }
                         ],
                     }
                 ]
             }), \
             patch("plugins_func.functions.ave_tools._data_post", return_value={
                 "data": {
                     "token-1-solana": {"current_price_usd": "2"}
                 }
             }), \
             patch("plugins_func.functions.ave_tools.os.environ.get", return_value="wallet-1"):
            ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        holding = sent[0][1]["holdings"][0]
        self.assertEqual(holding["balance"], "1.5000")
        self.assertEqual(holding["balance_raw"], "1500000")
        self.assertEqual(holding["value_usd"], "$3")

    async def test_ave_portfolio_skips_raw_only_holding_without_decimals(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools._trade_get", return_value={
                 "data": [
                     {
                        "chain": "solana",
                         "tokens": [
                             {
                                 "address": "token-1",
                                 "rawBalance": "1500000",
                                 "symbol": "BONK",
                             }
                         ],
                     }
                 ]
             }), \
             patch("plugins_func.functions.ave_tools._data_post", return_value={"data": {}}), \
             patch("plugins_func.functions.ave_tools.os.environ.get", return_value="wallet-1"):
            resp = ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "portfolio:0tokens")
        payload = sent[0][1]
        self.assertEqual(payload["holdings"], [])
        self.assertEqual(payload["total_usd"], "$0")

    async def test_ave_portfolio_skips_raw_only_holding_with_invalid_decimals(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools._trade_get", return_value={
                 "data": [
                     {
                        "chain": "solana",
                         "tokens": [
                             {
                                 "address": "token-1",
                                 "rawBalance": "1500000",
                                 "decimals": "bad",
                                 "symbol": "BONK",
                             }
                         ],
                     }
                 ]
             }), \
             patch("plugins_func.functions.ave_tools._data_post", return_value={"data": {}}), \
             patch("plugins_func.functions.ave_tools.os.environ.get", return_value="wallet-1"):
            resp = ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "portfolio:0tokens")
        payload = sent[0][1]
        self.assertEqual(payload["holdings"], [])
        self.assertEqual(payload["total_usd"], "$0")

    async def test_ave_portfolio_aggregates_duplicate_holdings_for_same_token(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools._trade_get", return_value={
                 "data": [
                     {
                        "chain": "solana",
                         "tokens": [
                             {
                                 "address": "token-1",
                                 "balance": "1.25",
                                 "rawBalance": "1250000",
                                 "decimals": 6,
                                 "symbol": "BONK",
                             },
                             {
                                 "address": "token-1",
                                 "balance": "0.75",
                                 "rawBalance": "750000",
                                 "decimals": 6,
                                 "symbol": "BONK",
                             }
                         ],
                     }
                 ]
             }), \
             patch("plugins_func.functions.ave_tools._data_post", return_value={
                 "data": {
                     "token-1-solana": {"current_price_usd": "2"}
                 }
             }), \
             patch("plugins_func.functions.ave_tools.os.environ.get", return_value="wallet-1"):
            resp = ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "portfolio:1tokens")
        payload = sent[0][1]
        self.assertEqual(len(payload["holdings"]), 1)
        self.assertEqual(payload["holdings"][0]["balance"], "2.0000")
        self.assertEqual(payload["holdings"][0]["balance_raw"], "2000000")
        self.assertEqual(payload["total_usd"], "$4")

    async def test_ave_portfolio_without_wallet_id_uses_simulator_empty_payload(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        with patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display), \
             patch("plugins_func.functions.ave_tools.os.environ.get", return_value=""):
            resp = ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "no_wallet_sim")
        self.assertEqual(sent[0][0], "portfolio")
        self.assertEqual(sent[0][1]["holdings"], [])
        self.assertEqual(sent[0][1]["total_usd"], "$0")
        self.assertEqual(conn.ave_state["screen"], "portfolio")


if __name__ == "__main__":
    unittest.main()
