import asyncio
import unittest
from unittest.mock import MagicMock, patch

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
        self.websocket = MagicMock()


class PortfolioSurfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_portfolio_no_wallet_branch_uses_na_pnl(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _env_get(key, default=None):
            if key == "AVE_PROXY_WALLET_ID":
                return ""
            return default

        with patch("plugins_func.functions.ave_tools.os.environ.get", side_effect=_env_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            resp = ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "no_wallet_sim")
        self.assertEqual(sent[0][0], "portfolio")
        payload = sent[0][1]
        self.assertEqual(payload["holdings"], [])
        self.assertEqual(payload["total_usd"], "$0")
        self.assertEqual(payload["pnl"], "N/A")
        self.assertEqual(payload["pnl_pct"], "N/A")

    async def test_portfolio_empty_wallet_branch_uses_na_pnl(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _env_get(key, default=None):
            if key == "AVE_PROXY_WALLET_ID":
                return "wallet-empty"
            return default

        def _fake_trade_get(path, params=None):
            return {"data": []}

        with patch("plugins_func.functions.ave_tools.os.environ.get", side_effect=_env_get), \
             patch("plugins_func.functions.ave_tools._trade_get", side_effect=_fake_trade_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            resp = ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "empty_portfolio")
        self.assertEqual(sent[0][0], "portfolio")
        payload = sent[0][1]
        self.assertEqual(payload["holdings"], [])
        self.assertEqual(payload["total_usd"], "$0")
        self.assertEqual(payload["pnl"], "N/A")
        self.assertEqual(payload["pnl_pct"], "N/A")

    async def test_portfolio_empty_wallet_branch_explains_na_pnl_and_wallet_source(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _env_get(key, default=None):
            if key == "AVE_PROXY_WALLET_ID":
                return "wallet-empty"
            return default

        def _fake_trade_get(path, params=None):
            return {"data": []}

        with patch("plugins_func.functions.ave_tools.os.environ.get", side_effect=_env_get), \
             patch("plugins_func.functions.ave_tools._trade_get", side_effect=_fake_trade_get), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        payload = sent[0][1]
        self.assertEqual(payload["pnl"], "N/A")
        self.assertEqual(payload["pnl_reason"], "Cost basis unavailable")
        self.assertEqual(payload["wallet_source_label"], "Proxy wallet")

    async def test_portfolio_missing_cost_basis_renders_pnl_as_na_not_blank(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _env_get(key, default=None):
            if key == "AVE_PROXY_WALLET_ID":
                return "wallet-portfolio"
            return default

        def _fake_trade_get(path, params=None):
            # Wallet schema is irrelevant for this test; holdings come from the collector.
            return {"data": [{"assetsId": "wallet-portfolio", "addressList": []}]}

        def _fake_collect_portfolio_holdings(wallets):
            return (
                ["0xToken-base", "So11111111111111111111111111111111111111112-solana"],
                {
                    "0xToken-base": {
                        "symbol": "TKN",
                        "balance_raw": 2.0,
                        "balance_raw_display": "2",
                        "chain": "base",
                        "addr": "0xToken",
                    },
                    "So11111111111111111111111111111111111111112-solana": {
                        "symbol": "SOL",
                        "balance_raw": 1.0,
                        "balance_raw_display": "1",
                        "chain": "solana",
                        "addr": "So11111111111111111111111111111111111111112",
                    },
                },
                ["getUserByAssetsId.addressList"],
            )

        def _fake_data_post(path, payload):
            # Prices are not the focus; provide deterministic values so total_usd is non-zero.
            return {
                "data": {
                    "0xToken-base": {"current_price_usd": 5.0},
                    "So11111111111111111111111111111111111111112-solana": {"current_price_usd": 100.0},
                }
            }

        with patch("plugins_func.functions.ave_tools.os.environ.get", side_effect=_env_get), \
             patch("plugins_func.functions.ave_tools._trade_get", side_effect=_fake_trade_get), \
             patch("plugins_func.functions.ave_tools._collect_portfolio_holdings", side_effect=_fake_collect_portfolio_holdings), \
             patch("plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            resp = ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "portfolio:2tokens")
        self.assertEqual(sent[0][0], "portfolio")
        payload = sent[0][1]

        # Frozen policy: do not fabricate cost basis / P&L. Use neutral N/A.
        self.assertEqual(payload["pnl"], "N/A")
        self.assertEqual(payload["pnl_pct"], "N/A")
        self.assertEqual(len(payload["holdings"]), 2)
        for row in payload["holdings"]:
            self.assertEqual(row["pnl_pct"], "N/A")
            self.assertIsNone(row["pnl_positive"])

    async def test_portfolio_refresh_restores_prior_selected_holding_cursor(self):
        loop = asyncio.get_running_loop()
        conn = _FakeConn(loop)
        conn.ave_state = {
            "screen": "spotlight",
            "nav_from": "portfolio",
            "portfolio_cursor": 1,
            "current_token": {"addr": "token-b", "chain": "solana", "symbol": "BBB"},
        }
        sent = []

        async def _fake_send_display(conn, screen, payload):
            sent.append((screen, payload))

        def _env_get(key, default=None):
            if key == "AVE_PROXY_WALLET_ID":
                return "wallet-portfolio"
            return default

        def _fake_trade_get(path, params=None):
            return {"data": [{"assetsId": "wallet-portfolio", "addressList": []}]}

        def _fake_collect_portfolio_holdings(wallets):
            return (
                ["token-a-solana", "token-b-solana"],
                {
                    "token-a-solana": {
                        "symbol": "AAA",
                        "display_balance_decimal": 10.0,
                        "chain": "solana",
                        "addr": "token-a",
                    },
                    "token-b-solana": {
                        "symbol": "BBB",
                        "display_balance_decimal": 1.0,
                        "chain": "solana",
                        "addr": "token-b",
                    },
                },
                ["getUserByAssetsId.addressList"],
            )

        def _fake_data_post(path, payload):
            return {
                "data": {
                    "token-a-solana": {"current_price_usd": 2.0},
                    "token-b-solana": {"current_price_usd": 1.0},
                }
            }

        with patch("plugins_func.functions.ave_tools.os.environ.get", side_effect=_env_get), \
             patch("plugins_func.functions.ave_tools._trade_get", side_effect=_fake_trade_get), \
             patch("plugins_func.functions.ave_tools._collect_portfolio_holdings", side_effect=_fake_collect_portfolio_holdings), \
             patch("plugins_func.functions.ave_tools._data_post", side_effect=_fake_data_post), \
             patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
            resp = ave_tools.ave_portfolio(conn)
            await asyncio.sleep(0)

        self.assertEqual(resp.result, "portfolio:2tokens")
        payload = sent[0][1]
        self.assertEqual(payload.get("cursor"), 1)
        self.assertEqual(conn.ave_state.get("portfolio_cursor"), 1)

    def test_screen_portfolio_explanation_summary_surfaces_reason_and_wallet_source(self):
        import os
        import subprocess
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]

        display_json = (
            '{"screen":"portfolio","data":{"holdings":[],"total_usd":"$0",'
            '"pnl":"N/A","pnl_pct":"N/A","pnl_reason":"Cost basis unavailable",'
            '"wallet_source_label":"Proxy wallet"}}'
        )
        display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_PORTFOLIO
{verifier_prefix}

#ifndef LV_OPA_TRANSP
#define LV_OPA_TRANSP 0
#endif


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

lv_obj_t *screen_portfolio__verify_get_top_pnl_label(void);
lv_obj_t *screen_portfolio__verify_get_summary_label(void);

#include "{repo_root / 'shared/ave_screens/screen_portfolio.c'}"

int main(void)
{{
    screen_portfolio_show("{display_json_c}");

    lv_obj_t *top_pnl = screen_portfolio__verify_get_top_pnl_label();
    lv_obj_t *summary = screen_portfolio__verify_get_summary_label();

    if (!top_pnl || strcmp(top_pnl->text, "N/A") != 0) {{
        fprintf(stderr, "top pnl expected N/A, got: %s\\n", top_pnl ? top_pnl->text : "<null>");
        return 2;
    }}
    if (!summary || strstr(summary->text, "P&L summary unavailable") == NULL) {{
        fprintf(stderr, "summary missing pnl reason: %s\\n", summary ? summary->text : "<null>");
        return 3;
    }}
    if (strstr(summary->text, "Proxy wallet") != NULL) {{
        fprintf(stderr, "summary should not expose wallet source: %s\\n", summary ? summary->text : "<null>");
        return 4;
    }}
    if (strstr(summary->text, "·") != NULL) {{
        fprintf(stderr, "summary should not contain bullet separator: %s\\n", summary ? summary->text : "<null>");
        return 5;
    }}
    return 0;
}}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_portfolio_explanation_summary.c"
            binary = tmpdir_path / "verify_portfolio_explanation_summary"
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    str(repo_root / "shared/ave_screens/ave_json_utils.c"),
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

    def test_screen_portfolio_first_row_starts_below_header_band(self):
        import os
        import subprocess
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]

        display_json = (
            '{"screen":"portfolio","data":{"holdings":[],"total_usd":"$0",'
            '"pnl":"N/A","pnl_pct":"N/A","pnl_reason":"Cost basis unavailable",'
            '"wallet_source_label":"Proxy wallet"}}'
        )
        display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_PORTFOLIO
{verifier_prefix}

#ifndef LV_OPA_TRANSP
#define LV_OPA_TRANSP 0
#endif


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

#include "{repo_root / 'shared/ave_screens/screen_portfolio.c'}"

int main(void)
{{
    screen_portfolio_show("{display_json_c}");

    if (!s_row_bg[0]) {{
        fprintf(stderr, "first portfolio row missing\\n");
        return 2;
    }}
    if (s_row_bg[0]->y < 38) {{
        fprintf(stderr, "first portfolio row overlaps header band, y=%d\\n", s_row_bg[0]->y);
        return 3;
    }}
    return 0;
}}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_portfolio_header_spacing.c"
            binary = tmpdir_path / "verify_portfolio_header_spacing"
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    str(repo_root / "shared/ave_screens/ave_json_utils.c"),
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

    def test_screen_portfolio_locks_value_and_pnl_columns_to_fixed_widths(self):
        import os
        import subprocess
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]

        display_json = (
            '{"screen":"portfolio","data":{"holdings":['
            '{"symbol":"BTC","addr":"0xbtc","chain":"eth","value_usd":"$12345.67","pnl_pct":"+12.34%"}'
            '],"total_usd":"$12345.67","pnl":"N/A","pnl_pct":"N/A"}}'
        )
        display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_PORTFOLIO
{verifier_prefix}

#ifndef LV_OPA_TRANSP
#define LV_OPA_TRANSP 0
#endif
#ifndef LV_TEXT_ALIGN_LEFT
#define LV_TEXT_ALIGN_LEFT 0
#define LV_TEXT_ALIGN_CENTER 1
#define LV_TEXT_ALIGN_RIGHT 2
#endif

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

#include "{repo_root / 'shared/ave_screens/screen_portfolio.c'}"

int main(void)
{{
    screen_portfolio_show("{display_json_c}");

    if (!s_row_val[0] || s_row_val[0]->width < 70) {{
        fprintf(stderr, "value column width too small: %d\\n", s_row_val[0] ? s_row_val[0]->width : -1);
        return 2;
    }}
    if (s_row_val[0]->text_align != LV_TEXT_ALIGN_RIGHT) {{
        fprintf(stderr, "value column not right aligned: %d\\n", s_row_val[0]->text_align);
        return 3;
    }}
    if (!s_row_pnl[0] || s_row_pnl[0]->width < 44) {{
        fprintf(stderr, "pnl column width too small: %d\\n", s_row_pnl[0] ? s_row_pnl[0]->width : -1);
        return 4;
    }}
    if (s_row_pnl[0]->text_align != LV_TEXT_ALIGN_RIGHT) {{
        fprintf(stderr, "pnl column not right aligned: %d\\n", s_row_pnl[0]->text_align);
        return 5;
    }}
    return 0;
}}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_portfolio_fixed_columns.c"
            binary = tmpdir_path / "verify_portfolio_fixed_columns"
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    str(repo_root / "shared/ave_screens/ave_json_utils.c"),
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

    def test_screen_portfolio_skips_missing_symbol_rows_instead_of_rendering_placeholder(self):
        import os
        import subprocess
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]

        display_json = (
            '{"screen":"portfolio","data":{"holdings":['
            '{"addr":"0xabc","chain":"bsc","value_usd":"--","pnl_pct":"N/A"}'
            '],"total_usd":"$0","pnl":"N/A","pnl_pct":"N/A"}}'
        )
        display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_PORTFOLIO
{verifier_prefix}

#ifndef LV_OPA_TRANSP
#define LV_OPA_TRANSP 0
#endif


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

#include "{repo_root / 'shared/ave_screens/screen_portfolio.c'}"

int main(void)
{{
    screen_portfolio_show("{display_json_c}");

    if (s_row_sym[0] && s_row_sym[0]->text[0] != '\\0') {{
        fprintf(stderr, "missing-symbol row should remain empty, got: %s\\n", s_row_sym[0]->text);
        return 2;
    }}
    if (s_row_val[0] && s_row_val[0]->text[0] != '\\0') {{
        fprintf(stderr, "missing-symbol row value should remain empty, got: %s\\n", s_row_val[0]->text);
        return 3;
    }}
    return 0;
}}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_portfolio_skip_missing_symbol.c"
            binary = tmpdir_path / "verify_portfolio_skip_missing_symbol"
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    str(repo_root / "shared/ave_screens/ave_json_utils.c"),
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

    def test_screen_portfolio_pnl_fallback_renders_na_in_top_bar_and_summary(self):
        """Renderer-level contract: if portfolio-level pnl/pnl_pct fields are absent, show N/A (not blank/--)."""
        import os
        import subprocess
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]

        # Deliberately omit portfolio-level pnl/pnl_pct fields.
        display_json = (
            '{"screen":"portfolio","data":{"holdings":[],'
            '"total_usd":"$0"}}'
        )
        display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_PORTFOLIO
{verifier_prefix}

