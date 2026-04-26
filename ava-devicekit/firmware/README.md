# Firmware Runtime Target

This directory is the target home for Ava DeviceKit's firmware-facing runtime.

The clean framework should expose only these concepts to ESP32 ports:

| Concept | Purpose |
|---|---|
| Device transport | send/receive JSON messages |
| Key mapper | joystick/buttons/FN into `DeviceMessage` actions |
| Audio hooks | microphone input and speaker output routed by deployment |
| Screen runtime | render `ScreenPayload` messages |
| OTA/settings | deployment-managed device lifecycle |

The current production firmware still lives in the repo-level `firmware/` directory while this clean boundary is implemented.

## Current Runtime Boundary

| File | Purpose |
|---|---|
| `include/ava_devicekit_runtime.h` | Small C runtime contract for device state, network events, hello/listen messages, and wake detection |
| `src/ava_devicekit_runtime.c` | Framework-owned implementation adapted from the legacy application/network state flow |
| `tests/test_ava_devicekit_runtime.c` | Host-side contract test compiled by pytest |

The code intentionally does not include ESP-IDF or xiaozhi headers. ESP32 board ports should wire their Wi-Fi manager, WebSocket transport, microphone, speaker, and screen code into this boundary.

## Mapping From Legacy Firmware

| Legacy behavior | DeviceKit boundary |
|---|---|
| `WifiBoard::StartNetwork` / Wi-Fi events | `ava_dk_runtime_on_network_event()` |
| `Application::InitializeProtocol` hello frame | `ava_dk_runtime_send_hello()` |
| `Application::StartListening` / FN PTT | `ava_dk_runtime_start_listening()` |
| wake word detected flow | `ava_dk_runtime_send_wake_detect()` |
| stop listening | `ava_dk_runtime_stop_listening()` |

This keeps the behavior we need for Ava Box while preventing the new framework from depending on the old monolithic application class.
