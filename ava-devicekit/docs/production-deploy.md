# Production Deploy

## Services

Run the HTTP gateway and WebSocket gateway behind a reverse proxy. The WebSocket gateway handles text commands, binary audio buffering, ASR routing, and optional TTS audio frames:

```bash
PYTHONPATH=backend python3 -m ava_devicekit.cli run-http --host 0.0.0.0 --port 8788 --config runtime.local.json
PYTHONPATH=backend python3 -m ava_devicekit.cli run-legacy-ws --host 0.0.0.0 --port 8787 --config runtime.local.json
```

Use long proxy read timeouts for hardware sessions and keep WebSocket ping enabled through `websocket_ping_interval` and `websocket_ping_timeout`.

## Runtime Safety

| Area | Rule |
|---|---|
| Secrets | Store only environment variable names in config files |
| Wallet signing | Keep user-key custody outside ESP32 unless a secure element/wallet design is added |
| AI actions | Use deterministic routing for known actions and require physical confirmation for high-risk actions |
| OTA | Serve firmware only from the configured `firmware_bin_dir` |
| Admin APIs | Expose sanitized runtime state only; never return secret values |


## Auth

Set these environment variables to enable bearer-token protection. If they are unset, local development stays open.

| Env Var | Protects |
|---|---|
| `AVA_DEVICEKIT_ADMIN_TOKEN` | `/admin/*` endpoints |
| `AVA_DEVICEKIT_DEVICE_TOKEN` | `/device/*` endpoints |

Requests use `Authorization: Bearer <token>`. Device requests may also send `X-Ava-Device-Id` to bind state to a specific session.

## Multi-Device Runtime

The HTTP and generic WebSocket gateways use `RuntimeManager` to keep independent sessions by device id. Admin endpoints include:

| Path | Purpose |
|---|---|
| `/admin/devices` | List active device sessions |
| `/admin/devices/{device_id}/state` | Inspect one device session |
| `/admin/devices/{device_id}/outbox` | Inspect one device outbox |
| `/admin/events` | View recent runtime events |