/* screen_portfolio.c doesn't depend on these today, but keep compatibility with
 * newer LVGL usage patterns across screens. */
#ifndef LV_OPA_TRANSP
#define LV_OPA_TRANSP 0
#endif


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

lv_obj_t *screen_portfolio__verify_get_top_pnl_label(void);
lv_obj_t *screen_portfolio__verify_get_summary_label(void);

#include "{repo_root / 'shared/ave_screens/screen_portfolio.c'}"

int main(void)
{{
    screen_portfolio_show("{display_json_c}");

    lv_obj_t *top_pnl = screen_portfolio__verify_get_top_pnl_label();
    lv_obj_t *summary = screen_portfolio__verify_get_summary_label();

    if (!top_pnl || strcmp(top_pnl->text, "N/A") != 0) {{
        fprintf(stderr, "top pnl expected N/A, got: %s\\n", top_pnl ? top_pnl->text : "<null>");
        return 2;
    }}
    if (!summary || strstr(summary->text, "N/A") == NULL) {{
        fprintf(stderr, "summary expected to contain N/A, got: %s\\n", summary ? summary->text : "<null>");
        return 3;
    }}
    if (strstr(summary->text, "--") != NULL) {{
        fprintf(stderr, "summary unexpectedly contains --: %s\\n", summary->text);
        return 4;
    }}
    return 0;
}}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_portfolio_pnl_fallback.c"
            binary = tmpdir_path / "verify_portfolio_pnl_fallback"
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    str(repo_root / "shared/ave_screens/ave_json_utils.c"),
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

    def test_screen_portfolio_pnl_fallback_does_not_leak_holding_pct_into_summary(self):
        """Renderer-level contract: missing portfolio-level pnl/pnl_pct stays neutral, even if holdings include pnl_pct."""
        import os
        import subprocess
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]

        # Deliberately omit portfolio-level pnl/pnl_pct fields, but include a holding with pnl_pct.
        display_json = (
            '{"screen":"portfolio","data":{"holdings":['
            '{"symbol":"TKN","value_usd":"$10","pnl_pct":"+12.34%","pnl_positive":true}'
            '],"total_usd":"$10"}}'
        )
        display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_PORTFOLIO
{verifier_prefix}

