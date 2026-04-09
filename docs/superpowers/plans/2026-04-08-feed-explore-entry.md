# Feed Explore Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `B` on standard FEED home open a lightweight Explore panel with `Search`, `Orders`, and `Sources`, while leaving SEARCH / SPECIAL / ORDERS / SPOTLIGHT / CONFIRM / PORTFOLIO and every other non-standard-FEED `B` path unchanged.

**Architecture:** Keep Explore inside `shared/ave_screens/screen_feed.c` as FEED-local substate instead of adding new top-level `AVE_SCREEN_*` ids. That preserves the existing global `Y -> PORTFOLIO` behavior in `ave_screen_manager.c`, keeps non-standard FEED variants isolated, and limits server work to reusing current `ave_list_orders` and feed/platform loaders through two narrow `key_action` additions.

**Tech Stack:** C with LVGL shared screens, SDL simulator screenshot harness, C behavior verifiers, Python websocket/router tests, markdown product docs.

---

## File Structure

- `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_feed.c` - add FEED-local Explore substates, overlay rendering, Search guidance copy, Sources list rendering, and the standard-FEED-only `B` interception.
- `/home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.c` - intentionally unchanged; Explore stays FEED-local so global `Y -> PORTFOLIO` remains centralized and stable.
- `/home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.h` - intentionally unchanged; do not add new top-level screen ids for this scope.
- `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py` - add `orders` and `feed_platform` handlers so Explore destinations reuse existing server tools instead of inventing a new route family.
- `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_surface_input_sync.py` - prove Explore, Search guide, and Sources list do not emit trusted FEED selection into `listen.detect` payloads.
- `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_orders.py` - cover Explore -> Orders activation reusing the existing orders flow.
- `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_trade_flows.py` - cover Explore -> Sources platform activation and feed-state bookkeeping.
- `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_ave_voice_protocol.py` - keep simulator/docs assertions aligned with `FN/F1` remaining global and with the new Explore wording.
- `/home/jupiter/ave-xiaozhi/simulator/mock/verify_p3_5_minimal.c` - add deterministic behavior checks for standard FEED `B`, Explore navigation clamp, Search guide entry, Sources entry, unchanged non-standard FEED `B`, and global `Y`.
- `/home/jupiter/ave-xiaozhi/simulator/mock/verify_screenshot_feed.c` - add screenshot cases for `feed_explore_panel`, `feed_explore_search_guide`, and `feed_explore_sources`.
- `/home/jupiter/ave-xiaozhi/simulator/mock/run_screenshot_test.sh` - include the new Explore screenshot cases in the default gate.
- `/home/jupiter/ave-xiaozhi/simulator/mock/screenshot/baselines/feed_explore_panel.ppm` - new baseline proving FEED remains visible under the lightweight Explore panel.
- `/home/jupiter/ave-xiaozhi/simulator/mock/screenshot/baselines/feed_explore_search_guide.ppm` - new baseline proving the Search entry is guidance-only and includes `FN` copy.
- `/home/jupiter/ave-xiaozhi/simulator/mock/screenshot/baselines/feed_explore_sources.ppm` - new baseline proving the Sources entry opens a shallow chooser, not a full-screen replacement.
- `/home/jupiter/ave-xiaozhi/docs/simulator-ui-guide.md` - update the FEED key matrix and add Explore interaction details, including `F1/FN` staying unchanged.
- `/home/jupiter/ave-xiaozhi/docs/ave-feature-map.md` - update the implementation-aligned keymap row for FEED and document the Explore entry surface.
- `/home/jupiter/ave-xiaozhi/docs/product-surface-audit-2026-04-08.md` - update the FEED and key-surface audit rows so product docs no longer say standard FEED `B` only shows `已在首页`.
- Reuse `/home/jupiter/ave-xiaozhi/simulator/mock/mock_scenes/01_feed_bonk.json`, `/home/jupiter/ave-xiaozhi/simulator/mock/mock_scenes/10_feed_search.json`, `/home/jupiter/ave-xiaozhi/simulator/mock/mock_scenes/11_feed_special_source.json`, and `/home/jupiter/ave-xiaozhi/simulator/mock/mock_scenes/12_feed_orders.json`; do not add new mock scene JSON files for this scope.

## Scope Guardrails

