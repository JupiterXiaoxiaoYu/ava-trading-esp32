# Firmware Main Runtime

This directory contains the core ESP32 device runtime used by AVE.

The broader `firmware/` folder still carries the upstream XiaoZhi firmware foundation, but `main/` is where the concrete runtime wiring lives: application startup, board selection, display/audio integration, transport protocols, settings, OTA, and the AVE-specific bridge into the shared screen layer.

## Key entry points

- `main.cc` - firmware entry point
- `application.cc` / `.h` - app-level orchestration and lifecycle
- `ave_transport_idf.cc` - AVE transport glue between the ESP-IDF runtime and the shared screen layer
- `ota.cc` / `.h` - OTA update flow on device
- `settings.cc` / `.h` - persisted device settings and preferences
- `mcp_server.cc` / `.h` - device-side MCP integration
- `device_state_machine.cc` / `.h` - high-level runtime state transitions

## Important subdirectories

### `boards/`

Board ports, pin mappings, display/audio setup, and target-specific runtime integration.

For the active AVE hardware work, the most important target is:

- `boards/scratch-arcade/` - Scratch Arcade style ESP32-S3 board integration used by the current AVE device build

### `display/`

Display abstraction and target-specific display implementations.

Key areas:
- `display/lvgl_display/` - LVGL-backed display integration
- `lcd_display.*`, `oled_display.*`, `emote_display.*` - target-specific display variants

### `audio/`

Audio codec, service, wake-word, and processing pipeline support.

### `protocols/`

Network transport implementations such as WebSocket and MQTT.

### `assets/`

Firmware-packaged locales, fonts, and other user-facing assets.

## How this folder fits into AVE

- Receives backend and user events, then forwards AVE display data into [`../../shared/ave_screens/README.md`](../../shared/ave_screens/README.md)
- Hosts the board-level code needed to run the shared screens on real hardware
- Owns hardware concerns that the simulator does not: I/O, power, transport, wake word, and peripherals

## Typical workflows

- Add or adjust board support in `boards/`
- Integrate device-side input/display behavior for shared AVE pages
- Tune wake-word, audio, or transport behavior
- Build and flash firmware after validating UI changes in the simulator

## Related navigation

- [`../README.md`](../README.md) - upstream firmware overview with AVE monorepo notes
- [`../../shared/README.md`](../../shared/README.md) - shared cross-target UI layer
- [`../../simulator/README.md`](../../simulator/README.md) - desktop validation before flashing
- [`../../docs/README.md`](../../docs/README.md) - architecture and implementation notes
