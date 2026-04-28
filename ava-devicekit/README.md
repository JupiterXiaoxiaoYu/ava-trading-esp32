# Ava DeviceKit

Ava DeviceKit is the clean framework boundary for ESP32-based Solana AI hardware apps. It is intentionally separate from the previous monorepo assistant runtime and exposes its own app, device, provider, OTA, and control-plane contracts.

## What This Contains

| Directory | Role |
|---|---|
| `backend/ava_devicekit/` | Framework package: app/session types, adapters, gateway, model router, screen builders |
| `apps/ava_box/` | Ava Box reference app manifest |
| `adapters/solana/` | Solana adapter notes and adapter-specific behavior |
| `schemas/` | Public manifest, screen payload, and action draft contracts |
| `examples/` | Runnable local examples and payload fixtures |
| `firmware/` | Target boundary for clean ESP32 runtime integration |
| `shared_ui/` | Target boundary for portable LVGL screen runtime |
| `reference_apps/ava_box/` | Ava Box app-level UI package and product-specific reference assets |
| `userland/` | Developer-facing configuration templates, capability list, and extension templates |

## Boundary

The clean framework must not import parent-repo assistant-runtime modules such as `core.*`, `plugins_func.*`, or implementation-specific registration/connection classes.

## Userland Boundary

Framework users should start in `userland/`, not by editing core files. That directory documents the capabilities available to app developers and separates configuration/development work from framework maintenance.

| User Goal | Start Here | Implement Or Configure |
|---|---|---|
| Deploy an existing app | `userland/runtime.example.json`, `userland/env.example` | Public URL, WS URL, ports, firmware bin dir, API keys |
| Build a new hardware app | `userland/app/` | App manifest, app routing, app skills, screen choices |
| Build a Solana AI DePIN device | `ava-devicekit init-app ./my-device --type depin` | Device identity, heartbeat/proof actions, physical confirmation, Solana backend boundary |
| Operate C-end hardware users | `/admin`, `docs/c-end-hardware-ops-prd.md` | Customers, activation, device status/config, provider config, diagnostics |
| Add a chain or data source | `userland/adapter/chain_adapter_template.py` | `ChainAdapter` implementation and registry entry |
| Add live market updates | `userland/adapter/market_stream_adapter_template.py` | `MarketStreamAdapter` implementation |
| Add AI providers | `userland/provider/` | ASR, LLM, TTS provider implementations |
| Port a board | `userland/hardware_port/` | GPIO/input mapping, transport send, network events, audio/display hooks |
| Build screens | `userland/ui/` | Screen contracts, screen vtables, LVGL/layout rendering, context snapshots |

The machine-readable capability map is `userland/capabilities.json`.

## App Logic Boundary

`ChainAdapter` stays limited to basic chain data: feed, search, and token detail. Trading drafts, watchlists, portfolio composition, and skill routing live in the reference app layer (`apps/ava_box.py` plus `apps/ava_box_skills/`). This keeps additional chain/helper adapters replaceable without turning the framework into an Ava Box trading server.

## Numeric Display Policy

Small hardware screens use a conditional compact numeric policy across prices, volumes, PnL, chart axes, holders, and percentage values:

| Value Type | Rule | Example |
|---|---|---|
| Money / price | Fixed notation while it fits the small-screen budget; scientific notation only below `0.0001` or at `100,000,000+` | `$12.34`, `$0.1235`, `$7.96e-5`, `$1.23e8` |
| Percent | Signed fixed notation while it fits; scientific only for oversized values | `+1.5%`, `-74.73%` |
| Volumes / counts | Compact `K/M/B/T` suffixes; scientific only when compact text no longer fits | `$404K`, `$1.5M`, `12.3K` |
| Zero | Rendered as plain zero with unit prefix/suffix if any | `$0`, `0`, `+0%` |

Backend code should use `ava_devicekit.formatting.numbers`; C/LVGL code should use `ave_price_fmt`.

## Standalone Runtime

Ava Box can run through DeviceKit without importing the previous assistant backend. The gateway builds a session from a hardware app manifest, an adapter registry, and app-local skills:

