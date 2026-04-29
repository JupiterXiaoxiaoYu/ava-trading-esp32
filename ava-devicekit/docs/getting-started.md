# Getting Started

## Install For Local Development

```bash
cd ava-devicekit
python3 -m pip install -e .[dev,websocket]
```

## Run The Reference App Against DeviceKit

```bash
cd /path/to/ava-trading-esp32
cp ava-devicekit/userland/env.example ava-devicekit/.env.local
./scripts/run-devicekit-local.sh
```

Then send device messages to `POST /device/message` or inspect state at `GET /device/state`.

## Runtime Configuration

Copy `userland/runtime.example.json`, set public URLs, and configure providers through `providers.asr`, `providers.llm`, and `providers.tts`. Secrets are referenced by environment variable names only; they are not stored in the JSON file.

```bash
export AVE_API_KEY=...
export DASHSCOPE_API_KEY=...
export OPENAI_API_KEY=...
PYTHONPATH=backend python3 -m ava_devicekit.cli validate --config runtime.local.json
```

## Admin Endpoints

### Control-Plane Relationship

| Layer | Meaning | Operator-facing rule |
|---|---|---|
| App | The product experience a customer device runs, such as `ava_box` or `sensor_oracle`. | Operators choose/create an `app_id`; this is the primary product handle. |
| Project | Internal control-plane record backing an app. | `project_id` is resolved from `app_id` and should not be hand-entered for normal provisioning. |
| Device | One physical ESP32 hardware unit. | Every device belongs to exactly one `app_id`; provisioning with only `device_id + app_id` is valid. |
| Hardware profile | Board/model class derived from device `board_model`. | Used for inventory, OTA targeting, and board-port documentation. |
| Providers/services | Server runtime defaults plus optional app overrides. | Configure defaults in `Providers`; configure app-scoped overrides in `Apps`. Active-app overrides apply to the running gateway immediately. |
| Purchase/order | Activation-card record for shipped hardware. | Connects `app_id + device_id + plan_id + activation_code + optional customer_wallet`. |
| Customer | C-end hardware owner. | Customer enters through `/customer`, signs with wallet, then binds an activation code. |

| Path | Purpose |
|---|---|
| `/admin` | Operator dashboard with setup checklist, apps, fleet, customers, providers, usage, firmware, services, events, and raw state |
| `/admin/onboarding` | Server-computed setup checklist and next action for closing the app/user/device loop |
| `/admin/capabilities` | Machine-readable framework/userland capability map |
| `/admin/runtime` | Sanitized runtime settings without secret values |
| `/admin/runtime/providers` | Update one ASR, LLM, TTS, chain, or execution provider block |
| `/admin/apps` | App overview with app -> project -> device/order/customer counts |
| `/admin/apps/{app_id}/customers` | App-scoped C-end users and their bound devices |
| `/admin/apps/{app_id}/devices` | App-scoped hardware inventory |
| `/admin/apps/{app_id}/runtime/config` | App-scoped provider/adapter/execution/service config and effective merged runtime |
| `/admin/apps/{app_id}/runtime/providers` | Update one app-scoped ASR, LLM, TTS, chain, or execution provider block |
| `/admin/apps/{app_id}/developer/services` | Register/list app-scoped backend services such as Solana RPC, oracle, data anchor, or proxy wallet |
| `/admin/projects` | Create/list app project records; project is the internal backing record for an app |
| `/admin/devices/register` | Provision hardware by `device_id + app_id`; returns provisioning token plus activation code |
| `/device/register` | Device exchanges provisioning token for a per-device bearer token |
| `/device/config` | Device pulls resolved configuration after registration |
| `/admin/devices/{device_id}/diagnostics` | Support view for one device: control-plane record, config, state, connection, usage, and events |

## Customer Endpoints

`/admin` is the service-owner/operator console. C-end hardware owners should not use it.

| Path | Purpose |
|---|---|
| `/customer` | Customer-facing activation portal for purchased hardware |
| `/customer/login` | Create/reuse a customer account and issue a browser session token |
| `/customer/me` | Verify the customer session token and return the user's bound devices |
| `/customer/demo-purchase` | Local demo checkout: creates a purchase, auto-provisions a device, and returns an activation card |
| `/customer/activate` | Bind an activation code to the logged-in customer |
| `/customer/register` | API-compatible one-step registration/binding flow for scripted setup |

## First Closed Loop

Use this sequence to verify the local service is usable as a hardware-product backend:

1. Open `/admin` and check `Dashboard -> Setup checklist`.
2. Create an app/project in `Apps`, or use the default `ava_box` project.
3. Configure server default providers in `Providers`, or app-owned provider overrides in `Apps`.
4. Create a service plan in `Usage`.
5. Provision hardware in `Fleet Setup` with `device_id + app_id`; copy the `provisioning_token` and `activation_code`.
6. Register the device with `POST /device/register`.
7. Open `/customer`, connect/sign with the hardware buyer wallet, and activate the device with the `activation_code`.
8. Confirm the user appears in `Apps -> App users`, the device appears in `Hardware`, and the order appears in `Orders`.

## Developer 0-1 Smoke Demo

This script creates an app record, app-level provider override, app-level Solana RPC service, service plan, purchase activation card, device registration, and first device messages against an in-process DeviceKit server:

```bash
PYTHONPATH=ava-devicekit/backend \
python3 ava-devicekit/examples/developer_zero_to_one_flow.py
```

## Wallet-Signature Purchase Flow

Production flow:

1. In `/admin`, create the app/project and service plan.
2. Payment or fulfillment backend calls `/admin/purchases` with `device_id`, `app_id`, optional `customer_wallet`, and `plan_id`.
3. `/admin/purchases` creates/reuses the device, provisions it, and returns `provisioning_token + activation_code + activation_card`.
4. Factory/firmware receives the `provisioning_token`; the customer never sees this token.
5. Customer receives the activation card URL/code with the shipped device.
6. Customer opens `/customer`, connects a Solana wallet, signs the challenge, and submits the activation code.
7. The device becomes bound to that wallet-authenticated customer and the plan entitlement is activated.

Local demo flow:

1. Open `/customer`.
2. Click `Demo buy Ava hardware`.
3. The customer page calls `/customer/demo-purchase`, which auto-provisions a demo device and displays the activation code; it does not expose the device provisioning token to the customer.
4. Connect/sign with a wallet. If the demo purchase was wallet-locked, the same wallet must activate it.
5. Submit the activation code. `/admin -> Apps/Hardware/Orders/Customer Support` will show the bound customer/device/order.

| Path | Purpose |
|---|---|
| `POST /admin/purchases` | Record hardware purchase and generate activation card. |
| `GET /admin/purchases` | List purchase/order records. |
| `GET /admin/purchases/{purchase_id}/activation-card` | Re-open the activation card payload. |
| `POST /customer/demo-purchase` | Dev-only checkout demo; disabled in production unless `AVA_DEVICEKIT_ENABLE_DEMO_CHECKOUT=1`. |
| `POST /customer/wallet/challenge` | Create a nonce-bound Solana wallet login challenge. |
| `POST /customer/wallet/login` | Verify the wallet signature and issue a customer session token. |
