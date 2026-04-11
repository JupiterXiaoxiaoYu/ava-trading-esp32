import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from core.handle.textHandler.keyActionHandler import KeyActionHandler
from core.handle.textHandler.listenMessageHandler import ListenTextMessageHandler
from core.providers.asr.dto.dto import InterfaceType


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


def _build_disambiguation_listen_harness():
    repo_root = Path(__file__).resolve().parents[3]
    include_dir = repo_root / "simulator/mock/json_verify_include"
    manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
    display_json = (
        '{"screen":"disambiguation","data":{"cursor":1,"items":['
        '{"token_id":"So111...","chain":"solana","symbol":"PEPE"},'
        '{"token_id":"0xabc...","chain":"base","symbol":"PEPE"}'
        "]}}"
    )
    display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')

    screen_disambiguation_src = repo_root / "shared/ave_screens/screen_disambiguation.c"
    extra_sources = []
    extra_ldflags = []
    if screen_disambiguation_src.exists():
        extra_sources.append(screen_disambiguation_src)
        extra_ldflags.append("-DHAVE_SCREEN_DISAMBIGUATION")

    harness_source = """
#include <stdio.h>
#include <string.h>

#include "ave_screen_manager.h"

void ave_send_json(const char *json) { (void)json; }
void screen_feed_show(const char *json_data) { (void)json_data; }
void screen_feed_reveal(void) { }
void screen_feed_key(int key) { (void)key; }
bool screen_feed_should_ignore_live_push(void) { (void)0; return false; }
int screen_feed_get_selected_context_json(char *out, size_t out_n) { (void)out; (void)out_n; return 0; }
void screen_explorer_show(const char *json_data) { (void)json_data; }
void screen_explorer_key(int key) { (void)key; }
int screen_explorer_get_selected_context_json(char *out, size_t out_n) { (void)out; (void)out_n; return 0; }
void screen_browse_show(const char *json_data) { (void)json_data; }
void screen_browse_show_placeholder(const char *mode) { (void)mode; }
void screen_browse_reveal(void) { }
void screen_browse_key(int key) { (void)key; }
int screen_browse_get_selected_context_json(char *out, size_t out_n) { (void)out; (void)out_n; return 0; }
void screen_spotlight_show(const char *json_data) { (void)json_data; }
void screen_spotlight_key(int key) { (void)key; }
void screen_spotlight_cancel_back_timer(void) { }
int screen_spotlight_get_selected_context_json(char *out, size_t out_n) { (void)out; (void)out_n; return 0; }
void screen_confirm_show(const char *json_data) { (void)json_data; }
void screen_confirm_key(int key) { (void)key; }
void screen_confirm_cancel_timers(void) { }
int screen_confirm_get_selected_context_json(char *out, size_t out_n) { (void)out; (void)out_n; return 0; }
void screen_limit_confirm_show(const char *json_data) { (void)json_data; }
void screen_limit_confirm_key(int key) { (void)key; }
void screen_limit_confirm_cancel_timers(void) { }
int screen_limit_confirm_get_selected_context_json(char *out, size_t out_n) { (void)out; (void)out_n; return 0; }
void screen_result_show(const char *json_data) { (void)json_data; }
void screen_result_key(int key) { (void)key; }
void screen_result_cancel_timers(void) { }
int screen_result_get_selected_context_json(char *out, size_t out_n) { (void)out; (void)out_n; return 0; }
void screen_portfolio_show(const char *json_data) { (void)json_data; }
void screen_portfolio_key(int key) { (void)key; }
void screen_portfolio_cancel_back_timer(void) { }
int screen_portfolio_get_selected_context_json(char *out, size_t out_n) { (void)out; (void)out_n; return 0; }
void screen_notify_show(const char *json_data) { (void)json_data; }
bool screen_notify_is_visible(void) { return false; }
void screen_notify_key(int key) { (void)key; }

#if !defined(HAVE_SCREEN_DISAMBIGUATION)
void screen_disambiguation_show(const char *json_data) { (void)json_data; }
void screen_disambiguation_key(int key) { (void)key; }
void screen_disambiguation_cancel_timers(void) { }
int screen_disambiguation_get_selected_context_json(char *out, size_t out_n) { (void)out; (void)out_n; return 0; }
#endif

int main(void)
{
    char out[4096];
    ave_sm_handle_json("{display_json_c}");
    if (!ave_sm_build_listen_detect_json("看这个", out, sizeof(out))) {
        fprintf(stderr, "listen payload build failed\\n");
        return 2;
    }
    printf("%s", out);
    return 0;
}
"""

    harness_source = harness_source.replace("{display_json_c}", display_json_c)

    return harness_source, include_dir, manager_src, tuple(extra_sources), tuple(extra_ldflags)

class SurfaceInputSyncTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _common_screen_sources(repo_root: Path):
        return (
            repo_root / "shared/ave_screens/ave_json_utils.c",
            repo_root / "simulator/mock/ave_screen_harness_support.c",
        )

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
        return conn

    def _assert_real_selection_emitter_missing_chain_fails_closed(
        self,
        *,
        screen_macro,
        screen_source,
        display_json,
        extra_sources=(),
        extra_ldflags=(),
    ):
        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        common_sources = self._common_screen_sources(repo_root)
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        display_json_c = (
            display_json.replace("\\", "\\\\").replace('"', '\\"')
        )
        harness_source = f"""
#define {screen_macro}
{verifier_prefix}

/* json_verify_include/lvgl/lvgl.h is intentionally minimal. Keep forward-compat
 * with production screen code by stubbing newer LVGL constants/APIs here. */
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

void screen_feed_show(const char *json_data) {{ (void)json_data; }}
void screen_feed_reveal(void) {{ }}
void screen_feed_key(int key) {{ (void)key; }}
bool screen_feed_should_ignore_live_push(void) {{ return false; }}
int screen_feed_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_explorer_show(const char *json_data) {{ (void)json_data; }}
void screen_explorer_key(int key) {{ (void)key; }}
int screen_explorer_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_browse_show(const char *json_data) {{ (void)json_data; }}
void screen_browse_show_placeholder(const char *mode) {{ (void)mode; }}
void screen_browse_reveal(void) {{ }}
void screen_browse_key(int key) {{ (void)key; }}
int screen_browse_get_selected_context_json(char *out, size_t out_n)
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
    char out[1024];

    ave_sm_handle_json("{display_json_c}");
    if (!ave_sm_build_listen_detect_json("watch this", out, sizeof(out))) {{
        fprintf(stderr, "build failed\\n");
        return 2;
    }}
    if (strstr(out, "\\"selection\\"")) {{
        fprintf(stderr, "unexpected selection for missing-chain payload: %s\\n", out);
        return 3;
    }}
    if (strstr(out, "\\"chain\\":\\"solana\\"")) {{
        fprintf(stderr, "unexpected synthetic solana chain: %s\\n", out);
        return 4;
    }}
    return 0;
}}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_missing_chain_selection.c"
            binary = tmpdir_path / "verify_missing_chain_selection"
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    *[str(source) for source in common_sources],
                    *[str(source) for source in extra_sources],
                    *extra_ldflags,
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

    def _compile_and_run_c_harness(
        self,
        harness_source,
        include_dir,
        manager_src,
        *,
        extra_sources=(),
        extra_ldflags=(),
        binary_name="verify_feed_explore_overlay",
    ):
        repo_root = Path(__file__).resolve().parents[3]
        common_sources = self._common_screen_sources(repo_root)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / f"{binary_name}.c"
            binary_path = tmpdir_path / binary_name
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    *[str(source) for source in common_sources],
                    *[str(source) for source in extra_sources],
                    *extra_ldflags,
                    "-o",
                    str(binary_path),
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
                [str(binary_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                run_result.returncode,
                0,
                msg=run_result.stdout + run_result.stderr,
            )
            return run_result.stdout

    def _assert_real_key_action_missing_chain_fails_closed(
        self,
        *,
        screen_name,
        screen_source,
        display_json,
        key_steps,
        extra_sources=(),
        extra_ldflags=(),
    ):
        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')
        screen_macro = {
            "feed": "VERIFY_FEED",
            "portfolio": "VERIFY_PORTFOLIO",
            "spotlight": "VERIFY_SPOTLIGHT",
        }.get(screen_name, "")

        harness_source = f"""
{f"#define {screen_macro}" if screen_macro else ""}
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

{"void screen_disambiguation_show(const char *json_data) { (void)json_data; }\nvoid screen_disambiguation_key(int key) { (void)key; }\nvoid screen_disambiguation_cancel_timers(void) { }\nint screen_disambiguation_get_selected_context_json(char *out, size_t out_n) { (void)out; (void)out_n; return 0; }" if screen_name != "disambiguation" else ""}

