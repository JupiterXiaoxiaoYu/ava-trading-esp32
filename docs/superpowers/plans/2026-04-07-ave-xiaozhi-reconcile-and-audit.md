# AVE Xiaozhi Reconcile And Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile `pending-tasks.md` with the current codebase, add missing functional tests, and surface any remaining bugs, UX issues, or code/doc inconsistencies before declaring task status.

**Architecture:** Split the work into three independent audit domains: Python server behavior, C screen interaction behavior, and docs/task reconciliation. Use parallel agents for read-heavy inspection first, then turn confirmed findings into focused fixes and test additions. Update the task document only after code and tests support the claimed status.

**Tech Stack:** Python, unittest, C, LVGL 9, simulator CMake build, markdown docs

---

### Task 1: Parallel audit of Python server logic, tests, and task status

**Files:**
- Inspect: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Inspect: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
- Inspect: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/core/handle/textHandler/tradeActionHandler.py`
- Inspect: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/plugins_func/functions/ave_trade_mgr.py`
- Inspect: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`
- Inspect: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_batch1.py`
- Inspect: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_orders.py`
- Inspect: `/home/jupiter/ave-xiaozhi/docs/pending-tasks.md`

- [ ] Step 1: Dispatch an audit agent focused on Python server behavior, missing tests, and mismatches against `pending-tasks.md`.
- [ ] Step 2: Collect concrete findings with file/line references and classify them as bug, test gap, or doc mismatch.
- [ ] Step 3: Implement any confirmed Python fixes and add regression tests before updating task status.
- [ ] Step 4: Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_p3_batch1.py test_p3_orders.py` from `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server` and verify pass/fail status from fresh output.

### Task 2: Parallel audit of C-side interaction logic and UX behavior

**Files:**
- Inspect: `/home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.c`
- Inspect: `/home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.h`
- Inspect: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_feed.c`
- Inspect: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_spotlight.c`
- Inspect: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_confirm.c`
- Inspect: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_limit_confirm.c`
- Inspect: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_result.c`
- Inspect: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_portfolio.c`
- Inspect: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_notify.c`
- Inspect: `/home/jupiter/ave-xiaozhi/docs/pending-tasks.md`

- [ ] Step 1: Dispatch an audit agent focused on button routing, fallback behavior, and UX-path mismatches against `pending-tasks.md`.
- [ ] Step 2: Collect concrete findings with file/line references and classify them as bug, UX issue, or stale task entry.
- [ ] Step 3: Implement any confirmed C fixes.
- [ ] Step 4: Run `cmake --build /home/jupiter/ave-xiaozhi/simulator/build` and verify the simulator still builds from fresh output.

### Task 3: Parallel audit of docs reconciliation and task table updates

**Files:**
- Inspect: `/home/jupiter/ave-xiaozhi/docs/pending-tasks.md`
- Inspect: `/home/jupiter/ave-xiaozhi/docs/ave-feature-map.md`
- Inspect: `/home/jupiter/ave-xiaozhi/docs/superpowers/specs/2026-04-07-ave-xiaozhi-p3-continuation-design.md`
- Inspect: `/home/jupiter/ave-xiaozhi/docs/superpowers/plans/2026-04-07-ave-xiaozhi-p3-continuation.md`

- [ ] Step 1: Dispatch an audit agent focused on stale task entries, completed items still listed as pending, and missing caveats/decisions.
- [ ] Step 2: Reconcile task status only after code and tests support the claim.
- [ ] Step 3: Update `pending-tasks.md` to reflect current reality: completed work, explicitly removed items, remaining gaps, and any newly discovered blockers.
- [ ] Step 4: Re-read the updated task table and verify every listed remaining task maps to an actual unresolved code/doc issue.
