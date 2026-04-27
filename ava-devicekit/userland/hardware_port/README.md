# Hardware Port Development

A hardware port maps a real ESP32 board into DeviceKit runtime contracts. It is
where GPIO, joystick, touch, display, microphone, speaker, Wi-Fi, and WebSocket
implementation details belong.

## Implement In A Port

| Concern | Use |
|---|---|
| Network events | `ava_dk_runtime_on_network_event()` |
| Text transport | `ava_dk_runtime_set_transport()` |
| Boot hello | `ava_dk_runtime_send_hello()` |
| Push-to-talk | `ava_dk_runtime_start_listening()` / `ava_dk_runtime_stop_listening()` |
| Wake word | `ava_dk_runtime_send_wake_detect()` |
| Buttons/touch | Emit `key_action` messages |
| Screen rendering | Register `ava_dk_screen_vtable_t` handlers in shared UI runtime |

See `firmware/ports/scratch_arcade/` for the reference port boundary.
