# SPOTLIGHT Rich Detail Design

**Date:** 2026-04-10
**Status:** Draft for review
**Scope:** `SPOTLIGHT` single-token detail page in `ava-trading-esp32`

---

## 1. Goal

Upgrade `SPOTLIGHT` from a price-chart-risk snapshot into a denser but still one-screen decision surface, without adding new key conflicts or turning the page into a research terminal.

The redesign must:
- keep the current `A / X / B / LEFT / RIGHT / UP / DOWN` mental model unchanged
- fit all added data in the existing 320x240 landscape page
- avoid temporary blank-state flicker during interval or next/prev token transitions
- fix false-positive risk labeling caused by unsafe server-side boolean coercion
- avoid using `main pair` as a new dependency for this round

---

## 2. User Problem

Current `SPOTLIGHT` is already usable, but it has three material gaps:

1. The page lacks enough market structure context for fast decision-making. The user can see price, 24h change, holders, and liquidity, but not 24h volume, market cap, top-holder concentration, or a readable contract identity.
2. The current risk normalization is unsafe. Some AVE contract payloads return values like `-1` for `is_honeypot`; the current `bool(...)` coercion incorrectly turns those into `True`, making many assets look like honeypots.
3. The page must stay action-first. Adding another info page, info carousel, or extra key would increase cognitive load and create button conflicts with existing buy/sell/navigation behavior.

So the correct solution is not “more pages”, but “better packing, better normalization, and safer refresh behavior on the same page.”

---

## 3. Constraints

- Device surface is fixed at `320x240`.
- Existing key map must remain stable:
  - `LEFT/RIGHT`: previous/next token
  - `UP/DOWN`: kline interval cycle
  - `A`: buy
  - `X`: quick sell
  - `B`: back
- No new button semantics may be introduced.
- Only token names may remain CJK-capable. System chrome and system messages remain English.
- User explicitly does **not** want `main pair` integrated in this round.
- Contract short identity should appear on the fourth line below the chart, not in the top bar.
- Transition behavior should feel stable: do not clear good data to placeholders while fetching the next valid spotlight state.

---

## 4. Chosen Approach

### Option A — One-screen denser layout (recommended)

Keep a single `SPOTLIGHT` page, retain the chart, and reorganize the post-chart area into four compact lines:

1. `Risk | Mint | Freeze`
2. `Vol24h | Liq | Mcap`
3. `Holders | Top10`
4. `CA short`

Pros:
- no new key semantics
- preserves current fast trading muscle memory
- all critical decision data stays visible at once
- lowest product risk

Cons:
- tighter layout work in LVGL
- formatting discipline is required to avoid overflow

### Option B — Info toggle state

Use one key to flip between “trade view” and “info view”.

Pros:
- easier spacing
- can show more fields with larger typography

Cons:
- adds statefulness and recall burden
- creates button conflict risk
- hides information exactly when the user needs fast comparison

### Option C — Secondary details page

Push extra data into a second page under `SPOTLIGHT`.

Pros:
- simplest visual layout

Cons:
- slower decision flow
- increases navigation depth
- directly conflicts with the product’s current “short path to trade” direction

**Decision:** Option A.

---

## 5. Page Design

### 5.1 Top Bar

Keep the current top bar role unchanged:
- left: symbol / token identity
- center/right: compact price
- far right: 24h change
- interval badge remains on-chart
- feed position indicator remains when present

Top bar should stay focused on “what asset is this right now” and “what is it doing now”, not on deep metadata.

### 5.2 Chart Area

Keep the existing kline chart, existing time labels, and existing interval cycling behavior.

This redesign does not change:
- interval set
- live/subscribed kline pipeline
- chart normalization strategy

This redesign **does** require that interval switching and next/prev token switching stop visually regressing to placeholder data before the real payload arrives. Good current data should remain visible until a newer valid payload is ready.

### 5.3 Post-Chart Information Block

The chart footer becomes a four-line information block.

#### Line 1
- `Risk`
- `Mint`
- `Freeze`

This remains the safety line. `HONEYPOT` still dominates the risk label when truly present.

#### Line 2
- `Vol24h`
- `Liq`
- `Mcap`

These are the fast market-structure numbers needed to judge whether price movement is meaningful.

#### Line 3
- `Holders`
- `Top10`

`Top10` is the top-10 holder concentration summary, shown as a percentage when available.

#### Line 4
- `CA: 0x1234...abcd`

This is a short contract identity string derived from the token address. It is not interactive; it is there to reduce same-symbol ambiguity.

### 5.4 No Secondary Info Mode

No info toggle, no extra overlay, no details pager, and no extra buttons in this round.

The user should never have to choose between “see data” and “trade now”.

---

## 6. Data Model and API Mapping

### 6.1 Existing Sources Already in Use

Current `SPOTLIGHT` server path already uses:
- `GET /v2/tokens/{token}-{chain}` for token detail
- `GET /v2/contracts/{token}-{chain}` for risk contract flags
- `GET /v2/klines/token/{token}-{chain}` for chart data

