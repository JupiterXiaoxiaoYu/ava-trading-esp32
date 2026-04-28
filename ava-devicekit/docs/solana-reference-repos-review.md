# Solana Reference Repositories Review

This note records which Solana hardware, DePIN, payment, and embedded SDK repositories are useful for Ava DeviceKit. The intent is not to copy these projects into framework core. The intent is to map proven patterns into DeviceKit docs, templates, optional dependencies, and service types.

## Review Scope

| Source | Role In Review |
|---|---|
| https://github.com/SkyRizzAI/esp-solana | Rust/no_std Solana SDK for ESP32 signing, wallet, transaction, and RPC patterns |
| https://github.com/SkyRizzAI/Qeychain | ESP32-S3 + OLED + secure element hardware profile reference |
| https://github.com/hogyzen12/unruggable-rust-esp32 | Physical-confirmation ESP32 Solana hardware signer pattern |
| https://github.com/Mantistc/esp32-ssd1306-solana | Rust ESP32 + SSD1306 + Solana data display reference |
| https://github.com/solana-developers/solana-depin-examples | Collection of Solana DePIN / IoT examples and linked projects |
| https://github.com/torrey-xyz/solduino | Arduino/ESP32 Solana SDK reference |
| https://github.com/Woody4618/bar | Solana Pay physical payment / product dispenser reference |
| https://github.com/Woody4618/depin-reward-distributor | Device identity + oracle + reward claim reference |
| https://github.com/Woody4618/talking-fish | On-chain event listener -> TTS -> physical actuator reference |
| https://github.com/priyanshpatel18/aeroscan-esp32 | ESP32 WSS telemetry + HTTP fallback + heartbeat reference |
| https://github.com/priyanshpatel18/aeroscan-ws | Realtime device ingest backend reference |
| https://github.com/priyanshpatel18/aeroscan | Sensor dashboard + Solana/MagicBlock app reference |

## High-Level Findings

| Area | Finding | DeviceKit Decision |
|---|---|---|
| ESP32 Solana signing | `esp-solana`, `solduino`, and `unruggable-rust-esp32` prove Solana signing/RPC can run on constrained hardware. | Keep as optional board/app templates. Do not make on-device custody a framework default. |
| Device identity | DePIN examples often use a device Ed25519 key, oracle verification, and reward claims. | Add first-class DeviceKit capability and templates for device identity, signed readings, oracle reward claim, and optional on-chain registry. |
| Physical confirmation | Hardware signer and payment examples require a user to physically approve high-risk actions. | Keep `ActionDraft` + confirm screen as the mandatory framework pattern for high-risk actions. |
| Transport resilience | `aeroscan-esp32` uses WebSocket, reconnect, heartbeat, and HTTP fallback. | Add this to board-port docs/templates as the recommended transport model. |
| Solana Pay / PayFi | `bar`, `led-switch`, `solana-bar`, and `helium-lorawan-chest` demonstrate transaction requests controlling physical outcomes. | Expand payment-terminal templates and `solana_pay` service type. |
| Data anchoring | `termina-data-anchor` demonstrates batch data anchoring and verification. | Add `data_anchor` service type and keep implementation provider-specific. |
| Secure hardware | Qeychain demonstrates ESP32-S3 + OLED + secure element + buzzer/LED feedback. | Add optional secure-element hardware profile. Do not require it for every board. |

## Repository-by-Repository Mapping

