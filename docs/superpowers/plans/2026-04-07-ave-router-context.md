# AVE Router And Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic AVE command router and standardized AVE UI context so device-like commands stop depending on prompt-only tool selection.

**Architecture:** Introduce a small router ahead of `startToChat()` for high-certainty AVE commands, plus a shared `ave_context` builder used both by the router and by the LLM handoff path. Keep the change localized to listen handling and AVE state helpers.

**Tech Stack:** Python, existing xiaozhi text handlers, AVE tool functions, pytest/unittest-style regression tests.

---

### Task 1: Add failing tests for deterministic AVE utterance routing
- [ ] Cover feed/portfolio/spotlight/confirm utterances with direct expectations.
- [ ] Verify current code fails on at least one of: `买这个`, `确认`, `看ROCKET`.

### Task 2: Add shared AVE context builder and command classification helpers
- [ ] Build a normalized context object from `conn.ave_state`.
- [ ] Define allowed actions per screen.

### Task 3: Add deterministic AVE router before LLM handoff
- [ ] Route screen-bound commands directly to AVE tools.
- [ ] Return deterministic rejection when state is missing.

### Task 4: Inject ave_context into non-router LLM path
- [ ] Ensure open-ended language still flows to LLM.
- [ ] Make current UI state available to downstream intent handling.

### Task 5: Verify with focused tests and existing AVE regressions
- [ ] Run targeted router tests.
- [ ] Run existing AVE regression suites.
