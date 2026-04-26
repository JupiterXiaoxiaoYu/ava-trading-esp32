# Ava Box Reference App

Ava Box is the first reference app for Ava DeviceKit. It demonstrates how an ESP32-S3 handheld can become a Solana AI hardware terminal with screen-grounded voice interaction and physical confirmation.

## Reference Device

| Capability | Value |
|---|---|
| MCU | ESP32-S3 |
| Display | 320x240 |
| Input | Joystick, physical buttons, wake/PTT voice |
| Audio | MEMS/PDM microphone and speaker output |
| Runtime | Wi-Fi, WebSocket transport, OTA, settings, device state |

## Solana App Surface

| Screen | Purpose |
|---|---|
| Feed / Browse | Solana token discovery, Pump.fun hot/new, watchlist, orders, signals |
| Spotlight | Token detail, price, kline, watchlist action, context for AI answers |
| Portfolio | Wallet and paper portfolio state |
| Confirm / Limit Confirm | Physical confirmation for trade drafts and order cancellation |
| Result / Notify | Execution result, errors, and assistant state |

## DeviceKit Contracts Used

| Contract | Implementation |
|---|---|
| Manifest | `devicekit/manifests/ava_box.solana.json` |
| Screen payloads | `shared/ave_screens/` |
| Action gateway | `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py` |
| Shared helper boundary | `server/main/xiaozhi-server/plugins_func/functions/ava_devicekit.py` |
| Device runtime bridge | `firmware/main/ave_transport_idf.cc` |

## Safety Position

Ava Box is a physical confirmation surface. The app can display Solana action drafts and require button confirmation before execution. It does not require storing a primary user asset key on the ESP32.
