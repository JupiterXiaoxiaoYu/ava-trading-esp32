# Board Port Template

This template is the C boundary a new ESP32 board implements to connect to DeviceKit.

| Function | Board Responsibility |
|---|---|
| `send_json` | Send DeviceKit protocol JSON over WebSocket |
| `send_binary` | Send microphone audio frames over WebSocket |
| `render_json` | Render received `ScreenPayload` JSON |
| `play_audio` | Play TTS audio chunks when the gateway sends `state=audio` |
| `ava_board_on_button` | Map GPIO/joystick/touch into `key_action` |
| `ava_board_on_cursor` | Send current cursor and selected row context |
| `ava_board_on_audio_frame` | Forward PCM16 or OPUS frames according to runtime config |

Keep hardware-specific GPIO, display, codec, and networking code outside framework core.


## Production Resilience Hooks

| Hook | Purpose |
|---|---|
| `ava_board_on_transport_connected()` | Marks WebSocket online and sends hello. |
| `ava_board_on_transport_disconnected()` | Marks realtime transport offline. |
| `ava_board_on_tick()` | Sends heartbeat while online and logs reconnect ticks while offline. |
| `ava_board_send_http_fallback()` | Sends important JSON to HTTP fallback when WebSocket is unavailable. |
| `ava_board_send_challenge_response()` | Signs a backend challenge with the board/device key and sends the response. |
| `send_http_json` | Board-owned HTTP POST implementation with bearer-token support. |
| `sign_challenge` | Board-owned secure-element or device-key signing function. |

A production port should persist the per-device bearer token returned by `/device/register`, include it in HTTP fallback calls, and rotate/revoke it through the admin control plane when needed.
