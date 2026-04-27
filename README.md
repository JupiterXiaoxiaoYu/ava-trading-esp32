# Ava DeviceKit

(English | [中文](README_zh.md))

Ava DeviceKit is a full-stack ESP32 framework for building Solana AI hardware apps. The clean framework implementation now lives in `ava-devicekit/`: app/session types, adapter interfaces, Solana adapter, gateway/session runtime, schemas, and the Ava Box reference app.

Ava Box is the first reference app built with the kit: a handheld Solana AI terminal for token discovery, watchlists, portfolio views, and trade drafts on an ESP32-S3 Scratch Arcade style board.

Parts of the legacy device/runtime stack are based on [`nulllaborg/xiaozhi-esp32`](https://github.com/nulllaborg/xiaozhi-esp32). The new `ava-devicekit/` code does not import the legacy assistant runtime; it extracts the Ava Box capabilities into our own app, adapter, transport, screen, and confirmation contracts.

For the cloud-side capability layer and Skills integration, also see [`AveCloud/ave-cloud-skill`](https://github.com/AveCloud/ave-cloud-skill).

## Device Preview

![Ava Box hardware preview](docs/assets/readme/ava-box-device-preview.png)

## Ava IP

Ava is the product IP and on-device operator persona for Ava hardware apps: voice-first, screen-grounded, and designed for always-available crypto device experiences.

![Ava IP character sheet](docs/assets/readme/ava-ip-character-sheet.png)

## Framework Layers

| Layer | Role | Current code |
|---|---|---|
| Device Runtime | ESP32 firmware boundary, device messages, transport, future clean board ports | `ava-devicekit/firmware/`, legacy reference in `firmware/` |
| Screen Contracts | Framework screen payload schema and portable LVGL target | `ava-devicekit/schemas/`, `ava-devicekit/shared_ui/`, reference UI in `ava-devicekit/reference_apps/ava_box/ui/` |
| Solana Action Gateway | Clean `ChainAdapter` plus Solana feed/search/detail/watchlist/draft implementation | `ava-devicekit/backend/ava_devicekit/adapters/solana.py` |
| AI Router | Vendor-neutral model routing policy and app-level deterministic routing | `ava-devicekit/backend/ava_devicekit/model/`, `ava-devicekit/backend/ava_devicekit/apps/ava_box.py` |
| DeviceKit Contracts | Clean manifests, schemas, examples, safety model, reference app metadata | `ava-devicekit/` |
| Reference Apps | Concrete hardware apps built on the framework | `ava-devicekit/apps/ava_box/`, `ava-devicekit/examples/` |

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
| `ava-devicekit/` | Clean Ava DeviceKit framework implementation with backend package, adapters, schemas, examples, and Ava Box app |
| `devicekit/` | Earlier framework notes kept as migration reference |
| `apps/ava_box/` | Earlier Ava Box reference notes kept as migration reference |
| `firmware/` | ESP32 firmware runtime, board ports, audio pipeline, OTA, protocols, and device integration |
| `server/` | Backend stack, management services, action gateway, AI routing/tool logic, deployment docs, and tests |
| `shared/` | Shared LVGL screens compiled into both firmware and simulator |
| `simulator/` | Desktop validation harness for DeviceKit UI and live gateway interaction flows |
| `docs/` | Current architecture and product/reference documents |
| `config/` | Repo-owned shared assets and small configuration artifacts |
| `data/` | Local runtime data placeholder for non-committed state |
| `tmp/` | Generated logs, local probes, and scratch artifacts used during debugging |

## Start Here

| Task | Entry point |
|---|---|
| Understand the clean framework | [`ava-devicekit/README.md`](ava-devicekit/README.md) |
| Review Ava Box as reference app | [`ava-devicekit/apps/ava_box/manifest.json`](ava-devicekit/apps/ava_box/manifest.json), [`ava-devicekit/backend/ava_devicekit/apps/ava_box.py`](ava-devicekit/backend/ava_devicekit/apps/ava_box.py) |
| Bring up ESP32 runtime | [`firmware/README.md`](firmware/README.md), [`firmware/main/README.md`](firmware/main/README.md) |
| Work on Solana backend behavior | [`server/README_en.md`](server/README_en.md), [`server/main/README_en.md`](server/main/README_en.md) |
| Preview pages on desktop | [`simulator/README.md`](simulator/README.md), [`ava-devicekit/reference_apps/ava_box/ui/README.md`](ava-devicekit/reference_apps/ava_box/ui/README.md) |
| Understand shared UI contracts | [`shared/README.md`](shared/README.md) |
| Read architecture notes | [`docs/README.md`](docs/README.md), [`docs/architecture/xiaozhi-extraction.md`](docs/architecture/xiaozhi-extraction.md) |
| Confirm legacy capability decisions | [`ava-devicekit/docs/legacy-capability-inventory.md`](ava-devicekit/docs/legacy-capability-inventory.md) |

## Architecture At A Glance

```text
voice + physical input
  -> firmware/ (ESP32 runtime, board drivers, transport)
  -> ava-devicekit/backend (AvaBoxApp, session gateway, model router)
  -> ChainAdapter(SolanaAdapter first, future adapters later)
  -> ScreenPayload / ActionDraft contracts
       -> current LVGL reference in ava-devicekit/reference_apps/ava_box/ui
       -> future clean runtime in ava-devicekit/shared_ui
```

Key coupling points:

| Coupling point | Purpose |
|---|---|
| `ava-devicekit/apps/ava_box/manifest.json` | Reference app identity, device capabilities, adapters, actions, screens, and safety policy |
| `ava-devicekit/schemas/` | Stable framework contracts for hardware app, action draft, and screen payloads |
| `ava-devicekit/reference_apps/ava_box/ui/` | Single source of truth for the current Ava Box screen layer used by simulator and firmware |
| `firmware/main/boards/scratch-arcade/` | Active Scratch Arcade ESP32-S3 hardware target |
| `firmware/main/ave_transport_idf.cc` | Bridges device events into the shared screen/runtime layer |
| `ava-devicekit/backend/ava_devicekit/adapters/base.py` | Adapter interface for chains/helpers |
| `ava-devicekit/backend/ava_devicekit/adapters/solana.py` | Clean Solana market, watchlist, portfolio, and action draft adapter |
| `simulator/` | Layout, navigation, gateway, and regression validation before flashing hardware |

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

The public framework surface is `ava-devicekit/`. The xiaozhi-derived runtime remains only as legacy reference while equivalent app, adapter, transport, screen, and confirmation contracts move into our own code.
