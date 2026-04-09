# AVE Batch 1 Product-Surface Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first product-surface hardening batch for AVE Xiaozhi: asset identity reinforcement, conditional disambiguation, confirm-timeout explanations, search session restore, and wallet/order explanation layers without expanding the top-level page system.

**Architecture:** Keep the existing AVE screen/state-machine contract intact and extend it in place. Add one conditional intermediate screen (`DISAMBIGUATION`) only when asset identity is ambiguous; keep all wallet/order/history improvements as explanation layers on top of `FEED`, `SPOTLIGHT`, `CONFIRM`, `RESULT`, and `PORTFOLIO` rather than introducing a new UI universe.

**Tech Stack:** C/LVGL screen renderer under `shared/ave_screens/`, Python server logic under `server/main/xiaozhi-server/`, websocket/display contract helpers in `ave_tools.py`, router/input logic in `keyActionHandler.py` and `aveCommandRouter.py`, pytest regression suite, simulator screenshot gate.

---

## File Structure

### Core UI / state-machine files
- Modify: `shared/ave_screens/ave_screen_manager.h`
- Modify: `shared/ave_screens/ave_screen_manager.c`
- Create: `shared/ave_screens/screen_disambiguation.c`
- Modify: `shared/ave_screens/CMakeLists.txt`
- Modify: `shared/ave_screens/screen_feed.c`
- Modify: `shared/ave_screens/screen_spotlight.c`
- Modify: `shared/ave_screens/screen_confirm.c`
- Modify: `shared/ave_screens/screen_limit_confirm.c`
- Modify: `shared/ave_screens/screen_result.c`
- Modify: `shared/ave_screens/screen_portfolio.c`
- Modify: `shared/ave_screens/screen_notify.c`

### Server routing / payload shaping files
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
- Modify: `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py`
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_trade_mgr.py`
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`

### Tests
- Modify: `server/main/xiaozhi-server/test_ave_router.py`
- Modify: `server/main/xiaozhi-server/test_surface_input_sync.py`
- Modify: `server/main/xiaozhi-server/test_p3_trade_flows.py`
- Modify: `server/main/xiaozhi-server/test_p3_orders.py`
- Modify: `server/main/xiaozhi-server/test_portfolio_surface.py`
- Create or modify: `server/main/xiaozhi-server/test_p3_batch1.py`
- Modify: `simulator/mock/run_screenshot_test.sh`
- Create baselines as needed under: `simulator/mock/screenshot/baselines/`

### Docs
- Modify: `docs/ave-feature-map.md`
- Modify: `docs/simulator-ui-guide.md`
- Modify: `docs/pending-tasks.md`
- Reference only: `docs/page-blueprint-key-constitution-2026-04-09.md`
- Reference only: `docs/implementation-batch1-2026-04-09.md`

---

### Task 1: Add RED coverage for asset identity and disambiguation entry

**Files:**
- Modify: `server/main/xiaozhi-server/test_ave_router.py`
- Modify: `server/main/xiaozhi-server/test_surface_input_sync.py`
- Modify: `server/main/xiaozhi-server/test_p3_batch1.py`

- [ ] **Step 1: Add failing router tests for ambiguous token selection**

```python
async def test_search_with_ambiguous_symbol_routes_to_disambiguation(self):
    conn = make_fake_conn()
    with patch("plugins_func.functions.ave_tools.ave_search_token") as mock_search:
        mock_search.return_value = {
            "screen": "disambiguation",
            "items": [
                {"symbol": "PEPE", "chain": "solana", "token_id": "So111..."},
                {"symbol": "PEPE", "chain": "base", "token_id": "0xabc..."},
            ],
        }
        await self.router.handle_text(conn, "看PEPE")
        sent = conn.websocket.sent_json
        assert any(frame.get("type") == "display" and frame.get("screen") == "disambiguation" for frame in sent)
```

- [ ] **Step 2: Run the new ambiguous-selection tests and confirm they fail**

Run: `python3 -m pytest -q server/main/xiaozhi-server/test_ave_router.py -k disambiguation`
Expected: FAIL because `disambiguation` screen/routing does not exist yet.

- [ ] **Step 3: Add failing input-sync tests for disambiguation key contract**

```python
def test_disambiguation_surface_emits_no_trusted_selection_until_confirmed(self):
    payload = build_surface_payload(screen="disambiguation", cursor=1)
    assert payload["screen"] == "disambiguation"
    assert payload.get("selection") is None
```

