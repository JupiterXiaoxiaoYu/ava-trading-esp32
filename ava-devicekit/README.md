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
