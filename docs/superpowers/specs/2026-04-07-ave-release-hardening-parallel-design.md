# AVE Release Hardening Parallel Design

**Date:** 2026-04-07
**Scope:** Parallel hardening round covering confirm-flow safety, screenshot regression, and trade terminal attribution/E2E.

## Goal

Close the highest-confidence gaps that still block a real-money-ready AVE experience without introducing fallback-heavy debt.

## Approved execution shape

This round runs as three parallel tracks with disjoint ownership:

1. **Confirm-flow safety unification**
   - Unify voice and key exit behavior on `confirm` / `limit_confirm`
   - Ensure leaving a confirm screen always cancels pending trade first
   - Align `LIMIT_CONFIRM` with `CONFIRM` anti-mis-tap semantics
   - Fix server-side screen-state drift between `confirm` and `limit_confirm`

2. **Screenshot regression expansion**
   - Extend the existing simulator screenshot harness from one FEED scene to a small release gate for core screens
   - Prefer deterministic mock-scene or directly seeded display payloads
   - Keep the workflow runnable locally from `simulator/` without live server dependency

3. **Trade attribution + stronger E2E**
   - Tighten terminal trade-event attribution so deferred results are less ambiguous
   - Strengthen API/E2E tests around `submit != confirmed`
   - Preserve current deterministic behavior and avoid speculative fallback paths

## Constraints

- Use agents as implementers; main session acts as manager/reviewer.
- Do not revert unrelated dirty worktree changes.
- Use TDD per track.
- Changes must stay grounded in current UI, keyboard bindings, current AVE API behavior, and current docs.

## Success criteria

- Confirm/limit-confirm safety rules are behaviorally consistent across key and voice.
- Screenshot regression can verify multiple core screens with repeatable commands.
- Trade attribution/E2E coverage is stronger and demonstrably green.
- Final verification includes targeted tests plus an integrated regression pass.