- [ ] **Step 4: Add failing batch test for disambiguation lifecycle**

```python
async def test_disambiguation_select_enters_spotlight_and_back_restores_search(self):
    conn = make_fake_conn_with_search_state()
    await enter_disambiguation(conn)
    await dispatch_key(conn, "right")
    assert conn.ave_state["screen"] == "spotlight"
    await dispatch_key(conn, "back")
    assert conn.ave_state["screen"] == "feed"
    assert conn.ave_state["feed_mode"] == "search"
```

- [ ] **Step 5: Commit the RED tests**

```bash
git add server/main/xiaozhi-server/test_ave_router.py \
        server/main/xiaozhi-server/test_surface_input_sync.py \
        server/main/xiaozhi-server/test_p3_batch1.py
git commit -m "test: add failing coverage for asset disambiguation"
```

### Task 2: Implement asset identity shaping and conditional `DISAMBIGUATION`

**Files:**
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
- Modify: `shared/ave_screens/ave_screen_manager.h`
- Modify: `shared/ave_screens/ave_screen_manager.c`
- Create: `shared/ave_screens/screen_disambiguation.c`
- Modify: `shared/ave_screens/CMakeLists.txt`
- Modify: `shared/ave_screens/screen_feed.c`
- Modify: `shared/ave_screens/screen_spotlight.c`
- Modify: `shared/ave_screens/screen_confirm.c`
- Modify: `shared/ave_screens/screen_limit_confirm.c`
- Modify: `shared/ave_screens/screen_portfolio.c`
- Test: `server/main/xiaozhi-server/test_ave_router.py`
- Test: `server/main/xiaozhi-server/test_surface_input_sync.py`
- Test: `server/main/xiaozhi-server/test_p3_batch1.py`

- [ ] **Step 1: Add a normalized asset-identity helper in `ave_tools.py`**

```python
def _asset_identity_fields(token: dict) -> dict:
    chain = str(token.get("chain") or "").lower()
    addr = str(token.get("token_id") or token.get("addr") or "")
    tail = addr[-4:] if len(addr) >= 4 else addr
    return {
        "symbol": token.get("symbol") or "?",
        "chain": chain,
        "contract_tail": tail,
        "token_id": addr,
        "source_tag": token.get("platform") or token.get("source") or "",
    }
```

- [ ] **Step 2: Gate ambiguous search/detail flows through a disambiguation payload**

```python
def _build_disambiguation_payload(items: list[dict], *, nav_from: str = "feed") -> dict:
    return {
        "items": [_asset_identity_fields(item) for item in items],
        "cursor": 0,
        "nav_from": nav_from,
    }
```

- [ ] **Step 3: Extend screen manager enum and dispatch table**

```c
typedef enum {
    AVE_SCREEN_FEED = 0,
    AVE_SCREEN_SPOTLIGHT,
    AVE_SCREEN_CONFIRM,
    AVE_SCREEN_LIMIT_CONFIRM,
    AVE_SCREEN_RESULT,
    AVE_SCREEN_PORTFOLIO,
    AVE_SCREEN_NOTIFY,
    AVE_SCREEN_DISAMBIGUATION,
} ave_screen_id_t;
```

- [ ] **Step 4: Implement `screen_disambiguation.c` with locked key semantics**

```c
if (key == AVE_KEY_UP) move_cursor(-1);
else if (key == AVE_KEY_DOWN) move_cursor(+1);
else if (key == AVE_KEY_LEFT || key == AVE_KEY_B) send_back();
else if (key == AVE_KEY_RIGHT || key == AVE_KEY_A) send_confirm_selection();
else if (key == AVE_KEY_X) show_disabled_hint();
```

- [ ] **Step 5: Thread identity fields into FEED / SPOTLIGHT / CONFIRM / LIMIT_CONFIRM / PORTFOLIO renderers**

```c
snprintf(line, sizeof(line), "%s  %s  •%s", symbol, chain_label, contract_tail);
lv_label_set_text(identity_label, line);
```

- [ ] **Step 6: Run the targeted tests and verify they now pass**

Run: `python3 -m pytest -q server/main/xiaozhi-server/test_ave_router.py server/main/xiaozhi-server/test_surface_input_sync.py server/main/xiaozhi-server/test_p3_batch1.py -k 'disambiguation or identity'`
Expected: PASS