- Keep `B` changes limited to standard FEED home inside `screen_feed.c`; SEARCH / SPECIAL / ORDERS / SPOTLIGHT / CONFIRM / PORTFOLIO must continue using their current handlers.
- Keep Explore shallow: one entry panel, one Search guidance surface, one Sources list surface; no text keyboard, no deep menu tree, no FN rebinding.
- Keep `X` unchanged: it still does nothing new while Explore is open.
- Keep FEED cursor and source stable when Explore opens or closes; opening Explore must not refresh FEED, change source, or reset the selected token.
- Keep `FN/F1` untouched: the Search entry only explains `FN 说币名`; it must not create a panel-specific voice mode.

### Task 1: Add FEED-local Explore and Search Guide behavior first

**Files:**
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_feed.c`
- Test: `/home/jupiter/ave-xiaozhi/simulator/mock/verify_p3_5_minimal.c`
- Test: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_surface_input_sync.py`

- [ ] **Step 1: Add RED simulator behavior coverage for standard FEED `B`, clamp/close behavior, Search guide entry, and lossless close**

```c
static const char *k_standard_feed_json =
    "{"
    "\"source_label\":\"TRENDING\","
    "\"tokens\":[{"
    "\"token_id\":\"token-1\","
    "\"chain\":\"solana\","
    "\"symbol\":\"BONK\","
    "\"price\":\"$1\","
    "\"change_24h\":\"+1%\","
    "\"change_positive\":1"
    "}]}";

static int expect_equal_int(int actual, int expected, const char *msg)
{
    if (actual != expected) {
        fprintf(stderr, "FAIL: %s (actual=%d expected=%d)\n", msg, actual, expected);
        return 0;
    }
    return 1;
}

static int run_case_feed_home_b_opens_explore_without_side_effects(void)
{
    int ok = 1;

    feed_under_test_show(k_standard_feed_json);
    s_token_idx = 0;
    clear_last_io();
    feed_under_test_key(AVE_KEY_B);

    ok &= expect_json_empty("standard FEED B should stay local until a destination is chosen");
    ok &= expect_notify_empty("standard FEED B should no longer show already-on-home notify");
    ok &= expect_equal_int(s_feed_surface, FEED_SURFACE_EXPLORE_PANEL,
                           "standard FEED B should enter Explore panel");
    ok &= expect_equal_int(s_explore_idx, 0,
                           "Explore panel should default to Search");
    ok &= expect_equal_int(s_token_idx, 0,
                           "opening Explore should preserve FEED cursor");
    return ok;
}

static int run_case_feed_explore_navigation_clamps_and_closes_losslessly(void)
{
    int ok = 1;

    feed_under_test_show(k_standard_feed_json);
    clear_last_io();
    feed_under_test_key(AVE_KEY_B);
    feed_under_test_key(AVE_KEY_UP);
    ok &= expect_equal_int(s_explore_idx, 0, "Explore UP should clamp at Search");

    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_DOWN);
    ok &= expect_equal_int(s_explore_idx, 2, "Explore DOWN should clamp at Sources");

    feed_under_test_key(AVE_KEY_LEFT);
    ok &= expect_equal_int(s_feed_surface, FEED_SURFACE_STANDARD,
                           "Explore LEFT should close back to standard FEED");
    ok &= expect_equal_int(s_token_idx, 0,
                           "closing Explore should preserve FEED cursor");
    ok &= expect_json_empty("closing Explore should not emit a server action");
    return ok;
}

static int run_case_feed_explore_search_entry_is_local(void)
{
    int ok = 1;

    feed_under_test_show(k_standard_feed_json);
    clear_last_io();
    feed_under_test_key(AVE_KEY_B);
    feed_under_test_key(AVE_KEY_A);

    ok &= expect_equal_int(s_feed_surface, FEED_SURFACE_EXPLORE_SEARCH_GUIDE,
                           "Search should open the local guidance surface");
    ok &= expect_json_empty("Search guide entry should not send a server action");
    return ok;
}
```

- [ ] **Step 2: Run the simulator behavior verifier and confirm it fails on the new Explore assertions**

```bash
cc -std=c99 -Wall -Wextra \
  -I/home/jupiter/ave-xiaozhi/simulator \
  -I/home/jupiter/ave-xiaozhi/shared/ave_screens \
  /home/jupiter/ave-xiaozhi/simulator/mock/verify_p3_5_minimal.c \
  /home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.c \
  -o /tmp/verify_p3_5_minimal && /tmp/verify_p3_5_minimal
```

Expected: FAIL with a new message such as `standard FEED B should enter Explore panel` or `Search should open the local guidance surface`.

