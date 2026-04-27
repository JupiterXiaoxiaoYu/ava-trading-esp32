# Legacy Assistant Capability Inventory

This document is the review checklist before migrating more legacy runtime code into Ava DeviceKit. Nothing in `ava-devicekit/` should depend on legacy assistant modules directly; each capability must be explicitly marked as `keep`, `replace`, `drop`, or `later` before implementation.

## Decision Labels

| Label | Meaning |
|---|---|
| `keep` | Keep the capability and reimplement/extract it behind a DeviceKit interface |
| `replace` | Keep the product behavior but replace the legacy assistant implementation shape |
| `drop` | Do not migrate into DeviceKit |
| `later` | Do not migrate for v1; document as an optional adapter/module |
| `confirm` | Needs owner confirmation before implementation |

## Firmware / Device Runtime

| Capability | Legacy source | Proposed decision | DeviceKit target | Notes to confirm |
|---|---|---|---|---|
| Wi-Fi provisioning / settings | `firmware/main/settings.*`, board Wi-Fi flow | `keep` | `firmware/provisioning` | Confirm whether captive portal / web config is required in v1 |
| WebSocket transport | `firmware/main/protocols/websocket_protocol.*`, `ave_transport_idf.cc` | `replace` | `TransportAdapter` + `DeviceMessage` JSON | Keep behavior, replace message contract with DeviceKit protocol |
| MQTT/UDP transport | `firmware/main/protocols/mqtt_protocol.*` | `confirm` | optional transport adapter | Only keep if target deployments need MQTT/UDP |
| OTA update | `firmware/main/ota.*`, server OTA handler | `keep` | `firmware/ota` + backend OTA endpoint | Confirm OTA source: own server, static files, or GitHub releases |
| Board abstraction | `firmware/main/boards/*` | `keep` | `firmware/boards` | Keep Scratch Arcade first; avoid importing all board ports into clean repo |
| Display abstraction | `firmware/main/display/*` | `keep` | `shared_ui` + board display driver | Keep LCD/LVGL integration, not old screen-manager API |
| Audio codec / audio service | `firmware/main/audio/*` | `keep` | `firmware/audio` | Needed for wake/PTT, ASR streaming, and TTS playback |
| Wake word / PTT | `firmware/main/audio/wake_word.h`, app state | `replace` | `AudioInputAdapter` + `DeviceMessage.listen_detect` | Confirm wake words and whether always-on wake is v1 |
| Device state machine | `firmware/main/device_state_machine.*` | `replace` | `DeviceRuntimeState` | Keep states, simplify names around app/device/session |
| MCP server on device | `firmware/main/mcp_server.*` | `later` | optional helper adapter | Not core for Ava Box framework v1 |
| LED/emote display | `firmware/main/led/*`, `display/emote_display.*` | `later` | optional output adapter | Useful for robots/watch devices, not core for Scratch Arcade v1 |

## Backend Runtime

| Capability | Legacy source | Proposed decision | DeviceKit target | Notes to confirm |
|---|---|---|---|---|
| WebSocket server | `legacy server WebSocket implementation` | `replace` | `gateway/websocket_server.py` | Keep transport role, replace connection/tool lifecycle |
| Connection/session lifecycle | `core/connection.py` | `replace` | `DeviceSession`, `AppContext`, `ConfirmationState` | No direct dependency on `ConnectionHandler` |
| HTTP server / REST endpoints | `core/http_server.py`, `core/api/*` | `confirm` | `gateway/http_server.py` | Need confirmation: include dashboard/debug REST in v1 or keep websocket-only |
| OTA handler | `core/api/ota_handler.py` | `keep` | `gateway/ota` | Pair with firmware OTA decision |
| Vision handler | `core/api/vision_handler.py` | `drop` | none | Not needed for current ESP32-S3 + 320x240 Ava Box path |
| Auth | `core/auth.py`, `core/utils/auth.py` | `confirm` | `AuthAdapter` | Confirm whether v1 needs device token auth or signed device identity |
| Ping/keepalive | `textHandler/pingMessageHandler.py` | `keep` | `DeviceSession.heartbeat` | Required for online status and reconnect |
| Report/listen/hello messages | `helloHandle.py`, `reportHandle.py`, `listenMessageHandler.py` | `replace` | `DeviceMessage` variants | Keep semantics, replace protocol shape |
| Abort handling | `abortHandle.py`, `abortMessageHandler.py` | `keep` | `DeviceMessage.cancel` / stream abort | Required for voice interruption and cancel |
| Key action handling | `keyActionHandler.py` | `replace` | `AvaBoxApp.handle(DeviceMessage)` | Already started in clean app routing |
| Trade action handling | `tradeActionHandler.py` | `replace` | `ActionDraft` / `ActionResult` | Keep physical confirmation and result flow |
| Context provider | `core/utils/context_provider.py` | `replace` | `AppContext` + screen selection context | Must preserve current screen/cursor/selected token |
| Prompt manager | `core/utils/prompt_manager.py` | `replace` | app manifest + model routing policy | Do not keep legacy assistant config shape |

