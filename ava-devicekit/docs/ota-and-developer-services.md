# OTA And Developer Services

DeviceKit keeps firmware delivery and developer backend services on the server side. ESP32 devices receive configuration and signed/curated actions; they do not receive API secrets.

## Firmware Update Flow

DeviceKit OTA is pull-based, not a blind server push.

| Step | Actor | Endpoint / File | Result |
|---|---|---|---|
| 1 | Developer/CI | `ava-devicekit firmware publish` or `POST /admin/ota/firmware` | Copies a versioned `.bin` into `firmware_bin_dir`. |
| 2 | Device | `POST /ava/ota/` | Sends model and current firmware version. |
| 3 | DeviceKit | `firmware_bin_dir/{model}_{version}.bin` | Finds the highest version greater than the device version. |
| 4 | DeviceKit | OTA response | Returns `firmware.version`, `firmware.url`, `websocket.url`, and server time. |
| 5 | Device | `GET /ava/ota/download/{filename}` | Downloads the binary and applies OTA using firmware-side logic. |

The backend does not currently force-flash a connected device over WebSocket. If a product needs immediate upgrades, add a device command that asks the device to run its OTA check. The firmware still downloads through the same safe `/ava/ota/download/` path.

## Firmware Naming

Use this filename format:

```text
{model}_{version}.bin
```

Examples:

```text
scratch-arcade_1.4.0.bin
watch-round_0.2.3.bin
robot-head_2.0.0.bin
```

Versions are compared numerically. `1.10.0` is newer than `1.2.0`.

## CLI

```bash
PYTHONPATH=backend python3 -m ava_devicekit.cli firmware publish \
  --config runtime.local.json \
  --model scratch-arcade \
  --version 1.4.0 \
  --source build/ava_box.bin

PYTHONPATH=backend python3 -m ava_devicekit.cli firmware list --config runtime.local.json
```

## Admin API

| Method | Path | Body | Purpose |
|---|---|---|---|
| `GET` | `/admin/ota/firmware` | none | List firmware binaries visible to OTA. |
| `POST` | `/admin/ota/firmware` | `model`, `version`, `source_path` or `content_base64` | Publish a firmware binary. |
| `POST` | `/ava/ota/` | device model/version | Device OTA check. |
| `GET` | `/ava/ota/download/{filename}` | none | Firmware download. |

Admin endpoints use `AVA_DEVICEKIT_ADMIN_TOKEN` when configured.

## Developer Services

DeviceKit should provide a backend service registry for APIs that devices and apps depend on. This is where proxy wallets, market-data APIs, payment APIs, order routers, risk engines, or custom app services are declared.

| Principle | Rule |
|---|---|
| Secret location | Secrets stay in backend environment variables. |
| Device role | ESP32 is the interaction and physical confirmation surface. |
| App role | App skills decide when and how to call a service. |
| Framework role | DeviceKit lists, validates, and exposes service health; it does not hardcode one vendor. |
| Wallet safety | Proxy/custodial wallet providers run server-side after device confirmation. |

Example runtime config:

```json
{
  "services": [
    {
      "id": "proxy_wallet",
      "kind": "custodial_wallet",
      "base_url": "https://wallet.example.com",
      "api_key_env": "WALLET_API_KEY",
      "secret_key_env": "WALLET_SECRET_KEY",
      "wallet_id_env": "WALLET_ID",
      "capabilities": ["wallet.balance", "trade.market", "trade.limit", "order.status"]
    },
    {
      "id": "market_data",
      "kind": "market_data_api",
      "base_url": "https://data.example.com",
      "api_key_env": "DATA_API_KEY",
      "capabilities": ["token.feed", "token.search", "token.detail", "price.stream"]
    }
  ]
}
```

Inspect service readiness:

```bash
curl http://127.0.0.1:8788/admin/developer/services
```

The response is redacted and reports whether required env vars are present. It never returns the secret values.

## Should DeviceKit Provide Proxy Wallet/API Services?

Yes, but as a server-side interface, not as firmware logic.

| Service Type | Belongs In | Why |
|---|---|---|
| Proxy/custodial wallet credentials | Backend env/config | Avoid putting private keys or API secrets on ESP32. |
| Order construction/submission | App service provider | Different apps and chains need different execution rules. |
| Wallet balance/order status API | Developer service registry + app provider | Framework can expose health/capabilities; app owns business semantics. |
| Physical confirmation | Device UI | User must see and approve risky actions on screen. |
| Raw private key custody | Not DeviceKit core | Future products can integrate secure elements or external wallets. |

For Ava Box, the existing AVE proxy wallet provider remains app-level. For other products, implement a custom service provider and declare it in `services[]`.