- [ ] **Step 3: Add RED selection-emitter coverage so Explore surfaces do not hijack `FN` with stale FEED selection**

```python
def test_real_feed_explore_panel_omits_trusted_selection_in_listen_payload(self):
    repo_root = Path(__file__).resolve().parents[3]
    include_dir = repo_root / "simulator/mock/json_verify_include"
    manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
    screen_source = repo_root / "shared/ave_screens/screen_feed.c"
    verifier_prefix = (repo_root / "simulator/mock/verify_ave_json_payloads.c").read_text(
        encoding="utf-8"
    ).split("#if defined(VERIFY_FEED)", 1)[0]
    harness_source = f"""
#define VERIFY_FEED
{verifier_prefix}
#include "{screen_source}"
int main(void) {{
    char out[1024];
    ave_sm_handle_json("{{\"screen\":\"feed\",\"data\":{{\"source_label\":\"TRENDING\",\"tokens\":[{{\"token_id\":\"feed-1\",\"chain\":\"solana\",\"symbol\":\"BONK\",\"price\":\"$1\"}}]}}}}");
    screen_feed_key(AVE_KEY_B);
    if (!ave_sm_build_listen_detect_json("看这个", out, sizeof(out))) return 2;
    if (strstr(out, "\"selection\"")) return 3;
    return 0;
}}
"""
    self._compile_and_run_c_harness(harness_source, include_dir, manager_src)
```

Add the sibling helper once near the existing temporary-C-compilation helpers:

```python
def _compile_and_run_c_harness(self, harness_source, include_dir, manager_src):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        source_path = tmpdir_path / "verify_feed_explore_overlay.c"
        binary_path = tmpdir_path / "verify_feed_explore_overlay"
        source_path.write_text(harness_source, encoding="utf-8")
        compile_result = subprocess.run(
            [
                os.environ.get("CC", "cc"),
                "-std=c99",
                f"-I{include_dir}",
                f"-I{Path(__file__).resolve().parents[3] / 'shared/ave_screens'}",
                str(source_path),
                str(manager_src),
                "-o",
                str(binary_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(compile_result.returncode, 0, msg=compile_result.stdout + compile_result.stderr)
        run_result = subprocess.run([str(binary_path)], capture_output=True, text=True, check=False)
        self.assertEqual(run_result.returncode, 0, msg=run_result.stdout + run_result.stderr)
```

- [ ] **Step 4: Run the focused Python regression and confirm it fails before the FEED code changes land**

```bash
cd /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server && \
python3 -m pytest -q test_surface_input_sync.py -k "explore_panel"
```

Expected: FAIL because the current `screen_feed_get_selected_context_json()` still emits the FEED token selection and there is no Explore-mode suppression.

- [ ] **Step 5: Implement the minimal FEED-local Explore/Search Guide substate and selection guard in `screen_feed.c`**

```c
typedef enum {
    FEED_SURFACE_STANDARD = 0,
    FEED_SURFACE_EXPLORE_PANEL,
    FEED_SURFACE_EXPLORE_SEARCH_GUIDE,
    FEED_SURFACE_EXPLORE_SOURCES,
} feed_surface_t;

typedef struct {
    const char *title;
    const char *subtitle;
} feed_explore_item_t;

static const feed_explore_item_t EXPLORE_ITEMS[] = {
    {"Search", "FN 说币名"},
    {"Orders", "Open current orders list"},
    {"Sources", "Choose topic or platform"},
};

static feed_surface_t s_feed_surface = FEED_SURFACE_STANDARD;
static int s_explore_idx = 0;
static int s_source_menu_idx = 0;

static void _render_feed_surface(void)
{
    _update_mode_identity();
    _update_mode_hint();
    _update_rows();
    /* update the already-built Explore overlay widgets for panel, guide, and sources mode */
}

static int _feed_overlay_active(void)
{
    return s_feed_surface == FEED_SURFACE_EXPLORE_PANEL ||
           s_feed_surface == FEED_SURFACE_EXPLORE_SEARCH_GUIDE ||
           s_feed_surface == FEED_SURFACE_EXPLORE_SOURCES;
}

static int _is_standard_feed_home(void)
{
    return !s_is_orders_mode && !s_is_search_mode && !s_has_special_source_label &&
           s_feed_surface == FEED_SURFACE_STANDARD;
}

static void _open_explore_panel(void)
{
    s_feed_surface = FEED_SURFACE_EXPLORE_PANEL;
    s_explore_idx = 0;
    _render_feed_surface();
}

static void _close_feed_overlay(void)
{
    s_feed_surface = FEED_SURFACE_STANDARD;
    _render_feed_surface();
}

if (key == AVE_KEY_B && _is_standard_feed_home()) {
    _open_explore_panel();
    return;
}
if ((key == AVE_KEY_B || key == AVE_KEY_LEFT) && _feed_overlay_active()) {
    _close_feed_overlay();
    return;
}
if (s_feed_surface == FEED_SURFACE_EXPLORE_PANEL && (key == AVE_KEY_UP || key == AVE_KEY_DOWN)) {
    int next = s_explore_idx + (key == AVE_KEY_UP ? -1 : 1);
    if (next < 0) next = 0;
    if (next > 2) next = 2;
    s_explore_idx = next;
    _render_feed_surface();
    return;
}
if (s_feed_surface == FEED_SURFACE_EXPLORE_PANEL && (key == AVE_KEY_A || key == AVE_KEY_RIGHT) && s_explore_idx == 0) {
    s_feed_surface = FEED_SURFACE_EXPLORE_SEARCH_GUIDE;
    _render_feed_surface();
    return;
}

if (_feed_overlay_active()) return 0; /* no trusted selection while Explore overlays are active */
```