#ifndef LV_OPA_TRANSP
#define LV_OPA_TRANSP 0
#endif


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

lv_obj_t *screen_portfolio__verify_get_top_pnl_label(void);
lv_obj_t *screen_portfolio__verify_get_summary_label(void);

#include "{repo_root / 'shared/ave_screens/screen_portfolio.c'}"

int main(void)
{{
    screen_portfolio_show("{display_json_c}");

    lv_obj_t *top_pnl = screen_portfolio__verify_get_top_pnl_label();
    lv_obj_t *summary = screen_portfolio__verify_get_summary_label();

    if (!top_pnl || strcmp(top_pnl->text, "N/A") != 0) {{
        fprintf(stderr, "top pnl expected N/A, got: %s\\n", top_pnl ? top_pnl->text : "<null>");
        return 2;
    }}
    if (!summary || strcmp(summary->text, "P&L: N/A (N/A)") != 0) {{
        fprintf(stderr, "summary expected exactly P&L: N/A (N/A), got: %s\\n", summary ? summary->text : "<null>");
        return 3;
    }}
    return 0;
}}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_portfolio_pnl_no_leak.c"
            binary = tmpdir_path / "verify_portfolio_pnl_no_leak"
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    str(repo_root / "shared/ave_screens/ave_json_utils.c"),
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

    def test_screen_portfolio_empty_reset_clears_stale_selection_and_sell_action(self):
        import os
        import subprocess
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        display_json = (
            '{"screen":"portfolio","data":{"holdings":['
            '{"symbol":"BONK","addr":"token-1","chain":"solana","balance_raw":"1500000","value_usd":"$1"}'
            '],"total_usd":"$1"}}'
        )
        display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_PORTFOLIO
{verifier_prefix}

