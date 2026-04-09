# AVE Release Hardening Parallel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden AVE across three independent tracks: confirm-flow safety, screenshot regression coverage, and trade-attribution/E2E assurance.

**Architecture:** Use disjoint ownership so server interaction safety, simulator screenshot infrastructure, and trade-event attribution can advance in parallel. Each track must add or strengthen tests first, then implement the minimal behavior needed, then rerun its focused suite.

**Tech Stack:** Python server/router/tests, C LVGL shared screens, simulator CMake/SDL screenshot harness, pytest, mock scenes.

---

### Task 1: Confirm-Flow Safety Unification

**Files:**
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py`
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `/home/jupiter/ave-xiaozhi/shared/ave_screens/screen_limit_confirm.c`
- Test: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_ave_router.py`
- Test: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_trade_flows.py`

- [ ] Write failing tests for voice exits from `confirm/limit_confirm`, `limit_confirm` screen-state correctness, and `LIMIT_CONFIRM` anti-mis-tap parity.
- [ ] Run focused RED commands and confirm the new tests fail for the expected reason.
- [ ] Implement the minimal routing/state/screen changes to make those tests pass.
- [ ] Run focused GREEN commands, then rerun the broader confirm/trade suites.
- [ ] Report changed files, RED/GREEN commands, and any residual risk.

### Task 2: Screenshot Regression Expansion

**Files:**
- Modify: `/home/jupiter/ave-xiaozhi/simulator/CMakeLists.txt`
- Modify/Create: `/home/jupiter/ave-xiaozhi/simulator/mock/verify_screenshot_feed.c` or split helpers if needed
- Modify/Create: `/home/jupiter/ave-xiaozhi/simulator/mock/run_screenshot_test.sh`
- Create/Modify: `/home/jupiter/ave-xiaozhi/simulator/mock/screenshot/baselines/*`
- Optional Create: deterministic mock payload helpers under `/home/jupiter/ave-xiaozhi/simulator/mock/`

- [ ] Write failing screenshot coverage checks for additional core screens beyond FEED.
- [ ] Run RED command(s) showing missing baselines or mismatched expected coverage.
- [ ] Implement the smallest deterministic harness expansion to cover multiple core screens.
- [ ] Generate/update baselines intentionally and rerun GREEN commands.
- [ ] Report changed files, runbook, baseline paths, and stability risks.

### Task 3: Trade Attribution + Stronger E2E

**Files:**
- Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`
- Modify/Test: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_p3_trade_flows.py`
- Modify/Test: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_ave_api_matrix.py`
- Modify/Test: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/test_ave_e2e.py`
- Optional Modify: `/home/jupiter/ave-xiaozhi/server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`

- [ ] Write failing tests around ambiguous terminal events, deferred-result attribution, and stronger E2E assertions where practical.
- [ ] Run focused RED commands and verify genuine failures.
- [ ] Implement minimal attribution hardening without adding fallback-heavy behavior.
- [ ] Run focused GREEN commands, then rerun the integrated server regression suite.
- [ ] Report changed files, RED/GREEN commands, and any remaining launch blocker.

### Task 4: Manager Review and Integrated Verification

**Files:**
- Review outputs from Tasks 1-3
- Optionally update: `/home/jupiter/ave-xiaozhi/docs/product-director-backlog-2026-04-07-worker-e.md`

- [ ] Review each agent result for spec compliance first.
- [ ] Review each agent result for code quality and test sufficiency.
- [ ] Run integrated verification across server and simulator.
- [ ] Summarize what is now fixed, what remains open, and whether release-readiness changed.
