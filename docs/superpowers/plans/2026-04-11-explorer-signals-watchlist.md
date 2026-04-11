# Explorer Signals And Watchlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `Signals` and `Watchlist` as shallow `FEED -> Explore` entries, support voice-first watchlist add/remove, and show a non-interactive watchlist star state in `SPOTLIGHT`.

**Architecture:** Reuse the existing `feed` screen as the browse host for `signals` and `watchlist` modes instead of creating new global pages. Add a small JSON-backed watchlist store on the server, expose server tools and direct voice routes for signals/watchlist flows, and enrich `spotlight` payloads with `origin_hint` plus `is_watchlisted` so the device can render the final-row star without changing key semantics. Preserve and integrate with the current dirty `shared/ave_screens/screen_spotlight.c` worktree state rather than overwriting unrelated local edits.

**Tech Stack:** Python server tools/router (`pytest`), C LVGL screen code, simulator mock verifiers, screenshot baselines.

---

## File Structure

- Create: `server/main/xiaozhi-server/plugins_func/functions/ave_watchlist_store.py`
  - JSON-backed watchlist persistence keyed by AVE wallet / fallback namespace
  - add/list/remove/is_watchlisted helpers with deterministic row normalization
- Create: `server/main/xiaozhi-server/test_ave_watchlist_store.py`
  - unit coverage for add/remove/dedupe/list ordering and namespace isolation
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
  - signal row shaping
  - watchlist feed row shaping
  - watchlist add/remove/open helpers
  - spotlight payload enrichment for `origin_hint` and `is_watchlisted`
- Modify: `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py`
  - direct voice routing for `打开观察列表` / `收藏这个币` / `取消收藏`
  - allowed-action exposure for spotlight/watchlist state
- Modify: `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
  - new `signals`, `watchlist`, and `watchlist_remove` actions
  - preserve cursor + feed-mode state across spotlight entry/removal refreshes
- Modify: `server/main/xiaozhi-server/test_ave_router.py`
  - direct-routing and fail-closed selection tests for watchlist voice intents
- Create: `server/main/xiaozhi-server/test_ave_signals_watchlist_tools.py`
  - server display payload tests for signals/watchlist feeds and spotlight refresh after add/remove
- Modify: `shared/ave_screens/screen_feed.c`
  - add Explore items `Signals` and `Watchlist`
  - add browse-only feed modes `signals` / `watchlist`
  - add two-line row rendering support and `X Remove` only in watchlist mode
- Modify: `shared/ave_screens/screen_spotlight.c`
  - add display-only `☆ / ★` state on row 4 right side
  - add compact origin hint rendering (`From Signal`, `In Watchlist`)
- Modify: `server/main/xiaozhi-server/test_surface_input_sync.py`
  - compiled-harness checks for feed explore labels, watchlist remove key action, and spotlight star/origin labels
- Modify: `simulator/mock/verify_p3_5_minimal.c`
  - behavioral regression checks for Explore -> Signals/Watchlist and watchlist remove refresh
- Modify: `simulator/mock/verify_ave_json_payloads.c`
  - spotlight payload layout checks for star placement and origin hint
- Modify: `simulator/mock/verify_screenshot_feed.c`
  - add screenshot cases for `feed_signals` and `feed_watchlist`
  - update Explore panel label assertions to include the two new entries
- Create: `simulator/mock/mock_scenes/16_feed_signals.json`
- Create: `simulator/mock/mock_scenes/17_feed_watchlist.json`
- Create: `simulator/mock/screenshot/baselines/feed_signals.ppm`
- Create: `simulator/mock/screenshot/baselines/feed_watchlist.ppm`
- Modify: `simulator/mock/screenshot/baselines/feed_explore_panel.ppm`
- Modify: `simulator/mock/screenshot/baselines/spotlight.ppm`
- Modify: `docs/ave-feature-map.md`
- Modify: `docs/ave-page-feature-inventory-2026-04-10.md`

### Task 1: Build The Watchlist Store

**Files:**
- Create: `server/main/xiaozhi-server/plugins_func/functions/ave_watchlist_store.py`
- Test: `server/main/xiaozhi-server/test_ave_watchlist_store.py`

- [ ] **Step 1: Write the failing watchlist persistence tests**

```python
import tempfile
import unittest
from pathlib import Path

from plugins_func.functions.ave_watchlist_store import (
    add_watchlist_entry,
    list_watchlist_entries,
    remove_watchlist_entry,
    watchlist_contains,
)


class WatchlistStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.tmp.name) / "watchlists.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_dedupes_by_addr_and_chain(self):
        add_watchlist_entry(
            self.store_path,
            "wallet-1",
            {"addr": "So111", "chain": "solana", "symbol": "BONK", "added_at": "2026-04-11T10:00:00Z"},
        )
        add_watchlist_entry(
            self.store_path,
            "wallet-1",
            {"addr": "So111", "chain": "solana", "symbol": "BONK", "added_at": "2026-04-11T10:01:00Z"},
        )

        rows = list_watchlist_entries(self.store_path, "wallet-1")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "BONK")
        self.assertTrue(watchlist_contains(self.store_path, "wallet-1", "So111", "solana"))

    def test_remove_only_affects_matching_namespace(self):
        add_watchlist_entry(self.store_path, "wallet-1", {"addr": "So111", "chain": "solana", "symbol": "BONK"})
        add_watchlist_entry(self.store_path, "wallet-2", {"addr": "So111", "chain": "solana", "symbol": "BONK"})

        removed = remove_watchlist_entry(self.store_path, "wallet-1", "So111", "solana")

        self.assertTrue(removed)
        self.assertEqual(list_watchlist_entries(self.store_path, "wallet-1"), [])
        self.assertEqual(len(list_watchlist_entries(self.store_path, "wallet-2")), 1)
```

- [ ] **Step 2: Run the store test file and verify it fails**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_ave_watchlist_store.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'plugins_func.functions.ave_watchlist_store'`

- [ ] **Step 3: Write the minimal JSON-backed store implementation**

```python
import json
from pathlib import Path


def _load_store(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _save_store(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)


def _normalize_entry(entry: dict) -> dict:
    return {
        "addr": str(entry.get("addr") or "").strip(),
        "chain": str(entry.get("chain") or "").strip().lower(),
        "symbol": str(entry.get("symbol") or "?").strip() or "?",
        "added_at": str(entry.get("added_at") or ""),
    }


def list_watchlist_entries(path: Path, namespace: str) -> list[dict]:
    store = _load_store(path)
    rows = store.get(namespace, [])
    return [row for row in rows if isinstance(row, dict)]


def add_watchlist_entry(path: Path, namespace: str, entry: dict) -> list[dict]:
    store = _load_store(path)
    normalized = _normalize_entry(entry)
    rows = [row for row in store.get(namespace, []) if isinstance(row, dict)]
    rows = [row for row in rows if not (row.get("addr") == normalized["addr"] and row.get("chain") == normalized["chain"])]
    rows.insert(0, normalized)
    store[namespace] = rows
    _save_store(path, store)
    return rows


def remove_watchlist_entry(path: Path, namespace: str, addr: str, chain: str) -> bool:
    store = _load_store(path)
    rows = [row for row in store.get(namespace, []) if isinstance(row, dict)]
    kept = [row for row in rows if not (row.get("addr") == addr and row.get("chain") == chain)]
    changed = len(kept) != len(rows)
    store[namespace] = kept
    _save_store(path, store)
    return changed


def watchlist_contains(path: Path, namespace: str, addr: str, chain: str) -> bool:
    return any(
        row.get("addr") == addr and row.get("chain") == chain
        for row in list_watchlist_entries(path, namespace)
    )
```

- [ ] **Step 4: Run the store tests and verify they pass**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_ave_watchlist_store.py -v`

Expected: PASS with both `WatchlistStoreTests` cases green

- [ ] **Step 5: Commit the isolated store layer**

```bash
cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32
git add server/main/xiaozhi-server/plugins_func/functions/ave_watchlist_store.py \
        server/main/xiaozhi-server/test_ave_watchlist_store.py
git commit -m "feat: add AVE watchlist store"
```

### Task 2: Add Signals And Watchlist Server Tools

**Files:**
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
- Create: `server/main/xiaozhi-server/test_ave_signals_watchlist_tools.py`
- Reuse: `server/main/xiaozhi-server/plugins_func/functions/ave_watchlist_store.py`

- [ ] **Step 1: Write failing tool tests for signals feed, watchlist feed, and watchlist refresh**

```python
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from plugins_func.functions import ave_tools


class SignalsWatchlistToolTests(unittest.TestCase):
    def setUp(self):
        self.conn = SimpleNamespace(loop=asyncio.new_event_loop(), ave_state={})

    def tearDown(self):
        self.conn.loop.close()

    def test_ave_list_signals_sends_feed_payload_with_signals_mode(self):
        signal_payload = {
            "data": {
                "list": [
                    {
                        "symbol": "PUMP",
                        "token": "Token111",
                        "chain": "solana",
                        "signal_type": "SMART_MONEY",
                        "headline": "Smart buy x12",
                        "signal_time": "2026-04-11 10:00:00",
                    }
                ]
            }
        }

        with patch.object(ave_tools, "_data_get", return_value=signal_payload), \
             patch.object(ave_tools, "_send_display", new=AsyncMock()) as send_display:
            ave_tools.ave_list_signals(self.conn)
            self.conn.loop.run_until_complete(asyncio.sleep(0))

        screen, payload = send_display.await_args.args[1], send_display.await_args.args[2]
        self.assertEqual(screen, "feed")
        self.assertEqual(payload["mode"], "signals")
        self.assertEqual(payload["source_label"], "SIGNALS")
        self.assertEqual(payload["tokens"][0]["token_id"], "Token111")

    def test_watchlist_remove_key_action_refreshes_watchlist_feed(self):
        self.conn.ave_state = {
            "screen": "feed",
            "feed_mode": "watchlist",
            "feed_cursor": 0,
            "feed_token_list": [{"addr": "Token111", "chain": "solana", "symbol": "BONK"}],
            "current_token": {"addr": "Token111", "chain": "solana", "symbol": "BONK"},
        }

        with patch.object(ave_tools, "remove_watchlist_entry", return_value=True) as remove_entry, \
             patch.object(ave_tools, "ave_open_watchlist") as open_watchlist:
            ave_tools.ave_remove_current_watchlist_token(self.conn)

        remove_entry.assert_called_once()
        open_watchlist.assert_called_once_with(self.conn)