int main(void)
{{
    ave_sm_handle_json("{display_json_c}");
    clear_last_json();
    {key_steps}
    if (g_last_json[0] != '\\0') {{
        fprintf(stderr, "unexpected action emitted with missing chain: %s\\n", g_last_json);
        return 3;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name=f"verify_{screen_name}_missing_chain_action",
            extra_sources=(screen_source, *extra_sources),
            extra_ldflags=(
                "-DLV_OPA_TRANSP=0",
                "-DLV_TEXT_ALIGN_LEFT=0",
                "-DLV_TEXT_ALIGN_CENTER=1",
                "-DLV_TEXT_ALIGN_RIGHT=2",
                *extra_ldflags,
            ),
        )

    def _verify_disambiguation_selection_payload(self):
        harness_source, include_dir, manager_src, extra_sources, extra_ldflags = _build_disambiguation_listen_harness()
        payload_json = self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_disambiguation_selection",
            extra_sources=extra_sources,
            extra_ldflags=extra_ldflags,
        )
        payload = json.loads(payload_json.strip())
        selection = payload.get("selection")
        # Task 1's fail-closed contract is stricter than "no top-level token_id":
        # DISAMBIGUATION listen payloads may only expose inert screen/cursor
        # metadata, never nested trusted token aliases such as selection.token.
        self.assertEqual(
            selection,
            {
                "screen": "disambiguation",
                "cursor": 1,
            },
        )

    def _assert_real_feed_overlay_omits_trusted_selection_in_listen_payload(
        self,
        *,
        key_sequence,
        binary_name,
        failure_label,
    ):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        feed_source = repo_root / "shared/ave_screens/screen_feed.c"
        explorer_source = repo_root / "shared/ave_screens/screen_explorer.c"
        browse_source = repo_root / "shared/ave_screens/screen_browse.c"
        verifier_prefix = (repo_root / "simulator/mock/verify_ave_json_payloads.c").read_text(
            encoding="utf-8"
        ).split("#if defined(VERIFY_FEED)", 1)[0]
        key_steps = "\n    ".join(
            f"ave_sm_key_press({key_name});" for key_name in key_sequence
        )
        harness_source = f"""
#define VERIFY_FEED
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

void screen_feed_show(const char *json_data) {{ (void)json_data; }}
void screen_feed_reveal(void) {{ }}
void screen_feed_key(int key) {{ (void)key; }}
bool screen_feed_should_ignore_live_push(void) {{ return false; }}
int screen_feed_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_explorer_show(const char *json_data) {{ (void)json_data; }}
void screen_explorer_key(int key) {{ (void)key; }}
int screen_explorer_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_browse_show(const char *json_data) {{ (void)json_data; }}
void screen_browse_show_placeholder(const char *mode) {{ (void)mode; }}
void screen_browse_reveal(void) {{ }}
void screen_browse_key(int key) {{ (void)key; }}
int screen_browse_get_selected_context_json(char *out, size_t out_n)
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

#include "{explorer_source}"

int main(void)
{{
    char out[1024];

    ave_sm_handle_json("{{\\"screen\\":\\"feed\\",\\"data\\":{{\\"source_label\\":\\"TRENDING\\",\\"tokens\\":[{{\\"token_id\\":\\"feed-1\\",\\"chain\\":\\"solana\\",\\"symbol\\":\\"BONK\\",\\"price\\":\\"$1\\"}}]}}}}");
    {key_steps}
    if (!ave_sm_build_listen_detect_json("看这个", out, sizeof(out))) {{
        return 2;
    }}
    if (strstr(out, "\\"selection\\"")) {{
        fprintf(stderr, "unexpected selection in {failure_label}: %s\\n", out);
        return 3;
    }}
    return 0;
}}
"""
        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name=binary_name,
            extra_sources=(feed_source, browse_source),
        )

    def _assert_real_confirm_screen_locks_inputs_after_first_submit(
        self,
        *,
        screen_id,
        screen_source,
        first_trade_id,
        second_trade_id,
        binary_name,
        rename_stub_macros=(),
        extra_ldflags=(),
        data_fields,
    ):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]

        rename_block = "\n".join(
            f"#define {macro} {macro}__stub"
            for macro in rename_stub_macros
        )
        unrename_block = "\n".join(
            f"#undef {macro}"
            for macro in rename_stub_macros
        )

        first_display_json = (
            '{"type":"display","screen":"'
            + screen_id
            + '","data":{"trade_id":"'
            + first_trade_id
            + '",'
            + data_fields
            + "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')
        second_display_json = (
            '{"type":"display","screen":"'
            + screen_id
            + '","data":{"trade_id":"'
            + second_trade_id
            + '",'
            + data_fields
            + "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')

        if screen_id == "confirm":
            other_context_stub = """
int screen_limit_confirm_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}
"""
        else:
            other_context_stub = """
int screen_confirm_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}
"""

        harness_source = f"""
{rename_block}
{verifier_prefix}
{unrename_block}


{other_context_stub}
int screen_result_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_feed_show(const char *json_data) {{ (void)json_data; }}
void screen_feed_reveal(void) {{ }}
void screen_feed_key(int key) {{ (void)key; }}
bool screen_feed_should_ignore_live_push(void) {{ return false; }}
int screen_feed_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_explorer_show(const char *json_data) {{ (void)json_data; }}
void screen_explorer_key(int key) {{ (void)key; }}
int screen_explorer_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_browse_show(const char *json_data) {{ (void)json_data; }}
void screen_browse_show_placeholder(const char *mode) {{ (void)mode; }}
void screen_browse_reveal(void) {{ }}
void screen_browse_key(int key) {{ (void)key; }}
int screen_browse_get_selected_context_json(char *out, size_t out_n)
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

int main(void)
{{
    int ok = 1;

    ave_sm_handle_json("{first_display_json}");
    lv_tick_inc(600);
    clear_last_json();
    ave_sm_key_press(AVE_KEY_A);
    ok &= expect_contains("\\"action\\":\\"confirm\\"", "first confirm submit");
    ok &= expect_contains("\\"trade_id\\":\\"{first_trade_id}\\"", "first confirm trade id");

    clear_last_json();
    ave_sm_key_press(AVE_KEY_A);
    if (g_last_json[0] != '\\0') {{
        fprintf(stderr, "duplicate A should be ignored after submit: %s\\n", g_last_json);
        ok = 0;
    }}

    clear_last_json();
    ave_sm_key_press(AVE_KEY_B);
    if (g_last_json[0] != '\\0') {{
        fprintf(stderr, "B should be ignored while awaiting ack: %s\\n", g_last_json);
        ok = 0;
    }}

    clear_last_json();
    ave_sm_key_press(AVE_KEY_Y);
    if (g_last_json[0] != '\\0') {{
        fprintf(stderr, "Y should be ignored while awaiting ack: %s\\n", g_last_json);
        ok = 0;
    }}

    ave_sm_handle_json("{second_display_json}");
    lv_tick_inc(600);
    clear_last_json();
    ave_sm_key_press(AVE_KEY_A);
    ok &= expect_contains("\\"trade_id\\":\\"{second_trade_id}\\"", "lock resets on new screen");

    return ok ? 0 : 1;
}}
"""

        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name=binary_name,
            extra_sources=(screen_source,),
            extra_ldflags=("-DLV_ANIM_OFF=0", *extra_ldflags),
        )

    async def test_feed_mixed_input_watch_and_buy_use_explicit_selection_payload(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "feed_cursor": 0,
                "feed_token_list": [
                    {"addr": "feed-1", "chain": "solana", "symbol": "OLD"},
                    {"addr": "feed-2", "chain": "base", "symbol": "NEW"},
                ],
                "current_token": {"addr": "stale-spot", "chain": "solana", "symbol": "STALE"},
            }
        )

        def _detail_side_effect(passed_conn, addr, chain, symbol=""):
            passed_conn.ave_state["screen"] = "spotlight"
            passed_conn.ave_state["current_token"] = {
                "addr": "stale-after-watch",
                "chain": "solana",
                "symbol": "STALE",
            }

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat, \
             patch("plugins_func.functions.ave_tools.ave_token_detail", side_effect=_detail_side_effect) as mock_detail, \
             patch("plugins_func.functions.ave_tools.ave_buy_token") as mock_buy:
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
            await handler.handle(
                conn,
                {
                    "state": "detect",
                    "text": "买这个",
                    "selection": {
                        "screen": "spotlight",
                        "token": {"addr": "feed-2", "chain": "base", "symbol": "NEW"},
                    },
                },
            )

        start_chat.assert_not_awaited()
        mock_detail.assert_called_once_with(conn, addr="feed-2", chain="base", symbol="NEW")
        mock_buy.assert_called_once_with(conn, addr="feed-2", chain="base", symbol="NEW")

    async def test_portfolio_mixed_input_watch_uses_explicit_selection_payload(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "portfolio",
                "portfolio_cursor": 0,
                "portfolio_holdings": [
                    {"addr": "pf-1", "chain": "solana", "symbol": "OLD"},
                    {"addr": "pf-2", "chain": "eth", "symbol": "REAL"},
                ],
                "current_token": {"addr": "stale-spot", "chain": "solana", "symbol": "STALE"},
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
                        "cursor": 1,
                        "token": {"addr": "pf-2", "chain": "eth", "symbol": "REAL"},
                    },
                },
            )

        start_chat.assert_not_awaited()
        mock_detail.assert_called_once_with(conn, addr="pf-2", chain="eth", symbol="REAL")

    async def test_non_router_listen_detect_forwards_selection_payload_into_chat_pipeline(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn({"screen": "feed"})
        message = {
            "state": "detect",
            "text": "帮我分析这个",
            "selection": {
                "screen": "feed",
                "cursor": 1,
                "token": {"addr": "feed-2", "chain": "base", "symbol": "NEW"},
            },
        }

        with patch("core.handle.textHandler.listenMessageHandler.enqueue_asr_report"), \
             patch("core.handle.textHandler.listenMessageHandler.startToChat", new=AsyncMock()) as start_chat:
            await handler.handle(conn, message)

        start_chat.assert_awaited_once_with(conn, "帮我分析这个", message_payload=message)

    async def test_malformed_selection_payload_fails_closed_instead_of_using_stale_feed_cursor(self):
        handler = ListenTextMessageHandler()
        conn = self._build_listen_conn(
            {
                "screen": "feed",
                "feed_cursor": 0,
                "feed_token_list": [
                    {"addr": "stale-1", "chain": "solana", "symbol": "STALE"},
                ],
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
                    "selection": {"screen": "feed", "token": {"symbol": "BROKEN"}},
                },
            )

        start_chat.assert_not_awaited()
        mock_detail.assert_not_called()
        send_stt.assert_awaited_once_with(conn, "请先在界面上选中你要操作的代币，然后再说一次。")

    async def test_quick_sell_prefers_explicit_symbol_over_state_fallback(self):
        handler = KeyActionHandler()
        conn = SimpleNamespace(
            ave_state={"current_token": {"symbol": "STALE"}},
            loop=SimpleNamespace(create_task=lambda coro, name=None: None),
        )

        with patch("plugins_func.functions.ave_tools.ave_sell_token") as mock_sell:
            await handler.handle(
                conn,
                {
                    "type": "key_action",
                    "action": "quick_sell",
                    "token_id": "token-1",
                    "chain": "solana",
                    "symbol": "REAL",
                },
            )

        mock_sell.assert_called_once_with(
            conn,
            addr="token-1",
            chain="solana",
            sell_ratio=1.0,
            symbol="REAL",
        )

    def test_real_confirm_screen_blocks_repeat_a_b_y_until_new_screen(self):
        repo_root = Path(__file__).resolve().parents[3]
        self._assert_real_confirm_screen_locks_inputs_after_first_submit(
            screen_id="confirm",
            screen_source=repo_root / "shared/ave_screens/screen_confirm.c",
            first_trade_id="confirm-trade-1",
            second_trade_id="confirm-trade-2",
            binary_name="verify_confirm_submit_lock",
            rename_stub_macros=(
                "screen_confirm_show",
                "screen_confirm_key",
                "screen_confirm_cancel_timers",
            ),
            data_fields=(
                '"action":"BUY",'
                '"symbol":"BONK",'
                '"amount_native":"0.10 SOL",'
                '"amount_usd":"$10.00",'
                '"timeout_sec":10'
            ),
        )

    def test_real_limit_confirm_screen_blocks_repeat_a_b_y_until_new_screen(self):
        repo_root = Path(__file__).resolve().parents[3]
        self._assert_real_confirm_screen_locks_inputs_after_first_submit(
            screen_id="limit_confirm",
            screen_source=repo_root / "shared/ave_screens/screen_limit_confirm.c",
            first_trade_id="limit-trade-1",
            second_trade_id="limit-trade-2",
            binary_name="verify_limit_confirm_submit_lock",
            rename_stub_macros=(
                "screen_limit_confirm_show",
                "screen_limit_confirm_key",
                "screen_limit_confirm_cancel_timers",
            ),
            extra_ldflags=("-Dlv_font_montserrat_16=lv_font_montserrat_14",),
            data_fields=(
                '"action":"LIMIT BUY",'
                '"symbol":"BONK",'
                '"amount_native":"0.10 SOL",'
                '"limit_price":"0.0001",'
                '"current_price":"0.0002",'
                '"distance":"-50%",'
                '"timeout_sec":10'
            ),
        )

    def test_touched_c_key_action_payloads_escape_dynamic_values(self):
        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        common_sources = self._common_screen_sources(repo_root)
        price_fmt_src = repo_root / "shared/ave_screens/ave_price_fmt.c"
        selection_stub_source = """
#include <stddef.h>
#include "lvgl/lvgl.h"

void lv_obj_set_style_text_align(lv_obj_t *obj, int align, int part)
{
    (void)obj;
    (void)align;
    (void)part;
}

int screen_confirm_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

int screen_limit_confirm_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

int screen_result_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}


void screen_disambiguation_show(const char *json_data) { (void)json_data; }
void screen_disambiguation_key(int key) { (void)key; }
void screen_disambiguation_cancel_timers(void) {}
int screen_disambiguation_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            selection_stub = Path(tmpdir) / "selection_context_stubs.c"
            selection_stub.write_text(selection_stub_source)
            for macro in ("VERIFY_FEED", "VERIFY_PORTFOLIO", "VERIFY_SPOTLIGHT"):
                binary = Path(tmpdir) / macro.lower()
                compile_cmd = [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    "-DLV_OPA_TRANSP=0",
                    "-DLV_TEXT_ALIGN_LEFT=0",
                    "-DLV_TEXT_ALIGN_CENTER=1",
                    "-DLV_TEXT_ALIGN_RIGHT=2",
                    f"-D{macro}",
                    str(verifier),
                    str(manager_src),
                    *[str(source) for source in common_sources],
                    str(selection_stub),
                    str(price_fmt_src),
                    "-lm",
                    "-o",
                    str(binary),
                ]
                compile_result = subprocess.run(
                    compile_cmd,
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

    def test_real_feed_selection_emitter_omits_missing_chain_in_listen_payload(self):
        repo_root = Path(__file__).resolve().parents[3]
        self._assert_real_selection_emitter_missing_chain_fails_closed(
            screen_macro="VERIFY_FEED",
            screen_source=repo_root / "shared/ave_screens/screen_feed.c",
            display_json=(
                '{"screen":"feed","data":{"tokens":['
                '{"token_id":"feed-no-chain","symbol":"BROKEN","price":"$1"}'
                "]}}"
            ),
        )

    def test_real_feed_key_action_omits_missing_chain(self):
        repo_root = Path(__file__).resolve().parents[3]
        self._assert_real_key_action_missing_chain_fails_closed(
            screen_name="feed",
            screen_source=repo_root / "shared/ave_screens/screen_feed.c",
            display_json=(
                '{"screen":"feed","data":{"tokens":['
                '{"token_id":"feed-no-chain","symbol":"BROKEN","price":"$1"}'
                "]}}"
            ),
            key_steps="ave_sm_key_press(AVE_KEY_A);",
        )

    def test_real_spotlight_key_action_omits_missing_chain(self):
        repo_root = Path(__file__).resolve().parents[3]
        self._assert_real_key_action_missing_chain_fails_closed(
            screen_name="spotlight",
            screen_source=repo_root / "shared/ave_screens/screen_spotlight.c",
            display_json=(
                '{"screen":"spotlight","data":{'
                '"token_id":"spot-no-chain",'
                '"symbol":"BROKEN",'
                '"price":"$1",'
                '"change_24h":"+1%",'
                '"chart":[1,2],'
                '"chart_min":"$1",'
                '"chart_max":"$2"'
                "}}"
            ),
            key_steps="ave_sm_key_press(AVE_KEY_A);",
            extra_sources=(repo_root / "shared/ave_screens/ave_price_fmt.c",),
            extra_ldflags=("-lm",),
        )

    def test_real_spotlight_partial_payload_clears_stale_identity_before_actions(self):
        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        full_json = (
            '{"screen":"spotlight","data":{'
            '"token_id":"spot-1",'
            '"chain":"solana",'
            '"symbol":"PEPE",'
            '"price":"$1",'
            '"change_24h":"+1%",'
            '"chart":[1,2],'
            '"chart_min":"$1",'
            '"chart_max":"$2"'
            "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')
        partial_json = (
            '{"screen":"spotlight","data":{'
            '"symbol":"WIF",'
            '"price":"$2",'
            '"change_24h":"+2%",'
            '"chart":[2,3],'
            '"chart_min":"$2",'
            '"chart_max":"$3"'
            "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_SPOTLIGHT
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

int main(void)
{{
    ave_sm_handle_json("{full_json}");
    clear_last_json();
    ave_sm_handle_json("{partial_json}");
    clear_last_json();
    ave_sm_key_press(AVE_KEY_A);
    if (g_last_json[0] != '\\0') {{
        fprintf(stderr, "stale spotlight identity emitted action: %s\\n", g_last_json);
        return 3;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_spotlight_stale_identity",
            extra_sources=(
                repo_root / "shared/ave_screens/screen_spotlight.c",
                repo_root / "shared/ave_screens/ave_price_fmt.c",
            ),
            extra_ldflags=(
                "-DLV_OPA_TRANSP=0",
                "-DLV_TEXT_ALIGN_LEFT=0",
                "-DLV_TEXT_ALIGN_CENTER=1",
                "-DLV_TEXT_ALIGN_RIGHT=2",
                "-lm",
            ),
        )

    def test_real_spotlight_loading_payload_clears_stale_x_axis_labels(self):
        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        full_json = (
            '{"screen":"spotlight","data":{'
            '"token_id":"spot-1",'
            '"chain":"solana",'
            '"symbol":"PEPE",'
            '"price":"$1",'
            '"change_24h":"+1%",'
            '"chart":[1,2],'
            '"chart_min":"$1",'
            '"chart_max":"$2",'
            '"chart_t_start":"03/01 00:00",'
            '"chart_t_mid":"03/01 12:00",'
            '"chart_t_end":"03/01 23:59"'
            "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')
        loading_json = (
            '{"screen":"spotlight","data":{'
            '"token_id":"spot-1",'
            '"chain":"solana",'
            '"symbol":"PEPE",'
            '"price":"--",'
            '"change_24h":"Loading",'
            '"chart":[500,500],'
            '"chart_min":"--",'
            '"chart_max":"--",'
            '"chart_t_end":"now"'
            "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_SPOTLIGHT
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

void screen_feed_show(const char *json_data) {{ (void)json_data; }}
void screen_feed_reveal(void) {{ }}
void screen_feed_key(int key) {{ (void)key; }}
bool screen_feed_should_ignore_live_push(void) {{ return false; }}
int screen_feed_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_explorer_show(const char *json_data) {{ (void)json_data; }}
void screen_explorer_key(int key) {{ (void)key; }}
int screen_explorer_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_browse_show(const char *json_data) {{ (void)json_data; }}
void screen_browse_show_placeholder(const char *mode) {{ (void)mode; }}
void screen_browse_reveal(void) {{ }}
void screen_browse_key(int key) {{ (void)key; }}
int screen_browse_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

#include "{repo_root / 'shared/ave_screens/screen_spotlight.c'}"

int main(void)
{{
    ave_sm_handle_json("{full_json}");
    ave_sm_handle_json("{loading_json}");
    if (s_lbl_t_start->text[0] != '\\0' || s_lbl_t_mid->text[0] != '\\0') {{
        fprintf(stderr, "stale x-axis label: start='%s' mid='%s' end='%s'\\n",
                s_lbl_t_start->text, s_lbl_t_mid->text, s_lbl_t_end->text);
        return 3;
    }}
    if (strcmp(s_lbl_t_end->text, "now") != 0) {{
        fprintf(stderr, "unexpected end label: %s\\n", s_lbl_t_end->text);
        return 4;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_spotlight_loading_clears_xaxis",
            extra_sources=(
                repo_root / "shared/ave_screens/ave_price_fmt.c",
            ),
            extra_ldflags=(
                "-DLV_OPA_TRANSP=0",
                "-DLV_TEXT_ALIGN_LEFT=0",
                "-DLV_TEXT_ALIGN_CENTER=1",
                "-DLV_TEXT_ALIGN_RIGHT=2",
                "-lm",
            ),
        )

    def test_real_spotlight_stale_payload_does_not_release_feed_navigation_guard(self):
        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        old_json = (
            '{"screen":"spotlight","data":{'
            '"token_id":"old-token-solana",'
            '"chain":"solana",'
            '"symbol":"OLD",'
            '"price":"$1",'
            '"change_24h":"+1%",'
            '"interval":"60",'
            '"chart":[1,2],'
            '"chart_min":"$1",'
            '"chart_max":"$2"'
            "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')
        stale_json = (
            '{"screen":"spotlight","data":{'
            '"token_id":"old-token-solana",'
            '"chain":"solana",'
            '"symbol":"OLD",'
            '"price":"$1.01",'
            '"change_24h":"+1.1%",'
            '"interval":"60",'
            '"chart":[2,3],'
            '"chart_min":"$1",'
            '"chart_max":"$2"'
            "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')
        fresh_json = (
            '{"screen":"spotlight","data":{'
            '"token_id":"new-token-solana",'
            '"chain":"solana",'
            '"symbol":"NEW",'
            '"price":"$9",'
            '"change_24h":"+9%",'
            '"interval":"60",'
            '"chart":[9,10],'
            '"chart_min":"$9",'
            '"chart_max":"$10"'
            "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_SPOTLIGHT
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

void screen_feed_show(const char *json_data) {{ (void)json_data; }}
void screen_feed_reveal(void) {{ }}
void screen_feed_key(int key) {{ (void)key; }}
bool screen_feed_should_ignore_live_push(void) {{ return false; }}
int screen_feed_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_explorer_show(const char *json_data) {{ (void)json_data; }}
void screen_explorer_key(int key) {{ (void)key; }}
int screen_explorer_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_browse_show(const char *json_data) {{ (void)json_data; }}
void screen_browse_show_placeholder(const char *mode) {{ (void)mode; }}
void screen_browse_reveal(void) {{ }}
void screen_browse_key(int key) {{ (void)key; }}
int screen_browse_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

#include "{repo_root / 'shared/ave_screens/screen_spotlight.c'}"

int main(void)
{{
    ave_sm_handle_json("{old_json}");
    clear_last_json();
    ave_sm_key_press(AVE_KEY_RIGHT);
    if (!expect_contains("\\"action\\":\\"feed_next\\"", "feed_next")) {{
        return 2;
    }}
    if (!s_loading) {{
        fprintf(stderr, "feed_next did not arm loading guard\\n");
        return 3;
    }}

    clear_last_json();
    ave_sm_handle_json("{stale_json}");
    if (!s_loading) {{
        fprintf(stderr, "stale spotlight payload released loading guard\\n");
        return 4;
    }}
    ave_sm_key_press(AVE_KEY_A);
    if (g_last_json[0] != '\\0') {{
        fprintf(stderr, "buy should stay blocked while stale payload arrives: %s\\n", g_last_json);
        return 5;
    }}

    ave_sm_handle_json("{fresh_json}");
    if (s_loading) {{
        fprintf(stderr, "fresh spotlight payload did not release loading guard\\n");
        return 6;
    }}

    clear_last_json();
    ave_sm_key_press(AVE_KEY_A);
    if (!expect_contains("\\"action\\":\\"buy\\"", "buy action")) {{
        return 7;
    }}
    if (!expect_contains("\\"token_id\\":\\"new-token-solana\\"", "new token id")) {{
        return 8;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_spotlight_stale_payload_keeps_loading_guard",
            extra_sources=(
                repo_root / "shared/ave_screens/ave_price_fmt.c",
            ),
            extra_ldflags=(
                "-DLV_OPA_TRANSP=0",
                "-DLV_TEXT_ALIGN_LEFT=0",
                "-DLV_TEXT_ALIGN_CENTER=1",
                "-DLV_TEXT_ALIGN_RIGHT=2",
                "-lm",
            ),
        )

    def test_real_spotlight_same_identity_navigation_payload_releases_feed_guard(self):
        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        old_json = (
            '{"screen":"spotlight","data":{'
            '"token_id":"same-token-solana",'
            '"chain":"solana",'
            '"symbol":"SAME",'
            '"price":"$1",'
            '"change_24h":"+1%",'
            '"interval":"60",'
            '"cursor":0,'
            '"total":2,'
            '"chart":[1,2],'
            '"chart_min":"$1",'
            '"chart_max":"$2"'
            "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')
        nav_json = (
            '{"screen":"spotlight","data":{'
            '"token_id":"same-token-solana",'
            '"chain":"solana",'
            '"symbol":"SAME",'
            '"price":"$1.25",'
            '"change_24h":"+1.5%",'
            '"interval":"60",'
            '"cursor":1,'
            '"total":2,'
            '"chart":[2,3],'
            '"chart_min":"$1",'
            '"chart_max":"$2"'
            "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_SPOTLIGHT
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

void screen_feed_show(const char *json_data) {{ (void)json_data; }}
void screen_feed_reveal(void) {{ }}
void screen_feed_key(int key) {{ (void)key; }}
bool screen_feed_should_ignore_live_push(void) {{ return false; }}
int screen_feed_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_explorer_show(const char *json_data) {{ (void)json_data; }}
void screen_explorer_key(int key) {{ (void)key; }}
int screen_explorer_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

void screen_browse_show(const char *json_data) {{ (void)json_data; }}
void screen_browse_show_placeholder(const char *mode) {{ (void)mode; }}
void screen_browse_reveal(void) {{ }}
void screen_browse_key(int key) {{ (void)key; }}
int screen_browse_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

#include "{repo_root / 'shared/ave_screens/screen_spotlight.c'}"

int main(void)
{{
    ave_sm_handle_json("{old_json}");
    clear_last_json();
    ave_sm_key_press(AVE_KEY_RIGHT);
    if (!expect_contains("\\"action\\":\\"feed_next\\"", "feed_next")) {{
        return 2;
    }}
    if (!s_loading) {{
        fprintf(stderr, "feed_next did not arm loading guard\\n");
        return 3;
    }}

    ave_sm_handle_json("{nav_json}");
    if (s_loading) {{
        fprintf(stderr, "same-identity spotlight navigation payload did not release loading guard\\n");
        return 4;
    }}

    clear_last_json();
    ave_sm_key_press(AVE_KEY_A);
    if (!expect_contains("\\"action\\":\\"buy\\"", "buy action")) {{
        return 5;
    }}
    if (!expect_contains("\\"token_id\\":\\"same-token-solana\\"", "same token id")) {{
        return 6;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_spotlight_same_identity_nav_releases_guard",
            extra_sources=(
                repo_root / "shared/ave_screens/ave_price_fmt.c",
            ),
            extra_ldflags=(
                "-DLV_OPA_TRANSP=0",
                "-DLV_TEXT_ALIGN_LEFT=0",
                "-DLV_TEXT_ALIGN_CENTER=1",
                "-DLV_TEXT_ALIGN_RIGHT=2",
                "-lm",
            ),
        )

    def test_real_spotlight_live_payload_does_not_cancel_back_timer(self):
        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        old_json = (
            '{"screen":"spotlight","data":{'
            '"token_id":"old-token-solana",'
            '"chain":"solana",'
            '"symbol":"OLD",'
            '"price":"$1",'
            '"change_24h":"+1%",'
            '"interval":"60",'
            '"chart":[1,2],'
            '"chart_min":"$1",'
            '"chart_max":"$2"'
            "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')
        live_json = (
            '{"screen":"spotlight","data":{'
            '"token_id":"old-token-solana",'
            '"chain":"solana",'
            '"symbol":"OLD",'
            '"price":"$1.11",'
            '"change_24h":"+1.2%",'
            '"interval":"60",'
            '"chart":[2,3],'
            '"chart_min":"$1",'
            '"chart_max":"$2",'
            '"live":true'
            "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_SPOTLIGHT
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

void screen_feed_reveal(void) {{ }}

#include "{repo_root / 'shared/ave_screens/screen_spotlight.c'}"

int main(void)
{{
    ave_sm_handle_json("{old_json}");
    clear_last_json();
    ave_sm_key_press(AVE_KEY_B);
    if (!expect_contains("\\"action\\":\\"back\\"", "back action")) {{
        return 2;
    }}
    if (!s_back_timer) {{
        fprintf(stderr, "back key did not arm fallback timer\\n");
        return 3;
    }}

    ave_sm_handle_json("{live_json}");
    if (!s_back_timer) {{
        fprintf(stderr, "live spotlight payload cancelled back timer\\n");
        return 4;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_spotlight_live_payload_keeps_back_timer",
            extra_sources=(
                repo_root / "shared/ave_screens/ave_price_fmt.c",
            ),
            extra_ldflags=(
                "-DLV_OPA_TRANSP=0",
                "-DLV_TEXT_ALIGN_LEFT=0",
                "-DLV_TEXT_ALIGN_CENTER=1",
                "-DLV_TEXT_ALIGN_RIGHT=2",
                "-lm",
            ),
        )

    def test_real_spotlight_watchlist_star_layout(self):
        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        payload = (
            '{"screen":"spotlight","data":{'
            '"symbol":"SIG","token_id":"signal-spot","chain":"solana",'
            '"cursor":1,"total":3,'
            '"price":"$1.23","change_24h":"+2.1%","holders":"1,200",'
            '"liquidity":"$100K","volume_24h":"$90K","market_cap":"$4M",'
            '"top100_concentration":"12.3%","contract":"0xABCDEF1234567890ABCDEF1234567890ABCDEF12",'
            '"is_watchlisted":true,"origin_hint":"From Signal Watchlist",'
            '"chart":[500,520,530],'
            '"chart_min":"$1.00","chart_max":"$2.00"'
            "}}"
        ).replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_SPOTLIGHT
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

#include "{repo_root / 'shared/ave_screens/screen_spotlight.c'}"

int main(void)
{{
    screen_spotlight_show("{payload}");
    if (strcmp(s_lbl_watch_star->text, "★") != 0) {{
        fprintf(stderr, "unexpected watchlist star: %s\\n", s_lbl_watch_star->text);
        return 2;
    }}
    if (strcmp(s_lbl_origin->text, "From Signal Watchlist") != 0) {{
        fprintf(stderr, "origin hint missing: %s\\n", s_lbl_origin->text);
        return 3;
    }}
    if (strcmp(s_lbl_pos->text, "<2/3>") != 0) {{
        fprintf(stderr, "page marker missing: %s\\n", s_lbl_pos->text);
        return 4;
    }}
    const int expected_row4_width_with_marker =
        FOOTER_W - FOOTER_ROW4_STAR_W - FOOTER_ROW4_HINT_GAP - FOOTER_PAGE_W - FOOTER_ROW4_GAP;
    if (s_lbl_stats_row4->width != expected_row4_width_with_marker) {{
        fprintf(stderr, "unexpected row4 width: %d (want %d)\\n",
                s_lbl_stats_row4->width, expected_row4_width_with_marker);
        return 5;
    }}
    if (s_lbl_watch_star->x <= (s_lbl_stats_row4->x + s_lbl_stats_row4->width)) {{
        fprintf(stderr, "watchlist star overlaps CA: star_x=%d ca_right=%d\\n",
                s_lbl_watch_star->x, s_lbl_stats_row4->x + s_lbl_stats_row4->width);
        return 6;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            extra_sources=(
                repo_root / "shared/ave_screens/ave_price_fmt.c",
                repo_root / "shared/ave_screens/screen_explorer.c",
                repo_root / "shared/ave_screens/screen_browse.c",
            ),
            extra_ldflags=(
                "-DLV_OPA_TRANSP=0",
                "-DLV_TEXT_ALIGN_LEFT=0",
                "-DLV_TEXT_ALIGN_CENTER=1",
                "-DLV_TEXT_ALIGN_RIGHT=2",
                "-lm",
            ),
            binary_name="verify_spotlight_watchlist_star_layout",
        )

    def test_real_portfolio_key_action_omits_missing_chain(self):
        repo_root = Path(__file__).resolve().parents[3]
        self._assert_real_key_action_missing_chain_fails_closed(
            screen_name="portfolio",
            screen_source=repo_root / "shared/ave_screens/screen_portfolio.c",
            display_json=(
                '{"screen":"portfolio","data":{"holdings":['
                '{"symbol":"BROKEN","addr":"port-no-chain","value_usd":"$1","pnl_pct":"N/A"}'
                "]}}"
            ),
            key_steps="ave_sm_key_press(AVE_KEY_A);",
        )

    def test_real_disambiguation_key_action_omits_missing_chain(self):
        repo_root = Path(__file__).resolve().parents[3]
        self._assert_real_key_action_missing_chain_fails_closed(
            screen_name="disambiguation",
            screen_source=repo_root / "shared/ave_screens/screen_disambiguation.c",
            display_json=(
                '{"screen":"disambiguation","data":{"items":['
                '{"token_id":"amb-no-chain","symbol":"BROKEN"}'
                "]}}"
            ),
            key_steps="ave_sm_key_press(AVE_KEY_A);",
        )

    def test_real_feed_explore_panel_omits_trusted_selection_in_listen_payload(self):
        self._assert_real_feed_overlay_omits_trusted_selection_in_listen_payload(
            key_sequence=("AVE_KEY_B",),
            binary_name="verify_feed_explore_panel_selection",
            failure_label="explore panel",
        )

    def test_real_feed_explore_panel_signals_watchlist_actions(self):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        feed_source = repo_root / "shared/ave_screens/screen_feed.c"
        explorer_source = repo_root / "shared/ave_screens/screen_explorer.c"
        browse_source = repo_root / "shared/ave_screens/screen_browse.c"
        verifier_prefix = (repo_root / "simulator/mock/verify_ave_json_payloads.c").read_text(
            encoding="utf-8"
        ).split("#if defined(VERIFY_FEED)", 1)[0]
        feed_payload = (
            '{'
            '"screen":"feed",'
            '"data":{"source_label":"TRENDING","tokens":['
            '{"token_id":"feed-1","chain":"solana","symbol":"BONK","price":"$1","change_24h":"+1%"}'
            ']}}'
        ).replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_FEED
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

const char *screen_browse_get_source_label(void);

int main(void)
{{
    ave_sm_handle_json("{feed_payload}");
    clear_last_json();
    ave_sm_key_press(AVE_KEY_B);
    for (int i = 0; i < 4; i++) {{
        ave_sm_key_press(AVE_KEY_DOWN);
    }}
    ave_sm_key_press(AVE_KEY_A);
    if (ave_sm_get_current_screen_id() != AVE_SCREEN_BROWSE) {{
        fprintf(stderr, "signals did not open browse screen\\n");
        return 2;
    }}
    if (!screen_browse_get_source_label() || strcmp(screen_browse_get_source_label(), "SIGNALS") != 0) {{
        fprintf(stderr, "signals title not synced immediately\\n");
        return 3;
    }}
    if (!expect_contains("\\"action\\":\\"signals\\"", "signals explore activation")) {{
        return 4;
    }}

    ave_sm_handle_json("{feed_payload}");
    clear_last_json();
    ave_sm_key_press(AVE_KEY_B);
    for (int i = 0; i < 5; i++) {{
        ave_sm_key_press(AVE_KEY_DOWN);
    }}
    ave_sm_key_press(AVE_KEY_A);
    if (ave_sm_get_current_screen_id() != AVE_SCREEN_BROWSE) {{
        fprintf(stderr, "watchlist did not open browse screen\\n");
        return 5;
    }}
    if (!screen_browse_get_source_label() || strcmp(screen_browse_get_source_label(), "WATCHLIST") != 0) {{
        fprintf(stderr, "watchlist title not synced immediately\\n");
        return 6;
    }}
    if (!expect_contains("\\"action\\":\\"watchlist\\"", "watchlist explore activation")) {{
        return 7;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_feed_explore_panel_signals_watchlist",
            extra_sources=(feed_source, explorer_source, browse_source),
        )

    def test_real_feed_signals_browse_uses_signal_summary_not_headline(self):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        screen_source = repo_root / "shared/ave_screens/screen_browse.c"
        verifier_prefix = (repo_root / "simulator/mock/verify_ave_json_payloads.c").read_text(
            encoding="utf-8"
        ).split("#if defined(VERIFY_FEED)", 1)[0]

        signals_payload = (
            '{'
            '"screen":"browse",'
            '"data":{"mode":"signals","source_label":"SIGNALS","tokens":['
            '{"token_id":"sig-1","chain":"solana","symbol":"赢麻了","signal_type":"public_signal",'
            '"signal_label":"BUY","signal_value":"BUY 3.5 SOL","signal_first":"First 5m","signal_last":"Last 2m",'
            '"signal_count":"Count 2","signal_vol":"Vol $125.0K","signal_summary":"First 5m Last 2m Count 2 Vol $125.0K",'
            '"headline":"THIS_HEADLINE_MUST_NOT_RENDER"}'
            ']}}'
        ).replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_FEED
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

void screen_feed_show(const char *json_data) {{ (void)json_data; }}
void screen_feed_reveal(void) {{ }}
void screen_feed_key(int key) {{ (void)key; }}
bool screen_feed_should_ignore_live_push(void) {{ return false; }}
int screen_feed_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}
void screen_explorer_show(const char *json_data) {{ (void)json_data; }}
void screen_explorer_key(int key) {{ (void)key; }}
int screen_explorer_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}
#include "{screen_source}"

int main(void)
{{
    screen_browse_show("{signals_payload}");
    if (!s_rows[0].lbl_sym || strcmp(s_rows[0].lbl_sym->text, "赢麻了") != 0) {{
        fprintf(stderr, "signals symbol not preserved: %s\\n", s_rows[0].lbl_sym ? s_rows[0].lbl_sym->text : "<null>");
        return 2;
    }}
    if (!s_rows[0].lbl_price || strcmp(s_rows[0].lbl_price->text, "BUY 3.5 SOL") != 0) {{
        fprintf(stderr, "signals action label incorrect: %s\\n", s_rows[0].lbl_price ? s_rows[0].lbl_price->text : "<null>");
        return 3;
    }}
    if (!s_rows[0].lbl_meta1 || strcmp(s_rows[0].lbl_meta1->text, "First 5m") != 0) {{
        fprintf(stderr, "signals first meta incorrect: %s\\n", s_rows[0].lbl_meta1 ? s_rows[0].lbl_meta1->text : "<null>");
        return 4;
    }}
    if (!s_rows[0].lbl_meta2 || strcmp(s_rows[0].lbl_meta2->text, "Last 2m") != 0) {{
        fprintf(stderr, "signals last meta incorrect: %s\\n", s_rows[0].lbl_meta2 ? s_rows[0].lbl_meta2->text : "<null>");
        return 5;
    }}
    if (!s_rows[0].lbl_meta3 || strcmp(s_rows[0].lbl_meta3->text, "Count 2") != 0) {{
        fprintf(stderr, "signals count meta incorrect: %s\\n", s_rows[0].lbl_meta3 ? s_rows[0].lbl_meta3->text : "<null>");
        return 6;
    }}
    if (!s_rows[0].lbl_meta4 || strcmp(s_rows[0].lbl_meta4->text, "Vol $125.0K") != 0) {{
        fprintf(stderr, "signals vol meta incorrect: %s\\n", s_rows[0].lbl_meta4 ? s_rows[0].lbl_meta4->text : "<null>");
        return 7;
    }}
    if (s_rows[0].lbl_subtitle && s_rows[0].lbl_subtitle->text[0] != '\\0') {{
        fprintf(stderr, "signals subtitle should stay empty: %s\\n", s_rows[0].lbl_subtitle->text);
        return 8;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_feed_signals_browse_summary",
        )

    def test_real_feed_return_from_signals_restores_standard_row_colors(self):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        screen_source = repo_root / "shared/ave_screens/screen_feed.c"
        browse_source = repo_root / "shared/ave_screens/screen_browse.c"
        explorer_source = repo_root / "shared/ave_screens/screen_explorer.c"
        verifier_prefix = (repo_root / "simulator/mock/verify_ave_json_payloads.c").read_text(
            encoding="utf-8"
        ).split("#if defined(VERIFY_FEED)", 1)[0]

        signals_payload = (
            '{'
            '"screen":"browse",'
            '"data":{"mode":"signals","source_label":"SIGNALS","tokens":['
            '{"token_id":"sig-1","chain":"solana","symbol":"赢麻了","signal_type":"public_signal","signal_label":"BUY","signal_value":"BUY 3.5 SOL","signal_first":"First 5m","signal_last":"Last 2m","signal_count":"Count 2","signal_vol":"Vol $125.0K"},'
            '{"token_id":"sig-2","chain":"eth","symbol":"LINK","signal_type":"public_signal","signal_label":"BUY","signal_value":"BUY 1.2 ETH","signal_first":"First 9m","signal_last":"Last 1m","signal_count":"Count 4","signal_vol":"Vol $532.0K"}'
            ']}}'
        ).replace("\\", "\\\\").replace('"', '\\"')

        trending_payload = (
            '{'
            '"screen":"feed",'
            '"data":{"source_label":"TRENDING","tokens":['
            '{"token_id":"feed-1","chain":"solana","symbol":"BONK","price":"$1","change_24h":"+1%","change_positive":true},'
            '{"token_id":"feed-2","chain":"eth","symbol":"LINK","price":"$9","change_24h":"+2%","change_positive":true}'
            ']}}'
        ).replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_FEED
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

#include "{screen_source}"

void screen_browse_show(const char *json_data);

int main(void)
{{
    screen_feed_show("{trending_payload}");
    screen_browse_show("{signals_payload}");

    if (s_rows[0].lbl_sym->text_color_full != 0xFFFFFF || s_rows[1].lbl_sym->text_color_full != 0xFFFFFF) {{
        fprintf(stderr, "browse screen mutated feed symbol colors: row0=%u row1=%u\\n",
                s_rows[0].lbl_sym->text_color_full,
                s_rows[1].lbl_sym->text_color_full);
        return 2;
    }}
    if (s_rows[0].lbl_price->text_color_full != 0x9E9E9E || s_rows[1].lbl_price->text_color_full != 0x9E9E9E) {{
        fprintf(stderr, "browse screen mutated feed price colors: row0=%u row1=%u\\n",
                s_rows[0].lbl_price->text_color_full,
                s_rows[1].lbl_price->text_color_full);
        return 3;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_feed_signals_return_colors",
            extra_sources=(browse_source, explorer_source),
        )

    def test_real_feed_watchlist_mode_x_emits_watchlist_remove(self):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        screen_source = repo_root / "shared/ave_screens/screen_browse.c"
        verifier_prefix = (repo_root / "simulator/mock/verify_ave_json_payloads.c").read_text(
            encoding="utf-8"
        ).split("#if defined(VERIFY_FEED)", 1)[0]

        watchlist_payload = (
            '{'
            '"screen":"browse",'
            '"data":{"mode":"watchlist","source_label":"WATCHLIST","tokens":['
            '{"token_id":"wl-001","chain":"solana","symbol":"KEEP","price":"$2.11","change_24h":"+0.9%"}'
            ']}}'
        ).replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_FEED
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

void screen_feed_show(const char *json_data) {{ (void)json_data; }}
void screen_feed_reveal(void) {{ }}
void screen_feed_key(int key) {{ (void)key; }}
bool screen_feed_should_ignore_live_push(void) {{ return false; }}
int screen_feed_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}
void screen_explorer_show(const char *json_data) {{ (void)json_data; }}
void screen_explorer_key(int key) {{ (void)key; }}
int screen_explorer_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}
#include "{screen_source}"

int main(void)
{{
    screen_browse_show("{watchlist_payload}");
    clear_last_json();
    screen_browse_key(AVE_KEY_X);
    if (!expect_contains("\\"action\\":\\"watchlist_remove\\"", "watchlist X action")) {{
        return 2;
    }}
    if (!expect_contains("\\"token_id\\":\\"wl-001\\"", "watchlist token id")) {{
        return 3;
    }}
    return 0;
}}
"""

        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_feed_watchlist_mode_x_remove",
        )

    def test_real_feed_explore_search_guide_omits_trusted_selection_in_listen_payload(self):
        self._assert_real_feed_overlay_omits_trusted_selection_in_listen_payload(
            key_sequence=("AVE_KEY_B", "AVE_KEY_A"),
            binary_name="verify_feed_search_guide_selection",
            failure_label="search guide",
        )

    def test_real_feed_explore_search_guide_shows_last_search_query_when_available(self):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        screen_source = repo_root / "shared/ave_screens/screen_explorer.c"
        feed_source = repo_root / "shared/ave_screens/screen_feed.c"
        verifier_prefix = (repo_root / "simulator/mock/verify_ave_json_payloads.c").read_text(
            encoding="utf-8"
        ).split("#if defined(VERIFY_FEED)", 1)[0]

        harness_source = f"""
#define VERIFY_FEED
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

#include "{screen_source}"

static int label_contains(lv_obj_t *obj, const char *needle)
{{
    return obj && needle && strstr(obj->text, needle) != NULL;
}}

int main(void)
{{
    ave_sm_handle_json("{{\\"screen\\":\\"feed\\",\\"data\\":{{\\"source_label\\":\\"SEARCH\\",\\"mode\\":\\"search\\",\\"search_query\\":\\"PEPE\\",\\"cursor\\":1,\\"tokens\\":[{{\\"token_id\\":\\"feed-1\\",\\"chain\\":\\"solana\\",\\"symbol\\":\\"PEPE\\",\\"price\\":\\"$1\\"}},{{\\"token_id\\":\\"feed-2\\",\\"chain\\":\\"base\\",\\"symbol\\":\\"PEPE\\",\\"price\\":\\"$2\\"}}]}}}}");
    ave_sm_handle_json("{{\\"screen\\":\\"feed\\",\\"data\\":{{\\"source_label\\":\\"TRENDING\\",\\"tokens\\":[{{\\"token_id\\":\\"trend-1\\",\\"chain\\":\\"solana\\",\\"symbol\\":\\"BONK\\",\\"price\\":\\"$1\\"}}]}}}}");
    ave_sm_key_press(AVE_KEY_B);
    ave_sm_key_press(AVE_KEY_A);

    if (!label_contains(s_rows[0].lbl_sym, "Search")) {{
        fprintf(stderr, "search guide title missing\\n");
        return 2;
    }}
    if (!label_contains(s_rows[1].lbl_price, "Say token")) {{
        fprintf(stderr, "guided voice prompt missing\\n");
        return 3;
    }}
    if (!label_contains(s_rows[3].lbl_price, "PEPE")) {{
        fprintf(stderr, "last search query not surfaced in guide\\n");
        return 4;
    }}
    return 0;
}}
"""
        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_feed_search_guide_last_query",
            extra_sources=(feed_source,),
        )

    def test_real_feed_search_guide_uses_wide_left_aligned_detail_column(self):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        screen_source = repo_root / "shared/ave_screens/screen_explorer.c"
        feed_source = repo_root / "shared/ave_screens/screen_feed.c"
        verifier_prefix = (repo_root / "simulator/mock/verify_ave_json_payloads.c").read_text(
            encoding="utf-8"
        ).split("#if defined(VERIFY_FEED)", 1)[0]

        harness_source = f"""
#define VERIFY_FEED
{verifier_prefix}

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

static int label_contains(lv_obj_t *obj, const char *needle)
{{
    return obj && needle && strstr(obj->text, needle) != NULL;
}}

int main(void)
{{
    ave_sm_handle_json("{{\\"screen\\":\\"feed\\",\\"data\\":{{\\"source_label\\":\\"TRENDING\\",\\"tokens\\":[{{\\"token_id\\":\\"trend-1\\",\\"chain\\":\\"solana\\",\\"symbol\\":\\"BONK\\",\\"price\\":\\"$1\\"}}]}}}}");
    ave_sm_key_press(AVE_KEY_B);
    ave_sm_key_press(AVE_KEY_A);

    if (!label_contains(s_rows[0].lbl_price, "Guided entry")) {{
        fprintf(stderr, "search guide right column text missing\\n");
        return 2;
    }}
    if (s_rows[0].lbl_price->text_align != LV_TEXT_ALIGN_LEFT) {{
        fprintf(stderr, "search guide right column should be left aligned\\n");
        return 3;
    }}
    if (s_rows[0].lbl_sym->x > 28) {{
        fprintf(stderr, "search guide title column should shift left, x=%d\\n", s_rows[0].lbl_sym->x);
        return 4;
    }}
    if (s_rows[0].lbl_price->x > 120) {{
        fprintf(stderr, "search guide right column should shift left, x=%d\\n", s_rows[0].lbl_price->x);
        return 5;
    }}
    if (s_rows[0].lbl_price->width < 190) {{
        fprintf(stderr, "search guide right column should be widened to near the right edge\\n");
        return 6;
    }}
    return 0;
}}
"""
        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_feed_search_guide_overlay_column_layout",
            extra_sources=(feed_source,),
        )

    def test_real_feed_empty_reset_preserves_last_search_query_for_search_guide(self):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        screen_source = repo_root / "shared/ave_screens/screen_explorer.c"
        feed_source = repo_root / "shared/ave_screens/screen_feed.c"
        verifier_prefix = (repo_root / "simulator/mock/verify_ave_json_payloads.c").read_text(
            encoding="utf-8"
        ).split("#if defined(VERIFY_FEED)", 1)[0]

        harness_source = f"""
#define VERIFY_FEED
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

#include "{screen_source}"

static int label_contains(lv_obj_t *obj, const char *needle)
{{
    return obj && needle && strstr(obj->text, needle) != NULL;
}}

int main(void)
{{
    ave_sm_handle_json("{{\\"screen\\":\\"feed\\",\\"data\\":{{\\"source_label\\":\\"SEARCH\\",\\"mode\\":\\"search\\",\\"search_query\\":\\"PEPE\\",\\"tokens\\":[{{\\"token_id\\":\\"feed-1\\",\\"chain\\":\\"solana\\",\\"symbol\\":\\"PEPE\\",\\"price\\":\\"$1\\"}}]}}}}");
    ave_sm_go_to_feed();
    ave_sm_handle_json("{{\\"screen\\":\\"feed\\",\\"data\\":{{\\"source_label\\":\\"TRENDING\\",\\"tokens\\":[{{\\"token_id\\":\\"trend-1\\",\\"chain\\":\\"solana\\",\\"symbol\\":\\"BONK\\",\\"price\\":\\"$1\\"}}]}}}}");
    ave_sm_key_press(AVE_KEY_B);
    ave_sm_key_press(AVE_KEY_A);

    if (!label_contains(s_rows[3].lbl_price, "PEPE")) {{
        fprintf(stderr, "empty feed reset dropped last-search query\\n");
        return 5;
    }}
    return 0;
}}
"""
        self._compile_and_run_c_harness(
            harness_source,
            include_dir,
            manager_src,
            binary_name="verify_feed_empty_reset_preserves_last_query",
            extra_sources=(feed_source,),
        )

    def test_disambiguation_surface_emits_no_trusted_selection_until_confirmed(self):
        self._verify_disambiguation_selection_payload()

    def test_real_feed_orders_mode_omits_trusted_selection_in_listen_payload(self):
        repo_root = Path(__file__).resolve().parents[3]
        verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        common_sources = self._common_screen_sources(repo_root)
        verifier_prefix = verifier.read_text(encoding="utf-8").split(
            "#if defined(VERIFY_FEED)", 1
        )[0]
        display_json = (
            '{"screen":"feed","data":{"mode":"orders","tokens":['
            '{"token_id":"ord-1","chain":"solana","symbol":"ORDER1","price":"$1","change_24h":"+1%"}'
            "]}}"
        )
        display_json_c = display_json.replace("\\", "\\\\").replace('"', '\\"')

        harness_source = f"""
#define VERIFY_FEED
{verifier_prefix}

/* Keep lvgl stubs in sync with production screen usage. */
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
void screen_disambiguation_cancel_timers(void) {{}}
int screen_disambiguation_get_selected_context_json(char *out, size_t out_n)
{{
    (void)out;
    (void)out_n;
    return 0;
}}

#include "{repo_root / 'shared/ave_screens/screen_feed.c'}"

int main(void)
{{
    char out[1024];

    ave_sm_handle_json("{display_json_c}");
    if (!ave_sm_build_listen_detect_json("看这个", out, sizeof(out))) {{
        fprintf(stderr, "build failed\\n");
        return 2;
    }}
    if (strstr(out, "\\"selection\\"")) {{
        fprintf(stderr, "unexpected selection in orders mode: %s\\n", out);
        return 3;
    }}
    return 0;
}}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_orders_listen_selection.c"
            binary = tmpdir_path / "verify_orders_listen_selection"
            source_path.write_text(harness_source, encoding="utf-8")

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    *[str(source) for source in common_sources],
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

    def test_real_portfolio_selection_emitter_omits_missing_chain_in_listen_payload(self):
        repo_root = Path(__file__).resolve().parents[3]
        self._assert_real_selection_emitter_missing_chain_fails_closed(
            screen_macro="VERIFY_PORTFOLIO",
            screen_source=repo_root / "shared/ave_screens/screen_portfolio.c",
            display_json=(
                '{"screen":"portfolio","data":{"holdings":['
                '{"addr":"pf-no-chain","symbol":"BROKEN","value_usd":"$1"}'
                "]}}"
            ),
        )

    def test_real_spotlight_selection_emitter_omits_missing_chain_in_listen_payload(self):
        repo_root = Path(__file__).resolve().parents[3]
        self._assert_real_selection_emitter_missing_chain_fails_closed(
            screen_macro="VERIFY_SPOTLIGHT",
            screen_source=repo_root / "shared/ave_screens/screen_spotlight.c",
            display_json=(
                '{"screen":"spotlight","data":{'
                '"token_id":"spot-no-chain",'
                '"symbol":"BROKEN",'
                '"price":"$1",'
                '"change_24h":"+1%",'
                '"chart":[1,2],'
                '"chart_min":"$1",'
                '"chart_max":"$2"'
                "}}"
            ),
            extra_sources=(repo_root / "shared/ave_screens/ave_price_fmt.c",),
            extra_ldflags=("-lm",),
        )

    def test_listen_detect_payload_generation_escapes_text_and_includes_selection(self):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        common_sources = self._common_screen_sources(repo_root)
        harness_source = r"""
