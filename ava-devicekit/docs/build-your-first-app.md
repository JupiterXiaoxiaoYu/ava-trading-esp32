# Build Your First Hardware App

Create a starter app:

```bash
cd /path/to/ava-trading-esp32
PYTHONPATH=ava-devicekit/backend \
python3 -m ava_devicekit.cli init-app ./my-devicekit-app --type depin
```

The generated directory contains:

| File | You Own |
|---|---|
| `manifest.json` | App id, chain, screen list, adapter names, firmware targets |
| `app.py` | App routing, deterministic actions, app-specific skills |
| `runtime.example.json` | Deployment ports, URLs, ASR/LLM/TTS providers |

A hardware app receives `DeviceMessage` values and returns one of: `ScreenPayload`, `ActionDraft`, or `ActionResult`. Use deterministic routes for known actions and reserve LLM fallback for open-ended answers.

Keep these concerns separate:

| Concern | Put It In |
|---|---|
| Generic chain feed/search/detail | `ChainAdapter` |
| Product actions like trading/payment/watchlist | App skill package |
| Physical confirmation requirements | `ActionDraft` + app confirmation handler |
| Board buttons, joystick, touch, microphone | Board port |
| Screen rendering | App UI layer consuming screen payloads |

## Add A Custom Page

| Step | Output |
|---|---|
| Declare page | Add the page id to `manifest.json.screens`. |
| Declare contract | Add a `screen_contracts[]` entry with payload schema, context schema, and accepted actions. |
| Render page | Register an `ava_dk_screen_vtable_t` with `ava_dk_ui_register_custom_screen()`. |
| Expose AI context | Implement `selection_context_json()` and return a `ContextSnapshot` with `screen`, `cursor`, `selected`, `visible_rows`, and useful `page_data`. |
| Handle input | Emit `input_event` for joystick/touch/encoder/buttons, or emit direct `key_action` for fixed semantic actions. |
| Route backend | In `HardwareApp.handle()`, route `input_event.semantic_action` and `listen_detect` using the normalized context. |

The important rule is that the device must send the current page snapshot with
voice and meaningful input. That is what allows AI to answer questions about the
current page and lets deterministic actions avoid stale server-side selection.

## 0 To 1 Local Closed Loop

Run the framework-owned server, then configure the app from the dashboard:

```bash
cp ava-devicekit/userland/env.example ava-devicekit/.env.local
./scripts/run-devicekit-local.sh
```

| Step | Where | Result |
|---|---|---|
| 1. Create app record | `/admin -> Apps` | A stable `app_id` that devices, users, providers, and services attach to. |
| 2. Configure app providers | `/admin -> Apps -> App provider overrides` | App-level ASR/LLM/TTS/chain/execution config; active app overrides apply immediately. |
| 3. Configure app services | `/admin -> Apps -> App backend service` | App-level Solana RPC, Solana Pay, oracle, reward, data anchor, gasless tx, device ingest, wallet, or custom service entries. |
| 4. Create service plan | `/admin -> Usage` | Entitlement model for C-end hardware owners. |
| 5. Provision / sell hardware | `/admin -> Fleet Setup` or `/customer` demo buy | Device record, provisioning token, purchase record, and activation card. |
| 6. Register firmware | `POST /device/register` | Device exchanges factory provisioning token for a per-device bearer token. |
| 7. Customer activates | `/customer` | Wallet-signature customer binds the activation code to their device. |
| 8. Operate | `/admin -> Device Detail / Events / Firmware` | Logs, usage, provider health, and OTA are visible from the control plane. |

Smoke-test the same loop without a browser:

```bash
PYTHONPATH=ava-devicekit/backend \
python3 ava-devicekit/examples/developer_zero_to_one_flow.py
```

Expected output includes `app_provider_applied: true`, `device_registered: true`, and the first device screens.
