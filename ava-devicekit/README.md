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

## Boundary

The clean framework must not import parent-repo legacy modules such as `core.*`, `plugins_func.*`, or xiaozhi-specific registration/connection classes.

## App Logic Boundary

`ChainAdapter` stays limited to basic chain data: feed, search, and token detail. Trading drafts, watchlists, portfolio composition, and skill routing live in the reference app layer (`apps/ava_box.py` plus `apps/ava_box_skills/`). This keeps future chain/helper adapters replaceable without turning the framework into an Ava Box trading server.

## Standalone Runtime

Ava Box can run through DeviceKit without importing the legacy xiaozhi backend. The gateway builds a session from a hardware app manifest, an adapter registry, and app-local skills:

| Layer | Current Implementation |
|---|---|
| Hardware app contract | `apps/base.py` defines the minimal `boot()` and `handle()` runtime interface |
| App registry | `apps/registry.py` loads manifests and creates the Ava Box reference app |
| Adapter registry | `adapters/registry.py` resolves `solana` and offline `mock_solana` adapters |
| Session factory | `gateway/factory.py` creates a runnable `DeviceSession` from CLI or code |
| HTTP gateway | `gateway/http_server.py` exposes boot/message/state/outbox endpoints |
| WebSocket gateway | `gateway/websocket_server.py` exposes the same session flow over optional WebSocket transport |

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


## Legacy Capability Review

Before migrating more code from the parent repo, review `docs/xiaozhi-capability-inventory.md`. Every legacy capability must be explicitly marked `keep`, `replace`, `drop`, or `later` before implementation. This prevents accidental dependency on the old assistant framework while still preserving useful runtime capabilities such as Wi-Fi provisioning, OTA, audio, model providers, and live market streams.

## Run Local Checks

```bash
cd ava-devicekit
PYTHONPATH=backend python3 examples/demo_flow.py
PYTHONPATH=backend python3 -m ava_devicekit.gateway.dev_server --host 127.0.0.1 --port 8788 --mock
PYTHONPATH=backend python3 examples/mock_device_client.py --base-url http://127.0.0.1:8788
PYTHONPATH=backend python3 -m pytest tests
```

Use `--adapter solana` for a real data adapter deployment and `--mock` for deterministic offline demos/tests.
