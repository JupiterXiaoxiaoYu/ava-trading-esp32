# Shared Ava Box UI Layer

This directory contains the shared Ava Box UI code that is compiled into both the ESP32 firmware and the desktop simulator.

If a page should look and behave the same on hardware and in the simulator, it should generally live here. This is the single most important cross-target UI surface in the monorepo.

## Why this folder matters

- It prevents the firmware UI and simulator UI from drifting apart
- It keeps screen rendering, layout, and navigation logic in one place
- It makes desktop validation meaningful before flashing hardware

## Current structure

- `ave_screens/` - the shared screen implementations, manager, transport hooks, JSON helpers, and formatting utilities

## Solana branch scope

| UI area | Branch behavior |
|---|---|
| Feed sources | Solana topics plus Pump.fun hot/new |
| Chain labels | Runtime payloads are expected to resolve to `SOL` |
| Watchlist / portfolio | Solana rows only |
| Confirm / result | SOL-denominated action review |

## Typical workflows

- Add or change Ava Box pages in [`ave_screens/README.md`](ave_screens/README.md)
- Validate layout and navigation in [`../simulator/README.md`](../simulator/README.md)
- Integrate target-specific display or input behavior from [`../firmware/main/README.md`](../firmware/main/README.md)

## Related directories

- [`../simulator/README.md`](../simulator/README.md) - desktop validation harness for this code
- [`../firmware/main/README.md`](../firmware/main/README.md) - ESP32-side integration points
- [`../docs/README.md`](../docs/README.md) - current product/reference documents
