# Ava DeviceKit Hardware Service Product Closure

## Product Shape

Ava DeviceKit is not being shaped as a generic SaaS dashboard first. The near-term product is a self-hosted operator console for one builder who sells or distributes AI hardware devices to C-end users and runs the backend service for those devices.

The console must therefore prioritize service operation, not developer-account creation. Developer/team users exist only to operate the service. C-end customers bind purchased devices through activation. Devices authenticate independently and pull their configuration from the service.

## Stakeholders

| Stakeholder | Owns | Uses Console? | Primary Flow |
|---|---|---:|---|
| Service owner / builder | Backend, API keys, firmware, service plans, hardware inventory | Yes | Configure providers, provision devices, ship hardware, monitor cost and health |
| Operator/support | Device support, OTA, diagnostics, customer binding | Yes | Look up customer/device, inspect server timeline, suspend/revoke, push config/OTA |
| C-end hardware customer | A purchased physical device and optional wallet/account identity | Customer portal only | Sign in at `/customer`, activate/bind device, use hardware, receive service/config updates |
| Physical device | Device token, app config, firmware channel, telemetry | No | Register, activate, pull config, report usage/events, receive OTA/commands |

## Correct Account Model

| Account Type | Purpose | Created By | Current Implementation |
|---|---|---|---|
| Operator user | Admin/developer/support identity for running the backend | Service owner | `/admin/users` as team/operator records |
| Customer | C-end hardware owner | Customer portal, one-step API, or operator import | `/customer`, `/customer/login`, `/customer/activate`, `/customer/register`, `/admin/customers` |
| Device identity | Physical unit authentication and configuration target | Operator provisioning + device registration | `/admin/devices/register`, `/device/register` |

The important correction is: customers should not be treated as developers. A customer buys/receives hardware, registers once, then binds it to the service by activation code. Operators may pre-create or import customer records, but that is an operations shortcut, not the core product flow.

## App-Centered Data Model

The product unit is the app. A project is the internal control-plane record that stores app ownership/config metadata; operators should think in `app_id`, not manually in `project_id`.

| Relationship | Rule | Current Behavior |
|---|---|---|
| App -> Project | One app has a backing project record. | Creating an app creates a project/app record; provisioning can also auto-create the backing project from `app_id`. |
| App -> Providers | Apps inherit server default providers. | ASR, LLM, TTS, chain, and execution provider config are server-wide defaults in the MVP. |
| App -> Services | Apps inherit server service registry entries. | Solana RPC, wallet proxy, oracle, payment, data anchor, and custom APIs are registered at backend level. |
| App -> Hardware profiles | Hardware profiles are the board models used by devices under the app. | The console groups profiles from device `board_model`; OTA/profile targeting can build on this. |
| App -> Devices | Every physical unit belongs to one app. | `/admin/devices/register` accepts `device_id + app_id`; `project_id` is resolved internally. |
| App -> Orders | A purchase/activation card is scoped to the app and device. | `/admin/purchases` records `app_id`, `device_id`, `plan_id`, optional wallet lock, and activation URL. |
| App -> Customers | Customers become app users by wallet login plus device activation. | `/admin/apps/{app_id}/customers` shows app users and their bound devices. |

This is the intended operator flow: create/select app -> configure server defaults -> provision app-linked hardware -> create activation card -> customer wallet-signs and activates -> support by app/device/customer.

## End-To-End Flow

