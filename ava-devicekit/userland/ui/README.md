# UI Screen Development

DeviceKit treats UI as app/userland code. The framework only defines the wire
contracts that let a device render pages, emit input, and expose the current
screen state to deterministic routing and AI.

## The Three Contracts

| Contract | Implemented By | Consumed By | Purpose |
|---|---|---|---|
| `ScreenContract` | App developer | Device UI, tests, docs | Declares a page id, payload shape, context shape, and allowed actions. |
| `InputEvent` | Board port or screen runtime | Backend app router | Normalizes buttons, joystick, touch, encoder, and other hardware events. |
| `ContextSnapshot` | Current screen | Backend router and model pipeline | Describes what the user is looking at: screen, cursor, selected item, visible rows, focused component, and page data. |

Schemas live in `schemas/screen_contract.schema.json`,
`schemas/input_event.schema.json`, and `schemas/context_snapshot.schema.json`.

## Required Screen Hooks

Register one `ava_dk_screen_vtable_t` per screen id:

| Hook | Purpose |
|---|---|
| `show(json_data, user)` | Render the `ScreenPayload.data` object for this screen. |
| `key(key, user)` | Optional current-screen key handling for simple key-based devices. |
| `selection_context_json(out, out_n, user)` | Return the current `ContextSnapshot` JSON for voice, wake word, and AI routing. |
| `cancel_timers(user)` | Stop timers/animations that should not survive navigation. |

Built-in Ava Box screens still work through `ava_dk_ui_register_screen()`. New
products can register arbitrary page ids with `ava_dk_ui_register_custom_screen()`.

## Context Snapshot Shape

A screen should expose the most useful state, not the whole framebuffer:

```json
{
  "screen": "sensor_panel",
  "cursor": 1,
  "selected": {
    "id": "sensor-2",
    "symbol": "TEMP",
    "chain": "solana"
  },
  "visible_rows": [
    {"id": "sensor-1", "label": "Door", "value": "closed"},
    {"id": "sensor-2", "label": "Temp", "value": "24C"}
  ],
  "focused_component": "row:1",
  "page_data": {"room": "lab"}
}
```

For token-style apps, `selected` may also be sent as legacy `token`; the backend
normalizes both forms.

## Input Event Shape

Board ports should emit physical input as generic events. If the event already
maps to an app action, fill `semantic_action`; otherwise the app may interpret
`source/kind/code/value` itself.

```json
{
  "type": "input_event",
  "source": "joystick",
  "kind": "move",
  "code": "right",
  "semantic_action": "feed_next",
  "value": 1,
  "context": {"screen": "feed", "cursor": 0}
}
```

Use `ava_dk_ui_emit_input_event()` or `ava_dk_ui_build_input_event_json()` from C.

## Development Flow

| Step | What To Do |
|---|---|
| 1 | Add your page id to the app manifest `screens`. |
| 2 | Add a `screen_contracts[]` entry that documents payload/context/actions. |
| 3 | Implement a screen vtable and register it. |
| 4 | Return a `ContextSnapshot` from `selection_context_json()`. |
| 5 | Map hardware controls to `InputEvent` or direct `key_action`. |
| 6 | Route `input_event.semantic_action` and voice commands in the backend app. |
| 7 | Add tests that every UI-emitted action is handled and every screen payload matches the parser. |

Framework core does not prescribe layout, fonts, colors, animation, or exact
hardware controls. Those stay in the app UI and board port.
