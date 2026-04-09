# AVE Xiaozhi Product-Director Backlog & Launch Review (Worker E)

> Date: 2026-04-07  
> Scope: current implemented UI/keymap/voice-FN-PTT/API/test/docs only (no imagined features)

## One-line positioning and overall score

- Product score: **63/100**
- Positioning judgement: **engineering demo and closed beta ready; not ready for open real-fund launch**.

Reason: core interaction loop is mostly runnable, but trade-state consistency, result attribution, and evidence/observability are still below real-money trust threshold.

---

## Priority backlog (P0/P1/P2)

## P0 (launch blockers)

### P0-1 Voice vs key entry inconsistency on confirmation screens can leave orphan pending trades

- Problem:
  - Voice router directly handles `我的持仓/持仓` and `看热门/刷新热门` without pending-trade guard (direct tool call).
  - Hardware `Y` key explicitly cancels pending trade before going to portfolio.
  - This creates two different safety semantics for the same user intention "leave confirm page".
- User impact:
  - User believes they exited/aborted, but pending trade may remain active in server state; later trade events can be delayed or mis-attributed.
- Repro path/page:
  - `CONFIRM` or `LIMIT_CONFIRM` page -> speak `我的持仓` or `看热门`.
- Evidence:
  - `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py:221`
  - `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py:226`
  - `shared/ave_screens/ave_screen_manager.c:227`
- Suggested direction:
  - Add a unified "exit confirm intent" guard: any route from confirm/limit_confirm to feed/portfolio must run `cancel_trade` first (voice and key both).
- Existing test coverage:
  - **Partial only**: back-path cancel is covered, but `我的持仓/看热门` from confirm is not covered.

### P0-2 Trade terminal-state attribution is not order-correlated; financial trust risk remains

- Problem:
  - Trade WSS terminal events are deferred whenever *any* pending trade exists, without strict order-id correlation.
  - Submit-only ACK now has built-in `getSwapOrder` reconciliation, but correlation confidence still depends on current mapping/evidence depth in live traffic.
- User impact:
  - "which trade just succeeded/failed" can be unclear in multi-trade sessions; customer support and dispute handling are weak.
- Repro path/page:
  - `CONFIRM` pending trade B active -> receive terminal event from trade A -> event deferred, later flushed after pending clears.
- Evidence:
  - `server/main/xiaozhi-server/plugins_func/functions/ave_wss.py:961`
  - `server/main/xiaozhi-server/plugins_func/functions/ave_wss.py:984`
  - `server/main/xiaozhi-server/test_p3_trade_flows.py:168`
  - `docs/ave-feature-map.md:63`
- Suggested direction:
  - Introduce strict event correlation key (order id / tx id / trade_id mapping table) before RESULT enqueue/flush.
  - Keep `getSwapOrder` reconciler and extend live-case evidence (ambiguous/delayed WSS) with archived samples and replay checks.
- Existing test coverage:
  - **Yes (mechanism exists)** but coverage proves current behavior, not correctness for real-money attribution.

### P0-3 Real-launch evidence is still insufficient (live event sample + true E2E closure)

- Problem:
  - Current E2E is script-style display checking, not assertion-rich product acceptance; trade path intentionally uses `balance_raw="0"` to avoid real sell.
  - Team docs still record no captured real trade WSS sample in current round.
- User impact:
  - Cannot confidently claim end-to-end real-fund reliability before public launch.
- Repro path/page:
  - Run current E2E flow; result is pass/fail printouts, not contract-level launch proof.
- Evidence:
  - `server/main/xiaozhi-server/test_ave_e2e.py:99`
  - `server/main/xiaozhi-server/test_ave_e2e.py:182`
  - `docs/pending-tasks.md:34`
- Suggested direction:
  - Add production-like smoke with tiny real amount + sampled order-event archive + post-trade reconciliation report.
- Existing test coverage:
  - **Partial**: many unit/regression tests pass, but real-trade closure evidence remains missing.

## P1 (major product debt)

### P1-1 Search/special-source navigation model is inconsistent after spotlight return

- Problem:
  - Search feed displays as special source, but `feed_source/feed_platform` state is not updated by search tool.
  - Spotlight `back` rebuilds feed from stored source/platform, often returning to old trending/topic instead of prior search result context.
- User impact:
  - User loses search context and has to re-search; mental model of "back" breaks.
- Repro path/page:
  - `FEED (SEARCH results)` -> `SPOTLIGHT` -> `B/返回` -> returns non-search feed source.
- Evidence:
  - `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py:1136`
  - `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py:1146`
  - `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py:190`
- Suggested direction:
  - Persist and restore `last_special_source_context` (type+query+chain+cursor) for search/order modes.
- Existing test coverage:
  - **No direct coverage** for search->spotlight->back context retention.

