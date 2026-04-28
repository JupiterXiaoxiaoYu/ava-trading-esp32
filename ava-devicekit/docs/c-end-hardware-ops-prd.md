# Ava DeviceKit C-End Hardware Operations PRD

## Positioning

This document extends the AI DePIN framework PRD from framework/developer infrastructure into the practical operating model for an independent builder who sells or distributes Ava-powered ESP32 devices to C-end users.

The product is not a hosted SaaS for third-party developers yet. The immediate product is a self-hosted hardware service console: one builder can register devices, bind them to customers, configure AI/model providers, push firmware, inspect diagnostics, and keep C-end devices online.

## Core Operating Jobs

| Operator Job | Required Console Capability | Status |
|---|---|---|
| Prepare a new hardware unit | Provision device, generate provisioning token and activation code | Implemented MVP |
| Hand device to a C-end user | Activate device with customer profile or customer id | Implemented MVP |
| Let a C-end user log in | `/customer` portal creates/reuses the customer and stores a customer session token in the browser | Implemented MVP |
| Let a C-end user verify ownership | `/customer/activate` requires a customer session and binds the activation code to that user | Implemented MVP |
| Support scripted registration | Public `/customer/register` flow creates/reuses the customer and can bind an activation code in the same request | Implemented MVP |
| Manage app users | App-scoped customer/device views show which users belong to each hardware app | Implemented MVP |
| Manage device identity | Per-device bearer token, status, revoke/suspend | Implemented MVP |
| Configure AI providers without editing files | Web-edit ASR/LLM/TTS/chain/execution config by env key/model/base URL/options | Implemented MVP |
| Configure a user's device | Web-edit language, AI name, wake phrases, voice, volume, app id, firmware channel, wallet/risk mode | Implemented MVP |
| Diagnose user support issues | Per-device diagnostics endpoint with state, connection, events, config | Implemented MVP |
| Push firmware | Publish bin and queue OTA check | Implemented MVP from previous phase |
| Track service usage/cost | ASR seconds, LLM tokens, TTS chars, API calls per device/customer | Implemented MVP |
| Manage service plans | Free/pro/lifetime/internal entitlement and expiry | Implemented MVP |
| Know the next setup action | Onboarding checklist computes app/provider/plan/device/customer/activation/live-session progress | Implemented MVP |
| Run staged OTA rollouts | Firmware channels, cohorts, rollback, OTA result reporting | Later |
| Submit real Solana DePIN proofs | Device identity registry/proof provider with tx status | Later |

## Entity Model

| Entity | Purpose | Current Fields |
|---|---|---|
| Control-plane user | Admin/developer/operator identity for managing the backend | `user_id`, `username`, `display_name`, `role` |
| Customer | C-end hardware user receiving a physical device | `customer_id`, `email`, `display_name`, `wallet`, `status`, `app_ids`, `project_ids`, hashed customer session token |
| App | Product experience assigned to hardware and customers | `app_id`, app manifest, app-scoped devices/users/orders |
| Project | Internal app backing record, defaulting to Solana | `project_id`, `app_id`, `name`, `chain`, `owner_user_id`, `device_config` |
| Device | Physical ESP32 unit | `device_id`, `project_id`, `customer_id`, `board_model`, `app_id`, `status`, `firmware_version`, `config` |
| Purchase/order | Hardware sale or shipment activation record | `purchase_id`, `order_ref`, `app_id`, `device_id`, `plan_id`, `activation_code`, `customer_wallet` |
| Runtime config | Server-side provider/service configuration | `providers`, `adapters`, `execution`, `services` |
| Firmware | OTA binary artifact | `model`, `version`, `filename`, `size` |

## App Relationship Requirements

| Requirement | Implementation |
|---|---|
| Device belongs to app | Provisioning accepts `device_id + app_id`; the backend stores `device.app_id` and resolves/creates the backing project. |
| Project id is not an operator input | `project_id` remains accepted for compatibility, but normal UI does not expose it for provisioning. |
| Providers/services have clear scope | Provider and service registry entries are shown as `server_default` inherited by apps until per-app overrides are implemented. |
| Hardware is visible by app | Admin Hardware page lists `app_id`, `board_model`, `device_id`, customer, plan, and status. |
| Orders are visible by app | Admin Orders page lists purchase/order records with app, device, wallet lock, activation code, plan, and status. |
| Customers are visible by app | `/admin/apps/{app_id}/customers` returns wallet-authenticated customers and their bound devices. |

## Device Lifecycle

| State | Meaning | Operator Action |
|---|---|---|
| `provisioned` | Device exists in backend and has a one-time provisioning token | Flash firmware, register device, prepare shipment |
| `registered` | Device exchanged provisioning token for per-device bearer token | Ready for activation or internal test |
| `active` | Device is bound to a C-end customer | Normal operating state |
| `online_seen` | Registered/active device recently contacted backend | Support/monitoring state |
| `suspended` | Device temporarily blocked by operator | Customer support, unpaid service, suspected abuse |
| `revoked` | Device tokens are invalidated | Lost/stolen/replaced unit |

## Provider Configuration Requirements

The web console must allow changing runtime provider selection without editing server files. It should configure names and env-key references, not raw secrets.

| Provider | Configurable Fields |
|---|---|
| ASR | provider, model, base URL, API key env, language, sample rate, class path, options JSON |
| LLM | provider, model, base URL, API key env, timeout, class path, options JSON |
| TTS | provider, model, base URL, API key env, voice, format, timeout, class path, options JSON |
| Chain adapter | provider, class path, options JSON |
| Execution | mode/provider, base URL, API key env, secret env, proxy wallet env, class path, options JSON |

