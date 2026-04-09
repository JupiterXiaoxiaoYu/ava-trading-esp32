# Feed Explore Entry Design

**Date:** 2026-04-08
**Scope:** P0-2 only. Add a lightweight Explore entry panel from standard FEED home so hidden capabilities are reachable without changing non-FEED `B` behavior.

## Problem / Goal

On standard FEED home, `B` currently returns `已在首页`, which is technically correct but does not help users reach useful functions that already exist behind voice, routing, or deeper entry points. This creates a home-screen reachability asymmetry: core discovery starts on FEED, but search, orders, and source switching are not visibly reachable from there by keys alone.

Goals for this change:
- make hidden but already-supported capabilities reachable from standard FEED home
- preserve FEED as the primary landing surface instead of replacing it with a menu-first home
- avoid introducing new friction or regressions in the core trading path
- keep scope narrow to P0-2 and reuse existing capabilities where possible

## Scope And Non-Goals

### In scope
- Change `B` on standard FEED home from a no-op hint into an Explore panel open action.
- Show three first-version entries in the panel:
  - `Search` — guidance entry with prompt such as `FN 说币名`
  - `Orders` — enter the existing `FEED_ORDERS` flow
  - `Sources` — enter an item list / entry point that reuses the current standard-source and special-source selection capability
- Support panel navigation with `UP/DOWN`, `A/RIGHT`, `B/LEFT`.
- Keep `Y` as a global portfolio shortcut while the panel is open.
- Keep `X` with no new meaning.
- Close the panel back to unchanged standard FEED without permanent layout takeover.

### Non-goals
- No free-text keyboard input.
- No deep nested menu tree.
- No change to `B` behavior on SEARCH / SPECIAL / ORDERS / SPOTLIGHT / CONFIRM / PORTFOLIO or other non-standard-FEED pages.
- No redefinition of `FN`; it remains the existing voice/PTT trigger.
- No redesign of FEED cards, trading flow, or source capability itself.

## Interaction Model

### Entry condition
- The Explore panel is available only when the user is on standard FEED home.
- Pressing `B` from that state opens the panel instead of showing `已在首页`.
- "Standard FEED home" here means the normal FEED landing context, not alternate screens that reuse feed-like rendering for orders, special content, or other modes.

### Panel behavior
- The panel is lightweight and temporary. It overlays or docks over part of FEED, but FEED remains visually present underneath or beside it so the home surface is still recognizable.
- The panel opens with a single current selection and no extra sub-panels.
- Initial selection defaults to `Search`.
- `UP/DOWN` moves the current selection in a clamped three-item list: top stays on top, bottom stays on bottom.
- `A` and `RIGHT` activate the current item.
- `B` and `LEFT` close the panel and return focus to unchanged standard FEED.
- `Y` still enters `PORTFOLIO` using the existing global shortcut behavior.
- `X` continues to do nothing new in this context.

### Item actions
- `Search`
  - Enters a lightweight guidance state, not a text-entry workflow.
  - The screen explains that the user can hold or press `FN` and say a coin name, using copy in the style of `FN 说币名`.
  - This entry may transition into the existing search screen or a search-guidance surface, but it must not redefine `FN` outside this path.
- `Orders`
  - Directly enters the existing `FEED_ORDERS` path.
  - No new orders-specific submenu is introduced.
- `Sources`
  - Enters a source-selection list or entry point that reuses existing standard-source / special-source capability.
  - The first version should expose source switching, not create a new source-management information architecture.

## Screen / State Model

States introduced or clarified by this design:
- `FEED_STANDARD`
  - Existing standard FEED home state.
  - `B` opens Explore.
- `FEED_EXPLORE_PANEL`
  - Transient panel-open state layered on standard FEED.
  - Maintains knowledge of the highlighted entry.
  - Closing the panel returns to the same FEED content and cursor context.
- `FEED_EXPLORE_SEARCH_GUIDE`
  - Lightweight guidance state for voice-driven search entry.
  - Guides the user toward existing `FN` usage; it does not become a general text input mode.
