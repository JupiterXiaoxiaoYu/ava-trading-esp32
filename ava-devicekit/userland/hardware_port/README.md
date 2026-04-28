# Hardware Port Development

A hardware port maps a concrete ESP32 board into DeviceKit runtime contracts. It
owns GPIO, joystick, touch, display, microphone, speaker, Wi-Fi, and WebSocket
implementation details.

## What A Port Implements

| Concern | Use |
|---|---|
| Network events | `ava_dk_runtime_on_network_event()` |
| Text transport | `ava_dk_runtime_set_transport()` |
| Boot hello | `ava_dk_runtime_send_hello()` |
| Push-to-talk | `ava_dk_runtime_start_listening()` / `ava_dk_runtime_stop_listening()` |
| Wake word | `ava_dk_runtime_send_wake_detect()` |
| Buttons/touch/joystick/encoder | Emit `input_event` frames or direct `key_action` frames |
| Screen rendering | Register `ava_dk_screen_vtable_t` handlers in shared UI runtime |
| Render ACK | Send `{"type":"ack","message_id":"..."}` after applying a payload with `ack_required` |
| OTA trigger | Handle `device_command: ota_check` by calling the board OTA check routine |
| AI page grounding | Include `ContextSnapshot` JSON from the current screen when emitting listen/input events |

## Input Mapping Rule

Do not bake a board-specific key layout into framework core. Convert raw hardware
signals into one of two transport frames:

| Frame | Use When | Example |
|---|---|---|
| `key_action` | The control directly means one app action | `{"type":"key_action","action":"portfolio"}` |
| `input_event` | You want hardware-agnostic input, coordinates, values, or deferred routing | `{"type":"input_event","source":"touch","kind":"tap","x":120,"y":88}` |

If the board already knows the semantic action, set `semantic_action` in the
`input_event`. The backend app can route it the same way as a `key_action`.

## Context Rule

Whenever a user asks by voice or presses an AI/action control, attach the current
screen snapshot:

```json
{
  "type": "input_event",
  "source": "button",
  "kind": "press",
  "code": "A",
  "semantic_action": "buy",
  "context": {
    "screen": "spotlight",
    "cursor": 0,
    "selected": {"token_id": "...", "symbol": "SOL", "chain": "solana"}
  }
}
```

This is what lets AI answer “what am I selecting?” and lets deterministic actions
avoid stale server-side state.

See `firmware/ports/scratch_arcade/` for the reference board boundary and
`userland/hardware_port/templates/` for a minimal port template.