### P1-2 LIMIT_CONFIRM confirmation safety is weaker than CONFIRM; page-state label drift exists

- Problem:
  - `CONFIRM` has 500ms anti-mis-tap guard; `LIMIT_CONFIRM` does not.
  - Pending trade helper sets `screen="confirm"` universally; limit confirm route does not explicitly overwrite to `limit_confirm` in server state.
- User impact:
  - Higher accidental confirm risk for limit orders; voice/page-state interpretation can drift from actual UI.
- Repro path/page:
  - Enter `LIMIT_CONFIRM` and fast-press `A`; compare with `CONFIRM` behavior.
- Evidence:
  - `shared/ave_screens/screen_confirm.c:351`
  - `shared/ave_screens/screen_limit_confirm.c:286`
  - `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py:305`
  - `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py:1838`
- Suggested direction:
  - Apply one confirmation safety contract to both confirm screens (anti-tap + explicit page-state write).
- Existing test coverage:
  - **Partial**: limit payload contract tested, but anti-mis-tap and screen-state consistency not tested.

### P1-3 Symbol-intent routing can be ambiguous across chains/sources

- Problem:
  - `feed_tokens` map is keyed by upper symbol only; duplicate symbols across chains overwrite each other.
  - Voice commands like `看BONK`/`买BONK` can resolve to unintended token.
- User impact:
  - Wrong token detail/trade route risk, especially in multi-chain contexts.
- Repro path/page:
  - Feed contains same symbol on multiple chains -> voice `看<symbol>` or `买<symbol>`.
- Evidence:
  - `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py:1063`
  - `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py:111`
- Suggested direction:
  - Resolve by ranked candidate list (visible list position + chain disambiguation prompt), not 1-symbol-1-entry overwrite.
- Existing test coverage:
  - **No coverage** for duplicate-symbol ambiguity.

### P1-4 FN/PTT has protocol-level listen start/stop, but parity validation is still incomplete

- Problem:
  - Simulator FN/PTT (`F1`) now emits protocol-level `listen` transitions on press/release (`start`/`stop`, `mode=manual`).
  - However, there is still limited automated parity coverage between simulator key timing and device/ASR voice-state machine edge cases.
- User impact:
  - Core semantics are aligned, but long-press/repeat/focus-loss edge behavior could still diverge without dedicated parity tests.
- Repro path/page:
  - Simulator press and release `F1`; observe websocket JSON `{"type":"listen","state":"start","mode":"manual"}` then `{"type":"listen","state":"stop","mode":"manual"}`.
- Evidence:
  - `simulator/src/sim_keymap.c:6`
  - `simulator/src/main.c:127`
- Suggested direction:
  - Keep protocol-level mapping as baseline and add simulator/device parity tests for long-press, key-repeat suppression, and focus-loss recovery.
- Existing test coverage:
  - **Partial**: implementation is in place, but dedicated simulator parity automation is still limited.

### P1-5 Portfolio expression still lacks decision-critical fields

- Problem:
  - UI presents `Symbol/Value/P&L`; no position quantity column, no cost-basis, P&L often `N/A`.
- User impact:
  - Users cannot quickly judge exposure and realized/unrealized logic; sell decisions are less informed.
- Repro path/page:
  - Open `PORTFOLIO`; inspect list and top summary.
- Evidence:
  - `shared/ave_screens/screen_portfolio.c:226`
  - `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py:2041`
  - `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py:2063`
- Suggested direction:
  - Add quantity and cost-basis readiness flags; if cost-basis unavailable, explicitly label "valuation only" instead of pseudo-P&L area.
- Existing test coverage:
  - **Partial**: schema stability covered, UX meaning correctness not covered.

## P2 (important but non-blocking)

### P2-1 Spotlight risk panel is too compressed for high-stakes decisions

- Problem:
  - Current spotlight risk display is badge-heavy but explanation-light (risk_level + mint/freeze + holders/liq); no explicit risk reason/source freshness.
- User impact:
  - Users may over-trust short badges without understanding why risk is high/critical.
- Repro path/page:
  - Open `SPOTLIGHT`; inspect risk badges and data row.
- Evidence:
  - `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py:1439`
  - `shared/ave_screens/screen_spotlight.c:223`
- Suggested direction:
  - Introduce a compact second-layer risk explainer (top 1-2 reason tags + source timestamp).
- Existing test coverage:
  - **No UX-level coverage**.

### P2-2 RESULT page closes too quickly for some failure/debug scenarios

- Problem:
  - RESULT auto-dismisses in 3s regardless of complexity of message.
- User impact:
  - Users can miss tx/error detail, especially on slower reading speed or noisy environment.
- Repro path/page:
  - Trigger RESULT with long/complex error text and wait.
- Evidence:
  - `shared/ave_screens/screen_result.c:281`
- Suggested direction:
  - Keep 3s default for success, but longer dwell/explicit dismiss for failures or long text.