```

- [ ] **Step 2: Run the tool tests and verify they fail**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_ave_signals_watchlist_tools.py -v`

Expected: FAIL because `ave_list_signals`, `ave_open_watchlist`, and `ave_remove_current_watchlist_token` do not exist yet

- [ ] **Step 3: Implement the server tool layer and key-action wiring**

```python
from datetime import datetime, timezone
from pathlib import Path

from plugins_func.functions.ave_watchlist_store import (
    add_watchlist_entry,
    list_watchlist_entries,
    remove_watchlist_entry,
    watchlist_contains,
)

_WATCHLIST_STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "ave_watchlists.json"


def _watchlist_namespace(conn: "ConnectionHandler") -> str:
    return os.environ.get("AVE_PROXY_WALLET_ID", "default").strip() or "default"


def _build_signal_rows(items: list[dict]) -> list[dict]:
    rows = []
    for item in items:
        identity = _asset_identity_fields(
            {
                "token_id": item.get("token"),
                "chain": item.get("chain"),
                "symbol": item.get("symbol"),
                "source": "signals",
            }
        )
        rows.append(
            {
                **identity,
                "signal_type": str(item.get("signal_type") or "").strip(),
                "headline": str(item.get("headline") or "").strip(),
                "detail_right": str(item.get("action_type") or "").strip(),
                "change_24h": _fmt_change(item.get("price_change_24h")),
                "change_positive": float(item.get("price_change_24h", 0) or 0) >= 0,
                "price": _fmt_price(item.get("first_signal_price") or item.get("price") or 0),
            }
        )
    return rows[:20]


def _empty_feed_row(symbol: str, subtitle: str) -> dict:
    return {
        "token_id": "",
        "chain": "solana",
        "symbol": symbol,
        "price": "--",
        "change_24h": "--",
        "change_positive": True,
        "headline": subtitle,
        "signal_type": "",
    }


def _build_watchlist_rows(saved_rows: list[dict]) -> list[dict]:
    rows = []
    for row in saved_rows[:20]:
        identity = _asset_identity_fields(
            {
                "addr": row.get("addr"),
                "chain": row.get("chain"),
                "symbol": row.get("symbol"),
                "source": "watchlist",
            }
        )
        rows.append(
            {
                **identity,
                "headline": "Saved token",
                "price": "--",
                "change_24h": "--",
                "change_positive": True,
            }
        )
    return rows


@register_function("ave_list_signals", ave_list_signals_desc, ToolType.SYSTEM_CTL)
def ave_list_signals(conn: "ConnectionHandler"):
    resp = _data_get("/signals/public/list", {"limit": 20})
    raw = resp.get("data", {})
    items = raw.get("list", raw) if isinstance(raw, dict) else raw
    rows = _build_signal_rows(items if isinstance(items, list) else [])
    state = _ensure_ave_state(conn)
    state["screen"] = "feed"
    state["feed_mode"] = "signals"
    state["feed_source"] = "signals"
    state["feed_platform"] = ""
    _set_feed_navigation_state(state, rows, cursor=0)
    conn.loop.create_task(_send_display(conn, "feed", {"tokens": rows or [_empty_feed_row("SIGNALS", "No signals now")], "mode": "signals", "source_label": "SIGNALS"}))
    return ActionResponse(action=Action.NONE, result=f"signals:{len(rows)}", response=None)


def ave_open_watchlist(conn: "ConnectionHandler"):
    namespace = _watchlist_namespace(conn)
    saved = list_watchlist_entries(_WATCHLIST_STORE_PATH, namespace)
    rows = _build_watchlist_rows(saved)
    state = _ensure_ave_state(conn)
    state["screen"] = "feed"
    state["feed_mode"] = "watchlist"
    state["feed_source"] = "watchlist"
    _set_feed_navigation_state(state, rows, cursor=0)
    conn.loop.create_task(_send_display(conn, "feed", {"tokens": rows or [_empty_feed_row("WATCHLIST", "Watchlist empty")], "mode": "watchlist", "source_label": "WATCHLIST"}))
    return ActionResponse(action=Action.NONE, result=f"watchlist:{len(rows)}", response=None)


def ave_remove_current_watchlist_token(conn: "ConnectionHandler"):
    state = _ensure_ave_state(conn)
    current = state.get("current_token") or {}
    removed = remove_watchlist_entry(
        _WATCHLIST_STORE_PATH,
        _watchlist_namespace(conn),
        str(current.get("addr") or ""),
        str(current.get("chain") or ""),
    )
    if removed:
        conn.loop.create_task(_send_display(conn, "notify", {"level": "info", "title": "Watchlist", "body": "Removed from watchlist"}))
    return ave_open_watchlist(conn)
```