- [ ] **Step 7: Commit the disambiguation/identity implementation**

```bash
git add shared/ave_screens/ave_screen_manager.h \
        shared/ave_screens/ave_screen_manager.c \
        shared/ave_screens/screen_disambiguation.c \
        shared/ave_screens/CMakeLists.txt \
        shared/ave_screens/screen_feed.c \
        shared/ave_screens/screen_spotlight.c \
        shared/ave_screens/screen_confirm.c \
        shared/ave_screens/screen_limit_confirm.c \
        shared/ave_screens/screen_portfolio.c \
        server/main/xiaozhi-server/plugins_func/functions/ave_tools.py \
        server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py \
        server/main/xiaozhi-server/test_ave_router.py \
        server/main/xiaozhi-server/test_surface_input_sync.py \
        server/main/xiaozhi-server/test_p3_batch1.py
git commit -m "feat: add asset identity reinforcement and disambiguation"
```

### Task 3: Implement search guide completion and search-session restore

**Files:**
- Modify: `shared/ave_screens/screen_feed.c`
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
- Modify: `server/main/xiaozhi-server/test_ave_router.py`
- Modify: `server/main/xiaozhi-server/test_surface_input_sync.py`
- Modify: `simulator/mock/run_screenshot_test.sh`

- [ ] **Step 1: Add RED tests for restoring `FEED_SEARCH` query + cursor**

```python
async def test_back_from_spotlight_restores_search_query_and_cursor(self):
    conn = make_fake_conn()
    conn.ave_state.update({
        "feed_mode": "search",
        "search_query": "PEPE",
        "search_cursor": 2,
        "search_results": [{"symbol": "PEPE"}] * 5,
    })
    await dispatch_key(conn, "back")
    assert conn.ave_state["feed_mode"] == "search"
    assert conn.ave_state["search_query"] == "PEPE"
    assert conn.ave_state["search_cursor"] == 2
```

- [ ] **Step 2: Persist a dedicated search session in `ave_state`**

```python
def _save_search_session(conn, *, query: str, items: list[dict], cursor: int = 0) -> None:
    conn.ave_state["search_session"] = {
        "query": query,
        "items": items,
        "cursor": cursor,
    }
```

- [ ] **Step 3: Restore search state on `back` instead of collapsing to generic feed source**

```python
if state.get("feed_mode") == "search" and state.get("search_session"):
    return await _send_display(conn, "feed", _search_session_payload(state["search_session"]))
```

- [ ] **Step 4: Upgrade Search guide copy from single-line hint to guided entry**

```c
static const char *k_search_guide_lines[] = {
    "Hold FN and say a coin name",
    "Example: BONK / PEPE / DOGE",
    "Last search: %s",
};
```

- [ ] **Step 5: Refresh screenshot gate for updated FEED_SEARCH guidance**

Run: `cd /home/jupiter/ave-xiaozhi/simulator && ./mock/run_screenshot_test.sh`
Expected: PASS after updating baselines for Search guide and any FEED identity changes.

- [ ] **Step 6: Commit the search-closure work**

```bash
git add shared/ave_screens/screen_feed.c \
        server/main/xiaozhi-server/plugins_func/functions/ave_tools.py \
        server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py \
        server/main/xiaozhi-server/test_ave_router.py \
        server/main/xiaozhi-server/test_surface_input_sync.py \
        simulator/mock/run_screenshot_test.sh \
        simulator/mock/screenshot/baselines
git commit -m "feat: restore search sessions and improve search guidance"
```

### Task 4: Implement timeout / submitted / deferred explanation layer

**Files:**
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_trade_mgr.py`
- Modify: `shared/ave_screens/screen_confirm.c`
- Modify: `shared/ave_screens/screen_limit_confirm.c`
- Modify: `shared/ave_screens/screen_result.c`
- Modify: `shared/ave_screens/screen_notify.c`
- Modify: `server/main/xiaozhi-server/test_p3_trade_flows.py`
- Modify: `server/main/xiaozhi-server/test_trade_contract_fixes.py`
- Modify: `server/main/xiaozhi-server/test_ave_api_matrix.py`

- [ ] **Step 1: Add RED tests for distinct confirm timeout vs ack-watchdog messaging**

```python
async def test_confirm_timeout_pushes_explicit_auto_cancel_explanation(self):
    conn = make_fake_conn()
    await simulate_confirm_timeout(conn)
    payload = latest_display_payload(conn, "result")
    assert payload["title"] == "Trade Cancelled"
    assert "timed out" in payload["subtitle"].lower()
