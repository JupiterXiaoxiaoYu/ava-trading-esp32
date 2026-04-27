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
