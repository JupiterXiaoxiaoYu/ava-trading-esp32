# AVE Xiaozhi P3 Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the interrupted P3 work for AVE Xiaozhi in the approved order, starting with the small navigation and chart-follow-up fixes.

**Architecture:** Keep server-side routing as the single source of truth for navigation and spotlight state. Apply focused fixes in the existing handlers and screen files rather than introducing new abstractions. Use Python unit tests for handler and helper behavior, and use simulator build verification for C-side screen changes.

**Tech Stack:** Python, asyncio, unittest, C, LVGL 9, simulator CMake build

---

### Task 1: Batch 1 — P3-3 / P3-4 / P3-6 / P3-7

**Files:**
- Create: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_batch1.py`
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.c`
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_feed.c`

- [ ] Step 1: Write failing Python tests for kline interval handling and kline size mapping.
- [ ] Step 2: Run `python3 -m unittest /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_batch1.py` and verify the new tests fail for the expected reasons.
- [ ] Step 3: Implement the minimal Python changes in `keyActionHandler.py` and `ave_tools.py`.
- [ ] Step 4: Re-run `python3 -m unittest /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_batch1.py` and verify it passes.
- [ ] Step 5: Implement the C-side navigation changes in `ave_screen_manager.c` and `screen_feed.c`.
- [ ] Step 6: Run a fresh simulator build to verify the C changes compile.

### Task 2: Batch 2 — P3-5 RESULT follows nav_from

**Files:**
- Create: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_result_nav.py`
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_result.c`
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`

- [ ] Step 1: Write failing Python tests for server-side `back` behavior when `nav_from` is set by result-producing flows.
- [ ] Step 2: Run `python3 -m unittest /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_result_nav.py` and verify the tests fail for the expected reasons.
- [ ] Step 3: Implement minimal server-side state and RESULT routing changes.
- [ ] Step 4: Update `screen_result.c` to send `back` with a safe fallback.
- [ ] Step 5: Re-run the Python test file and verify it passes.
- [ ] Step 6: Run a fresh simulator build to verify the C changes compile.

### Task 3: Batch 3 — P3-1 / P3-2 Orders flow

**Files:**
- Create: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_orders.py`
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/config.yaml`
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_feed.c`

- [ ] Step 1: Write failing tests for pending-order fetch normalization and cancel request shaping.
- [ ] Step 2: Run `python3 -m unittest /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_orders.py` and verify the tests fail for the expected reasons.
- [ ] Step 3: Implement `ave_list_orders` and `ave_cancel_order` with the minimum payload needed by FEED reuse.
- [ ] Step 4: Update the FEED rendering branch and config prompt wiring.
- [ ] Step 5: Re-run the orders test file and verify it passes.
- [ ] Step 6: Run a fresh simulator build if FEED C changes were touched, then run any targeted server verification needed for the tools.
