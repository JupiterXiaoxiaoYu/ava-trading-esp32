# Product Surface P0/P1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the highest-impact product-surface issues found in `docs/product-surface-audit-2026-04-08.md`, with priority on mixed-input correctness and visible interaction consistency.

**Architecture:** Treat the surface issues as four focused tracks: state-sync correctness, FEED-mode interaction consistency, result/notification readability, and portfolio value expression. Each track should add regression coverage first, implement the smallest change that removes the product risk, then update docs/screenshot evidence.

**Tech Stack:** C LVGL shared screens, SDL simulator, Python websocket/router/server state, pytest, screenshot regression harness, markdown docs.

---

### Task 1: Fix FEED / PORTFOLIO Cursor Drift Between Local UI and Server Intent Routing

**Files:**
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_feed.c`
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_portfolio.c`
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py`
- Test: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_ave_router.py`
- Test or Create: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_surface_input_sync.py`

- [ ] Add RED coverage for “move selection by key, then say 看这个 / 买这个” on `feed` and `portfolio`; assert router resolves the moved item rather than the stale default item.
- [ ] Add a deterministic message contract for client-side selection sync instead of depending on implicit server cursor updates from unrelated pushes.
- [ ] Implement minimal sync wiring from local selection changes to server state, preferably via explicit `key_action` or lightweight state-sync messages rather than heuristic inference.
- [ ] Keep existing pure-key flows unchanged: `A/RIGHT` on FEED and `A` on PORTFOLIO must still resolve the same selected item after the sync change.
- [ ] Run focused verification:
  - `cd /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server && python3 -m pytest -q test_ave_router.py test_surface_input_sync.py`
- [ ] Run broader regression:
  - `cd /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server && python3 -m pytest -q test_ave_api_matrix.py test_p3_trade_flows.py test_ave_router.py test_ave_voice_protocol.py`

### Task 2: Make FEED Mode Identity and Orders/Search Behavior Visibly Consistent

**Files:**
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_feed.c`
- Modify: `/home/jupiter/ave-xiaozhi/docs/product-surface-audit-2026-04-08.md`
- Modify: `/home/jupiter/ave-xiaozhi/docs/simulator-ui-guide.md`
- Test: `/home/jupiter/ave-xiaozhi/simulator/mock/verify_screenshot_feed.c`
- Modify/Create baselines: `/home/jupiter/ave-xiaozhi/simulator/mock/screenshot/baselines/*.ppm`

- [ ] Review FEED’s three non-default modes (`SEARCH`, special source, `ORDERS`) and freeze one explicit rule per mode for what `LEFT`, `X`, `A/RIGHT`, and `B` should do.
- [ ] Fix the current mismatch where orders-mode hints imply “back only” while code still allows deeper entry; choose one behavior and align hint copy, code path, and screenshot evidence.
- [ ] Make mode identity more explicit on-screen so users can tell “standard feed” vs `SEARCH` vs `ORDERS` vs special source without memorizing hidden behavior.
- [ ] Add or update screenshot cases proving the chosen presentation for:
  - `feed`
  - `feed_search`
  - `feed_special_source`
  - orders-mode if added to the gate
- [ ] Run focused verification:
  - `cd /home/jupiter/ave-xiaozhi/simulator && ./mock/run_screenshot_test.sh`
- [ ] Reconcile documentation after behavior locks:
  - `cd /home/jupiter/ave-xiaozhi && rg -n "ORDERS|SEARCH|special source|来源" docs/product-surface-audit-2026-04-08.md docs/simulator-ui-guide.md`

### Task 3: Improve RESULT / NOTIFY Readability Without Breaking Fast Expert Flows

**Files:**
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_result.c`
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_notify.c`
- Test: `/home/jupiter/ave-xiaozhi/simulator/mock/verify_screenshot_feed.c`
- Optional Test/Create: `/home/jupiter/ave-xiaozhi/simulator/mock/verify_surface_timers.c`

