# Security Hardening

DeviceKit is designed so ESP32 devices are interaction and confirmation surfaces, not secret stores.

## Production Mode

Set `production_mode: true` in runtime config and configure both token env vars:

```json
{
  "production_mode": true,
  "admin_token_env": "AVA_DEVICEKIT_ADMIN_TOKEN",
  "device_token_env": "AVA_DEVICEKIT_DEVICE_TOKEN"
}
```

When production mode is enabled, admin and device endpoints reject requests if the expected token env var is missing. This prevents accidentally deploying an unauthenticated gateway.

## Recommended Controls

| Surface | Control |
|---|---|
| Admin API | Require bearer token, restrict network exposure, put behind HTTPS reverse proxy. |
| Device API | Require device token for HTTP flows; for WebSocket, put token in headers or reverse-proxy auth. |
| Firmware publish | Restrict `/admin/ota/firmware` to CI/admin token only. |
| Developer service invocation | Use `invocable: true` plus `allowed_paths`; never expose arbitrary proxying. |
| Wallet/API credentials | Store only in backend env vars; never send to firmware. |
| High-risk actions | Require device screen confirmation before app provider execution. |
| Logs | Avoid recording secrets; DeviceKit reports env var names and health, not values. |

## Developer Service Invocation

Service invocation is intentionally allowlist-based:

```json
{
  "id": "payment_api",
  "kind": "payment",
  "base_url": "https://payments.example.com",
  "api_key_env": "PAYMENT_API_KEY",
  "capabilities": ["payment.quote"],
  "options": {
    "invocable": true,
    "allowed_paths": ["/quote"],
    "timeout_sec": 10
  }
}
```

Only backend admin/app-side code should call this. Devices should not directly invoke service URLs.
