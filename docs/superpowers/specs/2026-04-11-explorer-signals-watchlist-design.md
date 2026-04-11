# Explorer Signals And Watchlist Design

**Date:** 2026-04-11
**Status:** Draft for review
**Scope:** Add `Signals` and `Watchlist` as shallow `Explore` entries, and add voice-first watchlist actions from `SPOTLIGHT`.

---

## 1. Goal

Extend the existing `FEED -> Explore` model with two lightweight, browse-first capabilities:
- `Signals` for discovery from AVE public signal data
- `Watchlist` for user-saved tokens that can be revisited quickly

The design must preserve the current product shape:
- no new deep menu tree
- no new keyboard dependency
- no new `SPOTLIGHT` button conflicts
- no shift away from the current action-first flow centered on `FEED`, `SPOTLIGHT`, `PORTFOLIO`, and `RESULT`

This is a reachability and retention enhancement, not a research-terminal expansion.

---

## 2. User Problem

The product currently has two gaps around discovery and return visits:

1. There is no lightweight way to browse structured public trading signals from the device UI, even though `GET /signals/public/list` is available and already returns usable token-linked signal data.
2. There is no first-class way to save a token for later and revisit it without repeating voice search or waiting for it to reappear in feed sources.

At the same time, the device has a hard interaction constraint:
- only 8 buttons
- no text keyboard
- existing `SPOTLIGHT` buttons are already fully loaded by trading and navigation semantics

So the right answer is not “add more buttons” or “make a deep menu,” but:
- keep new entry points inside `Explore`
- keep `Signals` and `Watchlist` browse-only
- keep `SPOTLIGHT` as the single-token center
- make watchlist add/remove voice-first from token context

---

## 3. Constraints

- Device surface remains the current landscape screen and key model.
- `FEED -> B -> Explore` is already established as a shallow local entry layer.
- `SPOTLIGHT` key map stays unchanged:
  - `UP/DOWN`: kline interval
  - `LEFT/RIGHT`: previous / next token
  - `A`: buy
  - `X`: quick sell
  - `B`: back
  - `Y`: global `PORTFOLIO`
- No new global entry button is available for a standalone watchlist page.
- User explicitly wants solutions that work with voice + buttons, not keyboard-driven flows.
- `tx / holders / pair / liq` should not become Explorer top-level entries in this round.

---

## 4. Considered Approaches

### Option A — `Signals` only in Explore

Add only `Signals` as a new Explore item, and postpone watchlist.

Pros:
- smallest UI change
- easiest to implement

Cons:
- does not solve token retention / revisit
- misses the user need for a saved list

### Option B — `Signals` and `Watchlist` as shallow Explore entries (recommended)

Add both as top-level Explore entries. Keep both pages browse-only and route selected tokens into `SPOTLIGHT`.

Pros:
- solves both discovery and revisit
- fits existing Explore mental model
- does not require a new global button
- preserves `SPOTLIGHT` trading keys

Cons:
- Explore grows from 3 to 5 items
- requires a small local watchlist storage layer

### Option C — Dedicated global Watchlist page

Create a new page outside Explore and try to expose it as a global surface.

Pros:
- watchlist would be more prominent

Cons:
- there is no clean spare button to enter it
- would create reachability inconsistency
- risks key conflict with existing page model

**Decision:** Option B.

---

## 5. Chosen Product Shape

### 5.1 Explore Entries

`Explore` expands from 3 items to 5 items, in this order:
- `Search`
- `Orders`
- `Sources`
- `Signals`
- `Watchlist`

Rationale:
- keep the current high-frequency entries first
- place `Signals` before `Watchlist` because discovery comes before revisit
- avoid a second-level submenu

Key behavior remains unchanged:
- `UP/DOWN`: move selection
- `A/RIGHT`: enter selected item
- `B/LEFT`: close or return
- `Y`: keep existing global `PORTFOLIO` shortcut
- no new `X` meaning inside Explore

### 5.2 Signals Role

`Signals` is a browse-only discovery page backed by AVE public signal data.

It is not:
- a signal detail app
- a filter-heavy market scanner
- a research dashboard

Its single job is:
- show a compact list of signal-linked tokens
- let the user jump into `SPOTLIGHT` for the selected token

### 5.3 Watchlist Role

`Watchlist` is a browse-only saved-token page.

It is not:
- a portfolio replacement
- a complex multi-list organizer
- a personalized research workspace

Its single job is:
- show the user’s saved tokens
- let the user revisit or remove them

### 5.4 SPOTLIGHT Role

`SPOTLIGHT` remains the single-token decision page and the only token-level action center in this flow.

This design intentionally keeps all token detail continuation paths converging into `SPOTLIGHT`:
- `FEED -> SPOTLIGHT`
- `Signals -> SPOTLIGHT`
- `Watchlist -> SPOTLIGHT`

Future `tx / holders / pair` work should continue to enrich `SPOTLIGHT`, not create more top-level Explore destinations.

---

## 6. Signals Page Design

### 6.1 Data Requirements

`Signals` is backed by `GET /signals/public/list`.

The live probe already shows that signal rows include token identity and usable summary data such as:
- `symbol`
- `token`
- `chain`
- `signal_type`
- `signal_time`
- `headline`
- `action_type`
- `action_wallet_type`
- `action_count`
- `price_change_24h`
- `mc_cur`

The device page should receive only the minimum shaped fields needed for list rendering:
- `symbol`
- `token`
- `chain`
- `signal_type`
- `headline`
- `signal_time`
- optional compact enrichments: `action_type`, `action_count`, `price_change_24h`, `mc_cur`

### 6.2 Layout