#ifndef LV_OPA_TRANSP
#define LV_OPA_TRANSP 0
#endif


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

#include "{repo_root / 'shared/ave_screens/screen_portfolio.c'}"

int main(void)
{{
    char ctx[256];

    screen_portfolio_show("{display_json_c}");
    screen_portfolio_show("{{}}");

    if (screen_portfolio_get_selected_context_json(ctx, sizeof(ctx))) {{
        fprintf(stderr, "stale portfolio context survived empty reset: %s\\n", ctx);
        return 2;
    }}

    clear_last_json();
    screen_portfolio_key(AVE_KEY_X);
    if (g_last_json[0] != '\\0') {{
        fprintf(stderr, "stale sell action emitted after empty reset: %s\\n", g_last_json);
        return 3;
    }}
    return 0;
}}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_portfolio_empty_reset.c"
            binary = tmpdir_path / "verify_portfolio_empty_reset"
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    str(repo_root / "shared/ave_screens/ave_json_utils.c"),
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

    def test_screen_portfolio_applies_payload_cursor_to_selected_context(self):
        import os
        import subprocess
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        display_json = (
            '{"screen":"portfolio","data":{"cursor":1,"holdings":['
            '{"symbol":"AAA","addr":"token-a","chain":"solana","balance_raw":"1","value_usd":"$10"},'
            '{"symbol":"BBB","addr":"token-b","chain":"solana","balance_raw":"2","value_usd":"$9"}'
            '],"total_usd":"$19"}}'
        )
        display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_PORTFOLIO
{verifier_prefix}

