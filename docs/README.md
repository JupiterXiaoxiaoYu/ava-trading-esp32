# Docs Directory

This directory holds current Ava DeviceKit and Ava Box reference documents.

## Reading Order

| Document | Purpose |
|---|---|
| [`../README.md`](../README.md) | Monorepo overview and navigation |
| [`../ava-devicekit/README.md`](../ava-devicekit/README.md) | Clean framework implementation boundary |
| [`../ava-devicekit/apps/ava_box/manifest.json`](../ava-devicekit/apps/ava_box/manifest.json) | Ava Box reference app manifest |
| [`architecture/xiaozhi-extraction.md`](architecture/xiaozhi-extraction.md) | Plan for reducing the legacy runtime into the smaller DeviceKit boundary |
| [`../ava-devicekit/docs/xiaozhi-capability-inventory.md`](../ava-devicekit/docs/xiaozhi-capability-inventory.md) | Decision matrix for which legacy capabilities to keep, replace, drop, or defer |
| [`ave-claw-hackathon-product-document-2026-04-13.md`](ave-claw-hackathon-product-document-2026-04-13.md) | English product/reference write-up |
| [`ava-box-product-document-zh-2026-04-13.md`](ava-box-product-document-zh-2026-04-13.md) | 中文产品 / 参考文档 |

## Framework Scope

| Area | Rule |
|---|---|
| Public product boundary | `ava-devicekit/` clean framework plus Ava Box reference app |
| Legacy runtime | Existing `server/`, `firmware/`, and `shared/` trees remain migration references until their required pieces are replaced |
| Current chain adapter | Solana only |
| Current platform feed | Pump.fun hot/new only |
| Native unit | SOL |
| Device role | Physical interaction and confirmation surface |
| Custody stance | Primary user asset keys are not required to live on ESP32 |
| Implementation source of truth | `ava-devicekit/backend/ava_devicekit/`, `ava-devicekit/apps/ava_box/`, `ava-devicekit/schemas/` |

Keep durable notes tied to code that exists in this branch. Avoid presenting legacy assistant internals as the public framework API; DeviceKit contracts should stay narrow and hardware-app focused.