```python
elif action == "signals":
    ave_list_signals(conn)
elif action == "watchlist":
    ave_open_watchlist(conn)
elif action == "watchlist_remove":
    ave_remove_current_watchlist_token(conn)
```

- [ ] **Step 4: Run the new tool tests and existing server regressions**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_ave_watchlist_store.py test_ave_signals_watchlist_tools.py test_trade_contract_fixes.py -v`

Expected: PASS; signal/watchlist tools send `feed` payloads with `mode in {"signals","watchlist"}` and key-action routing still keeps trade-contract fixes green

- [ ] **Step 5: Commit the server tool layer**

```bash
cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32
git add server/main/xiaozhi-server/plugins_func/functions/ave_tools.py \
        server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py \
        server/main/xiaozhi-server/test_ave_signals_watchlist_tools.py \
        server/main/xiaozhi-server/plugins_func/functions/ave_watchlist_store.py \
        server/main/xiaozhi-server/test_ave_watchlist_store.py
git commit -m "feat: add signals and watchlist server flows"
```

### Task 3: Route Voice Commands And Spotlight Refresh

**Files:**
- Modify: `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py`
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `server/main/xiaozhi-server/test_ave_router.py`
- Modify: `server/main/xiaozhi-server/test_ave_signals_watchlist_tools.py`

- [ ] **Step 1: Write failing router tests for add/remove/open watchlist**

```python
async def test_spotlight_add_to_watchlist_routes_directly(self):
    conn = self._build_listen_conn(
        {"screen": "spotlight", "current_token": {"addr": "a1", "chain": "solana", "symbol": "BONK"}}
    )

    with patch("plugins_func.functions.ave_tools.ave_add_current_watchlist_token") as add_current:
        handled = await try_route_ave_command(
            conn,
            "收藏这个币",
            {"selection": {"screen": "spotlight", "token": {"addr": "a1", "chain": "solana", "symbol": "BONK"}}},
        )

    self.assertTrue(handled)
    add_current.assert_called_once_with(conn)


async def test_add_to_watchlist_without_trusted_selection_fails_closed(self):
    conn = self._build_listen_conn({"screen": "spotlight"})

    with patch("core.handle.textHandler.aveCommandRouter.send_stt_message", new=AsyncMock()) as send_stt:
        handled = await try_route_ave_command(conn, "收藏这个币", None)

    self.assertTrue(handled)
    send_stt.assert_awaited_once()


async def test_open_watchlist_routes_without_llm(self):
    conn = self._build_listen_conn({"screen": "feed"})

    with patch("plugins_func.functions.ave_tools.ave_open_watchlist") as open_watchlist:
        handled = await try_route_ave_command(conn, "打开观察列表", None)

    self.assertTrue(handled)
    open_watchlist.assert_called_once_with(conn)
```

- [ ] **Step 2: Run the router tests and verify they fail**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_ave_router.py -k "watchlist" -v`

Expected: FAIL because the new watchlist command sets and handlers are not defined

- [ ] **Step 3: Implement direct command sets, allowed actions, and spotlight refresh after add/remove**

```python
_OPEN_WATCHLIST_COMMANDS = {"打开观察列表", "查看观察列表", "watchlist"}
_ADD_WATCHLIST_COMMANDS = {"收藏这个币", "加入观察列表", "收藏它"}
_REMOVE_WATCHLIST_COMMANDS = {"取消收藏", "从观察列表移除", "移除这个币"}


def _build_allowed_actions(screen, current_token, pending_trade, has_trusted_selection):
    actions = {"search_symbol", "open_feed", "open_portfolio", "back_to_feed", "open_watchlist"}
    if screen in {"feed", "portfolio", "spotlight"} and current_token and has_trusted_selection:
        actions.add("watch_current")
    if screen == "spotlight" and current_token and has_trusted_selection:
        actions.add("buy_current")
        actions.add("add_to_watchlist")
        actions.add("remove_from_watchlist")
    if screen in {"confirm", "limit_confirm"} and pending_trade.get("trade_id"):
        actions.add("confirm_trade")
        actions.add("cancel_trade")
    return sorted(actions)


if normalized in _OPEN_WATCHLIST_COMMANDS:
    await _handle_tool_response(conn, ave_tools.ave_open_watchlist(conn))
    _refresh_turn_context()
    return True

if normalized in _ADD_WATCHLIST_COMMANDS:
    token = _resolve_selection_token(selection_payload) if has_trusted_selection(selection_payload) else None
    if not token:
        await _send_router_reply(conn, missing_selection_reply(utterance))
        return True
    await _handle_tool_response(conn, ave_tools.ave_add_current_watchlist_token(conn))
    _refresh_turn_context()
    return True

if normalized in _REMOVE_WATCHLIST_COMMANDS:
    token = _resolve_selection_token(selection_payload) if has_trusted_selection(selection_payload) else None
    if not token:
        await _send_router_reply(conn, missing_selection_reply(utterance))
        return True
    await _handle_tool_response(conn, ave_tools.ave_remove_current_watchlist_voice(conn))
    _refresh_turn_context()
    return True
```

