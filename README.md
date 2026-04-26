# Ava DeviceKit

(English | [中文](README_zh.md))

Ava DeviceKit is a full-stack ESP32 framework for building Solana AI hardware apps. It provides device UI, physical input, voice interaction, backend Solana action APIs, model routing, and confirmation flows so developers can bring Solana actions into real-world devices.

Ava Box is the first reference app built with the kit: a handheld Solana AI terminal for token discovery, watchlists, portfolio views, and trade drafts on an ESP32-S3 Scratch Arcade style board.

Parts of the current device/runtime stack are based on [`nulllaborg/xiaozhi-esp32`](https://github.com/nulllaborg/xiaozhi-esp32). The framework work is extracting only the runtime pieces Ava hardware apps need, then moving app behavior into smaller DeviceKit contracts and reference apps.

For the cloud-side capability layer and Skills integration, also see [`AveCloud/ave-cloud-skill`](https://github.com/AveCloud/ave-cloud-skill).

## Device Preview

![Ava Box hardware preview](docs/assets/readme/ava-box-device-preview.png)

## Ava IP

Ava is the product IP and on-device operator persona for Ava hardware apps: voice-first, screen-grounded, and designed for always-available crypto device experiences.

![Ava IP character sheet](docs/assets/readme/ava-ip-character-sheet.png)

## Framework Layers

| Layer | Role | Current code |
|---|---|---|
| Device Runtime | ESP32 firmware, board drivers, display/audio lifecycle, Wi-Fi, OTA, device state, transport | `firmware/` |
| Screen Contracts | LVGL payloads shared by firmware and simulator | `shared/ave_screens/` |
| Solana Action Gateway | Backend action APIs, screen payload pushes, trade/order drafts, confirmation/result handling | `server/main/xiaozhi-server/plugins_func/functions/` |
| AI Router | ASR/TTS, wake/PTT, model routing, deterministic actions, LLM fallback | `server/main/xiaozhi-server/core/` |
| DeviceKit Contracts | Manifests, schemas, examples, safety model, reference app metadata | `devicekit/` |
| Reference Apps | Concrete hardware apps built on the framework | `apps/ava_box/`, `devicekit/examples/` |

## Ava Box Reference App

| Area | Behavior |
|---|---|
| Chain scope | Solana only for feed, search, spotlight, watchlist, portfolio, orders, and trade drafts |
| Platform feeds | Pump.fun only: `pump_in_hot` and `pump_in_new` |
| Native unit | SOL for market buy/sell, limit order, paper balances, and spoken amounts |
| Screen layer | Solana feed, spotlight, watchlist, portfolio, confirm, and result surfaces shared by firmware and simulator |
| Assistant routing | Ava keeps page context and selected cursor context while routing voice commands into Solana actions |
| Confirmation | High-risk actions are displayed as drafts and require explicit confirmation |

## What Lives Here

| Directory | Role |
|---|---|
| `devicekit/` | Ava DeviceKit contracts, manifests, schemas, examples, and framework notes |
| `apps/ava_box/` | Ava Box reference app description and app-level contracts |
| `firmware/` | ESP32 firmware runtime, board ports, audio pipeline, OTA, protocols, and device integration |
| `server/` | Backend stack, management services, action gateway, AI routing/tool logic, deployment docs, and tests |
| `shared/` | Shared LVGL screens compiled into both firmware and simulator |
| `simulator/` | Desktop validation harness for shared UI and mock interaction flows |
| `docs/` | Current architecture and product/reference documents |
| `config/` | Repo-owned shared assets and small configuration artifacts |
| `data/` | Local runtime data placeholder for non-committed state |
| `tmp/` | Generated logs, local probes, and scratch artifacts used during debugging |

## Start Here

| Task | Entry point |
|---|---|
| Understand the framework | [`devicekit/README.md`](devicekit/README.md) |
| Review Ava Box as reference app | [`apps/ava_box/README.md`](apps/ava_box/README.md), [`devicekit/manifests/ava_box.solana.json`](devicekit/manifests/ava_box.solana.json) |
| Bring up ESP32 runtime | [`firmware/README.md`](firmware/README.md), [`firmware/main/README.md`](firmware/main/README.md) |
| Work on Solana backend behavior | [`server/README_en.md`](server/README_en.md), [`server/main/README_en.md`](server/main/README_en.md) |
| Preview pages on desktop | [`simulator/README.md`](simulator/README.md), [`shared/ave_screens/README.md`](shared/ave_screens/README.md) |
| Understand shared UI contracts | [`shared/README.md`](shared/README.md) |
| Read architecture notes | [`docs/README.md`](docs/README.md), [`docs/architecture/xiaozhi-extraction.md`](docs/architecture/xiaozhi-extraction.md) |

## Architecture At A Glance

```text
voice + physical input
  -> firmware/ (ESP32 runtime, board drivers, transport)
  -> server/ (AI router, action gateway, Solana tool/provider logic)
  -> shared/ave_screens/ (feed, spotlight, portfolio, confirm, result, etc.)
       -> compiled into firmware for hardware rendering
       -> compiled into simulator for desktop validation
  -> devicekit/ (manifest/schema/action contracts for reusable hardware apps)
```

Key coupling points:

| Coupling point | Purpose |
|---|---|
| `devicekit/manifests/ava_box.solana.json` | Reference app identity, device capabilities, actions, screens, and safety policy |
| `devicekit/schemas/` | Stable framework contracts for hardware app, action, and screen payloads |
| `shared/ave_screens/` | Single source of truth for the current Ava Box screen layer |
| `firmware/main/boards/scratch-arcade/` | Active Scratch Arcade ESP32-S3 hardware target |
| `firmware/main/ave_transport_idf.cc` | Bridges device events into the shared screen/runtime layer |
| `server/main/xiaozhi-server/plugins_func/functions/ava_devicekit.py` | Lightweight backend helper boundary for DeviceKit payloads |
| `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py` | Ava Box Solana market, wallet, watchlist, portfolio, and order tools |
| `simulator/` | Layout, navigation, mock scene, and regression validation before flashing hardware |

## Safety Position

ESP32 is the physical interaction and confirmation surface, not the default custody layer for user assets.

| Principle | Implementation direction |
|---|---|
| No blind AI execution | Model output creates drafts; high-risk actions require confirmation |
| Screen-visible risk | Device displays action summary, token/amount, chain, and result state |
| Physical confirmation | Buttons confirm/cancel sensitive actions |
| External custody path | Primary user keys can remain in external wallets or secure wallet layers |
| Device identity path | ESP32 device keys can be used for device identity, heartbeat, or sensor proofs, separate from user funds |

## Upstream Origins

This monorepo is Ava DeviceKit-first, with several major directories derived from upstream projects:

| Directory | Origin |
|---|---|
| `firmware/` | `78/xiaozhi-esp32` runtime lineage, being narrowed to the pieces needed by Ava hardware apps |
| `server/` | `xinnan-tech/xiaozhi-esp32-server` runtime lineage, with Ava action gateway and model routing additions |
| `simulator/` | `lvgl/lv_port_pc_vscode` |
| cloud capability layer | [`AveCloud/ave-cloud-skill`](https://github.com/AveCloud/ave-cloud-skill) |

The public framework surface is `devicekit/`, `apps/`, shared screen contracts, and the backend action gateway. The xiaozhi-derived runtime remains an implementation layer, not the product boundary.
