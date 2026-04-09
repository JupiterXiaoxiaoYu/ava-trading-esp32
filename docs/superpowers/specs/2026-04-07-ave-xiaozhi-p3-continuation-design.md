# AVE Xiaozhi P3 Continuation Design

**Scope:** Continue from the interrupted `ave-xiaozhi-implementation` session and finish remaining P3 work in the order approved by the user.

**Reference Specs:**
- `/home/jupiter/ave-xiaozhi/docs/pending-tasks.md`
- `/home/jupiter/ave-xiaozhi/docs/ave-feature-map.md`

## Approved Execution Order

1. Batch 1: `P3-3`, `P3-4`, `P3-6`, `P3-7`
2. Batch 2: `P3-5`
3. Batch 3: `P3-1`, `P3-2`

## Batch 1 Design

### P3-3 — kline interval dynamic enhancement
- Keep the existing `ave_token_detail(...)` call as the source of truth for the spotlight payload.
- After the payload is refreshed, explicitly update the WSS spotlight subscription interval from the `kline_interval` key handler.
- Use the existing `AveWssManager.set_spotlight(...)` signature and pass the currently selected token and the new interval in `kNN` format.

### P3-4 — CONFIRM/LIMIT_CONFIRM Y-key protection
- Preserve `Y` as a global shortcut to portfolio.
- If `Y` is pressed while the current screen is `CONFIRM` or `LIMIT_CONFIRM`, first send the existing `cancel_trade` key action to the server, then navigate to portfolio.
- This closes the pending-trade window before leaving the confirmation screen.

### P3-6 — FEED B-key gentle hint
- `LEFT` remains the feed refresh key.
- `B` on FEED shows a short NOTIFY overlay with `已在首页`.
- The event should not trigger source refresh or screen navigation.

### P3-7 — kline point count optimization
- Replace the current two-bucket kline size heuristic with an explicit interval map:
  - `5` -> `48`
  - `60` -> `48`
  - `240` -> `42`
  - `1440` -> `30`
- Unknown intervals should fall back to `48`.

## Batch 2 Design

### P3-5 — RESULT follows nav_from
- RESULT auto-dismiss and any-key exit should follow the same server-driven `back` semantics already used by SPOTLIGHT/PORTFOLIO.
- C-side RESULT should send `{"type":"key_action","action":"back"}` instead of directly calling `ave_sm_go_to_feed()`.
- Server-side `back` already reads `nav_from`; this becomes the single navigation authority.
- If the server does not respond, C-side RESULT should keep a short fallback path to FEED to avoid a dead-end screen.

## Batch 3 Design

### P3-1 — list pending limit orders
- Add a server tool that fetches pending limit orders from the documented AVE endpoint.
- Reuse FEED rendering with an explicit orders mode payload instead of inventing a new screen.
- Include only the fields needed for on-device scanability and later cancellation.

### P3-2 — cancel pending limit orders
- Add a server tool that cancels one or more orders using IDs produced by P3-1.
- Cancellation uses the existing confirm/result/notify flow instead of inventing a new path.

## Testing Strategy
- Python behavior changes use TDD with focused unit tests where feasible.
- C UI changes are verified via build-level validation because no local LVGL unit harness exists in this repo.
- Before claiming completion, run fresh verification commands for the touched Python and C codepaths.
