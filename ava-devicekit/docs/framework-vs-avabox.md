# Framework vs Ava Box App Boundary

DeviceKit is the reusable framework. Ava Box is the first reference app built on it. The implementation must keep product logic out of framework core so the same runtime can support trading terminals, payment devices, alert boxes, sensors, approval pads, and other ESP32 hardware apps.

| Capability | Layer | Implemented In | Notes |
|---|---|---|---|
| ASR provider contract and runtime wiring | Framework | `providers/asr`, `providers/registry.py`, `runtime/settings.py` | Qwen realtime and OpenAI-compatible ASR providers are selectable. The gateway buffers binary audio, decodes through `AudioDecoder`, and routes ASR transcript into app commands. |
| TTS provider contract and OpenAI-compatible TTS | Framework | `providers/tts` | Mock remains available for tests; real HTTP/WebSocket TTS is config-driven, including OpenAI-compatible speech and AliBL CosyVoice. |
| LLM fallback production config | Framework | `providers/llm`, `providers/registry.py`, `providers/pipeline.py` | Deterministic app routing happens before LLM fallback. |
| Generic gateway, admin, OTA, app session | Framework | `gateway`, `ota`, `runtime` | `/admin/*` endpoints expose capabilities, sanitized runtime, and app manifests. |
| CLI, package, templates, docs | Framework | `cli.py`, `pyproject.toml`, `userland`, `docs` | Used by app developers and board-port developers. |
| Chain data adapter interface | Framework | `adapters/base.py`, `adapters/registry.py` | Limited to feed, search, token detail; custom adapter classes can be selected in runtime config. |
| AVE-backed Solana data adapter | Reference adapter | `adapters/solana.py` | Swappable implementation of the generic chain adapter. |
| Live AVE market WSS | Ava Box/reference integration | `streams/ave_data_wss.py` | Kept out of core app/session contracts; runtime can subscribe, cache, and apply price/kline events to Ava Box screens. |
| Watchlist, portfolio, trading skills | Ava Box app | `apps/ava_box_skills` | Product behavior owned by Ava Box, not DeviceKit core. |
| Real wallet/trade transaction construction | Ava Box app | `apps/ava_box_skills/execution.py` | ESP32 is the physical confirmation surface; Ava Box can use server-managed proxy/custodial wallets or any custom `TradeExecutionProvider`, with credentials and signing kept server-side. |
| Ava Box LVGL screens | Ava Box app/UI userland | `shared_ui/screens` contracts plus app screen C files | Framework owns portable screen contracts; product screens render product payloads. |
| Scratch Arcade buttons/joystick | Reference board port | `firmware/ports/scratch_arcade` | Core firmware runtime does not mandate input hardware. |
| Dashboard/app builder | Framework dashboard surface | `gateway/http_server.py`, `gateway/admin_page.py` | Admin APIs and the local dashboard expose app setup, provider config, fleet status, usage, firmware, and developer services. |

## Development Rule

If a feature mentions a token, trade, watchlist, portfolio, AVE, or Solana-specific execution flow, it belongs in an app, adapter, or execution provider. If a feature describes message transport, provider lifecycle, manifest loading, screen payload contracts, runtime config, OTA, or board-port boundaries, it belongs in DeviceKit framework.
