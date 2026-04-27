# Ava DeviceKit

Ava DeviceKit is the clean framework boundary for ESP32-based Solana AI hardware apps. It is intentionally separate from the legacy assistant runtime in the parent repo.

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
| `userland/` | Developer-facing configuration templates, capability list, and extension templates |

## Boundary

The clean framework must not import parent-repo legacy modules such as `core.*`, `plugins_func.*`, or legacy-assistant-specific registration/connection classes.

## Userland Boundary

Framework users should start in `userland/`, not by editing core files. That directory documents the capabilities available to app developers and separates configuration/development work from framework maintenance.

| User Goal | Start Here | Implement Or Configure |
|---|---|---|
| Deploy an existing app | `userland/runtime.example.json`, `userland/env.example` | Public URL, WS URL, ports, firmware bin dir, API keys |
| Build a new hardware app | `userland/app/` | App manifest, app routing, app skills, screen choices |
| Add a chain or data source | `userland/adapter/chain_adapter_template.py` | `ChainAdapter` implementation and registry entry |
| Add live market updates | `userland/adapter/market_stream_adapter_template.py` | `MarketStreamAdapter` implementation |
| Add AI providers | `userland/provider/` | ASR, LLM, TTS provider implementations |
| Port a board | `userland/hardware_port/` | GPIO/input mapping, transport send, network events, audio/display hooks |
| Build screens | `userland/ui/` | Screen vtables, LVGL/layout rendering, selection context JSON |

The machine-readable capability map is `userland/capabilities.json`.

## App Logic Boundary

`ChainAdapter` stays limited to basic chain data: feed, search, and token detail. Trading drafts, watchlists, portfolio composition, and skill routing live in the reference app layer (`apps/ava_box.py` plus `apps/ava_box_skills/`). This keeps future chain/helper adapters replaceable without turning the framework into an Ava Box trading server.

## Standalone Runtime

Ava Box can run through DeviceKit without importing the legacy assistant backend. The gateway builds a session from a hardware app manifest, an adapter registry, and app-local skills:

| Layer | Current Implementation |
|---|---|
| Hardware app contract | `apps/base.py` defines the minimal `boot()` and `handle()` runtime interface |
| App registry | `apps/registry.py` loads manifests and creates the Ava Box reference app |
| Adapter registry | `adapters/registry.py` resolves `solana` and offline `mock_solana` adapters |
| Session factory | `gateway/factory.py` creates a runnable `DeviceSession` from CLI or code |
| HTTP gateway | `gateway/http_server.py` exposes boot/message/state/outbox endpoints |
| WebSocket gateway | `gateway/websocket_server.py` exposes the same session flow over optional WebSocket transport |
| legacy firmware compatibility shim | `gateway/legacy_firmware.py` accepts existing firmware `hello`, `listen`, and `key_action` frames and routes them into `DeviceSession` |
| OTA/settings runtime | `runtime/settings.py` and `ota/` emit the existing firmware OTA contract without importing legacy server code |
| Model providers | `providers/` defines ASR, LLM, TTS, and voice fallback boundaries |
| Market streams | `streams/` defines live/polling market update boundaries |
| Scratch Arcade port | `firmware/ports/scratch_arcade/` maps the reference hardware buttons, OTA path, and WebSocket path |

## Minimal Flow

```text
ESP32 input / voice
  -> DeviceMessage
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


## Production Components Added

| Area | Framework Or App | Current Implementation |
|---|---|---|
| ASR audio chain | Framework provider boundary | Selectable ASR registry with Qwen realtime, OpenAI-compatible transcription, custom provider classes, and explicit `AudioDecoder` board/deployment hook |
| TTS provider | Framework provider boundary | Selectable TTS registry with mock, OpenAI-compatible HTTP TTS, and custom provider classes |
| LLM fallback | Framework provider boundary | Runtime-configured OpenAI-compatible chat provider plus custom LLM provider classes through `providers/registry.py` |
| Live market WSS | Ava Box reference integration | AVE data WSS frame builder/parser in `streams/ave_data_wss.py` |
| Real trade/wallet flow | Ava Box app layer | Paper execution by default; AVE Solana transaction construction provider in `apps/ava_box_skills/execution.py` for external wallet signing |
| Admin API | Framework gateway | `/admin/capabilities`, `/admin/runtime`, `/admin/apps` |
| Package/CLI | Framework developer surface | `ava-devicekit` CLI with `capabilities`, `validate`, `init-app`, `run-http`, and `run-legacy-ws` |
| UI migration boundary | Framework + app UI | Shared UI screen contracts under `shared_ui/screens`; product LVGL screens consume payloads outside core |

## Documentation

| Doc | Purpose |
|---|---|
| `docs/framework-vs-avabox.md` | Strict boundary between DeviceKit framework and Ava Box app logic |
| `docs/getting-started.md` | Local install, offline run, runtime provider config, admin APIs |
| `docs/build-your-first-app.md` | Create and structure a new hardware app |
| `docs/port-a-board.md` | Port ESP32 boards without baking hardware assumptions into core |
| `docs/provider-setup.md` | ASR, LLM, TTS, market stream, and trade provider setup |
| `docs/production-deploy.md` | Gateway deployment, proxy/heartbeat, OTA, wallet safety |
| `docs/package-release.md` | CLI/package release and versioning notes |

## Existing Firmware Compatibility

The current production firmware can be moved over incrementally by pointing its OTA URL at the DeviceKit HTTP gateway and its WebSocket URL at the compatibility gateway:

```bash
cd ava-devicekit
PYTHONPATH=backend python3 -m ava_devicekit.gateway.dev_server --host 0.0.0.0 --port 8788 --mock --config runtime.local.json
PYTHONPATH=backend python3 -m ava_devicekit.gateway.legacy_firmware --host 0.0.0.0 --port 8787 --mock --config runtime.local.json
```

Example runtime config:

```json
{
  "public_base_url": "https://ava.example.com",
  "websocket_url": "wss://ava.example.com/ava/v1/",
  "firmware_bin_dir": "data/bin",
  "websocket_ping_interval": 30,
  "websocket_ping_timeout": 10
}
```

This preserves the legacy firmware wire protocol while keeping the implementation inside DeviceKit-owned modules.


## Legacy Capability Review

Before migrating more code from the parent repo, review `docs/legacy-capability-inventory.md`. Every legacy capability must be explicitly marked `keep`, `replace`, `drop`, or `later` before implementation. This prevents accidental dependency on the old assistant framework while still preserving useful runtime capabilities such as Wi-Fi provisioning, OTA, audio, model providers, and live market streams.

## Run Local Checks

```bash
cd ava-devicekit
PYTHONPATH=backend python3 examples/demo_flow.py
PYTHONPATH=backend python3 -m ava_devicekit.gateway.dev_server --host 127.0.0.1 --port 8788 --mock
PYTHONPATH=backend python3 examples/mock_device_client.py --base-url http://127.0.0.1:8788
PYTHONPATH=backend python3 -m pytest tests
```

Use `--adapter solana` for a real data adapter deployment and `--mock` for deterministic offline demos/tests.
