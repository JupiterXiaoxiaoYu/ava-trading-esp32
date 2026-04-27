# Shared UI Runtime

`shared_ui/` is the clean C boundary between Ava DeviceKit `ScreenPayload` messages and ESP32/LVGL screens.

The goal is not to copy the old screen manager wholesale. The goal is to expose a small reusable runtime contract that any hardware app can bind to its own screens.

## Runtime Contract

| File | Role |
|---|---|
| `include/ava_devicekit_ui.h` | Public C API for screen registration, custom screen contracts, display JSON dispatch, key/input routing, transport emit, and context-aware listen messages |
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

Board-specific input
  -> ava_dk_ui_emit_input_event()
  -> {"type":"input_event","source","kind","code","semantic_action","context"}
  -> backend app routes semantic_action or interprets raw input
```

## Screen Names

Built-in names are available for the Ava Box reference UI:

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

New apps can register arbitrary screen ids with
`ava_dk_ui_register_custom_screen()`. The screen id must match the app manifest
and the `ScreenPayload.screen` value sent by the backend.

## Key Contract

| Key | Default framework behavior |
|---|---|
| `AVA_DK_KEY_Y` | Global portfolio action emit |
| `AVA_DK_KEY_FN` | Emit `listen_detect` with current selection context when available |
| Other keys | Routed to the current registered screen |

## Generic Input Contract

Use `ava_dk_input_event_t` when the hardware interaction is richer than a fixed
key enum or when you want the app to stay hardware-agnostic:

```c
ava_dk_input_event_t event = {
    .source = "joystick",
    .kind = "move",
    .code = "right",
    .semantic_action = "feed_next",
    .value = 1,
};
ava_dk_ui_emit_input_event(&ui, &event, current_context_json);
```

The `current_context_json` should be the active screen's `ContextSnapshot`.

## Migration From Legacy Screens

The production Ava Box LVGL implementation now lives in `ava-devicekit/reference_apps/ava_box/ui/`. New apps should depend on DeviceKit screen contracts and vtables rather than repo-level legacy screen-manager APIs.
