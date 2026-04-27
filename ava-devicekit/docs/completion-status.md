# DeviceKit Completion Status

This status file separates framework responsibility from Ava Box reference-app responsibility.

| Area | Layer | Status | Implementation |
|---|---|---|---|
| ASR provider selection | Framework | Complete | Runtime provider registry supports Qwen realtime, OpenAI-compatible transcription, and custom provider classes. |
| ASR audio transport | Framework gateway | Complete for PCM16; OPUS supported through configurable decoder plugin | Existing-firmware WebSocket buffers binary audio, decodes through `AudioDecoder`, calls ASR on `listen:stop`, and routes transcript into app commands. |
| TTS provider selection | Framework | Complete | Runtime provider registry supports mock, OpenAI-compatible speech, and custom provider classes. |
| TTS device return | Framework gateway | Complete at protocol boundary | Existing-firmware gateway sends text TTS frames and optional base64 audio frames with content type. |
| LLM fallback config | Framework | Complete | OpenAI-compatible and custom LLM providers are runtime selectable; deterministic app routes run before fallback. |
| Live market stream contract | Framework | Complete | `MarketStreamAdapter` + `MarketStreamRuntime`. |
| AVE live WSS | Ava Box/reference | Complete at adapter/runtime boundary | AVE WSS adapter builds subscriptions, parses events, caches snapshots, and can run reconnecting WSS loop. |
| Live price UI updates | Ava Box app | Complete | Ava Box applies price/kline events to current feed or spotlight payload and emits updated screens. |
| Paper execution | Ava Box app | Complete | Local confirmed drafts update paper orders/positions. |
| Custodial/proxy wallet execution | Ava Box app | Complete at provider boundary | AVE proxy-wallet provider submits market/limit orders with HMAC auth after physical device confirmation. |
| Concrete Ava Box UI package | Ava Box app | Complete as reference-app package | Current LVGL screens are copied into `reference_apps/ava_box/ui`; DeviceKit core keeps only generic UI contracts. |
| Admin APIs | Framework | Complete | `/admin`, `/admin/capabilities`, `/admin/runtime`, `/admin/apps`, `/admin/devices`, `/admin/events` with optional bearer auth. |
| CLI/package | Framework | Complete first release | `ava-devicekit` CLI supports capabilities, validate, init-app, init-board, run-http, and run-legacy-ws. |
| CI | Repo infra | Complete first pass | GitHub Actions workflow compiles, tests, and validates runtime config. |

## Explicit Runtime Assumptions

| Topic | Decision |
|---|---|
| OPUS audio | DeviceKit has an `AudioDecoder` plugin boundary. If firmware sends OPUS, configure `ava_devicekit.providers.asr.audio.OpusLibDecoder` with `opuslib` installed or provide a custom decoder. If firmware sends PCM16, the built-in passthrough decoder is production-ready. |
| Wallet custody | Ava Box uses server-managed proxy/custodial wallets for default real execution. ESP32 confirms intents only; API credentials stay server-side. |
| App-specific UI | Product pages belong to `reference_apps/ava_box/ui`, not framework core. |
| Multi-device sessions | Runtime state is keyed by `X-Ava-Device-Id` or message `device_id`; each device gets an independent app session and event log. |
| Chain-specific trading | AVE/Solana trade execution belongs to Ava Box app skills, not `ChainAdapter`. |
