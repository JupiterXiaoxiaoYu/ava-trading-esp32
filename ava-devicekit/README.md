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

## Run Local Checks

```bash
cd ava-devicekit
PYTHONPATH=backend python3 examples/demo_flow.py
PYTHONPATH=backend python3 -m pytest tests
```
