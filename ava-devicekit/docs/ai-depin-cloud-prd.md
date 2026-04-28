# Ava DeviceKit AI DePIN Framework PRD

## Product Definition

Ava DeviceKit is a full-stack framework for building Solana-aware AI hardware apps on ESP32-class devices. The framework provides the runtime contract, cloud control plane, device registration, provider configuration, OTA delivery, app templates, and backend service boundaries needed to ship physical AI devices without hard-coding one product or one board.

Ava Box is the first reference app built on this framework. Framework code must stay app-agnostic; Ava Box trading, watchlist, portfolio, and market-screen logic belong in the app layer.

## Product Goals

| Goal | Product Requirement |
|---|---|
| Build Solana AI hardware apps quickly | Provide app, board, adapter, provider, and DePIN templates. |
| Manage real device fleets | Provide users, projects, provisioned devices, device registration, per-device auth, events, OTA, and provider health. |
| Keep devices safe | ESP32 acts as the physical interaction and confirmation surface; credentials and signing providers stay server-side or in external wallets. |
| Stay chain and hardware extensible | Core contracts avoid fixed buttons, fixed displays, or fixed chain/business APIs. |
| Support self-hosted first, SaaS later | Implement a local control-plane store and HTTP APIs now; keep entities aligned with future hosted multi-tenant service. |

## Users And Jobs

| Persona | Jobs To Be Done | DeviceKit Capability |
|---|---|---|
| Platform admin | Deploy the gateway, configure provider credentials, manage firmware and device access. | Admin token, runtime config, `/admin`, OTA catalog, provider health, developer services. |
| App developer | Build a Solana hardware app with screens, actions, AI context, and backend services. | `init-app`, app manifest, screen contracts, context snapshots, service registry. |
| Hardware developer | Port a new ESP32 board without changing app logic. | `init-board`, board profile, input/event mapping, display/audio/transport hooks. |
| Device operator | Register devices, assign devices to projects, monitor online state and events. | Control-plane users/projects/devices, provisioning token, per-device token, event log. |
| End user | Use a physical device to speak, inspect, approve, cancel, or monitor Solana actions. | Voice/provider pipeline, screen payloads, physical confirmation, TTS/display results. |

## Core Entities

| Entity | Required Now | Notes |
|---|---:|---|
| User | Yes | Local records for admin/developer/operator/viewer roles. This is not password login yet. |
| Project | Yes | Groups devices and apps under a chain, defaulting to Solana. |
| Device | Yes | Provisioned by admin, registered once by firmware, authenticated with per-device token. |
| App | Yes | Manifest-driven hardware app. Templates include payment, alert, sensor, and Solana AI DePIN. |
| Board | Yes | Developer-owned hardware port profile and input/output implementation. |
| Firmware | Yes | Versioned pull-based OTA binaries by model/version. |
| Provider | Yes | Configurable ASR, LLM, TTS, chain, stream, and execution providers. |
| Developer Service | Yes | Server-side API/proxy wallet/payment/order services exposed through allowlisted backend calls. |
| Event | Yes | Runtime and device events for diagnosis and AI context debugging. |

## MVP Scope Implemented In This Phase

| Area | Decision | Implementation |
|---|---|---|
| Control plane store | Implement now | Local JSON store with users, projects, devices, bootstrap defaults. |
| Admin registry APIs | Implement now | `/admin/control-plane`, `/admin/users`, `/admin/projects`, `/admin/registered-devices`, `/admin/devices/register`. |
| Device provisioning | Implement now | Admin receives one-time provisioning token; device exchanges it at `/device/register`. |
| Per-device auth | Implement now | Device endpoints accept per-device bearer token and keep global token compatibility. |
| Admin console | Implement now | `/admin` includes control-plane tab, provisioning forms, and registered-device table. |
| DePIN app template | Implement now | `examples/apps/solana_ai_depin_device` and `init-app --type depin`. |
| Password login | Later | Self-hosted admin bearer token remains the access boundary for this phase. |
| Hosted SaaS billing/tenant isolation | Later | Data model is SaaS-ready, but this repo remains self-hosted. |
| On-device asset custody | Not in scope | Devices may have identity keys; user asset keys stay outside ESP32 by default. |

## Registration Flow

| Step | Actor | Action | Output |
|---|---|---|---|
| 1 | Admin | Creates user/project in `/admin`. | User/project records. |
| 2 | Admin | Provisions a device with project, board model, and app id. | Device record plus one-time provisioning token. |
| 3 | Firmware/device | Calls `POST /device/register` with provisioning token. | Device id and per-device token returned once. |
| 4 | Firmware/device | Stores token in NVS/secure storage where available. | Future requests include `Authorization: Bearer <device_token>`. |
| 5 | Gateway | Validates per-device token for `/device/state`, `/device/boot`, `/device/message`, `/device/outbox`. | Device session is isolated by `X-Ava-Device-Id`. |
| 6 | Admin/operator | Monitors device through `/admin/control-plane`, `/admin/devices`, `/admin/events`, OTA tab. | Fleet view and debugging data. |

## Solana AI DePIN App Template

| Layer | Template Responsibility |
|---|---|
| Device UI | `device_home`, `proof_detail`, `confirm`, `result`, `notify` screens. |
| Actions | `device.register`, `device.heartbeat`, `proof.submit`, `action.confirm`, `action.cancel`. |
| Solana boundary | Emits chain-aware action/proof drafts; backend adapter/service decides whether to send a transaction, write proof data, or route to external wallet. |
| AI context | Screen payload includes device id, project, status, heartbeat count, selected proof context. |
| Safety | Requires physical confirmation for registration/proof actions and does not put user asset private keys on ESP32. |

## API Surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/control-plane` | Full sanitized users/projects/devices snapshot. |
| `GET/POST` | `/admin/users` | List or create local control-plane users. |
| `GET/POST` | `/admin/projects` | List or create projects. |
| `GET` | `/admin/registered-devices` | List provisioned and registered devices. |
| `POST` | `/admin/devices/register` | Provision a device and return a one-time provisioning token. |
| `POST` | `/admin/devices/{device_id}/provision-token` | Rotate a one-time provisioning token. |
| `POST` | `/device/register` | Exchange provisioning token for per-device bearer token. |

## Security Model

| Boundary | Rule |
|---|---|
| Admin | Protected by `AVA_DEVICEKIT_ADMIN_TOKEN` when set; required in `production_mode`. |
| Device | Uses per-device token after provisioning; global `AVA_DEVICEKIT_DEVICE_TOKEN` remains for compatibility. |
| Secrets | Control plane stores token hashes only; returned provisioning/device tokens are shown once. |
| Wallet/API credentials | Stay in runtime config/env/developer services, not in device payloads. |
| Physical action safety | Risky actions become drafts and require screen/button confirmation. |

## Acceptance Criteria

| Requirement | Verification |
|---|---|
| PRD exists and maps framework vs app responsibilities. | This document. |
| Local users/projects/devices can be managed. | Control-plane tests and `/admin` UI. |
| Device can register and then authenticate independently. | HTTP gateway tests. |
| Existing Ava Box/simulator flows are not broken. | Full tests and simulator verification. |
| DePIN app template can be generated. | CLI tests and conformance manifest tests. |