| Layer | Current Implementation |
|---|---|
| Hardware app contract | `apps/base.py` defines the minimal `boot()` and `handle()` runtime interface |
| App registry | `apps/registry.py` loads manifests and creates the Ava Box reference app |
| Adapter registry | `adapters/registry.py` resolves built-ins (`solana`, `mock_solana`) and runtime-configured custom chain adapters |
| Session factory | `gateway/factory.py` creates a runnable `DeviceSession` from CLI or code |
| HTTP gateway | `gateway/http_server.py` exposes boot/message/state/outbox endpoints |
| WebSocket gateway | `gateway/websocket_server.py` exposes the same session flow over optional WebSocket transport |
| Control plane | `control_plane/store.py` manages local users, projects, provisioned devices, one-time registration, and per-device tokens |
| firmware compatibility bridge | `gateway/firmware_compat.py` accepts deployed firmware `hello`, `listen`, and `key_action` frames and routes them into `DeviceSession` |
| OTA/settings runtime | `runtime/settings.py` and `ota/` emit the deployed firmware OTA contract without importing the previous server implementation |
| Model providers | `providers/` defines ASR, LLM, TTS, and voice fallback boundaries |
| Market streams | `streams/` defines live/polling market update boundaries |
| Scratch Arcade port | `firmware/ports/scratch_arcade/` maps the reference hardware buttons, OTA path, and WebSocket path |

## Minimal Flow

```text
ESP32 input / voice
  -> DeviceMessage
  -> ContextSnapshot / InputEvent when the device has page or hardware context
  -> AvaBoxApp
  -> ChainAdapter(SolanaAdapter)
  -> ScreenPayload or ActionDraft
  -> physical confirm/cancel
  -> ActionResult
```

## Gateway Contract

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Process health |
| `GET` | `/manifest` | Active hardware app manifest |
| `GET` | `/device/state` | Current app context, screen, and session metadata |
| `GET` | `/device/outbox` | Payloads emitted by the session |
| `POST` | `/device/boot` | Start the hardware app and render the first screen |
| `POST` | `/device/message` | Send a `DeviceMessage` such as `key_action`, `listen_detect`, `confirm`, or `cancel` |
| `GET` | `/ava/ota/` | Compatibility health response for existing firmware OTA checks |
| `POST` | `/ava/ota/` | Compatibility OTA response containing `websocket`, `server_time`, and optional firmware update |
| `GET` | `/ava/ota/download/{filename}` | Safe firmware binary download from the configured bin directory |
| `GET` | `/admin/ota/firmware` | List versioned firmware binaries available for OTA |
| `POST` | `/admin/ota/firmware` | Publish a `.bin` into the OTA directory by `model` and `version` |
| `GET` | `/admin/developer/services` | Inspect backend services such as proxy wallets, market-data APIs, payment APIs, and order routers without exposing secrets |
| `GET` | `/admin/control-plane` | Inspect local users, projects, and registered devices |
| `GET/POST` | `/admin/users` | List or create local control-plane users |
| `GET/POST` | `/admin/customers` | List or create C-end hardware customers |
| `GET/POST` | `/admin/service-plans` | List or create service plans and usage limits |
| `GET/POST` | `/admin/usage` | View usage by device/period or record usage manually |
| `GET/POST` | `/admin/projects` | List or create projects, defaulting to Solana |
| `GET` | `/admin/registered-devices` | List provisioned and registered devices |
| `POST` | `/admin/devices/register` | Provision a device and return a one-time provisioning token |
| `POST` | `/admin/devices/{device_id}/provision-token` | Rotate a device provisioning token |
| `GET/POST` | `/admin/devices/{device_id}/config` | View or update device-level app/voice/wake/OTA/wallet config |
| `POST` | `/admin/devices/{device_id}/status` | Suspend, activate, or revoke a device |
| `POST` | `/admin/devices/{device_id}/entitlement` | Assign a service plan and entitlement status to a device |
| `GET` | `/admin/devices/{device_id}/diagnostics` | Inspect device state, connection, config, and recent events |
| `GET/POST` | `/admin/runtime/config` | View or update persisted runtime provider/service config |
| `POST` | `/admin/runtime/providers` | Update one ASR/LLM/TTS/chain/execution provider from the web console |
| `POST` | `/admin/devices/{device_id}/ota-check` | Queue an `ota_check` command so an online device runs its normal OTA pull flow |
| `POST` | `/admin/developer/services/{service_id}/invoke` | Backend-only allowlisted service invocation for app/admin tooling |
| `POST` | `/device/register` | Exchange a one-time provisioning token for a per-device bearer token |
| `POST` | `/device/activate` | Bind a physical device to a C-end customer using its activation code |
| `GET` | `/device/config` | Device pulls its resolved language/voice/wake/app/OTA/wallet config |
| `POST` | `/device/usage` | Device reports ASR/LLM/TTS/API usage with its bearer token |