Implementation rules while editing the real file:
- Keep the existing SEARCH / SPECIAL / ORDERS branches intact; only standard FEED home gets the new `B` behavior.
- Extend `screen_feed_should_ignore_live_push()` so live FEED pushes do not blow away the local Explore/search-guide/source-list overlays.
- Keep `Y` untouched by leaving the screen manager global shortcut alone.

- [ ] **Step 6: Re-run the focused behavior and selection regressions until both pass**

```bash
cc -std=c99 -Wall -Wextra \
  -I/home/jupiter/ave-xiaozhi/simulator \
  -I/home/jupiter/ave-xiaozhi/shared/ave_screens \
  /home/jupiter/ave-xiaozhi/simulator/mock/verify_p3_5_minimal.c \
  /home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.c \
  -o /tmp/verify_p3_5_minimal && /tmp/verify_p3_5_minimal

cd /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server && \
python3 -m pytest -q test_surface_input_sync.py -k "explore_panel"
```

Expected:
- C verifier prints `PASS: P3-5 minimal simulator fallback verification succeeded.`
- Pytest reports the new Explore-panel selection test passing.

- [ ] **Step 7: Commit just the FEED-local state-machine work**

```bash
git add \
  /home/jupiter/ave-xiaozhi/shared/ave_screens/screen_feed.c \
  /home/jupiter/ave-xiaozhi/simulator/mock/verify_p3_5_minimal.c \
  /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_surface_input_sync.py && \
git commit -m "feat: add feed explore panel state machine"
```

### Task 2: Reuse existing Orders and Sources backends instead of inventing new flows

**Files:**
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_feed.c`
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
- Test: `/home/jupiter/ave-xiaozhi/simulator/mock/verify_p3_5_minimal.c`
- Test: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_orders.py`
- Test: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_trade_flows.py`

- [ ] **Step 1: Add RED server-side tests for Explore -> Orders and Explore -> Sources(platform)**

```python
async def test_key_action_orders_reuses_existing_orders_flow(self):
    loop = asyncio.get_running_loop()
    conn = _FakeConn(loop)
    handler = KeyActionHandler()

    with patch("plugins_func.functions.ave_tools.ave_list_orders") as mock_orders:
        await handler.handle(conn, {"type": "key_action", "action": "orders"})

    mock_orders.assert_called_once_with(conn, chain="solana")

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
```

- [ ] **Step 2: Add RED simulator probes for Explore item activation and Sources-list selection**

```c
static int run_case_feed_explore_orders_activation_reuses_orders_flow(void)
{
    int ok = 1;

    feed_under_test_show(k_standard_feed_json);
    clear_last_io();
    feed_under_test_key(AVE_KEY_B);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_A);

    ok &= expect_json_contains("\"action\":\"orders\"",
                               "Explore Orders should emit orders key_action");
    return ok;
}