Secrets remain in environment variables or an external secret manager. The console stores env var names and non-secret provider options.

## Device Configuration Requirements

| Config | Purpose |
|---|---|
| `language` | Device/AI language preference |
| `ai_name` | Assistant name shown/spoken by the product |
| `wake_phrases` | Wake phrase hints and ASR context phrases |
| `tts_voice` | Voice choice for the user/device |
| `volume` | Default device volume |
| `app_id` | Active hardware app on the device |
| `firmware_channel` | OTA channel such as stable/beta/dev |
| `wallet_mode` | proxy/external/paper wallet mode |
| `risk_mode` | confirmation and high-risk action policy |

Configuration is resolved as default config -> project config -> device override. The current MVP implements default plus device override, and leaves richer project-level editing for the next phase.

## API Additions

| Method | Path | Purpose |
|---|---|---|
| `GET/POST` | `/admin/runtime/config` | View or update persisted runtime provider/service config and apply it to the running process |
| `POST` | `/admin/runtime/providers` | Update one provider block from the console |
| `GET/POST` | `/admin/customers` | List or create C-end customers |
| `GET` | `/customer` | Customer-facing hardware activation portal |
| `POST` | `/customer/login` | Create/reuse a customer account and issue a customer bearer token |
| `GET` | `/customer/me` | Verify customer token and return the user's devices |
| `POST` | `/customer/activate` | Bind an activation code to the logged-in customer |
| `POST` | `/customer/register` | C-end user registration; creates/reuses customer and optionally binds an activation code |
| `GET` | `/admin/apps` | App overview with project/device/order/customer counts and provider/service scope |
| `GET` | `/admin/apps/{app_id}/customers` | App-scoped user list with bound devices |
| `GET` | `/admin/apps/{app_id}/devices` | App-scoped hardware list |
| `GET` | `/admin/onboarding` | Server-side setup checklist and next required action for closing the app/user/device loop |
| `GET/POST` | `/admin/service-plans` | List or create service plans and usage limits |
| `GET/POST` | `/admin/usage` | View usage reports or record usage for a device |
| `POST` | `/device/activate` | Bind a provisioned device to a customer using activation code |
| `GET/POST` | `/admin/devices/{device_id}/config` | View or update device-level config |
| `POST` | `/admin/devices/{device_id}/status` | Set device status, including suspend/revoke |
| `POST` | `/admin/devices/{device_id}/entitlement` | Assign a service plan and status to a device |
| `GET` | `/admin/devices/{device_id}/diagnostics` | View device state, connection, config, and recent events |
| `GET` | `/device/config` | Device pulls its resolved configuration |
| `POST` | `/device/usage` | Device reports usage with its bearer token |
| `GET/POST` | `/admin/purchases` | List/create app-scoped purchase activation cards |
| `GET` | `/admin/purchases/{purchase_id}/activation-card` | Re-open the customer activation payload |

## Remaining Later Work

| Area | Why It Matters |
|---|---|
| Payment/billing automation | Manual plans and entitlements are implemented; payment collection can be connected through the service registry. |
| OTA rollout cohorts | Reduces risk when pushing firmware to C-end devices. |
| OTA result reporting | Operator must know whether C-end devices updated successfully. |
| Production identity provider | The portal currently uses local customer bearer tokens; email OTP, wallet signature, or an external identity provider can replace the login boundary. |
| Real Solana proof provider | Required to move from Solana-ready hardware framework to complete on-chain DePIN proof flow. |

## Purchase And Wallet Login MVP

| Capability | Implementation |
|---|---|
| Purchase/order record | `POST /admin/purchases` creates a purchase record for a device, app, plan, order reference, buyer wallet/email, and amount label. |
| Activation card | Purchase creation returns `activation_card` with `activation_code`, activation URL, QR payload, and printable instructions. |
| Wallet challenge | `POST /customer/wallet/challenge` returns a nonce-bound Solana sign-in message valid for 5 minutes. |
| Wallet login | `POST /customer/wallet/login` verifies the Ed25519 signature, creates/reuses the customer, and returns a customer bearer token. |
| Wallet-locked activation | If the purchase has `customer_wallet`, `/customer/activate` only succeeds for a customer logged in with that wallet. |
| Plan activation | A purchase can assign `plan_id`; after successful activation the device entitlement becomes active. |
| Demo checkout | `POST /customer/demo-purchase` is a local demo path that creates a purchase, auto-provisions a demo device, and returns the activation card directly to the customer page without exposing the provisioning token. |

The production identity boundary is wallet signature first. Email remains optional metadata and support fallback, not the primary proof of customer ownership.

## Customer Purchase Demo Requirement

The customer portal must show the hardware ownership loop, not only the final activation form.

| UI Step | Backend Action | Admin Visibility |
|---|---|---|
| Customer clicks `Demo buy Ava hardware` | `/customer/demo-purchase` calls the same purchase/provision path used by operator fulfillment | `Orders` shows the purchase; `Hardware` shows the provisioned device |
| Customer optionally wallet-locks the purchase | Purchase stores `customer_wallet` | `Orders` shows wallet lock |
| Customer receives activation code on page | Activation card includes URL/code and app/device id | `Orders -> Card` can re-open the same payload |
| Customer connects/signs wallet | `/customer/wallet/challenge` + `/customer/wallet/login` creates/reuses customer | `Customer Support` shows customer |
| Customer submits activation code | `/customer/activate` binds device to customer and activates plan | `Apps -> App users`, `Hardware`, and `Orders` show the activated relationship |

Production deployments should replace the demo checkout with a real payment/fulfillment call into `/admin/purchases` or an allowlisted service webhook. The customer-visible activation model stays the same.