```

- [ ] **Step 2: Normalize user-facing state copy in `ave_tools.py`**

```python
def _trade_status_copy(reason: str) -> tuple[str, str]:
    mapping = {
        "trade_submitted": ("Order Submitted", "Waiting for chain confirmation."),
        "confirm_timeout": ("Trade Cancelled", "Confirmation timed out. Nothing was executed."),
        "ack_timeout": ("Still Pending", "We did not receive a final confirmation yet."),
        "deferred_result": ("Result Deferred", "Another confirmation flow is active. Result will appear next."),
    }
    return mapping[reason]
```

- [ ] **Step 3: Route local timeout/watchdog branches through explicit RESULT/NOTIFY payloads**

```c
/* Instead of silently falling through to back/feed, send a result-fail style payload. */
ave_send_json("{\"type\":\"trade_timeout\",\"reason\":\"confirm_timeout\"}");
```

- [ ] **Step 4: Make deferred-result queue flush preserve user-facing explanation text**

```python
payload.setdefault("explain_state", "deferred_result")
_queue_deferred_result_payload(conn, payload)
```

- [ ] **Step 5: Run the trade-flow regressions**

Run: `python3 -m pytest -q server/main/xiaozhi-server/test_p3_trade_flows.py server/main/xiaozhi-server/test_trade_contract_fixes.py server/main/xiaozhi-server/test_ave_api_matrix.py -k 'timeout or submitted or deferred or result'`
Expected: PASS

- [ ] **Step 6: Commit the trade explanation layer**

```bash
git add server/main/xiaozhi-server/plugins_func/functions/ave_tools.py \
        server/main/xiaozhi-server/plugins_func/functions/ave_wss.py \
        server/main/xiaozhi-server/plugins_func/functions/ave_trade_mgr.py \
        shared/ave_screens/screen_confirm.c \
        shared/ave_screens/screen_limit_confirm.c \
        shared/ave_screens/screen_result.c \
        shared/ave_screens/screen_notify.c \
        server/main/xiaozhi-server/test_p3_trade_flows.py \
        server/main/xiaozhi-server/test_trade_contract_fixes.py \
        server/main/xiaozhi-server/test_ave_api_matrix.py
git commit -m "feat: explain confirm timeouts and deferred trade states"
```

### Task 5: Add wallet/order explanation layers without new screens

**Files:**
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `shared/ave_screens/screen_portfolio.c`
- Modify: `shared/ave_screens/screen_feed.c`
- Modify: `shared/ave_screens/screen_result.c`
- Modify: `server/main/xiaozhi-server/test_portfolio_surface.py`
- Modify: `server/main/xiaozhi-server/test_p3_orders.py`
- Modify: `server/main/xiaozhi-server/test_ave_skill_tools.py`

- [ ] **Step 1: Add RED tests for portfolio `N/A` explanation and wallet-source hinting**

```python
async def test_portfolio_na_pnl_is_rendered_as_explained_state(self):
    payload = await build_portfolio_payload_without_cost_basis()
    assert payload["pnl"] == "N/A"
    assert payload["pnl_reason"] == "Cost basis unavailable"
```

- [ ] **Step 2: Add explanation fields to portfolio payload shaping**

```python
payload.update({
    "wallet_source_label": "Proxy wallet",
    "pnl_reason": "Cost basis unavailable" if payload.get("pnl") == "N/A" else "",
})
```

- [ ] **Step 3: Surface browse-only boundary in Orders page chrome**

```c
if (mode == FEED_MODE_ORDERS) {
    lv_label_set_text(s_hint_label, "Orders: view only");
}
```

- [ ] **Step 4: Distinguish order-result copy from trade-result copy in `RESULT`**

```python
if result_type == "cancel_order":
    payload["title"] = "Order Cancelled"
    payload["subtitle"] = "This changed an order state, not your wallet balance."
```

- [ ] **Step 5: Run wallet/order explanation tests**

Run: `python3 -m pytest -q server/main/xiaozhi-server/test_portfolio_surface.py server/main/xiaozhi-server/test_p3_orders.py server/main/xiaozhi-server/test_ave_skill_tools.py`
Expected: PASS

- [ ] **Step 6: Commit the wallet/order explanation work**

```bash
git add server/main/xiaozhi-server/plugins_func/functions/ave_tools.py \
        shared/ave_screens/screen_portfolio.c \
        shared/ave_screens/screen_feed.c \
        shared/ave_screens/screen_result.c \
        server/main/xiaozhi-server/test_portfolio_surface.py \
        server/main/xiaozhi-server/test_p3_orders.py \
        server/main/xiaozhi-server/test_ave_skill_tools.py