static int run_case_feed_explore_sources_platform_activation_reuses_platform_feed(void)
{
    int ok = 1;

    feed_under_test_show(k_standard_feed_json);
    clear_last_io();
    feed_under_test_key(AVE_KEY_B);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_A);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_DOWN);
    feed_under_test_key(AVE_KEY_A);

    ok &= expect_json_contains("\"action\":\"feed_platform\"",
                               "Explore Sources should reuse the platform feed action");
    ok &= expect_json_contains("\"platform\":\"pump_in_hot\"",
                               "Explore Sources should use the existing platform tag values");
    return ok;
}
```

- [ ] **Step 3: Run the focused server and simulator tests and confirm they fail before the action wiring exists**

```bash
cd /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server && \
python3 -m pytest -q test_p3_orders.py test_p3_trade_flows.py

cc -std=c99 -Wall -Wextra \
  -I/home/jupiter/ave-xiaozhi/simulator \
  -I/home/jupiter/ave-xiaozhi/shared/ave_screens \
  /home/jupiter/ave-xiaozhi/simulator/mock/verify_p3_5_minimal.c \
  /home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.c \
  -o /tmp/verify_p3_5_minimal && /tmp/verify_p3_5_minimal
```

Expected: pytest fails on missing `orders` / `feed_platform` handling, and the C verifier fails on the new Explore-activation assertions.

- [ ] **Step 4: Implement the narrow action reuse in client and server**

```c
typedef enum {
    FEED_SOURCE_ENTRY_TOPIC = 0,
    FEED_SOURCE_ENTRY_PLATFORM,
} feed_source_entry_kind_t;

typedef struct {
    const char *label;
    const char *value;
    feed_source_entry_kind_t kind;
} feed_source_entry_t;

static const feed_source_entry_t SOURCE_MENU[] = {
    {"TRENDING", "trending", FEED_SOURCE_ENTRY_TOPIC},
    {"GAINER", "gainer", FEED_SOURCE_ENTRY_TOPIC},
    {"LOSER", "loser", FEED_SOURCE_ENTRY_TOPIC},
    {"NEW", "new", FEED_SOURCE_ENTRY_TOPIC},
    {"PUMP HOT", "pump_in_hot", FEED_SOURCE_ENTRY_PLATFORM},
    {"PUMP NEW", "pump_in_new", FEED_SOURCE_ENTRY_PLATFORM},
    {"4MEME HOT", "fourmeme_in_hot", FEED_SOURCE_ENTRY_PLATFORM},
    {"4MEME NEW", "fourmeme_in_new", FEED_SOURCE_ENTRY_PLATFORM},
};

static void _activate_source_entry(void)
{
    const feed_source_entry_t *entry = &SOURCE_MENU[s_source_menu_idx];
    char cmd[256];

    if (entry->kind == FEED_SOURCE_ENTRY_TOPIC) {
        snprintf(cmd, sizeof(cmd),
                 "{\"type\":\"key_action\",\"action\":\"feed_source\",\"source\":\"%s\"}",
                 entry->value);
    } else {
        snprintf(cmd, sizeof(cmd),
                 "{\"type\":\"key_action\",\"action\":\"feed_platform\",\"platform\":\"%s\"}",
                 entry->value);
    }
    ave_send_json(cmd);
    _close_feed_overlay();
}

static void _activate_explore_item(void)
{
    if (s_explore_idx == 1) {
        ave_send_json("{\"type\":\"key_action\",\"action\":\"orders\"}");
        _close_feed_overlay();
        return;
    }
    if (s_explore_idx == 2) {
        s_feed_surface = FEED_SURFACE_EXPLORE_SOURCES;
        s_source_menu_idx = 0;
        _render_feed_surface();
        return;
    }
}
```

```python
elif action == "orders":
    state = getattr(conn, "ave_state", {})
    chain = msg_json.get("chain") or state.get("last_orders_chain") or "solana"
    ave_list_orders(conn, chain=chain)

elif action == "feed_platform":
    platform = msg_json.get("platform", "")
    valid_platforms = {"pump_in_hot", "pump_in_new", "fourmeme_in_hot", "fourmeme_in_new"}
    if platform not in valid_platforms:
        logger.bind(tag=TAG).warning(f"feed_platform: unknown platform '{platform}'")
        return
    ave_get_trending(conn, topic="", platform=platform)
    state = getattr(conn, "ave_state", {})
    state["feed_source"] = "trending"
    state["feed_platform"] = platform
    conn.ave_state = state
```

Implementation rules while editing the real files:
- `Orders` must call the existing orders path directly; do not create a submenu.
- `Sources` must reuse the existing topic/platform capability; do not add a second routing layer.
- `B/LEFT` inside the source list must close back to unchanged standard FEED when no source is chosen.

- [ ] **Step 5: Re-run the focused reuse tests until they pass**

```bash
cd /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server && \
python3 -m pytest -q test_p3_orders.py test_p3_trade_flows.py

