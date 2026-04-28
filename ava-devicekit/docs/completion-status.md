# DeviceKit Completion Status

This status file separates framework responsibility from Ava Box reference-app responsibility.

| Area | Layer | Status | Implementation |
|---|---|---|---|
| ASR provider selection | Framework | Complete | Runtime provider registry supports Qwen realtime, OpenAI-compatible transcription, and custom provider classes. |
| ASR audio transport | Framework gateway | Complete for PCM16; OPUS supported through configurable decoder plugin | Existing-firmware WebSocket buffers binary audio, decodes through `AudioDecoder`, calls ASR on `listen:stop`, and routes transcript into app commands. |
| TTS provider selection | Framework | Complete | Runtime provider registry supports mock, OpenAI-compatible speech, AliBL CosyVoice WebSocket TTS, and custom provider classes. |
| TTS device return | Framework gateway | Complete at protocol boundary | Existing-firmware gateway sends text TTS frames and optional base64 audio frames with content type. |
| LLM fallback config | Framework | Complete | OpenAI-compatible and custom LLM providers are runtime selectable; deterministic app routes run before fallback. |
| Live market stream contract | Framework | Complete | `MarketStreamAdapter` + `MarketStreamRuntime`. |
| Chain adapter selection | Framework | Complete | Runtime config can select built-in `solana`/`mock_solana` or a custom `ChainAdapter` class. |
| AVE live WSS | Ava Box/reference | Complete at adapter/runtime boundary | AVE WSS adapter builds subscriptions, parses events, caches snapshots, and can run reconnecting WSS loop. |
| Live price UI updates | Ava Box app | Complete | Ava Box applies price/kline events to current feed or spotlight payload and emits updated screens. |
| Paper execution | Ava Box app | Complete | Local confirmed drafts update paper orders/positions. |
| Custodial/proxy wallet execution | Ava Box app | Complete at provider boundary | AVE proxy-wallet provider submits market/limit orders with HMAC auth after physical device confirmation. |
| Custom trade execution | Ava Box app | Complete at provider boundary | Runtime config can load a custom `TradeExecutionProvider` class for non-AVE execution APIs. |
| Concrete Ava Box UI package | Ava Box app | Complete as reference-app package | Current LVGL screens are copied into `reference_apps/ava_box/ui`; DeviceKit core keeps only generic UI contracts. |
| Admin APIs | Framework | Complete | `/admin`, `/admin/capabilities`, `/admin/runtime`, `/admin/apps`, `/admin/devices`, `/admin/events`, `/admin/providers/health`, `/admin/tasks`, `/admin/ota/firmware`, and `/admin/developer/services` with optional bearer auth. |
| Firmware publish / OTA catalog | Framework | Complete | `ota/publish.py`, `ava-devicekit firmware publish/list`, and `/admin/ota/firmware` manage versioned pull-based OTA binaries. |
| OTA trigger command | Framework + firmware port contract | Complete at framework/template boundary | `/admin/devices/{device_id}/ota-check` queues a `device_command: ota_check`; board template handles it by calling `start_ota_check`. |
| Developer backend service registry | Framework | Complete | `services/registry.py` and `/admin/developer/services` declare proxy wallets, API services, market data, payment services, and order routers without exposing secrets to devices. |
| Developer service invocation boundary | Framework | Complete | `services/client.py` invokes only explicitly allowlisted backend services with `invocable: true` and `allowed_paths`. |
| Explicit ACK protocol | Framework + firmware port contract | Complete at protocol/template boundary | Backend supports ACK; board template extracts `message_id` and ACKs after render/command acceptance. Existing Ava Box remains compatible through legacy auto-ack. |
| Device protocol spec | Framework docs | Complete | `docs/device-protocol.md` defines all current JSON and binary protocol frames. |
| Security hardening | Framework deploy policy | Complete | `production_mode` enforces configured admin/device bearer tokens; docs define allowlist and credential boundaries. |
| Cloud control plane UI | Framework admin UI | Complete first pass | `/admin` is a lightweight developer console with Overview, Control Plane, Runtime Devices, Firmware, Providers, Services, Events, and Raw tabs. |
| Users/projects/devices registry | Framework control plane | Complete MVP | Local JSON-backed control plane bootstraps users/projects, provisions devices, exchanges one-time registration tokens, and validates per-device bearer tokens. |
| C-end customer activation | Framework control plane | Complete MVP | Local customers, activation codes, `/device/activate`, device status changes, suspend/revoke, and per-device config are supported. |
| Web provider configuration | Framework admin UI | Complete MVP | `/admin` can edit ASR, LLM, TTS, chain adapter, and execution provider config by provider/model/base URL/env key/options and apply it to the running gateway. |
| Device diagnostics | Framework admin API | Complete MVP | `/admin/devices/{device_id}/diagnostics` returns control-plane device data, resolved config, runtime state, connection, and recent events. |
| Usage and entitlements | Framework control plane | Complete MVP | Service plans, per-device entitlements, usage reports, admin usage recording, and authenticated device usage reports are supported. |
| Solana AI DePIN app template | Framework reference template | Complete MVP | `examples/apps/solana_ai_depin_device` and `ava-devicekit init-app --type depin` provide a hardware-app template for device identity, heartbeat, proof drafts, and physical confirmation. |
| CLI/package | Framework | Complete first release | `ava-devicekit` CLI supports capabilities, validate, init-app, init-board, init-adapter, init-provider, firmware publish/list, run-http, run-legacy-ws, and run-server. |
| CI | Repo infra | Complete first pass | GitHub Actions workflow compiles, tests, and validates runtime config. |

## Explicit Runtime Assumptions

| Topic | Decision |
|---|---|
| OPUS audio | DeviceKit has an `AudioDecoder` plugin boundary. If firmware sends OPUS, configure `ava_devicekit.providers.asr.audio.OpusLibDecoder` with `opuslib` installed or provide a custom decoder. If firmware sends PCM16, the built-in passthrough decoder is production-ready. |
| Wallet custody | Ava Box uses server-managed proxy/custodial wallets for default real execution. ESP32 confirms intents only; API credentials stay server-side. |
| App-specific UI | Product pages belong to `reference_apps/ava_box/ui`, not framework core. |
| Multi-device sessions | Runtime state is keyed by `X-Ava-Device-Id` or message `device_id`; each device gets an independent app session and event log. |
| Device registration | Production deployments should provision devices through the control plane and store the returned device token on the device. The global device token remains only for compatibility and lab deployments. |
| Provider config editing | The web console stores provider config and env var names, not raw secrets. Actual API keys should remain in environment variables or a secret manager. |
| Usage metering | Current metering records reports from devices or backend/admin calls. Automatic ASR/LLM/TTS provider instrumentation is a later provider-by-provider improvement. |
| C-end operations | The current scope is a self-hosted operator console for one builder serving hardware users. Hosted SaaS, billing, tenant isolation, and developer marketplaces remain outside this milestone. |
| Chain-specific trading | AVE/Solana trade execution belongs to Ava Box app skills, not `ChainAdapter`. |
