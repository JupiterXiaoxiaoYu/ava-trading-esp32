# Docs Directory

This directory holds current Ava DeviceKit and Ava Box reference documents.

## Reading Order

| Document | Purpose |
|---|---|
| [`../README.md`](../README.md) | Monorepo overview and navigation |
| [`../devicekit/README.md`](../devicekit/README.md) | Framework contracts, layers, and safety model |
| [`architecture/xiaozhi-extraction.md`](architecture/xiaozhi-extraction.md) | Plan for reducing the xiaozhi-derived runtime into the smaller DeviceKit boundary |
| [`ave-claw-hackathon-product-document-2026-04-13.md`](ave-claw-hackathon-product-document-2026-04-13.md) | English product/reference write-up |
| [`ava-box-product-document-zh-2026-04-13.md`](ava-box-product-document-zh-2026-04-13.md) | 中文产品 / 参考文档 |

## Framework Scope

| Area | Rule |
|---|---|
| Public product boundary | Ava DeviceKit framework plus Ava Box reference app |
| Current chain focus | Solana only |
| Current platform feed | Pump.fun hot/new only |
| Native unit | SOL |
| Device role | Physical interaction and confirmation surface |
| Custody stance | Primary user asset keys are not required to live on ESP32 |
| Implementation source of truth | `devicekit/`, `apps/ava_box/`, `server/main/xiaozhi-server/plugins_func/functions/`, and `shared/ave_screens/` |

Keep durable notes tied to code that exists in this branch. Avoid presenting xiaozhi internals as the public framework API; DeviceKit contracts should stay narrow and hardware-app focused.