cc -std=c99 -Wall -Wextra \
  -I/home/jupiter/ave-xiaozhi/simulator \
  -I/home/jupiter/ave-xiaozhi/shared/ave_screens \
  /home/jupiter/ave-xiaozhi/simulator/mock/verify_p3_5_minimal.c \
  /home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.c \
  -o /tmp/verify_p3_5_minimal && /tmp/verify_p3_5_minimal
```

Expected:
- Pytest passes with the new `orders` and `feed_platform` tests green.
- The C verifier still prints `PASS: P3-5 minimal simulator fallback verification succeeded.` after the new Explore activation cases are added.

- [ ] **Step 6: Commit the Orders/Sources wiring separately**

```bash
git add \
  /home/jupiter/ave-xiaozhi/shared/ave_screens/screen_feed.c \
  /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py \
  /home/jupiter/ave-xiaozhi/simulator/mock/verify_p3_5_minimal.c \
  /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_orders.py \
  /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_trade_flows.py && \
git commit -m "feat: reuse orders and source actions from feed explore"
```

### Task 3: Add screenshot evidence and update implementation-facing docs

**Files:**
- Modify: `/home/jupiter/ave-xiaozhi/simulator/mock/verify_screenshot_feed.c`
- Modify: `/home/jupiter/ave-xiaozhi/simulator/mock/run_screenshot_test.sh`
- Modify/Create: `/home/jupiter/ave-xiaozhi/simulator/mock/screenshot/baselines/feed_explore_panel.ppm`
- Modify/Create: `/home/jupiter/ave-xiaozhi/simulator/mock/screenshot/baselines/feed_explore_search_guide.ppm`
- Modify/Create: `/home/jupiter/ave-xiaozhi/simulator/mock/screenshot/baselines/feed_explore_sources.ppm`
- Modify: `/home/jupiter/ave-xiaozhi/docs/simulator-ui-guide.md`
- Modify: `/home/jupiter/ave-xiaozhi/docs/ave-feature-map.md`
- Modify: `/home/jupiter/ave-xiaozhi/docs/product-surface-audit-2026-04-08.md`
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_ave_voice_protocol.py`

- [ ] **Step 1: Extend the screenshot gate with Explore cases and explicit label assertions**

```c
static const int k_keys_feed_open_explore[] = {AVE_KEY_B};
static const int k_keys_feed_open_search_guide[] = {AVE_KEY_B, AVE_KEY_A};
static const int k_keys_feed_open_sources[] = {AVE_KEY_B, AVE_KEY_DOWN, AVE_KEY_DOWN, AVE_KEY_A};

static const screenshot_case_t k_cases[] = {
    {"feed_explore_panel", "mock/mock_scenes/01_feed_bonk.json",
     "mock/screenshot/baselines/feed_explore_panel.ppm",
     k_keys_feed_open_explore, 1, 4, 0, NULL, 1},
    {"feed_explore_search_guide", "mock/mock_scenes/01_feed_bonk.json",
     "mock/screenshot/baselines/feed_explore_search_guide.ppm",
     k_keys_feed_open_search_guide, 2, 4, 0, NULL, 1},
    {"feed_explore_sources", "mock/mock_scenes/01_feed_bonk.json",
     "mock/screenshot/baselines/feed_explore_sources.ppm",
     k_keys_feed_open_sources, 4, 4, 0, NULL, 1},
};

if (strcmp(test_case->screen_name, "feed_explore_panel") == 0) {
    if (count_labels_with_text_recursive(scr, "Search") <= 0 ||
        count_labels_with_text_recursive(scr, "Orders") <= 0 ||
        count_labels_with_text_recursive(scr, "Sources") <= 0 ||
        count_labels_with_text_recursive(scr, "TRENDING") <= 0) {
        fprintf(stderr, "FAIL: [feed_explore_panel] expected FEED plus Search / Orders / Sources\n");
        return 0;
    }
}
if (strcmp(test_case->screen_name, "feed_explore_search_guide") == 0) {
    if (count_labels_containing_text_recursive(scr, "FN") <= 0 ||
        count_labels_containing_text_recursive(scr, "币名") <= 0) {
        fprintf(stderr, "FAIL: [feed_explore_search_guide] expected FN guidance copy\n");
        return 0;
    }
}
if (strcmp(test_case->screen_name, "feed_explore_sources") == 0) {
    if (count_labels_with_text_recursive(scr, "TRENDING") <= 0 ||
        count_labels_with_text_recursive(scr, "PUMP HOT") <= 0) {
        fprintf(stderr, "FAIL: [feed_explore_sources] expected source chooser entries\n");
        return 0;
    }
}
```