- Existing destination states reused unchanged where possible:
  - `FEED_ORDERS`
  - existing source-selection state(s)
  - `PORTFOLIO` via global `Y`

State transition rules:
- `FEED_STANDARD` + `B` -> `FEED_EXPLORE_PANEL`
- `FEED_EXPLORE_PANEL` + `B/LEFT` -> `FEED_STANDARD`
- `FEED_EXPLORE_PANEL` + `A/RIGHT` on `Search` -> `FEED_EXPLORE_SEARCH_GUIDE` or the existing search guidance equivalent
- `FEED_EXPLORE_PANEL` + `A/RIGHT` on `Orders` -> existing `FEED_ORDERS`
- `FEED_EXPLORE_PANEL` + `A/RIGHT` on `Sources` -> existing source-selection entry flow
- `FEED_EXPLORE_PANEL` + `Y` -> existing `PORTFOLIO`

## Key Behavior Matrix

| Context | `UP/DOWN` | `A/RIGHT` | `B/LEFT` | `Y` | `X` | `FN` |
|---|---|---|---|---|---|---|
| Standard FEED home | existing FEED behavior | existing FEED behavior | open Explore panel | go to `PORTFOLIO` | unchanged | unchanged voice/PTT |
| Explore panel | move selection | enter selected item | close panel to standard FEED | go to `PORTFOLIO` | no new meaning | unchanged voice/PTT |
| Search guidance entry | existing guidance-screen behavior | existing guidance-screen behavior | return per existing back semantics | go to `PORTFOLIO` | no new meaning | existing voice/PTT; guidance copy points user to it |
| Orders / Sources destinations | existing behavior | existing behavior | existing behavior | existing behavior | existing behavior | existing behavior |

## Edge Cases / Error Handling

- `B` must open Explore only on standard FEED home. If FEED is showing orders, special content, or another non-standard mode, keep current `B` behavior unchanged.
- Opening Explore must not refresh FEED, change source, or reset the current FEED item selection.
- Closing Explore must be lossless: the user returns to the same standard FEED state they had before opening it.
- If an Explore destination is temporarily unavailable, show the existing lightweight failure treatment for that destination type rather than leaving the panel frozen.
- If source-selection capability is not available in the current build or configuration, `Sources` should be hidden or disabled consistently; it should not lead to a dead end.
- `Y` from the panel must behave exactly like other global `Y` transitions and should not require the panel to close first in a user-visible intermediate step.
- If `FN` is pressed while the panel is open, existing voice/PTT behavior still wins; the panel does not capture or reinterpret `FN`.

## Testing / Verification Expectations

Verification for this feature should cover behavior, not just rendering:
- standard FEED home: `B` opens Explore instead of showing `已在首页`
- non-standard FEED-derived or other screens: `B` keeps current semantics
- panel navigation: selection clamps correctly, activation enters the expected destination, `B/LEFT` closes cleanly
- `Search` path: user receives explicit `FN` guidance and global `FN` semantics remain unchanged
- `Orders` path: entry lands in existing `FEED_ORDERS`
- `Sources` path: entry reaches reused source-selection capability without introducing a new tree
- `Y` from panel still reaches `PORTFOLIO`
- FEED content/cursor are preserved after opening and closing the panel
- screenshot or simulator verification should confirm the panel is lightweight and does not permanently replace FEED

## Open Questions Resolved By Current Decision

- Should `B` on standard FEED remain a no-op hint? No. It becomes the Explore entry point.
- Should Explore become a new full-screen home menu? No. It stays lightweight and temporary over standard FEED.
- Should this first version add text input or a command tree? No. It is limited to three reachable entry points.
- Should `FN` gain new panel-specific meaning? No. Search can point users toward `FN`, but `FN` keeps its existing global role.
- Should existing `B` behavior be normalized across all screens in this change? No. This change is intentionally scoped to standard FEED home only.
