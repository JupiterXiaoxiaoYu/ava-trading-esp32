# Spotlight Live Kline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit `Live 1s` and `Live 1m` spotlight chart modes without reintroducing automatic chart takeover.

**Architecture:** Extend the spotlight interval contract end-to-end, special-case `s1` and `1` on the server, and let WSS push chart redraws only when the selected interval is a live mode. Keep historical modes on the existing REST-first flow.

**Tech Stack:** C/LVGL simulator UI, Python xiaozhi server, pytest, screenshot verification

---

### Task 1: Red tests for live interval contract

**Files:**
- Modify: `server/main/xiaozhi-server/test_ave_api_matrix.py`
- Modify: `server/main/xiaozhi-server/test_p3_batch1.py`
- Modify: `simulator/mock/verify_ave_json_payloads.c`

- [ ] Add failing tests for `interval="1"` mapping to REST `1` + WSS `k1`
- [ ] Add failing tests for `interval="s1"` avoiding REST kline and seeding a live chart
- [ ] Add failing tests proving live-mode `_on_kline_event()` pushes a refreshed spotlight chart
- [ ] Add failing UI contract checks for `s1 -> L1S` and `1 -> L1M`

### Task 2: Implement server live interval handling

**Files:**
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`
- Modify: `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`

- [ ] Implement a shared helper to build chart payloads from live raw points
- [ ] Teach `ave_token_detail()` to special-case `s1` and `1`
- [ ] Teach WSS spotlight state to refresh chart only for selected live intervals
- [ ] Preserve ordinary timeframe behavior unchanged

### Task 3: Implement client interval labels and cycling

**Files:**
- Modify: `shared/ave_screens/screen_spotlight.c`
- Modify: `simulator/mock/verify_ave_json_payloads.c`

- [ ] Extend interval arrays to `s1/1/5/60/240/1440`
- [ ] Map payload values to `L1S/L1M/5M/1H/4H/1D`
- [ ] Keep existing up/down cycling and key payload format
- [ ] Verify top bar layout still fits

### Task 4: Verify and refresh UI baselines

**Files:**
- Modify: `simulator/mock/screenshot/baselines/spotlight.ppm`

- [ ] Run targeted pytest slices
- [ ] Rebuild simulator targets
- [ ] Run JSON payload verification
- [ ] Run spotlight screenshot gate and refresh baseline if diff is expected
