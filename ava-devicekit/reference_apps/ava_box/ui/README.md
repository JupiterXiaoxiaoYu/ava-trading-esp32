# Ava Box UI Package

These LVGL screens are the Ava Box reference UI package. They consume DeviceKit `ScreenPayload` data and emit cursor/selection context back to the runtime.

This package is app-level code, not DeviceKit framework core. Other hardware apps can replace it with their own UI package while still using the same DeviceKit backend, provider, gateway, and firmware contracts.

| Screen File | Payload |
|---|---|
| `screen_feed.c` | `screen=feed`, token rows, cursor selection |
| `screen_spotlight.c` | `screen=spotlight`, selected token detail and chart |
| `screen_portfolio.c` | `screen=portfolio`, positions/orders |
| `screen_confirm.c` / `screen_limit_confirm.c` | `screen=confirm`, physical confirmation draft |
| `screen_result.c` | `screen=result`, action outcome |
| `screen_notify.c` | `screen=notify`, assistant/status messages |
