# Scratch Arcade Port Boundary

This directory is the clean Scratch Arcade board port target for Ava DeviceKit.
It captures the board-specific mapping that the current Ava Box hardware needs
without importing the legacy firmware application class.

| Area | DeviceKit boundary |
|---|---|
| Boot/runtime | `ava_scratch_arcade_init()` wraps `ava_dk_runtime_t` |
| Buttons/joystick | `ava_scratch_arcade_action_for_button()` maps hardware input to app actions |
| Voice/FN | `AVA_SA_BUTTON_FN` starts the DeviceKit listen flow |
| OTA path | `/ava/ota/` |
| WebSocket path | `/ava/v1/` |

ESP-IDF integration still needs a board-specific file that calls these C
functions from actual GPIO, Wi-Fi, WebSocket, audio, and LVGL drivers.
