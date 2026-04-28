# Getting Started

## Install For Local Development

```bash
cd ava-devicekit
python3 -m pip install -e .[dev,websocket]
```

## Run The Reference App Against DeviceKit

```bash
PYTHONPATH=backend python3 -m ava_devicekit.cli run-http --host 127.0.0.1 --port 8788 --config userland/runtime.example.json
PYTHONPATH=backend python3 -m ava_devicekit.cli run-firmware-ws --host 127.0.0.1 --port 8787 --config userland/runtime.example.json
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

| Path | Purpose |
|---|---|
| `/admin` | Operator dashboard with setup checklist, apps, fleet, customers, providers, usage, firmware, services, events, and raw state |
| `/admin/onboarding` | Server-computed setup checklist and next action for closing the app/user/device loop |
| `/admin/capabilities` | Machine-readable framework/userland capability map |
| `/admin/runtime` | Sanitized runtime settings without secret values |
| `/admin/runtime/providers` | Update one ASR, LLM, TTS, chain, or execution provider block |
| `/admin/apps` | Active app manifest list |
| `/admin/apps/{app_id}/customers` | App-scoped C-end users and their bound devices |
| `/admin/apps/{app_id}/devices` | App-scoped hardware inventory |
| `/admin/projects` | Create/list app project records |
| `/admin/devices/register` | Provision hardware and return provisioning token plus activation code |
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
| `/customer/activate` | Bind an activation code to the logged-in customer |
| `/customer/register` | API-compatible one-step registration/binding flow for scripted setup |

## First Closed Loop

Use this sequence to verify the local service is usable as a hardware-product backend:

1. Open `/admin` and check `Dashboard -> Setup checklist`.
2. Create an app/project in `Apps`, or use the default `ava_box` project.
3. Configure providers in `Providers`; secret values stay in environment variables.
4. Create a service plan in `Usage`.
5. Provision hardware in `Fleet Setup`; copy the `provisioning_token` and `activation_code`.
6. Register the device with `POST /device/register`.
7. Open `/customer`, sign in with the hardware buyer email, and activate the device with the `activation_code`.
8. Confirm the user appears in `Apps -> App users` and the device appears in `Device Detail`.
