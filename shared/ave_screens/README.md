# Ava Box Screens

This directory is the implementation home for the Ava Box shared LVGL screens.

These files define the market-facing UI surfaces that are shown on both the ESP32 device and the simulator, including feed, spotlight, portfolio, disambiguation, confirm, result, and related pages.

## Main pieces

### Screen implementations

- `screen_feed.c` - list/feed style market view and top-bar interactions
- `screen_spotlight.c` - token detail / spotlight page
- `screen_portfolio.c` - holdings surface
- `screen_disambiguation.c` - ambiguous search result selection
- `screen_confirm.c` and `screen_limit_confirm.c` - trade confirmation flows
- `screen_result.c` - success/failure result page
- `screen_browse.c`, `screen_explorer.c`, `screen_notify.c` - supporting navigation and informational surfaces

### Shared infrastructure

- `ave_screen_manager.c` / `.h` - top-level screen lifecycle, routing, scene loading, and input dispatch
- `ave_transport.c` / `.h` - transport bridge for pushing data into the screen layer
- `ave_json_utils.c` / `.h` - JSON parsing helpers for surface payloads
- `ave_price_fmt.c` / `.h` - compact market number formatting helpers
- `ave_font_provider.c` / `.h` - font selection and font-loading glue
- `CMakeLists.txt` - shared build wiring for simulator and firmware consumers

## Development workflow

1. Update or add screen behavior here first
2. Validate desktop behavior in [`../../simulator/README.md`](../../simulator/README.md)
3. Verify target-specific device integration in [`../../firmware/main/README.md`](../../firmware/main/README.md)
4. Check server payload expectations in [`../../server/main/README_en.md`](../../server/main/README_en.md)

## Extension rules

- Prefer shared behavior here instead of duplicating logic in firmware-only code
- Keep screen contracts aligned with server payloads and state snapshots
- Use the simulator for fast iteration before hardware flashing
- Put board-specific display/input work in firmware integration layers, not in shared page logic unless it is truly cross-target

## Related directories

- [`../README.md`](../README.md) - why the shared layer exists
- [`../../simulator/README.md`](../../simulator/README.md) - desktop validation harness
- [`../../docs/README.md`](../../docs/README.md) - remaining product/reference context for this repo