#include <stdio.h>
#include <string.h>

#include "ave_screen_manager.h"

void ave_send_json(const char *json) { (void)json; }

void screen_feed_show(const char *json_data) { (void)json_data; }
void screen_feed_reveal(void) { }
void screen_feed_key(int key) { (void)key; }
bool screen_feed_should_ignore_live_push(void) { return false; }
int screen_feed_get_selected_context_json(char *out, size_t out_n)
{
    const char *selection =
        "{\"screen\":\"feed\",\"cursor\":2,\"token\":{\"addr\":\"feed\\\"2\",\"chain\":\"ba\\\\se\",\"symbol\":\"NE\\nW\"}}";
    int n = snprintf(out, out_n, "%s", selection);
    return (n > 0 && (size_t)n < out_n) ? 1 : 0;
}

void screen_spotlight_show(const char *json_data) { (void)json_data; }
void screen_spotlight_key(int key) { (void)key; }
void screen_spotlight_cancel_back_timer(void) {}
int screen_spotlight_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

void screen_confirm_show(const char *json_data) { (void)json_data; }
void screen_confirm_key(int key) { (void)key; }
void screen_confirm_cancel_timers(void) {}
int screen_confirm_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}
void screen_limit_confirm_show(const char *json_data) { (void)json_data; }
void screen_limit_confirm_key(int key) { (void)key; }
void screen_limit_confirm_cancel_timers(void) {}
int screen_limit_confirm_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}
void screen_result_show(const char *json_data) { (void)json_data; }
void screen_result_key(int key) { (void)key; }
void screen_result_cancel_timers(void) {}
int screen_result_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}
void screen_portfolio_show(const char *json_data) { (void)json_data; }
void screen_portfolio_key(int key) { (void)key; }
void screen_portfolio_cancel_back_timer(void) {}
int screen_portfolio_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}
void screen_notify_show(const char *json_data) { (void)json_data; }
bool screen_notify_is_visible(void) { return false; }
void screen_notify_key(int key) { (void)key; }
void screen_disambiguation_show(const char *json_data) { (void)json_data; }
void screen_disambiguation_key(int key) { (void)key; }
void screen_disambiguation_cancel_timers(void) { }
int screen_disambiguation_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

