# Ava DeviceKit Userland

This directory is the developer-facing surface of Ava DeviceKit. It separates
what framework users configure or implement from what framework maintainers own.

## What You Can Use

| Capability | Use When | Where |
|---|---|---|
| Device session | You need app state, context, outbox, and action results | `backend/ava_devicekit/gateway/session.py` |
| HTTP/WebSocket gateways | You need a local or hosted device gateway | `backend/ava_devicekit/gateway/` |
| OTA runtime | You need devices to discover WS URL and firmware updates | `backend/ava_devicekit/ota/` |
| Firmware runtime C API | You need to wire ESP32 network/audio/listen state | `firmware/include/ava_devicekit_runtime.h` |
| Shared UI C runtime | You need to dispatch screen payloads on a device/simulator | `shared_ui/include/ava_devicekit_ui.h` |
| Provider interfaces | You need ASR, LLM, or TTS integrations | `backend/ava_devicekit/providers/` |
| Chain adapter interface | You need a new chain/data source | `backend/ava_devicekit/adapters/base.py` |
| Market stream interface | You need live price/kline updates | `backend/ava_devicekit/streams/base.py` |

The machine-readable list is `capabilities.json`.

## What You Configure

| File | Required For | Notes |
|---|---|---|
| `runtime.example.json` | Deployment | Copy to `runtime.local.json` and set public URLs, ports, firmware bin dir, and ping timeouts. |
| `env.example` | Deployment secrets | Copy values into shell/tmux/systemd env. Never commit real API keys. |
| `app/manifest.template.json` | New hardware app | Copy and fill app id, screens, actions, adapters, models, safety policy. |

## What You Implement

| Developer Goal | Implement | Template |
|---|---|---|
| Build a new hardware app | Manifest, app class, app skills | `app/` |
| Add a new chain | `ChainAdapter` and registry entry | `adapter/chain_adapter_template.py` |
| Add live market updates | `MarketStreamAdapter` | `adapter/market_stream_adapter_template.py` |
| Add a model provider | ASR/LLM/TTS provider | `provider/` |
| Port a new ESP32 board | Hardware port using firmware runtime C API | `hardware_port/` |
| Build custom screens | Screen vtables and selection context JSON | `ui/` |

## What You Should Not Modify First

| Framework-Owned Area | Why |
|---|---|
| `core/types.py` | This is the stable app/device contract. Extend with care. |
| `gateway/session.py` | All apps depend on this session lifecycle. |
| `schemas/` | Schema changes should be versioned and backward-compatible. |
| `firmware/include/ava_devicekit_runtime.h` | Board ports should bind to it, not fork it. |
| `shared_ui/include/ava_devicekit_ui.h` | Screen implementations should register vtables, not change dispatch rules. |

## Ava Box As Example

Ava Box is implemented as userland on top of the framework:

| Ava Box Part | Location |
|---|---|
| Manifest | `apps/ava_box/manifest.json` |
| App routing | `backend/ava_devicekit/apps/ava_box.py` |
| App skills | `backend/ava_devicekit/apps/ava_box_skills/` |
| Solana data | `backend/ava_devicekit/adapters/solana.py` |
| Scratch Arcade hardware mapping | `firmware/ports/scratch_arcade/` |

A different product should follow the same pattern instead of editing framework core.
