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

## End-To-End Flow

| Step | Actor | Console/API | Result |
|---|---|---|---|
| 1 | Service owner | Configure ASR/LLM/TTS/chain/execution providers | Backend can serve AI + Solana hardware actions |
| 2 | Service owner | Create service plans and usage limits | Cost/entitlement rules exist before devices are sold |
| 3 | Operator | Provision device | Device id, provisioning token, activation code are created |
| 4 | Device firmware | Register with provisioning token | Device receives per-device bearer token |
| 5 | Customer | Sign in through `/customer`, then submit activation code | Customer session is verified, device is bound, and the device becomes active |
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
| Apps | App/project records, app users, app-scoped logs | App records, customers, devices, runtime events |
| Fleet Setup | Team operators, provisioning, device inventory | Control-plane records |
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