Also update `/home/jupiter/ave-xiaozhi/simulator/mock/run_screenshot_test.sh` so the default `SCREENS=(...)` list includes `feed_explore_panel`, `feed_explore_search_guide`, and `feed_explore_sources`.

- [ ] **Step 2: Build the screenshot verifier and generate the three new baselines after the UI is visually correct**

```bash
cd /home/jupiter/ave-xiaozhi/simulator && \
cmake -S . -B build >/dev/null && \
cmake --build build --target verify_screenshot_feed -j4 >/dev/null && \
./bin/verify_screenshot_feed --update-baseline --screen feed_explore_panel && \
./bin/verify_screenshot_feed --update-baseline --screen feed_explore_search_guide && \
./bin/verify_screenshot_feed --update-baseline --screen feed_explore_sources
```

Expected:
- `PASS: [feed_explore_panel] baseline updated at mock/screenshot/baselines/feed_explore_panel.ppm`
- `PASS: [feed_explore_search_guide] baseline updated at mock/screenshot/baselines/feed_explore_search_guide.ppm`
- `PASS: [feed_explore_sources] baseline updated at mock/screenshot/baselines/feed_explore_sources.ppm`

- [ ] **Step 3: Re-run the full screenshot gate so Explore is part of the normal simulator regression suite**

```bash
cd /home/jupiter/ave-xiaozhi/simulator && ./mock/run_screenshot_test.sh
```

Expected: every listed case passes, ending with `PASS: screenshot regression gate passed for all`, including the three new Explore cases.

- [ ] **Step 4: Update the docs and doc-backed assertions only after behavior and screenshots are locked**

```md
| FEED | select up | select down | standard: refresh current source; SEARCH/SPECIAL/ORDERS: disabled | standard/SEARCH/SPECIAL: open SPOTLIGHT; ORDERS: disabled | standard/SEARCH/SPECIAL: open SPOTLIGHT; ORDERS: disabled | standard: open Explore panel; SEARCH/SPECIAL: restore standard source; ORDERS: exit orders | standard: cycle source; SEARCH/SPECIAL/ORDERS: disabled | global -> PORTFOLIO |
```

```md
- Explore is available only on standard FEED home.
- Entries: `Search`, `Orders`, `Sources`.
- `UP/DOWN` move; `A/RIGHT` activate; `B/LEFT` close; `Y` still goes to `PORTFOLIO`; `X` gets no new meaning.
- Search guidance is copy-only (`FN 说币名`); `F1/FN` keeps the existing manual listen start/stop behavior.
```

```python
def test_simulator_doc_covers_feed_explore_without_rebinding_fn(self):
    repo_root = Path(__file__).resolve().parents[3]
    simulator_doc = (repo_root / "docs" / "simulator-ui-guide.md").read_text(encoding="utf-8")

    self.assertIn("Explore", simulator_doc)
    self.assertIn("Search", simulator_doc)
    self.assertIn("Orders", simulator_doc)
    self.assertIn("Sources", simulator_doc)
    self.assertIn("FN 说币名", simulator_doc)
    self.assertIn("F1", simulator_doc)
```

Update the real markdown files with these exact content changes:
- `docs/simulator-ui-guide.md`: FEED key table, Explore interaction subsection, and `F1/FN` note.
- `docs/ave-feature-map.md`: current keymap row, FEED notes, and visual verification section listing `feed_explore_panel`, `feed_explore_search_guide`, and `feed_explore_sources`.
- `docs/product-surface-audit-2026-04-08.md`: FEED row, `B` key row, and the P0 commentary about discoverability.

- [ ] **Step 5: Run the docs-oriented regression checks**

```bash
cd /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server && \
python3 -m pytest -q test_ave_voice_protocol.py

cd /home/jupiter/ave-xiaozhi && \
rg -n "Explore|FN 说币名|feed_platform|Orders|Sources" \
  docs/simulator-ui-guide.md \
  docs/ave-feature-map.md \
  docs/product-surface-audit-2026-04-08.md
```

Expected:
- `test_ave_voice_protocol.py` passes.
- `rg` returns matches from all three docs, proving the docs reflect the new Explore behavior and unchanged `FN` semantics.