#ifndef LV_OPA_TRANSP
#define LV_OPA_TRANSP 0
#endif


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

#include "{repo_root / 'shared/ave_screens/screen_portfolio.c'}"

int main(void)
{{
    char ctx[256];
    screen_portfolio_show("{display_json_c}");
    if (!screen_portfolio_get_selected_context_json(ctx, sizeof(ctx))) {{
        fprintf(stderr, "missing selected context\\n");
        return 2;
    }}
    if (strstr(ctx, "\\"cursor\\":1") == NULL) {{
        fprintf(stderr, "expected cursor 1 in context, got: %s\\n", ctx);
        return 3;
    }}
    if (strstr(ctx, "\\"addr\\":\\"token-b\\"") == NULL) {{
        fprintf(stderr, "expected token-b selected, got: %s\\n", ctx);
        return 4;
    }}
    return 0;
}}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_portfolio_cursor_restore.c"
            binary = tmpdir_path / "verify_portfolio_cursor_restore"
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    str(repo_root / "shared/ave_screens/ave_json_utils.c"),
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

    def test_screen_portfolio_sell_without_machine_raw_amount_fails_closed(self):
        import os
        import subprocess
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        display_json = (
            '{"screen":"portfolio","data":{"holdings":['
            '{"symbol":"BONK","addr":"token-1","chain":"solana","balance":"1.5","value_usd":"$1"}'
            '],"total_usd":"$1"}}'
        )
        display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_PORTFOLIO
{verifier_prefix}

