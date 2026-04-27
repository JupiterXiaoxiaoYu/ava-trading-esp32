# Port A Board

DeviceKit core is ESP32-hardware-agnostic. A board port maps physical hardware into the framework message and screen contracts.

| Board Responsibility | Required Output |
|---|---|
| Wi-Fi / network readiness | Call OTA and WebSocket endpoints from runtime config |
| Buttons / joystick / touch | Emit `DeviceMessage(type="key_action", action="...")` |
| Current screen and cursor | Emit `screen_context` with `screen`, `cursor`, `selected`, and `visible_rows` |
| Microphone | Send PCM16 audio to ASR session or provide an `AudioDecoder` for OPUS-to-PCM conversion |
| Speaker | Play TTS audio returned by the provider or by deployment transport |
| Display | Render `ScreenPayload` using app UI screens |
| OTA | Use `/ava/ota/` and `/ava/ota/download/{filename}` |

The Scratch Arcade port is a reference port, not a framework requirement.


## Generate A Board Port

```bash
cd ava-devicekit
PYTHONPATH=backend python3 -m ava_devicekit.cli init-board ../my-esp32-board-port
```

The generated C template defines the required board callbacks for JSON transport, binary audio transport, screen rendering, audio playback, buttons, cursor selection, and listen start/stop.