```python
def ave_add_current_watchlist_token(conn: "ConnectionHandler"):
    state = _ensure_ave_state(conn)
    current = state.get("current_token") or {}
    entry = {
        "addr": current.get("addr", ""),
        "chain": current.get("chain", ""),
        "symbol": current.get("symbol", "?"),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    add_watchlist_entry(_WATCHLIST_STORE_PATH, _watchlist_namespace(conn), entry)

    conn.loop.create_task(_send_display(conn, "notify", {"level": "info", "title": "Watchlist", "body": "Added to watchlist"}))
    return ave_token_detail(
        conn,
        addr=str(current.get("addr") or ""),
        chain=str(current.get("chain") or "solana"),
        symbol=str(current.get("symbol") or ""),
        feed_cursor=state.get("feed_cursor"),
        feed_total=len(state.get("feed_token_list", [])) if isinstance(state.get("feed_token_list"), list) else None,
    )


def ave_remove_current_watchlist_voice(conn: "ConnectionHandler"):
    state = _ensure_ave_state(conn)
    current = state.get("current_token") or {}
    remove_watchlist_entry(
        _WATCHLIST_STORE_PATH,
        _watchlist_namespace(conn),
        str(current.get("addr") or ""),
        str(current.get("chain") or ""),
    )
    conn.loop.create_task(_send_display(conn, "notify", {"level": "info", "title": "Watchlist", "body": "Removed from watchlist"}))
    return ave_token_detail(
        conn,
        addr=str(current.get("addr") or ""),
        chain=str(current.get("chain") or "solana"),
        symbol=str(current.get("symbol") or ""),
        feed_cursor=state.get("feed_cursor"),
        feed_total=len(state.get("feed_token_list", [])) if isinstance(state.get("feed_token_list"), list) else None,
    )
```

- [ ] **Step 4: Run router and spotlight-refresh tests**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_ave_router.py -k "watchlist" -v && python3 -m pytest test_ave_signals_watchlist_tools.py -k "spotlight or watchlist" -v`

Expected: PASS; add/remove/open watchlist routes stay inside the direct-command layer, and add/remove emits an updated `spotlight` display with the new watchlist state

- [ ] **Step 5: Commit the voice-router layer**

```bash
cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32
git add server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py \
        server/main/xiaozhi-server/plugins_func/functions/ave_tools.py \
        server/main/xiaozhi-server/test_ave_router.py \
        server/main/xiaozhi-server/test_ave_signals_watchlist_tools.py
git commit -m "feat: route AVE watchlist voice commands"
```

### Task 4: Extend FEED Explore And Browse Modes

**Files:**
- Modify: `shared/ave_screens/screen_feed.c`
- Modify: `server/main/xiaozhi-server/test_surface_input_sync.py`
- Modify: `simulator/mock/verify_p3_5_minimal.c`
- Modify: `simulator/mock/verify_screenshot_feed.c`
- Create: `simulator/mock/mock_scenes/16_feed_signals.json`
- Create: `simulator/mock/mock_scenes/17_feed_watchlist.json`
- Create: `simulator/mock/screenshot/baselines/feed_signals.ppm`
- Create: `simulator/mock/screenshot/baselines/feed_watchlist.ppm`
- Modify: `simulator/mock/screenshot/baselines/feed_explore_panel.ppm`

- [ ] **Step 1: Write the failing FEED surface tests first**

```python
def test_real_feed_explore_panel_lists_signals_and_watchlist(self):
    harness_source = f"""
#define VERIFY_FEED
{verifier_prefix}
#include "{screen_source}"

static int label_contains(lv_obj_t *obj, const char *needle)
{{
    return obj && needle && strstr(obj->text, needle) != NULL;
}}

int main(void)
{{
    ave_sm_handle_json("{{\\"screen\\":\\"feed\\",\\"data\\":{{\\"source_label\\":\\"TRENDING\\",\\"tokens\\":[{{\\"token_id\\":\\"trend-1\\",\\"chain\\":\\"solana\\",\\"symbol\\":\\"BONK\\",\\"price\\":\\"$1\\"}}]}}}}");
    screen_feed_key(AVE_KEY_B);
    if (!label_contains(s_rows[3].lbl_sym, "Signals")) return 2;
    if (!label_contains(s_rows[4].lbl_sym, "Watchlist")) return 3;
    return 0;
}}
"""
```

```python
def test_real_watchlist_mode_x_emits_watchlist_remove(self):
    repo_root = Path(__file__).resolve().parents[3]
    verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
    include_dir = repo_root / "simulator/mock/json_verify_include"
    manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
    common_sources = self._common_screen_sources(repo_root)
    verifier_prefix = verifier.read_text(encoding="utf-8").split("#if defined(VERIFY_FEED)", 1)[0]
    display_json = (
        '{"screen":"feed","data":{"mode":"watchlist","source_label":"WATCHLIST","tokens":['
        '{"token_id":"tok-1","chain":"solana","symbol":"BONK","price":"$1","change_24h":"+1%","headline":"In Watchlist"}]}}'
    ).replace("\\", "\\\\").replace('"', '\\"')

    harness_source = f"""
#define VERIFY_FEED
{verifier_prefix}
#include "{repo_root / 'shared/ave_screens/screen_feed.c'}"

int main(void)
{{
    ave_sm_handle_json("{display_json}");
    screen_feed_key(AVE_KEY_X);
    if (strstr(g_last_json, "\\"action\\":\\"watchlist_remove\\"") == NULL) return 2;
    if (strstr(g_last_json, "\\"token_id\\":\\"tok-1\\"") == NULL) return 3;
    return 0;
}}
"""

    self._compile_and_run_c_harness(
        harness_source,
        include_dir,
        manager_src,
        *common_sources,
        binary_name="verify_watchlist_mode_remove_key",
    )
