# Docs Directory

This directory holds current Ava DeviceKit and Ava Box reference documents.

## Reading Order

| Document | Purpose |
|---|---|
| [`../README.md`](../README.md) | Monorepo overview and navigation |
| [`../ava-devicekit/README.md`](../ava-devicekit/README.md) | Clean framework implementation boundary |
| [`../ava-devicekit/docs/technical-architecture-and-builder-guide-zh.md`](../ava-devicekit/docs/technical-architecture-and-builder-guide-zh.md) | 中文技术架构、后台功能、硬件/固件/UI/AI 关系和开发者 0-1 构建指南 |
| [`../ava-devicekit/apps/ava_box/manifest.json`](../ava-devicekit/apps/ava_box/manifest.json) | Ava Box reference app manifest |
| [`../ava-devicekit/docs/legacy-capability-inventory.md`](../ava-devicekit/docs/legacy-capability-inventory.md) | Internal migration decision matrix for capabilities to keep, replace, drop, or defer |
| [`ave-claw-hackathon-product-document-2026-04-13.md`](ave-claw-hackathon-product-document-2026-04-13.md) | English product/reference write-up |
| [`ava-box-product-document-zh-2026-04-13.md`](ava-box-product-document-zh-2026-04-13.md) | 中文产品 / 参考文档 |

## Framework Scope

| Area | Rule |
|---|---|
| Public product boundary | `ava-devicekit/` clean framework plus Ava Box reference app |
| Migration references | Existing repo-level `server/`, `firmware/`, and `shared/` trees remain references until their required pieces are replaced |
| Current chain adapter | Solana only |
| Current platform feed | Pump.fun hot/new only |
| Native unit | SOL |
| Device role | Physical interaction and confirmation surface |
| Custody stance | Primary user asset keys are not required to live on ESP32 |
| Implementation source of truth | `ava-devicekit/backend/ava_devicekit/`, `ava-devicekit/apps/ava_box/`, `ava-devicekit/schemas/` |

Keep durable notes tied to code that exists in this branch. Avoid presenting old
assistant internals as the public framework API; DeviceKit contracts should stay
narrow and hardware-app focused.