The page should be a compact list similar in spirit to existing browse pages.

Per-row structure:
- primary line: `symbol  chain  signal_type`
- secondary line: short `headline` or short action summary such as `Smart buy x12`

Top bar:
- `SIGNALS`
- current cursor / total count

Bottom bar:
- `> Detail | B Back`

### 6.3 Interaction

- `UP/DOWN`: move selection
- `A/RIGHT`: open the selected token in `SPOTLIGHT`
- `B/LEFT`: return to `Explore`
- `X/Y`: no new page-local meaning in this round

### 6.4 Hand-off Into SPOTLIGHT

Selecting a signal opens `SPOTLIGHT` using:
- `token`
- `chain`
- a source hint such as `signal`

`SPOTLIGHT` should show a compact origin hint like:
- `From Signal`

The purpose is contextual continuity, not a new interaction state.

---

## 7. Watchlist Page Design

### 7.1 Storage Model

Watchlist should use a project-local lightweight storage layer, not an AVE cloud API.

Minimum stored fields:
- `token`
- `chain`
- `symbol`
- `added_at`

This keeps persistence simple and avoids over-coupling the saved list to any display-specific enrichment fields.

### 7.2 Display Model

The watchlist page should enrich saved items at render time using existing token detail / price-capable paths where practical.

Per-row structure:
- primary line: `symbol  chain`
- secondary line: `price  24h change`

Top bar:
- `WATCHLIST`

Bottom bar:
- `> Detail | X Remove | B Back`

### 7.3 Interaction

- `UP/DOWN`: move selection
- `A/RIGHT`: open selected token in `SPOTLIGHT`
- `X`: remove selected token from watchlist
- `B/LEFT`: return to `Explore`

Removing an item should refresh the current list in place without an intermediate navigation jump.

### 7.4 Hand-off Into SPOTLIGHT

When the user opens a token from watchlist, `SPOTLIGHT` should show a compact context hint like:
- `In Watchlist`

This is for orientation only and must not change `SPOTLIGHT` keys or transaction behavior.

---

## 8. Voice-First Watchlist Actions In SPOTLIGHT

`SPOTLIGHT` has no safe spare button for save / unsave:
- `A` and `X` are trading actions
- `LEFT/RIGHT` and `UP/DOWN` are navigation
- `B` and `Y` already have stable meanings

Therefore, watchlist add/remove must be voice-first.

### 8.1 Supported Intents

The server should add lightweight intent handling for:
- add current token to watchlist
- remove current token from watchlist
- open watchlist

Example phrases:
- `收藏这个币`
- `加入观察列表`
- `取消收藏`
- `打开观察列表`

### 8.2 Context Requirement

For add/remove, the current token must come from authoritative UI context:
- current `SPOTLIGHT` token
- current `chain`
- current display symbol when available

The user should not need to repeat the token name when they are already on the token page.

### 8.3 Why Voice Is Correct Here

This split keeps the interaction model clean:
- buttons are for high-frequency browse / trade actions
- voice handles secondary but still useful intents that are naturally phrased

This avoids introducing a fragile overloaded key on the most important action page in the product.

---

## 9. Empty States And Failure Handling

### 9.1 Signals

Empty state:
- show `No signals now`
- keep only back guidance

Failure state:
- show `Signals unavailable`
- keep `B Back`

The page should fail gracefully and never trap the user in a dead end.

### 9.2 Watchlist

Empty state:
- show `Watchlist empty`
- show helper copy such as `In Spotlight say: add to watchlist`

Add/remove success:
- stay on current flow
- refresh the list or show a lightweight confirmation

Add/remove failure:
- do not navigate away
- show a lightweight error treatment

### 9.3 Navigation Guarantees

- `Explore` remains recoverable by `B/LEFT`
- `Signals` and `Watchlist` must not redefine global behavior unexpectedly
- `SPOTLIGHT` back behavior remains unchanged regardless of whether the token came from `FEED`, `Signals`, or `Watchlist`

---

## 10. Explicit Non-Goals

This design does **not** include:
- signal filters, tabs, or sort controls
- signal detail pages separate from `SPOTLIGHT`
- multiple watchlists, tags, folders, or custom ordering
- new `SPOTLIGHT` buttons for save / unsave
- `holders`, `tx`, `pair`, `liq`, or `smart wallets` as Explorer entries in this round
- replacing `PORTFOLIO` or turning watchlist into a position-management page

---

## 11. Testing Expectations

Implementation and verification should cover:
- `Explore` now shows 5 entries in the intended order
- `Signals` entry is reachable and exits cleanly
- `Watchlist` entry is reachable and exits cleanly
- selecting a signal opens the correct token in `SPOTLIGHT`
- selecting a watchlist row opens the correct token in `SPOTLIGHT`
- `SPOTLIGHT` key behavior remains unchanged
- voice add/remove works from current spotlight token context
- watchlist remove via `X` works only on `Watchlist`, not elsewhere
- empty and failure states render cleanly
- `B` recovery path remains consistent across `Explore`, `Signals`, `Watchlist`, and `SPOTLIGHT`

---

## 12. Resolved Decisions

- Should watchlist be a standalone global page? No. It should live under `Explore` because there is no clean spare global entry button.
- Should `Signals` include token-linked navigation? Yes. Signal items include token identity and should flow directly into `SPOTLIGHT`.
- Should watchlist add/remove get a new `SPOTLIGHT` key? No. It should be voice-first to avoid button conflict.
- Should `tx / holders / pair` become Explorer pages now? No. They remain candidates for later `SPOTLIGHT` enrichment.
- Should Explore remain shallow? Yes. The product should add only lightweight browse pages, not a deep menu tree.