| Step | Actor | Console/API | Result |
|---|---|---|---|
| 1 | Service owner | Configure ASR/LLM/TTS/chain/execution providers | Backend can serve AI + Solana hardware actions |
| 2 | Service owner | Create service plans and usage limits | Cost/entitlement rules exist before devices are sold |
| 3 | Checkout/fulfillment or operator | Create purchase/activation card | Backend creates/reuses device, provisions it, assigns app/plan, and returns activation code |
| 4 | Device firmware | Register with provisioning token | Device receives per-device bearer token |
| 5 | Customer | Sign in through `/customer`, then submit activation code | Wallet session is verified, device is bound, and the device becomes active |
| 6 | Device | Pull `/device/config` | Device receives AI name, wake phrases, voice, app, firmware channel, wallet/risk mode |
| 7 | Device/backend | Record usage | ASR/LLM/TTS/API usage is visible by device/customer/period |
| 8 | Operator | Diagnose from server timeline and device diagnostics | Support can inspect backend state, connection, config, and events |
| 9 | Operator | OTA/check/config/status actions | Device stays maintainable after shipment |

## UI Information Architecture

The admin UI should be read as an operator console with these jobs:

| Area | Job | Data Scope |
|---|---|---|
| Overview | Server posture and fleet totals | Server-wide, all devices |
| Dashboard | Setup checklist and next required action | Server-computed app/user/device closure |
| Apps | App/project records, app relationship map, app users, app-scoped logs | App records, customers, devices, purchases, runtime events |
| Fleet Setup | Team operators, provisioning, purchase activation cards | Control-plane records |
| Hardware | App-linked hardware profiles and device inventory | Devices grouped by app/board model |
| Orders | Purchases, wallet locks, plans, activation cards | App/device/customer activation records |
| Customers | Operator import/support view for customer/device binding | Customer/device binding |
| Providers | Runtime ASR/LLM/TTS/chain/execution configuration | Server-wide provider config |
| Usage | Service plans, entitlements, cost/usage counters | Device/customer/service-period |
| Live Sessions | Currently connected runtime sessions | Runtime session state, not complete fleet inventory |
| Firmware | OTA binaries and OTA check command | Firmware catalog + device command |
| Server Timeline | Runtime events across all devices, filterable by device/type | Server-wide event log |
| Raw/Diagnostics | Debug payloads and per-device diagnostics | Support/debug only |

Recent events and the Events tab are server-side runtime event streams. They are not a single-device page unless the operator filters by `device_id`. The UI copy should call them server timeline/events to avoid misunderstanding.

## Dashboard Entry Points

| Operator Question | Dashboard Entry |
|---|---|
| What is the overall state of the service? | `Dashboard` shows server-wide posture, fleet totals, provider status, and recent server timeline. |
| How do I create an app? | `Apps` creates a project/app record and shows CLI app templates such as `init-app --type depin`; code generation remains a CLI/developer workflow. |
| What should I do next? | `Dashboard -> Setup checklist` uses `/admin/onboarding` to show required setup progress and next action. |
| Where does the C-end user enter? | `/customer` is the hardware-owner portal. `Customer Support` remains an operator support/import view. |
| How do I see app users? | `Apps -> App users` shows `/admin/apps/{app_id}/customers` with bound devices. |
| How do I see the full app relationship? | `Apps -> App relationship map` shows app -> project -> devices -> orders -> customers plus provider/service scope. |
| How do I provision hardware for one app? | `Fleet Setup -> Provision device` uses `device_id + app_id`; the backend resolves/creates the backing project. |
| How do I manage purchase activation cards? | `Orders` shows `/admin/purchases` records and re-opens activation-card payloads. |
| How do I demo customer purchase? | `/customer -> Demo checkout` calls `/customer/demo-purchase`, auto-provisions a demo device, and shows the activation code. |

## Purchase / Provision / Activation Binding

Provision and activation are two different trust boundaries:

| Boundary | Holder | Purpose |
|---|---|---|
| `provisioning_token` | Factory/device firmware | Lets the physical device register once and receive its long-lived device token. |
| `activation_code` | Customer/package/activation card | Lets the customer prove they have the purchased hardware package. |
| `customer_wallet` | Customer | Optional wallet lock; if present, only that wallet can activate the code. |
| `device_token` | Device only | Authenticates config pull, events, usage, and OTA after registration. |

