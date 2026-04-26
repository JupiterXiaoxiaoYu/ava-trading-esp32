# Ava DeviceKit

Ava DeviceKit is a full-stack framework for building ESP32-based Solana AI hardware apps. It combines a lightweight device runtime, LVGL screen contracts, backend Solana action APIs, model routing, and physical confirmation flows.

Ava Box is the first reference app built with the kit. The framework direction is broader: payments, token alerts, approval terminals, DePIN sensor devices, and other Solana hardware interfaces can reuse the same contracts.

## What The Kit Provides

| Layer | Responsibility | Current implementation |
|---|---|---|
| Device runtime | Wi-Fi setup, display lifecycle, buttons, joystick, microphone, speaker, OTA, WebSocket transport | `firmware/`, especially `firmware/main/ave_transport_idf.cc` and board ports |
| Screen contracts | LVGL payloads for feed, spotlight, watchlist, portfolio, confirm, result, and notifications | `shared/ave_screens/` |
| Action gateway | Backend receives device/user intents, constructs Solana action drafts, pushes screen payloads, and waits for confirmation | `server/main/xiaozhi-server/plugins_func/functions/` |
| AI router | ASR, wake/PTT handling, model provider routing, deterministic action routing, and LLM fallback | `server/main/xiaozhi-server/core/` plus Ava tools |
| App manifests | Declarative app identity, device capability, screen, action, model, and safety policy metadata | `devicekit/manifests/` |
| Reference apps | Concrete hardware apps built on the contracts | `apps/ava_box/` and `devicekit/examples/` |

## Safety Model

ESP32 is treated as a physical interaction and confirmation surface, not as the default custody layer for user assets.

| Mode | Description |
|---|---|
| Draft mode | Backend builds an action draft and the device displays the summary |
| Confirmation mode | High-risk actions require screen-visible confirmation and a physical button press |
| External signing mode | User assets can be signed by mobile/web/external wallets instead of storing primary keys on ESP32 |
| Device key mode | ESP32 may hold a device identity key for heartbeat, registration, or sensor proofs; this is separate from user funds |

## Minimal App Contract

A hardware app should define:

| Contract | File |
|---|---|
| App manifest | `devicekit/schemas/hardware_app.schema.json` |
| Action payload | `devicekit/schemas/action_payload.schema.json` |
| Screen payload | `devicekit/schemas/screen_payload.schema.json` |

The reference manifest is `devicekit/manifests/ava_box.solana.json`.

## Why This Is Not Just A Low-Level SDK

Low-level SDKs help ESP32 sign or talk to Solana. Ava DeviceKit is aimed at complete Solana hardware apps: device UI, physical input, voice, backend action APIs, model routing, and confirmation flows.

## Current Upstream Extraction Boundary

The runtime still contains pieces derived from the xiaozhi ecosystem, but the DeviceKit boundary is intentionally smaller:

| Keep | Extract / simplify |
|---|---|
| Audio I/O, wake/PTT, WebSocket session, OTA, board bring-up | Solana action gateway, app manifest, screen payloads, physical confirmation contract, reference apps |
| Generic assistant runtime behavior needed by the device | Product-specific xiaozhi app assumptions that are not needed by Ava hardware apps |

See `docs/architecture/xiaozhi-extraction.md` for the extraction plan.