## Production Components Added

| Area | Framework Or App | Current Implementation |
|---|---|---|
| ASR audio chain | Framework provider boundary | Selectable ASR registry with Qwen realtime, OpenAI-compatible transcription, custom provider classes, and explicit `AudioDecoder` board/deployment hook |
| TTS provider | Framework provider boundary | Selectable TTS registry with mock, OpenAI-compatible HTTP TTS, and custom provider classes |
| LLM fallback | Framework provider boundary | Runtime-configured OpenAI-compatible chat provider plus custom LLM provider classes through `providers/registry.py` |
| Live market WSS | Ava Box reference integration | AVE data WSS frame builder/parser in `streams/ave_data_wss.py` |
| Real trade/wallet flow | Ava Box app layer | Paper execution by default; AVE proxy/custodial wallet provider, optional self-custody transaction provider, and custom execution provider classes in `apps/ava_box_skills/execution.py` |
| Admin API | Framework gateway | `/admin/capabilities`, `/admin/runtime`, `/admin/apps`, `/admin/devices`, `/admin/events`, `/admin/ota/firmware`, `/admin/developer/services`, optional bearer auth |
| Control plane | Framework gateway | Local users/projects/devices registry, device provisioning token exchange, per-device bearer auth, and sanitized fleet snapshot APIs |
| C-end hardware ops | Framework control plane | Customer records, one-step user registration, activation codes, app-scoped users/devices, device status/config, provider config editing, and per-device diagnostics for self-hosted hardware service operation |
| Usage and entitlements | Framework control plane | Service plans, per-device entitlements, usage reports, and usage recording endpoints for C-end hardware service cost control |
| Package/CLI | Framework developer surface | `ava-devicekit` CLI with `capabilities`, `validate`, `init-app`, `init-board`, `init-adapter`, `init-provider`, `firmware`, `run-http`, `run-firmware-ws`, and `run-server` |
| Firmware publish | Framework OTA | `ota/publish.py`, `/admin/ota/firmware`, and `ava-devicekit firmware publish/list` manage pull-based OTA binaries |
| Developer services | Framework backend registry | `services/registry.py` declares proxy wallets, market-data APIs, payment APIs, order routers, and custom services with redacted health checks |
| Device protocol | Framework contract | `docs/device-protocol.md` defines hello, input, context, display, TTS, ACK, command, and OTA-trigger frames |
| Security hardening | Framework deploy policy | `production_mode`, bearer-token enforcement, and service invocation allowlists protect admin/device surfaces |
| Cloud control plane | Framework admin UI | `/admin` provides a lightweight developer console for devices, OTA, providers, services, events, and raw runtime state without a frontend build step |
| UI migration boundary | Framework + app UI | Shared UI screen contracts under `shared_ui/screens`; product LVGL screens consume payloads outside core |
| Generic page/input/context | Framework contract | Custom `ScreenContract`, `InputEvent`, and `ContextSnapshot` schemas let new pages and new hardware controls attach AI-readable state without changing core |

## Documentation