```

- [ ] **Step 2: Run FEED surface tests and verify they fail**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_surface_input_sync.py -k "signals or watchlist or explore_panel" -v`

Expected: FAIL because `screen_feed.c` still only knows `Search / Orders / Sources` and has no watchlist-remove action

- [ ] **Step 3: Implement the FEED Explore and browse-mode changes**

```c
typedef struct {
    char token_id[80];
    char chain[16];
    char symbol[24];
    char contract_tail[12];
    char source_tag[24];
    char price[24];
    char change_24h[16];
    char volume_24h[16];
    char market_cap[16];
    char signal_type[24];
    char headline[64];
    char origin_hint[24];
    int  change_positive;
} feed_token_t;

typedef enum {
    FEED_MODE_STANDARD = 0,
    FEED_MODE_SEARCH,
    FEED_MODE_ORDERS,
    FEED_MODE_SIGNALS,
    FEED_MODE_WATCHLIST,
} feed_mode_t;
```

```c
static const feed_explore_item_t EXPLORE_ITEMS[FEED_EXPLORE_ITEM_COUNT] = {
    {FEED_EXPLORE_ITEM_SEARCH, "Search", "Say token", FEED_SURFACE_EXPLORE_SEARCH_GUIDE},
    {FEED_EXPLORE_ITEM_ORDERS, "Orders", "Open current orders list", FEED_SURFACE_STANDARD},
    {FEED_EXPLORE_ITEM_SOURCES, "Sources", "Choose topic or platform", FEED_SURFACE_STANDARD},
    {FEED_EXPLORE_ITEM_SIGNALS, "Signals", "Browse public signal flow", FEED_SURFACE_STANDARD},
    {FEED_EXPLORE_ITEM_WATCHLIST, "Watchlist", "Open saved tokens", FEED_SURFACE_STANDARD},
};

if (item->id == FEED_EXPLORE_ITEM_SIGNALS) {
    ave_send_json("{\"type\":\"key_action\",\"action\":\"signals\"}");
    s_feed_surface = FEED_SURFACE_STANDARD;
    return;
}
if (item->id == FEED_EXPLORE_ITEM_WATCHLIST) {
    ave_send_json("{\"type\":\"key_action\",\"action\":\"watchlist\"}");
    s_feed_surface = FEED_SURFACE_STANDARD;
    return;
}
```

```c
if (s_feed_mode == FEED_MODE_WATCHLIST && key == AVE_KEY_X) {
    char cmd[384];
    ave_sm_json_field_t fields[] = {
        {"token_id", t->token_id},
        {"chain", t->chain},
        {"cursor", cursor_buf},
    };
    if (ave_sm_build_key_action_json("watchlist_remove", fields, 3, cmd, sizeof(cmd))) {
        ave_send_json(cmd);
    }
    return;
}
```

- [ ] **Step 4: Run the FEED sync tests, minimal C verifier, and screenshot gate**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_surface_input_sync.py -k "signals or watchlist or explore" -v`

Expected: PASS with new compiled harness checks green

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/simulator && cmake -S . -B build >/dev/null && cmake --build build --target verify_p3_5_minimal verify_screenshot_feed -j4 >/dev/null && ./bin/verify_p3_5_minimal && ./mock/run_screenshot_test.sh --screen feed_explore_panel --update-baseline && ./mock/run_screenshot_test.sh --screen feed_signals --update-baseline && ./mock/run_screenshot_test.sh --screen feed_watchlist --update-baseline`

Expected: PASS; new screenshot baselines are written for `feed_signals` and `feed_watchlist`, and `feed_explore_panel` baseline includes the two added entries

- [ ] **Step 5: Commit the FEED/device browse UI**

