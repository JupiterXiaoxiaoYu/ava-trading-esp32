# Shared UI Runtime

`shared_ui/` is the clean C boundary between Ava DeviceKit `ScreenPayload` messages and ESP32/LVGL screens.

The goal is not to copy the old screen manager wholesale. The goal is to expose a small reusable runtime contract that any hardware app can bind to its own screens.

## Runtime Contract

| File | Role |
|---|---|
| `include/ava_devicekit_ui.h` | Public C API for screen registration, display JSON dispatch, key routing, transport emit, and context-aware listen messages |
| `src/ava_devicekit_ui.c` | Small dispatcher that routes `{type:"display", screen, data}` into registered screen vtables |
| `tests/test_ava_devicekit_ui.c` | Compile-time and behavior test for the public C contract |

## Data Flow

```text
DeviceSession / ChainAdapter
  -> ScreenPayload JSON: {"type":"display","screen":"feed","data":{...}}
  -> ava_dk_ui_handle_display_json()
  -> registered screen vtable show(data)

Physical key
  -> ava_dk_ui_key_press()
  -> current screen key handler OR global action emit
  -> DeviceMessage JSON back to backend
```

## Supported Screen Names

| Screen | Purpose |
|---|---|
| `feed` | Token feed / source list |
| `browse` | Watchlist/signals/order list style browsing |
| `spotlight` | Token detail |
| `portfolio` | Portfolio view |
| `confirm` | Market/action confirmation |
| `limit_confirm` | Limit order confirmation |
| `result` | Action result |
| `notify` | Overlay notification |
| `disambiguation` | Search result disambiguation |

## Key Contract

| Key | Default framework behavior |
|---|---|
| `AVA_DK_KEY_Y` | Global portfolio action emit |
| `AVA_DK_KEY_FN` | Emit `listen_detect` with current selection context when available |
| Other keys | Routed to the current registered screen |

## Migration From Legacy Screens

The current production LVGL implementation remains in repo-level `shared/ave_screens/`. Migration should wrap each existing screen with an `ava_dk_screen_vtable_t` implementation instead of exposing legacy manager APIs to new apps.