- [ ] **Step 6: Commit screenshot coverage and docs separately from behavior code**

```bash
git add \
  /home/jupiter/ave-xiaozhi/simulator/mock/verify_screenshot_feed.c \
  /home/jupiter/ave-xiaozhi/simulator/mock/run_screenshot_test.sh \
  /home/jupiter/ave-xiaozhi/simulator/mock/screenshot/baselines/feed_explore_panel.ppm \
  /home/jupiter/ave-xiaozhi/simulator/mock/screenshot/baselines/feed_explore_search_guide.ppm \
  /home/jupiter/ave-xiaozhi/simulator/mock/screenshot/baselines/feed_explore_sources.ppm \
  /home/jupiter/ave-xiaozhi/docs/simulator-ui-guide.md \
  /home/jupiter/ave-xiaozhi/docs/ave-feature-map.md \
  /home/jupiter/ave-xiaozhi/docs/product-surface-audit-2026-04-08.md \
  /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_ave_voice_protocol.py && \
git commit -m "test: add feed explore screenshots and docs"
```

### Task 4: Run the integrated verification pass and lock the scope before merge

**Files:**
- Review: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_feed.c`
- Review: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
- Review: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_surface_input_sync.py`
- Review: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_orders.py`
- Review: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_trade_flows.py`
- Review: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_ave_voice_protocol.py`
- Review: `/home/jupiter/ave-xiaozhi/simulator/mock/verify_p3_5_minimal.c`
- Review: `/home/jupiter/ave-xiaozhi/simulator/mock/verify_screenshot_feed.c`
- Review: `/home/jupiter/ave-xiaozhi/docs/simulator-ui-guide.md`
- Review: `/home/jupiter/ave-xiaozhi/docs/ave-feature-map.md`
- Review: `/home/jupiter/ave-xiaozhi/docs/product-surface-audit-2026-04-08.md`

- [ ] **Step 1: Run the full Python regression set that this change can realistically affect**

```bash
cd /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server && \
python3 -m pytest -q \
  test_surface_input_sync.py \
  test_p3_orders.py \
  test_p3_trade_flows.py \
  test_ave_router.py \
  test_ave_voice_protocol.py
```

Expected: all tests pass; no failures mentioning `feed`, `orders`, `feed_platform`, `listen`, or doc assertions.

- [ ] **Step 2: Run the simulator behavior, screenshot, and keymap checks together**

```bash
cc -std=c99 -Wall -Wextra \
  -I/home/jupiter/ave-xiaozhi/simulator \
  -I/home/jupiter/ave-xiaozhi/shared/ave_screens \
  /home/jupiter/ave-xiaozhi/simulator/mock/verify_p3_5_minimal.c \
  /home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.c \
  -o /tmp/verify_p3_5_minimal && /tmp/verify_p3_5_minimal

cd /home/jupiter/ave-xiaozhi/simulator && \
./mock/run_screenshot_test.sh && \
cmake --build build --target verify_simulator_keymap -j4 >/dev/null && \
./bin/verify_simulator_keymap
```

Expected:
- `/tmp/verify_p3_5_minimal` prints `PASS: P3-5 minimal simulator fallback verification succeeded.`
- Screenshot gate passes all cases, including the new Explore ones.
- `./bin/verify_simulator_keymap` prints `PASS: simulator keymap + FN/PTT checks passed.`

- [ ] **Step 3: Run one final scope grep to ensure standard FEED changed but non-standard FEED behavior stayed documented and tested as before**

```bash
cd /home/jupiter/ave-xiaozhi && \
rg -n "已在首页|open Explore panel|SEARCH/SPECIAL|ORDERS|Y PORTFOLIO|FN 说币名" \
  docs/simulator-ui-guide.md \
  docs/ave-feature-map.md \
  docs/product-surface-audit-2026-04-08.md \
  shared/ave_screens/screen_feed.c \
  simulator/mock/verify_p3_5_minimal.c
```

Expected:
- Standard FEED references now mention Explore.
- SEARCH / SPECIAL / ORDERS references still mention their old `B` semantics.
- `已在首页` only remains where the text is intentionally historical or non-standard, not as the current standard FEED behavior.

- [ ] **Step 4: Verify the worktree is either clean or contains only the intended FEED Explore changes**

```bash
git status --short
```

Expected: a clean worktree if everything was already committed, or only the intended FEED Explore files listed in Tasks 1-3.

Plan complete and saved to `docs/superpowers/plans/2026-04-08-feed-explore-entry.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