`Provision device` already creates an activation code because the backend must know which physical device the customer will bind. The purchase/activation card layer adds the missing business relationship: order reference, app, plan, optional wallet lock, activation URL, and customer-visible instructions.

For a demo checkout, `/customer/demo-purchase` combines these steps:

```text
Customer clicks demo buy
  -> backend creates purchase/order
  -> backend auto-provisions a demo device
  -> backend returns activation card, not the device provisioning token
  -> customer wallet-signs and submits activation code
  -> admin sees order status activated, device customer_id, and app user
```
| How do I inspect one device? | `Device Detail` opens diagnostics for a device id, including owner/customer, config, runtime state, connection, usage, and recent events. |
| How do I see logs for one app? | `Apps -> App logs` filters events by devices assigned to that `app_id`; `Server Timeline` is the global backend log. |
| How do I manage usage limits? | `Usage` creates service plans, assigns entitlements, records usage, and shows limit status by device. |
| How do I update AI/model config? | `Providers` edits ASR/LLM/TTS/chain/execution provider settings without editing files. |

## What Is Complete Now

| Capability | Status |
|---|---|
| Operator/team records | Complete MVP |
| C-end customer records | Complete MVP |
| Customer portal login/session | Complete MVP |
| Customer activation portal | Complete MVP |
| One-step C-end user registration API | Complete MVP |
| App-scoped users/devices | Complete MVP |
| Server-computed onboarding checklist | Complete MVP |
| Device provisioning/registration/activation | Complete MVP |
| Per-device auth and revoke/suspend | Complete MVP |
| Device config pull and web edit | Complete MVP |
| Web-edit provider config | Complete MVP |
| Device diagnostics | Complete MVP |
| Service plans, entitlements, usage counters | Complete MVP |
| OTA publish and OTA check | Complete MVP |

## Later Extensions

| Capability | Reason |
|---|---|
| Passwordless email codes or wallet signature login | The current portal issues local bearer sessions after email login; production deployments can replace this with email OTP, wallet signature, or hosted identity. |
| Payment/billing automation | Service plans and entitlements are enough for manual operation; automated billing can connect through backend services. |
| OTA staged rollout and rollback UI | Important before large fleet rollout. |
| Real Solana device proof program | Needed for full on-chain DePIN proof/reward programs. |

## Wallet-Signature Customer Activation

The C-end portal now uses Solana wallet signatures as the customer login boundary. The user does not create a developer account and does not receive backend credentials.

| Step | Actor | API/UI | Result |
|---|---|---|---|
| 1 | Operator | `/admin` -> Apps | Create the app/project record. |
| 2 | Operator | `/admin` -> Usage | Create or select a service plan. |
| 3 | Operator | `/admin` -> Fleet Setup | Provision the physical device. |
| 4 | Operator | `/admin/purchases` or Fleet Setup purchase form | Record the purchase, optionally lock it to a buyer wallet, assign the plan, and generate the activation card. |
| 5 | Factory/device | `/device/register` | Exchange the provisioning token for a per-device bearer token. |
| 6 | Customer | `/customer` | Connect Solana wallet and sign the login challenge. |
| 7 | Customer | `/customer/activate` | Submit activation code; the device binds to the wallet-authenticated customer. |
| 8 | Operator | `/admin/apps/{app_id}/customers` and `/admin/devices/{device_id}/diagnostics` | Inspect user, device, plan, logs, usage, and support state. |

| Token/code | Holder | Purpose |
|---|---|---|
| `provisioning_token` | Factory/device only | First device registration. |
| `device_token` | Device only | Device auth for config, messages, usage, OTA. |
| `activation_code` | Customer | Proof that the user has the purchased hardware package. |
| Wallet signature | Customer wallet | Login proof; no transaction and no asset movement. |
| `customer_token` | Customer browser | Portal session after signature verification. |

If a purchase is created with `customer_wallet`, activation is restricted to that wallet. This prevents a leaked activation code from being bound by another wallet.
