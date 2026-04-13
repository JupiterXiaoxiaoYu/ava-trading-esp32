# Ava Box ESP32 Monorepo

(English | [中文](README_zh.md))

This repository is the active monorepo for the Ava Box hardware + backend + simulator stack.

Ava Box is a voice-driven trading assistant built on top of XiaoZhi-derived ESP32 firmware, a Python backend, and a shared LVGL screen layer that runs on both hardware and the desktop simulator. The current product focus is the Scratch Arcade style ESP32-S3 board with a 320x240 display, joystick input, voice wake-up, and Ava Box market pages such as feed, spotlight, portfolio, watchlist, and order flows.

Parts of the Ava Box backend and device-runtime stack are based on [`nulllaborg/xiaozhi-esp32`](https://github.com/nulllaborg/xiaozhi-esp32). The same architecture is designed to scale beyond the current Scratch Arcade target and can be extended to many ESP32 form factors, including watches, touch displays, robots, and other voice-enabled devices.

## What lives here

- `firmware/` - ESP32 firmware runtime, board ports, audio pipeline, OTA, protocols, and the Ava Box device integration layer
- `server/` - backend stack, management services, Ava Box routing/tool logic, deployment docs, and server-side tests
- `shared/` - shared Ava Box LVGL screens that are compiled into both the firmware and the simulator
- `simulator/` - desktop validation harness for the shared Ava Box UI and mock interaction flows
- `docs/` - current product/reference documents
- `config/` - repo-owned shared assets and small configuration artifacts used across the project
- `data/` - local runtime data placeholder for non-committed state
- `tmp/` - generated logs, local probes, and scratch artifacts used during debugging

## Start here

### If you want to...

- Bring up the ESP32 device runtime: start with [`firmware/README.md`](firmware/README.md) and [`firmware/main/README.md`](firmware/main/README.md)
- Work on server-side Ava Box behavior: start with [`server/README_en.md`](server/README_en.md) and [`server/main/README_en.md`](server/main/README_en.md)
- Preview or debug Ava Box pages on desktop: start with [`simulator/README.md`](simulator/README.md) and [`shared/ave_screens/README.md`](shared/ave_screens/README.md)
- Understand the shared Ava Box UI contract: start with [`shared/README.md`](shared/README.md)
- Read the remaining product/reference documents: start with [`docs/README.md`](docs/README.md)

## Architecture at a glance

```text
speech + input
  -> firmware/ (ESP32 runtime, board drivers, transport)
  -> server/main/xiaozhi-server/ (ASR, routing, tools, Ava Box backend logic)
  -> shared/ave_screens/ (feed, spotlight, portfolio, orders, result, etc.)
       -> compiled into firmware for hardware rendering
       -> compiled into simulator for desktop validation
```

Key Ava Box coupling points:

- the stack is intentionally portable across a wide range of ESP32 hardware classes, not only the current board, including watches, touch screens, robots, and other custom devices
- `shared/ave_screens/` is the single source of truth for the Ava Box screen layer
- `firmware/main/boards/scratch-arcade/` is the main active hardware target in this repo
- `firmware/main/ave_transport_idf.cc` bridges device events into the shared screen/runtime layer
- `server/main/xiaozhi-server/` contains Ava Box-specific router, WSS, trading, and context behavior
- `simulator/` is used to validate layout, navigation, mock scenes, and screen regressions before flashing hardware

## Repository navigation

### Product surfaces

- [`shared/README.md`](shared/README.md) - how the cross-target Ava Box UI is organized
- [`shared/ave_screens/README.md`](shared/ave_screens/README.md) - screen files, manager, utilities, and extension workflow
- [`simulator/README.md`](simulator/README.md) - desktop build/run flow for the Ava Box simulator

### Device runtime

- [`firmware/README.md`](firmware/README.md) - upstream firmware capabilities plus Ava Box monorepo notes
- [`firmware/main/README.md`](firmware/main/README.md) - firmware runtime internals, board ports, display/audio/protocol entry points

### Backend stack

- [`server/README_en.md`](server/README_en.md) - backend deployment overview with Ava Box monorepo framing
- [`server/main/README_en.md`](server/main/README_en.md) - backend module map for `xiaozhi-server`, `manager-api`, `manager-web`, and `manager-mobile`

### Reference docs and local support areas

- [`docs/README.md`](docs/README.md) - current product/reference documents
- [`config/README.md`](config/README.md) - shared repo assets and configuration notes
- [`data/README.md`](data/README.md) - runtime-data placeholder guidance
- [`tmp/README.md`](tmp/README.md) - scratch logs and local probe artifacts

## Upstream origins

This monorepo is Ava Box-first, but several major directories are derived from upstream projects:

- `firmware/` derives from `78/xiaozhi-esp32`
- `server/` derives from `xinnan-tech/xiaozhi-esp32-server`
- `simulator/` derives from `lvgl/lv_port_pc_vscode`

The READMEs in this repo describe those folders in terms of how Ava Box uses and customizes them today.