#ifndef LV_OPA_TRANSP
#define LV_OPA_TRANSP 0
#endif


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

#include "{repo_root / 'shared/ave_screens/screen_portfolio.c'}"

int main(void)
{{
    screen_portfolio_show("{display_json_c}");
    clear_last_json();
    screen_portfolio_key(AVE_KEY_X);
    if (g_last_json[0] != '\\0') {{
        fprintf(stderr, "portfolio sell should fail closed without machine raw amount: %s\\n", g_last_json);
        return 2;
    }}
    return 0;
}}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_portfolio_sell_missing_raw.c"
            binary = tmpdir_path / "verify_portfolio_sell_missing_raw"
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    str(repo_root / "shared/ave_screens/ave_json_utils.c"),
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

    def test_screen_portfolio_sell_with_truncated_machine_raw_amount_fails_closed(self):
        import os
        import subprocess
        import tempfile
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        long_raw = "1234567890" * 20
        display_json = (
            '{"screen":"portfolio","data":{"holdings":['
            '{"symbol":"BONK","addr":"token-1","chain":"solana","balance_raw":"'
            + long_raw +
            '","value_usd":"$1"}],"total_usd":"$1"}}'
        )
        display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_PORTFOLIO
{verifier_prefix}

#ifndef LV_OPA_TRANSP
#define LV_OPA_TRANSP 0
#endif


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

#include "{repo_root / 'shared/ave_screens/screen_portfolio.c'}"

int main(void)
{{
    screen_portfolio_show("{display_json_c}");
    clear_last_json();
    screen_portfolio_key(AVE_KEY_X);
    if (g_last_json[0] != '\\0') {{
        fprintf(stderr, "portfolio sell should fail closed on truncated raw amount: %s\\n", g_last_json);
        return 2;
    }}
    return 0;
}}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_portfolio_sell_truncated_raw.c"
            binary = tmpdir_path / "verify_portfolio_sell_truncated_raw"
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    str(repo_root / "shared/ave_screens/ave_json_utils.c"),
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
