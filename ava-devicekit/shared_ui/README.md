# Shared UI Runtime

This folder is the target home for the portable LVGL screen runtime.

Current migration rule:

| Source | Target |
|---|---|
| `shared/ave_screens/` screen payload behavior | `ava-devicekit/shared_ui/` portable screen runtime |
| Ava Box-specific screen names | reference app screens under `apps/ava_box` |
| transport glue | framework `TransportAdapter` boundary |

The first implementation keeps the existing `shared/ave_screens/` code as the working hardware/simulator reference while backend contracts move into `ava-devicekit/backend`.