## AI / Model Provider Stack

| Capability | Legacy source | Proposed decision | DeviceKit target | Notes to confirm |
|---|---|---|---|---|
| ASR provider abstraction | `core/providers/asr/*` | `keep` | `ModelAdapter.asr` | Keep provider idea; extract only used providers first |
| Qwen3 ASR realtime | `core/providers/asr/qwen3_asr_flash_realtime.py` | `keep` | `providers/asr/qwen3_realtime` | Current desired ASR path; confirm env var naming |
| LLM provider abstraction | `core/providers/llm/*` | `keep` | `ModelAdapter.llm` | Keep OpenAI-compatible base first, add others later |
| TTS provider abstraction | `core/providers/tts/*` | `keep` | `ModelAdapter.tts` | Keep streaming TTS if needed by hardware reply |
| VAD | `core/providers/vad/*` | `keep` | `AudioInputAdapter.vad` | Needed for sensitivity and turn detection |
| VLLM | `core/providers/vllm/*` | `later` | optional local/vision model adapter | Not core unless local model path is required |
| Memory providers | `core/providers/memory/*` | `later` | optional context memory adapter | Do not block v1 framework |
| Voiceprint | `core/utils/voiceprint_provider.py` | `later` | optional auth adapter | Previously unconfigured; not v1 core |
| Wakeup word utils | `core/utils/wakeup_word.py` | `replace` | app/model config wake policy | Keep behavior, not config shape |

## Backend Function / Tool System

| Capability | Legacy source | Proposed decision | DeviceKit target | Notes to confirm |
|---|---|---|---|---|
| `plugins_func` registration | `plugins_func/register.py`, registered tool descriptors | `drop` | none | Replace with app actions and adapters |
| Ava market behavior | older market tool implementation | `replace` | `SolanaAdapter` for basic chain data; `AvaBoxSkillService` / `apps/ava_box_skills/` for app trading/watchlist/portfolio | Keep framework adapter thin; app owns server skill behavior |
| Wallet skill tools | `ave_skill_tools.py` | `replace` | `WalletAdapter` / `PortfolioProvider` | Keep wallet capability, replace tool shape |
| Paper store | `ave_paper_store.py` | `keep` | `storage/paper_store.py` | Useful for safe demos and hackathon flow |
| Watchlist store | `ave_watchlist_store.py` | `keep` | `storage/watchlist_store.py` | Keep local JSON store first |
| Trade manager | `ave_trade_mgr.py` | `replace` | `AvaBoxSkillService` / `apps/ava_box_skills/` + future app-level execution provider | Keep draft/confirm/result semantics outside the base chain adapter |
| AVE WSS market stream | `ave_wss.py` | `confirm` | `MarketStreamAdapter` | Needed if live price/kline updates remain in v1 |
| MCP endpoint / server tools | `core/providers/tools/*mcp*` | `later` | optional helper adapter | Not core for hardware framework v1 |
| IoT tools | `core/providers/tools/device_iot` | `later` | optional device helper adapter | Useful for robots/sensors later |
| Custom functions | server plugins/tools | `replace` | `HelperAdapter` | Keep extensibility, not plugin registration shape |

## Admin / Dashboard / Management

| Capability | Legacy source | Proposed decision | DeviceKit target | Notes to confirm |
|---|---|---|---|---|
| Manager API | `server/main/manager-api` | `confirm` | optional `dashboard_api` | Decide whether DeviceKit needs built-in management backend |
| Manager Web | `server/main/manager-web` | `confirm` | optional web dashboard | Could be useful for app creation/model config demo |
| Manager Mobile | `server/main/manager-mobile` | `drop` | none | Not needed for ESP32 framework v1 unless explicitly requested |
| Config YAML | `legacy-server/config.yaml` | `replace` | app manifest + deployment env | Do not expose legacy config shape as framework API |
| `.env` model/API config | `legacy-server/.env` | `keep` | deployment env | Keep env-driven secrets, rename around DeviceKit |
| Docker compose | server docker files | `later` | deployment template | Current preference has been tmux/server; container can come later |