```bash
cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32
git add shared/ave_screens/screen_feed.c \
        server/main/xiaozhi-server/test_surface_input_sync.py \
        simulator/mock/verify_p3_5_minimal.c \
        simulator/mock/verify_screenshot_feed.c \
        simulator/mock/mock_scenes/16_feed_signals.json \
        simulator/mock/mock_scenes/17_feed_watchlist.json \
        simulator/mock/screenshot/baselines/feed_explore_panel.ppm \
        simulator/mock/screenshot/baselines/feed_signals.ppm \
        simulator/mock/screenshot/baselines/feed_watchlist.ppm
git commit -m "feat: add feed signals and watchlist surfaces"
```

### Task 5: Add The SPOTLIGHT Star And Final Docs Pass

**Files:**
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `shared/ave_screens/screen_spotlight.c`
- Modify: `server/main/xiaozhi-server/test_surface_input_sync.py`
- Modify: `simulator/mock/verify_ave_json_payloads.c`
- Modify: `simulator/mock/screenshot/baselines/spotlight.ppm`
- Modify: `docs/ave-feature-map.md`
- Modify: `docs/ave-page-feature-inventory-2026-04-10.md`

- [ ] **Step 1: Write failing spotlight payload/layout tests**

```python
def test_real_spotlight_row4_reserves_right_side_for_watchlist_star(self):
    repo_root = Path(__file__).resolve().parents[3]
    verifier = repo_root / "simulator/mock/verify_ave_json_payloads.c"
    include_dir = repo_root / "simulator/mock/json_verify_include"
    manager_src = repo_root / "shared/ave_screens/ave_screen_manager.c"
    verifier_prefix = verifier.read_text(encoding="utf-8").split("#if defined(VERIFY_FEED)", 1)[0]
    payload = (
        '{"screen":"spotlight","data":{'
        '"token_id":"tok-1-solana","chain":"solana","symbol":"BONK","price":"$1.23",'
        '"change_24h":"+2.1%","holders":"1,200","liquidity":"$100K","volume_24h":"$90K",'
        '"market_cap":"$4M","top100_concentration":"12.3%","contract":"Token111111",'
        '"is_watchlisted":true,"origin_hint":"From Signal","chart":[500,520,530]}}'
    ).replace("\\", "\\\\").replace('"', '\\"')

    harness_source = f"""
#define VERIFY_SPOTLIGHT
{verifier_prefix}
#include "{repo_root / 'shared/ave_screens/screen_spotlight.c'}"

int main(void)
{{
    screen_spotlight_show("{payload}");
    if (strcmp(s_lbl_watch_star->text, "★") != 0) return 2;
    if (strcmp(s_lbl_origin->text, "From Signal") != 0) return 3;
    if (s_lbl_watch_star->x <= s_lbl_stats_row4->x + s_lbl_stats_row4->width) return 4;
    return 0;
}}
"""

    self._compile_and_run_c_harness(
        harness_source,
        include_dir,
        manager_src,
        binary_name="verify_spotlight_watchlist_star_layout",
    )
```

- [ ] **Step 2: Run the spotlight-focused tests and verify they fail**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_surface_input_sync.py -k "spotlight and watchlist" -v`

Expected: FAIL because `spotlight` payloads and `screen_spotlight.c` do not yet expose `is_watchlisted` / `origin_hint`

- [ ] **Step 3: Implement spotlight payload fields and the display-only star**

```python
def _build_spotlight_loading_payload(
    addr: str,
    chain: str,
    *,
    symbol: str = "",
    interval: str = "60",
    feed_cursor=None,
    feed_total=None,
    origin_hint: str = "",
    is_watchlisted: bool = False,
) -> dict:
    spotlight_data = {
        "symbol": resolved_symbol,
        "chain": chain,
        "token_id": f"{addr}-{chain}",
        "price": "--",
        "change_24h": "Loading",
        "change_positive": True,
        "holders": "--",
        "liquidity": "--",
        "volume_24h": "--",
        "market_cap": "--",
        "top100_concentration": "--",
        "contract_short": _contract_short(addr),
        "chart": [500] * 12,
        "chart_min": "--",
        "chart_max": "--",
        "chart_min_y": "--",
        "chart_max_y": "--",
        "chart_t_start": "",
        "chart_t_mid": "",
        "chart_t_end": "now",
        "is_honeypot": False,
        "is_mintable": False,
        "is_freezable": False,
        "risk_level": "LOADING",
        "origin_hint": origin_hint,
        "is_watchlisted": is_watchlisted,
    }
    return spotlight_data