- [ ] Add RED coverage for readable failure/success states: result text must remain visible long enough to read, and error results should preserve actionable copy rather than collapsing into a generic flash.
- [ ] Decide one concrete timer policy for `RESULT` and `NOTIFY` that balances expert speed with novice readability; document the rule in code comments only if the logic would otherwise be non-obvious.
- [ ] Implement the minimal timer/copy change, keeping keyboard dismissal and `Y -> PORTFOLIO` behavior intact.
- [ ] Ensure “any key dismisses NOTIFY first” still works, but does not accidentally hide critical failure context before the user can parse it.
- [ ] Run focused verification:
  - `cd /home/jupiter/ave-xiaozhi/simulator && ./mock/run_screenshot_test.sh`
- [ ] Run simulator build verification if new timer tests are added:
  - `cd /home/jupiter/ave-xiaozhi/simulator && cmake --build build --target main`

### Task 4: Make PORTFOLIO More Trustworthy Even When Cost Basis Is Missing

**Files:**
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_portfolio.c`
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `/home/jupiter/ave-xiaozhi/docs/product-surface-audit-2026-04-08.md`
- Test: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_ave_api_matrix.py`
- Optional Test/Create: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_portfolio_surface.py`

- [ ] Add RED coverage for the “no cost basis / no pnl” case so it renders as an intentional product state, not as a broken or suspicious half-empty state.
- [ ] Keep the current truthfulness rule: do not fabricate P&L when cost basis is unavailable.
- [ ] Improve payload wording and/or UI summary so the page still feels useful when P&L is unavailable (for example: clearer total-value emphasis, explicit unavailable label, or better neutral summary text).
- [ ] Preserve existing sell/watch flows and `nav_from=portfolio` behavior.
- [ ] Run focused verification:
  - `cd /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server && python3 -m pytest -q test_ave_api_matrix.py test_portfolio_surface.py`
- [ ] Spot-check visual presentation through the screenshot gate if the visible portfolio copy changes:
  - `cd /home/jupiter/ave-xiaozhi/simulator && ./mock/run_screenshot_test.sh`

### Task 5: Reduce High-Risk Key Ambiguity With On-Screen Affordance, Not New Complexity

**Files:**
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_feed.c`
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_spotlight.c`
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_portfolio.c`
- Modify: `/home/jupiter/ave-xiaozhi/docs/simulator-ui-guide.md`
- Modify: `/home/jupiter/ave-xiaozhi/docs/product-surface-audit-2026-04-08.md`

- [ ] Keep the existing keymap stable unless a product decision explicitly changes it; this task is about reducing confusion, not reworking the whole control scheme.
- [ ] Improve bottom-bar affordance so users can see when `X` means “source switch” vs “sell” and when `Y` is globally available.
- [ ] Normalize wording across FEED, SPOTLIGHT, and PORTFOLIO so secondary actions feel intentionally different, not arbitrarily remapped.
- [ ] Re-run screenshot verification to confirm the affordance changes are real and legible:
  - `cd /home/jupiter/ave-xiaozhi/simulator && ./mock/run_screenshot_test.sh`

### Task 6: Manager Review, Spec Coverage Check, and Integrated Verification

**Files:**
- Review: `/home/jupiter/ave-xiaozhi/docs/product-surface-audit-2026-04-08.md`
- Review: `/home/jupiter/ave-xiaozhi/docs/simulator-ui-guide.md`
- Review: `/home/jupiter/ave-xiaozhi/docs/ave-feature-map.md`
- Optionally update: `/home/jupiter/ave-xiaozhi/docs/product-review-2026-04-07.md`

- [ ] Verify each P0/P1 issue from the audit maps to at least one task in this plan.
- [ ] Search the plan for drift against the audit:
  - `cd /home/jupiter/ave-xiaozhi && rg -n "P0|P1|cursor|ORDERS|SEARCH|RESULT|NOTIFY|PORTFOLIO|X|Y" docs/product-surface-audit-2026-04-08.md docs/superpowers/plans/2026-04-08-product-surface-p0-p1.md`
- [ ] After implementation, rerun the integrated suites:
  - `cd /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server && python3 -m pytest -q test_trade_contract_fixes.py test_ave_api_matrix.py test_p3_trade_flows.py test_ave_router.py test_ave_voice_protocol.py`
  - `cd /home/jupiter/ave-xiaozhi/simulator && ./mock/run_screenshot_test.sh && ./bin/verify_simulator_keymap`
- [ ] Update the audit/doc set to reflect any behavior that changed, then summarize what moved from P0/P1 to closed.