## Shared UI / Simulator

| Capability | Legacy source | Proposed decision | DeviceKit target | Notes to confirm |
|---|---|---|---|---|
| LVGL feed/spotlight/etc pages | `shared/ave_screens/screen_*.c` | `keep` | `shared_ui` screen vtables | Wrap pages behind `ava_dk_screen_vtable_t` |
| Legacy screen manager | `ave_screen_manager.*` | `replace` | `ava_devicekit_ui.*` | New public API already added |
| JSON helpers | `ave_json_utils.*` | `keep` | `shared_ui/json` | Keep small C helpers, rename to DeviceKit |
| Font provider | `ave_font_provider.*` | `keep` | `shared_ui/font_provider` | Needed for simulator/hardware visual consistency |
| Price formatting | `ave_price_fmt.*` | `keep` | app/reference UI helper | Useful for Ava Box, not core framework API |
| Simulator harness | `simulator/` | `keep` | `ava-devicekit/simulator` or bridge | Needed for fast validation before flashing |
| Mock scenes | simulator mock JSON | `keep` | `examples/mock_scenes` | Good for demo and CI screenshots |

## Confirmation Required From Product Owner

Before implementation beyond the clean skeleton, confirm these decisions:

| Topic | Default recommendation | Alternatives |
|---|---|---|
| Management backend | Do not include manager-api/web in DeviceKit core; build a small dashboard later | Keep existing manager stack, or drop dashboard entirely |
| MQTT/UDP | Drop from v1 | Keep as optional transport if hardware deployment needs it |
| Market streaming WSS | Keep if live feed/spotlight updates are required for demo | Use polling only for first clean runtime |
| Auth/device identity | Add simple device token first | Add signed device key, or no auth for local demos |
| Wake word | Keep wake/PTT support but provider-configurable | PTT-only for v1, or always-on wake for demo |
| ASR/LLM/TTS providers | Keep Qwen ASR + OpenAI-compatible LLM/TTS first | Port all legacy providers, or use one vendor only |
| OTA | Keep OTA concept, implement after runtime bridge | Skip OTA until firmware split is stable |
| Paper trading | Keep as default safe execution mode | Real trade first, or no trade execution |
| DePIN sensor support | Later as example app | Include in v1 demo |

## Implemented Adapted Copies

These capabilities have been copied as behavior/protocol contracts and rewritten behind DeviceKit-owned modules. They must not grow imports back to the legacy assistant code.

| Capability | DeviceKit module | Adapted behavior |
|---|---|---|
| legacy-firmware-compatible hello/listen/key_action WebSocket flow | `backend/ava_devicekit/gateway/legacy_firmware.py` | Existing firmware can speak the old frame shape while actions route through `DeviceSession` |
| OTA config response | `backend/ava_devicekit/ota/firmware.py` | Emits `server_time`, `websocket`, and `firmware` sections expected by current firmware |
| Firmware version scanning | `backend/ava_devicekit/ota/version.py` | Supports `{model}_{version}.bin` discovery and semver-like update selection |
| Runtime deployment config | `backend/ava_devicekit/runtime/settings.py` | Replaces legacy YAML/config loader for HTTP/WebSocket/OTA settings |
| Firmware app/network/listen state boundary | `firmware/include/ava_devicekit_runtime.h`, `firmware/src/ava_devicekit_runtime.c` | Keeps Wi-Fi/network state, hello, listen, stop, and wake-detect semantics without ESP-IDF/legacy assistant includes |

## Current Confirmed Defaults

These are the defaults used by the current `ava-devicekit/` skeleton until changed:

| Area | Default |
|---|---|
| Core dependency on legacy assistant runtime | none |
| First chain adapter | Solana basic market/token data only |
| First app | Ava Box |
| First transport | WebSocket / JSON messages |
| First UI contract | `ScreenPayload` into `ava_dk_ui_runtime_t` |
| Execution safety | app-level action drafts + physical confirmation |
| Custody | no primary user asset keys on ESP32 |