```

```python
origin_hint = str(state.get("spotlight_origin_hint") or "")
is_watchlisted = watchlist_contains(_WATCHLIST_STORE_PATH, _watchlist_namespace(conn), addr, chain)
spotlight_data = {
    **identity,
    "addr": addr,
    "interval": str(interval or "60"),
    "pair": f"{token.get('symbol', symbol or '???')} / USDC",
    "price": _fmt_price(token.get("current_price_usd", token.get("price"))),
    "price_raw": price_now,
    "change_24h": _fmt_change(token.get("token_price_change_24h", token.get("price_change_24h"))),
    "change_positive": float(token.get("token_price_change_24h", token.get("price_change_24h", 0)) or 0) >= 0,
    "holders": f"{int(token['holders']):,}" if token.get("holders") else "N/A",
    "liquidity": _fmt_volume(token.get("main_pair_tvl", token.get("tvl"))),
    "volume_24h": _fmt_volume(_coalesce_numeric_value(token.get("token_tx_volume_usd_24h"), token.get("tx_volume_u_24h"))),
    "market_cap": _fmt_volume(_coalesce_numeric_value(token.get("market_cap"), token.get("fdv"))),
    "top100_concentration": _extract_top100_concentration(top100_resp),
    "contract_short": _contract_short(addr),
    "chart": chart_values,
    "chart_min": _fmt_price(price_min),
    "chart_max": _fmt_price(price_max),
    "chart_min_y": _fmt_y_label(price_min),
    "chart_max_y": _fmt_y_label(price_max),
    "chart_t_start": _fmt_chart_time(t_start),
    "chart_t_mid": _fmt_chart_time(t_mid),
    "chart_t_end": "now",
    "is_honeypot": flags["is_honeypot"],
    "is_mintable": flags["is_mintable"],
    "is_freezable": flags["is_freezable"],
    "risk_level": flags["risk_level"],
    "origin_hint": origin_hint,
    "is_watchlisted": is_watchlisted,
}
```

```c
static lv_obj_t *s_lbl_origin = NULL;
static lv_obj_t *s_lbl_watch_star = NULL;

s_lbl_origin = lv_label_create(s_screen);
lv_obj_set_pos(s_lbl_origin, 8, 22);
lv_obj_set_style_text_font(s_lbl_origin, &lv_font_montserrat_10, 0);
lv_obj_set_style_text_color(s_lbl_origin, COLOR_GRAY, 0);

s_lbl_watch_star = lv_label_create(s_screen);
lv_obj_set_pos(s_lbl_watch_star, FOOTER_X + FOOTER_W - 12, FOOTER_ROW4_Y);
lv_obj_set_width(s_lbl_watch_star, 12);
lv_obj_set_style_text_align(s_lbl_watch_star, LV_TEXT_ALIGN_RIGHT, 0);
lv_obj_set_style_text_font(s_lbl_watch_star, &lv_font_montserrat_12, 0);

lv_label_set_text(s_lbl_origin, origin_hint[0] ? origin_hint : "");
lv_label_set_text(s_lbl_watch_star, is_watchlisted ? "★" : "☆");
```

- [ ] **Step 4: Run spotlight verifiers, refresh the screenshot baseline, and update docs**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_surface_input_sync.py -k "spotlight and watchlist" -v`

Expected: PASS; spotlight compiled harness sees the star/origin fields and row-4 layout remains non-overlapping

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/simulator/mock && cc -std=c99 -Ijson_verify_include -I../../shared/ave_screens verify_ave_json_payloads.c ../../shared/ave_screens/ave_json_utils.c -o /tmp/verify_ave_json_payloads && /tmp/verify_ave_json_payloads && cd .. && cmake -S . -B build >/dev/null && cmake --build build --target verify_screenshot_feed -j4 >/dev/null && ./mock/run_screenshot_test.sh --screen spotlight --update-baseline`

Expected: PASS; spotlight JSON payload verifier stays green and the updated `spotlight.ppm` now includes the row-4 star

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32 && python3 -m pytest server/main/xiaozhi-server/test_ave_router.py -k "watchlist" -v && python3 -m pytest server/main/xiaozhi-server/test_surface_input_sync.py -k "signals or watchlist or spotlight" -v`

Expected: PASS; final server + device regression sweep is green

- [ ] **Step 5: Commit the spotlight pass and docs**

```bash
cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32
git add server/main/xiaozhi-server/plugins_func/functions/ave_tools.py \
        shared/ave_screens/screen_spotlight.c \
        server/main/xiaozhi-server/test_surface_input_sync.py \
        simulator/mock/verify_ave_json_payloads.c \
        simulator/mock/screenshot/baselines/spotlight.ppm \
        docs/ave-feature-map.md \
        docs/ave-page-feature-inventory-2026-04-10.md
git commit -m "feat: surface watchlist state in spotlight"
```

## Spec Coverage Check

- `Explore` gets `Signals` and `Watchlist`: covered by Task 4
- `Signals -> SPOTLIGHT`: covered by Task 2 + Task 4
- `Watchlist -> SPOTLIGHT`: covered by Task 2 + Task 4
- voice-first add/remove/open watchlist: covered by Task 3
- final-row `☆ / ★` star in `SPOTLIGHT`: covered by Task 5
- no new spotlight button semantics: preserved by Tasks 3-5
- watchlist local persistence: covered by Task 1
- empty/failure states for signals/watchlist: covered by Task 2 + Task 4

## Placeholder Scan

- No `TODO`, `TBD`, or “similar to previous task” references remain
- Every task names exact files, commands, and target behaviors
- Later tasks reuse only symbols introduced earlier in this plan