int main(void)
{
    char out[1024];
    const char *text = "buy \"this\"\\\\now\n";

    if (!ave_sm_build_listen_detect_json(text, out, sizeof(out))) {
        fprintf(stderr, "build failed\n");
        return 1;
    }
    if (!strstr(out, "\"type\":\"listen\"")) {
        fprintf(stderr, "missing listen type: %s\n", out);
        return 1;
    }
    if (!strstr(out, "buy \\\"this\\\"\\\\\\\\now\\n")) {
        fprintf(stderr, "text not escaped: %s\n", out);
        return 1;
    }
    if (!strstr(out, "\"selection\":{\"screen\":\"feed\",\"cursor\":2")) {
        fprintf(stderr, "selection missing: %s\n", out);
        return 1;
    }
    if (!strstr(out, "feed\\\"2")) {
        fprintf(stderr, "addr not preserved: %s\n", out);
        return 1;
    }
    if (!strstr(out, "ba\\\\se")) {
        fprintf(stderr, "chain not preserved: %s\n", out);
        return 1;
    }
    if (!strstr(out, "NE\\nW")) {
        fprintf(stderr, "symbol not preserved: %s\n", out);
        return 1;
    }

    return 0;
}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_listen_detect.c"
            binary = tmpdir_path / "verify_listen_detect"
            source_path.write_text(harness_source)

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    *[str(source) for source in common_sources],
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

    def test_listen_detect_payload_includes_authoritative_screen_for_confirm_limit_and_result(self):
        repo_root = Path(__file__).resolve().parents[3]
        include_dir = repo_root / "simulator/mock/json_verify_include"
        manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
        common_sources = self._common_screen_sources(repo_root)
        harness_source = r"""
#include <stdio.h>
#include <string.h>

#include "ave_screen_manager.h"

void ave_send_json(const char *json) { (void)json; }

void screen_feed_show(const char *json_data) { (void)json_data; }
void screen_feed_reveal(void) { }
void screen_feed_key(int key) { (void)key; }
bool screen_feed_should_ignore_live_push(void) { return false; }
int screen_feed_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

void screen_spotlight_show(const char *json_data) { (void)json_data; }
void screen_spotlight_key(int key) { (void)key; }
void screen_spotlight_cancel_back_timer(void) {}
int screen_spotlight_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

void screen_confirm_show(const char *json_data) { (void)json_data; }
void screen_confirm_key(int key) { (void)key; }
void screen_confirm_cancel_timers(void) {}
int screen_confirm_get_selected_context_json(char *out, size_t out_n)
{
    int n = snprintf(out, out_n, "%s", "{\"screen\":\"confirm\"}");
    return (n > 0 && (size_t)n < out_n) ? 1 : 0;
}

void screen_limit_confirm_show(const char *json_data) { (void)json_data; }
void screen_limit_confirm_key(int key) { (void)key; }
void screen_limit_confirm_cancel_timers(void) {}
int screen_limit_confirm_get_selected_context_json(char *out, size_t out_n)
{
    int n = snprintf(out, out_n, "%s", "{\"screen\":\"limit_confirm\"}");
    return (n > 0 && (size_t)n < out_n) ? 1 : 0;
}

void screen_result_show(const char *json_data) { (void)json_data; }
void screen_result_key(int key) { (void)key; }
void screen_result_cancel_timers(void) {}
int screen_result_get_selected_context_json(char *out, size_t out_n)
{
    int n = snprintf(out, out_n, "%s", "{\"screen\":\"result\"}");
    return (n > 0 && (size_t)n < out_n) ? 1 : 0;
}

void screen_portfolio_show(const char *json_data) { (void)json_data; }
void screen_portfolio_key(int key) { (void)key; }
void screen_portfolio_cancel_back_timer(void) {}
int screen_portfolio_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

void screen_notify_show(const char *json_data) { (void)json_data; }
bool screen_notify_is_visible(void) { return false; }
void screen_notify_key(int key) { (void)key; }

void screen_disambiguation_show(const char *json_data) { (void)json_data; }
void screen_disambiguation_key(int key) { (void)key; }
void screen_disambiguation_cancel_timers(void) {}
int screen_disambiguation_get_selected_context_json(char *out, size_t out_n)
{
    (void)out;
    (void)out_n;
    return 0;
}

static int expect_screen(const char *screen)
{
    char json[256];
    char out[512];
    char needle[64];

    snprintf(
        json,
        sizeof(json),
        "{\"type\":\"display\",\"screen\":\"%s\",\"data\":{\"trade_id\":\"trade-1\"}}",
        screen
    );
    ave_sm_handle_json(json);
    if (!ave_sm_build_listen_detect_json("确认", out, sizeof(out))) {
        fprintf(stderr, "build failed for %s\n", screen);
        return 0;
    }
    snprintf(needle, sizeof(needle), "\"selection\":{\"screen\":\"%s\"}", screen);
    if (!strstr(out, needle)) {
        fprintf(stderr, "missing authoritative screen %s in %s\n", screen, out);
        return 0;
    }
    return 1;
}

int main(void)
{
    if (!expect_screen("confirm")) return 1;
    if (!expect_screen("limit_confirm")) return 1;
    if (!expect_screen("result")) return 1;
    return 0;
}
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            source_path = tmpdir_path / "verify_listen_detect_screens.c"
            binary = tmpdir_path / "verify_listen_detect_screens"
            source_path.write_text(harness_source)

            compile_result = subprocess.run(
                [
                    os.environ.get("CC", "cc"),
                    "-std=c99",
                    f"-I{include_dir}",
                    f"-I{repo_root / 'shared/ave_screens'}",
                    str(source_path),
                    str(manager_src),
                    *[str(source) for source in common_sources],
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


if __name__ == "__main__":
    unittest.main()