| Repo | Useful Architecture Value | License / Risk | What To Introduce Into DeviceKit |
|---|---|---|---|
| `SkyRizzAI/esp-solana` | Compact Rust/no_std Solana wallet, signing, transaction, and bring-your-own-RPC client model. | `Cargo.toml` declares MIT, but no root LICENSE file was present in the local shallow clone. Confirm before vendoring. | Optional Rust board-port dependency and signer app note. Keep out of default C/ESP-IDF firmware. |
| `torrey-xyz/solduino` | Arduino/ESP32 Solana SDK with RPC, wallet, signing, serialization, HTTPS, and Arduino/PlatformIO compatibility. | Apache-2.0 LICENSE present. | Optional Arduino board-port example and dependency note. |
| `SkyRizzAI/Qeychain` | Strong hardware reference: ESP32-S3, OLED, secure element, buttons, RGB LED, buzzer, USB-C, exposed GPIO. | No root LICENSE found. Treat as architecture reference only. | `secure_element_profile.md`, board profile guidance, physical confirmation UX ideas. |
| `hogyzen12/unruggable-rust-esp32` | ESP32 signing protocol: public key query, base64 transaction/message review, button-confirmed signature return. | README says MIT, but no root LICENSE found in shallow clone. Do not copy code without confirmation. | `hardware_signer_approval` app template and signer protocol sketch. |
| `Mantistc/esp32-ssd1306-solana` | Rust ESP32 + SSD1306 + Solana data display; useful for small-display data rendering. | No root LICENSE found. Reference only. | Small-display app notes; no dependency in core. |
| `solana-developers/solana-depin-examples` | Curated patterns: rewards, payment devices, LED control, data anchor, memo listener, sensor-to-chain. | Mixed; inspect each linked project before code reuse. | Product template catalog and narrative validation for Solana physical devices. |
| `Woody4618/bar` | Solana Pay transaction request + physical product fulfillment + gasless/payment app direction. | No root LICENSE found. Reference patterns only. | Strengthen `payment_terminal` with Solana Pay request, QR, payment status, physical action result. |
| `Woody4618/depin-reward-distributor` | Device key -> oracle -> reward claim -> Anchor verification pattern. | No root LICENSE found. Reference architecture only. | Add `depin_reward_device` template, `oracle` and `reward_distributor` service kinds. |
| `Woody4618/talking-fish` | On-chain memo/event listener triggers speech and physical actuation. | No root LICENSE found. Reference architecture only. | Add `onchain_event_listener` template and event-listener service guidance. |
| `priyanshpatel18/aeroscan-esp32` | ESP32 WSS telemetry, reconnect interval, heartbeat, token auth, HTTP fallback. | MIT LICENSE present. | Board-port transport docs/templates for WSS + HTTP fallback and heartbeat. |
| `priyanshpatel18/aeroscan-ws` | Realtime device ingest, auth token, WebSocket clients, HTTP fallback endpoint, database, chain integration. | MIT LICENSE present. | `device_ingest` service kind and backend ingest design pattern. |
| `termina-data-anchor` in collection | Blob upload/fetch/verify flow for batched sensor/reward data. | Collection-specific; confirm exact module licenses before integration. | `data_anchor` service kind and provider adapter. |

## Optional Dependency Policy

| Dependency | Where It Belongs | Why Not Framework Core |
|---|---|---|
| `esp-solana` | Rust board-port or hardware-signer reference app | DeviceKit core is C/Python and chain/hardware agnostic; on-device Solana signing is optional. |
| `solduino` | Arduino/PlatformIO board-port example | Useful for Arduino developers, but not all DeviceKit firmware targets use Arduino. |
| `ArduinoJson` | Arduino transport template | JSON encoding helper for Arduino examples only. |
| `links2004/WebSockets` | Arduino WSS template | Transport implementation detail; framework protocol remains generic JSON/binary frames. |
| DHT/MQ135 sensor libraries | `sensor_oracle_device` template | Sensor-specific dependencies should not pollute core. |
| `@solana/pay` | Payment web/backend template | Payment request generation is app/service layer, not core gateway. |
| `@solana/web3.js` | Solana service/template | Useful for JS sidecars; Python DeviceKit backend should call services through `developer_services`. |
| `@coral-xyz/anchor` | Anchor program examples/templates | On-chain program framework is app-specific. |
| `@solana/kora` | Gasless/payment service template | Gasless execution is an optional developer service. |

## DeviceKit Changes Made From This Review

| Change | Location |
|---|---|
| Reference review document | `docs/solana-reference-repos-review.md` |
| New capability map entries | `userland/capabilities.json` |
| DePIN reward template | `examples/apps/depin_reward_device/` |
| Sensor oracle template | `examples/apps/sensor_oracle_device/` |
| On-chain event listener template | `examples/apps/onchain_event_listener/` |
| Hardware signer approval template | `examples/apps/hardware_signer_approval/` |
| Board-port WSS/HTTP fallback and heartbeat notes | `userland/hardware_port/` |
| Optional secure-element profile | `userland/hardware_port/secure_element_profile.md` |
| Standardized service kinds | `backend/ava_devicekit/services/registry.py` |

## Implementation Rules

1. Keep DeviceKit core hardware-agnostic and chain-adapter based.
2. Keep Solana signing libraries optional and template-scoped.
3. Keep user asset custody outside ESP32 by default.
4. Use device identity keys for device proof and reward flows, not as user wallet keys.
5. Require `ActionDraft` and physical confirmation for payment, trade, registration, reward claim, and signer approval flows.
6. Require WSS heartbeat, reconnect, and HTTP fallback in production board ports.
7. Do not copy code from projects that do not have a clear compatible license; use them as architecture references only.
