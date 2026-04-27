# Generic Screen, Input, And Context Contracts

Ava DeviceKit apps should not hardcode one device layout or one product UI into
framework core. The generic integration model is:

```text
ScreenPayload -> device screen renderer
InputEvent    -> backend app router
ContextSnapshot -> deterministic routing + AI grounding
```

## Responsibilities

| Layer | Owns | Does Not Own |
|---|---|---|
| Framework core | Message types, session lifecycle, schemas, dispatch helpers | Product pages, button layout, trading logic |
| Backend app | App routes, skills, action drafts, model fallback policy | GPIO or LVGL layout |
| Screen implementation | Rendering, cursor, visible rows, selected item, page snapshot | Chain/provider APIs |
| Board port | Raw hardware mapping, audio/display/network transport | Product business decisions |

## Add A New Page

1. Add the page id to `manifest.json.screens`.
2. Add a `screen_contracts[]` item:
   - `screen_id`
   - `payload_schema`
   - `context_schema`
   - `actions`
3. Backend returns `ScreenPayload(screen_id, data, context)`.
4. Device registers a screen with `ava_dk_ui_register_custom_screen()`.
5. The screen renders `data` in `show()`.
6. The screen exposes `ContextSnapshot` in `selection_context_json()`.

## Add New Hardware Controls

1. Read raw input in the board port: GPIO, ADC joystick, touch, encoder, etc.
2. Convert it into `InputEvent`:
   - `source`: physical subsystem, for example `joystick`
   - `kind`: event kind, for example `move`
   - `code`: input code, for example `right`
   - `semantic_action`: optional app action, for example `feed_next`
3. Attach the active `ContextSnapshot` if the event is meaningful for AI or app routing.
4. Send it through `ava_dk_ui_emit_input_event()` or the transport directly.

## AI Context Rule

Every deictic command depends on context: “this token”, “open this”, “buy it”,
“what am I selecting?”, “explain this page”. The device should attach a snapshot
when it emits voice or high-level input:

```json
{
  "screen": "portfolio",
  "cursor": 0,
  "selected": {"symbol": "SOL", "token_id": "...", "chain": "solana"},
  "visible_rows": [{"symbol": "SOL", "value_usd": "$100"}],
  "focused_component": "row:0",
  "page_data": {"mode": "paper"}
}
```

The backend normalizes token-style `token` snapshots into `selected` for
compatibility, but new apps should prefer `selected`.