### 6.2 Added Fields

The redesigned payload should add these presentation fields:
- `volume_24h`
- `market_cap`
- `top10_concentration`
- `contract_short`

### 6.3 Field Sourcing

- `volume_24h`: sourced from token detail when available, already present in existing feed shaping logic as an AVE-compatible concept.
- `market_cap`: sourced from token detail via `market_cap`, with `fdv` as the display fallback if direct market cap is absent.
- `top10_concentration`: sourced from the holders endpoint if available, otherwise `N/A`.
- `contract_short`: derived locally from the token address using prefix + suffix shortening.

### 6.4 Explicit Non-Goals

This round does **not** add:
- main pair detail
- full top holders list
- separate holders page
- trade history on `SPOTLIGHT`
- issuer / smart wallet / whale / signals expansion

---

## 7. Risk Normalization Fix

Current server code uses raw `bool(...)` coercion for contract flags. This is unsafe for AVE responses where numeric sentinel values like `-1` can mean “unknown / not detected / unavailable” rather than `true`.

The server must introduce explicit normalization for contract booleans:
- treat only `1`, `true`, `"true"`, `"1"`, `"yes"`, `"y"` as true
- treat `0`, `false`, `"false"`, `"0"`, `-1`, empty strings, `None`, and missing fields as false unless AVE documentation later proves otherwise

This applies at least to:
- `is_honeypot`
- `has_mint_method` / `is_mintable`
- `has_black_method` / `is_freezable`

The purpose is simple: `HONEYPOT` must only appear when the API positively says so.

---

## 8. Formatting Rules

To make the denser layout readable, server formatting should happen before the payload reaches LVGL where reasonable.

### Number formatting
- volume, liquidity, and market cap use the existing compact money formatter style
- holders remain grouped with commas when exact count is available
- top10 concentration displays as percent with one decimal when meaningful, otherwise `N/A`
- contract short displays `prefix...suffix` and should be stable across chains

### Overflow behavior
- do not let a single missing/long field collapse the row
- when data is unavailable, display `N/A`, not empty strings that visually look broken
- token names remain separately handled by the existing CJK-capable font path; numeric/stat rows remain in the normal system font

---

## 9. Interaction Behavior

Key behavior stays unchanged.

- `A`: buy current spotlight token
- `X`: quick sell current spotlight token
- `B`: back
- `LEFT/RIGHT`: previous / next spotlight token from feed context
- `UP/DOWN`: cycle kline interval

The redesign must not introduce any new interaction state that can trap the user or alter these meanings.

---

## 10. Loading and Transition Behavior

A correct `SPOTLIGHT` refresh should behave like a state replacement, not a state collapse.

### Required behavior
- while next interval or next token data is loading, the current valid payload stays on screen
- once the next valid payload is ready, replace the old state in one update
- loading guard still prevents accidental duplicate actions
- invalid or stale requests must never overwrite newer spotlight state

### Not acceptable
- clearing the footer rows to placeholders and then filling them later
- jumping to an empty target spotlight and then snapping back
- showing “fake safe / fake honeypot” values due to partial or stale risk data

---

## 11. Testing Strategy

### Server tests
Add or update tests for:
- `_risk_flags()` boolean normalization across `1 / 0 / -1 / missing / string booleans`
- spotlight payload shaping with new fields present
- spotlight payload shaping with missing top10 / market cap values returning `N/A`
- stale request protection so older spotlight responses do not replace newer ones

### UI / surface tests
Add or update tests for:
- new spotlight JSON fields parsing correctly in `screen_spotlight.c`
- line rendering / field labels for all four post-chart lines
- no regressions in interval switching and feed prev/next state persistence

### Manual validation
Validate in simulator and, when practical, against the running server:
- normal token with full data
- token with missing market cap / missing holders concentration
- token with `is_honeypot = -1`
- rapid interval switching
- rapid `watch next` switching

---

## 12. Implementation Impact

Expected primary touch points:
- `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- `server/main/xiaozhi-server/test_ave_api_matrix.py`
- `server/main/xiaozhi-server/test_trade_contract_fixes.py`
- `shared/ave_screens/screen_spotlight.c`
- spotlight-related simulator/surface tests if coverage gaps appear

This should remain an incremental change, not a subsystem rewrite.

---

## 13. Success Criteria

This work is successful when:
- `SPOTLIGHT` shows `Vol24h`, `Liq`, `Mcap`, `Holders`, `Top10`, and short contract identity on one page
- no new key/button behavior is introduced
- honeypot labeling no longer false-triggers from `-1` or other non-true sentinel values
- switching token or interval no longer visually collapses to blank placeholders before the target payload arrives
- simulator and server tests cover the new payload and risk normalization paths

---

## 14. Rollout Note

This is a ship-quality refinement pass on an existing page, not a feature expansion into research mode.

If later rounds need deeper asset analysis, that should become a separate product surface, not more hidden density inside `SPOTLIGHT`.