git commit -m "feat: add wallet and order explanation layers"
```

### Task 6: Sync docs and run final batch verification

**Files:**
- Modify: `docs/ave-feature-map.md`
- Modify: `docs/simulator-ui-guide.md`
- Modify: `docs/pending-tasks.md`
- Test: `server/main/xiaozhi-server/test_ave_router.py`
- Test: `server/main/xiaozhi-server/test_surface_input_sync.py`
- Test: `server/main/xiaozhi-server/test_p3_trade_flows.py`
- Test: `server/main/xiaozhi-server/test_p3_orders.py`
- Test: `server/main/xiaozhi-server/test_portfolio_surface.py`
- Test: `server/main/xiaozhi-server/test_p3_batch1.py`
- Test: `server/main/xiaozhi-server/test_ave_skill_tools.py`
- Test: `simulator/mock/run_screenshot_test.sh`

- [ ] **Step 1: Update implementation-aligned docs to match the new contracts**

```markdown
- Add `DISAMBIGUATION` to the screen/state table.
- Document `X` freeze: no third meaning.
- Document search-session restore.
- Document timeout/deferred explanation states.
- Document wallet/order explanation fields.
```

- [ ] **Step 2: Run the full Python regression batch**

Run:
```bash
python3 -m pytest -q \
  server/main/xiaozhi-server/test_ave_router.py \
  server/main/xiaozhi-server/test_surface_input_sync.py \
  server/main/xiaozhi-server/test_p3_trade_flows.py \
  server/main/xiaozhi-server/test_p3_orders.py \
  server/main/xiaozhi-server/test_portfolio_surface.py \
  server/main/xiaozhi-server/test_p3_batch1.py \
  server/main/xiaozhi-server/test_ave_skill_tools.py
```
Expected: PASS

- [ ] **Step 3: Run the simulator screenshot gate**

Run:
```bash
cd /home/jupiter/ave-xiaozhi/simulator && ./mock/run_screenshot_test.sh
```
Expected: PASS with updated baselines for any changed screens and a new baseline for `DISAMBIGUATION` if introduced.

- [ ] **Step 4: Run the lightweight fallback/state-machine probe if renderer/state routing changed**

Run:
```bash
cc -std=c99 -Wall -Wextra \
  -I/home/jupiter/ave-xiaozhi/simulator \
  -I/home/jupiter/ave-xiaozhi/shared/ave_screens \
  /home/jupiter/ave-xiaozhi/simulator/mock/verify_p3_5_minimal.c \
  /home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.c \
  -o /tmp/verify_p3_5_minimal && /tmp/verify_p3_5_minimal
```
Expected: PASS

- [ ] **Step 5: Commit the docs/test sync**

```bash
git add docs/ave-feature-map.md \
        docs/simulator-ui-guide.md \
        docs/pending-tasks.md \
        simulator/mock/screenshot/baselines
git commit -m "docs: align batch1 product-surface contracts"
```

---

## Spec Coverage Check

- `DISAMBIGUATION`: covered by Task 1 + Task 2.
- Asset identity reinforcement: covered by Task 2.
- Search closure and restore: covered by Task 3.
- Confirm timeout / submitted / deferred explanation: covered by Task 4.
- Wallet explanation / orders explanation: covered by Task 5.
- Test + doc sync: covered by Task 6.

## Placeholder Scan

- No `TODO` / `TBD` placeholders remain in the execution steps.
- All tasks name exact files and test commands.
- All high-risk behavior changes include explicit regression targets.

## Type / Contract Consistency Check

- New screen name is consistently `disambiguation` / `AVE_SCREEN_DISAMBIGUATION`.
- Search restore consistently uses `search_session` rather than overloading `feed_source`.
- Explanation-state copy uses normalized reason keys: `trade_submitted`, `confirm_timeout`, `ack_timeout`, `deferred_result`.

---

## Recommended Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6

This order preserves the highest-risk product fixes first: wrong-asset risk, then transaction-state ambiguity, then search closure, then explanation polish.