| Doc | Purpose |
|---|---|
| `docs/technical-architecture-and-builder-guide-zh.md` | 中文技术架构、后台功能、固件/硬件/UI/AI 关系，以及从 0 到 1 构建 Ava Box 类产品的开发者指南 |
| `docs/solana-reference-repos-review.md` | Solana ESP32 / DePIN / payment / signer reference repository review, license notes, optional dependencies, and DeviceKit mapping |
| `docs/framework-vs-avabox.md` | Strict boundary between DeviceKit framework and Ava Box app logic |
| `docs/completion-status.md` | Current framework/app completion matrix and runtime assumptions |
| `docs/getting-started.md` | Local install, offline run, runtime provider config, admin APIs |
| `docs/build-your-first-app.md` | Create and structure a new hardware app |
| `docs/generic-screen-input-context.md` | Add custom pages, hardware input, and AI-readable page context |
| `docs/port-a-board.md` | Port ESP32 boards without baking hardware assumptions into core |
| `docs/provider-setup.md` | ASR, LLM, TTS, market stream, and trade provider setup |
| `docs/production-deploy.md` | Gateway deployment, proxy/heartbeat, OTA, wallet safety |
| `docs/package-release.md` | CLI/package release and versioning notes |
| `docs/ota-and-developer-services.md` | Pull-based firmware updates and server-side developer service registry |
| `docs/device-protocol.md` | Firmware/backend protocol frames including explicit ACK and OTA trigger |
| `docs/security-hardening.md` | Production mode, auth tokens, allowlists, and wallet/API safety |
| `docs/ai-depin-cloud-prd.md` | Product requirements for the self-hosted AI DePIN control plane and Solana app template |
| `docs/c-end-hardware-ops-prd.md` | Product requirements for operating C-end hardware users from a self-hosted console |
| `docs/hardware-service-product-closure.md` | Stakeholder and product-flow closure for the operator console vs customer/device model |
| `docs/compatibility-capability-inventory.md` | Adapted capability inventory for firmware, backend, providers, UI, OTA, and dashboard boundaries |

## Existing Firmware Compatibility

The current production firmware can be moved over incrementally by pointing its OTA URL at the DeviceKit HTTP gateway and its WebSocket URL at the compatibility gateway:

```bash
cd ava-devicekit
PYTHONPATH=backend python3 -m ava_devicekit.cli run-http --host 0.0.0.0 --port 8788 --config runtime.local.json
PYTHONPATH=backend python3 -m ava_devicekit.cli run-firmware-ws --host 0.0.0.0 --port 8787 --config runtime.local.json
```

Example runtime config:

```json
{
  "public_base_url": "https://ava.example.com",
  "websocket_url": "wss://ava.example.com/ava/v1/",
  "firmware_bin_dir": "data/bin",
  "websocket_ping_interval": 30,
  "websocket_ping_timeout": 10,
  "adapters": {
    "chain": {
      "provider": "custom",
      "class": "my_app.adapters.MyChainAdapter",
      "options": {
        "base_url": "https://data.example.com"
      }
    }
  },
  "execution": {
    "mode": "custom",
    "class": "my_app.execution.MyTradeExecutor",
    "options": {
      "base_url": "https://trade.example.com"
    }
  }
}
```

This preserves the deployed firmware wire protocol while keeping the implementation inside DeviceKit-owned modules.


## Migration Capability Review

Before migrating more code from the parent repo, review `docs/compatibility-capability-inventory.md`. Every carried-over capability is mapped to `keep`, `replace`, `drop`, or `optional` so DeviceKit keeps clean ownership while preserving useful production behavior such as Wi-Fi provisioning, OTA, audio, model providers, and live market streams.

## Run Local Checks

```bash
cd ava-devicekit
PYTHONPATH=backend python3 examples/demo_flow.py
PYTHONPATH=backend python3 -m ava_devicekit.cli run-http --host 127.0.0.1 --port 8788 --config userland/runtime.example.json
PYTHONPATH=backend python3 examples/mock_device_client.py --base-url http://127.0.0.1:8788
PYTHONPATH=backend python3 -m pytest tests
```

The production path uses `--adapter solana` or the manifest default. Offline fixtures are reserved for tests and must not be used for Ava Box runs.

## Multi-Device Runtime

HTTP device endpoints use `X-Ava-Device-Id` to keep independent sessions. Admin endpoints can inspect `/admin/devices`, `/admin/control-plane`, and `/admin/events`. Set `AVA_DEVICEKIT_ADMIN_TOKEN` for admin access. Devices can either use the compatibility-wide `AVA_DEVICEKIT_DEVICE_TOKEN` or register through `/device/register` and then use their own per-device bearer token.