- Existing test coverage:
  - **No behavior tests** for dwell-time UX policy.

### P2-3 Screenshot regression gate exists, but coverage is still only first-stage

- Problem:
  - The simulator now has a screenshot regression gate for `FEED / FEED_SEARCH / FEED_SPECIAL_SOURCE / SPOTLIGHT / CONFIRM / LIMIT_CONFIRM / RESULT / RESULT_FAIL / PORTFOLIO`, but it is still a first-stage gate rather than full release-grade visual coverage.
  - The gate currently relies on per-screen isolated process runs for determinism; cross-screen transition continuity is still outside this gate.
- User impact:
  - Major layout regressions are now easier to catch, but some important UI states can still drift unnoticed, especially failure/result variants and cross-screen transition artifacts.
- Repro path/page:
  - Run `cd /home/jupiter/ave-xiaozhi/simulator && ./mock/run_screenshot_test.sh`.
- Evidence:
  - `simulator/mock/verify_screenshot_feed.c`
  - `simulator/mock/run_screenshot_test.sh`
  - `simulator/mock/screenshot/baselines/*.ppm`
- Suggested direction:
  - Keep this gate as a release prerequisite, then expand with high-risk transition scenes and additional dynamic-state variants.
- Existing test coverage:
  - **Partial**: nine core/static scenes are now covered by simulator screenshot baselines.

### P2-4 Product observability is log-centric; missing user-journey metrics

- Problem:
  - Current validation relies on logs + manual scripts; lacks structured product KPIs (confirm abandon, deferred-result ratio, back-fallback rate).
- User impact:
  - Hard to detect UX debt in production before support tickets accumulate.
- Repro path/page:
  - Review tests/docs: no KPI definitions or metric assertions for AVE journey quality.
- Evidence:
  - `server/main/xiaozhi-server/test_ave_e2e.py` is script-driven print workflow, not KPI assertion suite.
- Suggested direction:
  - Add event schema and dashboard-ready counters for each screen transition and trade funnel stage.
- Existing test coverage:
  - **None** for product telemetry KPIs.

---

## Director judgement on three requested policy topics

### 1) Should we add screenshot regression?

- Decision: **Yes — and an initial gate now exists; keep expanding it before real launch**.
- Why:
  - Current quality gate is strong on protocol/contracts, weak on visual correctness and screen legibility.
- Minimal gate proposal:
  - Current implemented gate: FEED, FEED_SEARCH, FEED_SPECIAL_SOURCE, SPOTLIGHT, CONFIRM, LIMIT_CONFIRM, RESULT, RESULT_FAIL, PORTFOLIO.
  - Next expansion: transition-heavy scenes and visually distinct high-risk spotlight variants.

### 2) Should we pass page context to LLM?

- Decision: **Yes, continue and strengthen (already implemented)**.
- Current status:
  - Context is injected as temporary `[AVE_CONTEXT]...[/AVE_CONTEXT]` user message.
- Hardening needed:
  - Add schema version and strict "allowed_actions" enforcement in router/handoff boundary, not prompt-only reliance.
- Evidence:
  - `server/main/xiaozhi-server/core/connection.py:920`
  - `server/main/xiaozhi-server/core/connection.py:1258`

### 3) Voice-state vs page-state UX constraints (recommended contract)

- Decision: **Must define and enforce as product invariant**.
- Recommended invariants:
  - `INV-1`: On `confirm/limit_confirm`, any route to feed/portfolio/search must cancel pending trade first.
  - `INV-2`: Voice and key intents with same semantic target must share one transition policy.
  - `INV-3`: Router may execute only if `allowed_actions` contains the action for current page-state.
  - `INV-4`: If screen state and displayed page diverge, reject high-risk actions and force re-sync.

---

## Verification basis used for this review

- Code and docs inspection:
  - `shared/ave_screens/*.c`
  - `simulator/src/main.c`, `simulator/src/sim_keymap.c`
  - `server/main/xiaozhi-server/core/handle/textHandler/*.py`
  - `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
  - `server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`
  - `docs/simulator-ui-guide.md`, `docs/ave-feature-map.md`, `docs/pending-tasks.md`
- Fresh regression run (2026-04-07):

```bash
cd /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server
pytest -q test_ave_api_matrix.py test_p3_trade_flows.py test_ave_router.py test_ave_voice_protocol.py test_ave_e2e.py
```

Result:

```text
82 passed, 1 warning, 25 subtests passed in 5.32s
```

---

## Suggested next-agent execution order

1. Close P0-1 + P1-2 together (state machine and confirm safety contract unification).  
2. Close P0-2 with correlation key + order reconciliation endpoint integration.  
3. Add screenshot regression gate and product telemetry KPIs (P2-3/P2-4).  
4. Then improve search/nav continuity and portfolio/spotlight information expression.
