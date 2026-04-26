# Xiaozhi Runtime Extraction Plan

Ava DeviceKit currently reuses parts of the xiaozhi ecosystem because it already solves practical ESP32 assistant problems: audio input/output, wake/PTT behavior, WebSocket sessions, OTA, and board bring-up.

The framework direction is to keep only the runtime pieces Ava hardware apps need and move product behavior into smaller DeviceKit modules.

## Keep As Runtime Infrastructure

| Area | Why it stays |
|---|---|
| Audio pipeline | Microphone, speaker, ASR/TTS streaming, wake/PTT lifecycle |
| Connectivity | Wi-Fi setup, WebSocket protocol, reconnect behavior |
| OTA and settings | Required for real hardware iteration |
| Board ports | Existing ESP32 board bring-up and display/audio drivers |
| Session lifecycle | Device online state, connection state, assistant turn handling |

## Extract Into Ava DeviceKit

| Area | Target |
|---|---|
| App manifest | Device/app capabilities, model policy, screen list, action list, safety policy |
| Screen contracts | Stable payload contracts shared by firmware and simulator |
| Action gateway | Deterministic Solana actions and confirmation payload construction |
| Context router | Current screen, cursor, selected token, portfolio/watchlist state |
| Reference apps | Ava Box first, then payment terminal, alert device, sensor demo |

## Simplification Rule

The backend should not expose the full xiaozhi application model as the public framework. Public DeviceKit APIs should be narrow:

| Public DeviceKit concept | Not exposed as public API |
|---|---|
| Hardware app manifest | Internal xiaozhi config shape |
| Action payload | Provider-specific tool call internals |
| Screen payload | Assistant implementation details |
| Physical confirmation | Raw conversation state machine |
| Model routing policy | Provider-specific adapter wiring |

## First Code Boundary

`server/main/xiaozhi-server/plugins_func/functions/ava_devicekit.py` is the first lightweight backend boundary. Existing Ava Box tools can call this helper while the larger server still runs on the current xiaozhi-derived runtime.
