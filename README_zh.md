# Ava DeviceKit

([English](README.md) | 中文)

Ava DeviceKit 是一个面向 ESP32 的 Solana AI 硬件应用全栈框架。干净框架实现现在位于 `ava-devicekit/`：包含 app/session 类型、adapter 接口、Solana adapter、gateway/session runtime、schema 和 Ava Box 参考应用。

Ava Box 是基于这个框架构建的第一个参考应用：运行在 ESP32-S3 Scratch Arcade 类掌机上的 Solana AI 终端，支持代币发现、收藏列表、组合查看和交易草稿确认。

legacy 设备/runtime 栈的一部分基于 [`nulllaborg/xiaozhi-esp32`](https://github.com/nulllaborg/xiaozhi-esp32)。新的 `ava-devicekit/` 代码不 import legacy assistant runtime，而是把 Ava Box 能力抽象到我们自己的 app、adapter、transport、screen 和 confirmation contract。

云端能力层和 Skills 集成也可参考 [`AveCloud/ave-cloud-skill`](https://github.com/AveCloud/ave-cloud-skill)。

## 设备预览

![Ava Box hardware preview](docs/assets/readme/ava-box-device-preview.png)

## Ava IP

Ava 是 Ava 硬件应用的产品 IP 和设备端操作员人格：语音优先、基于屏幕上下文，并面向常驻式 crypto 硬件体验设计。

![Ava IP character sheet](docs/assets/readme/ava-ip-character-sheet.png)

## 框架层次

| 层 | 作用 | 当前代码 |
|---|---|---|
| Device Runtime | ESP32 固件边界、device message、transport、未来干净板级端口 | `ava-devicekit/firmware/`，legacy 参考在 `firmware/` |
| Screen Contracts | 框架 screen payload schema 和 portable LVGL 目标 | `ava-devicekit/schemas/`, `ava-devicekit/shared_ui/`，参考 UI 在 `ava-devicekit/reference_apps/ava_box/ui/` |
| Solana Action Gateway | 干净 `ChainAdapter` 和 Solana feed/search/detail/watchlist/draft 实现 | `ava-devicekit/backend/ava_devicekit/adapters/solana.py` |
| AI Router | 模型无关的 routing policy 和 app 级确定性路由 | `ava-devicekit/backend/ava_devicekit/model/`, `ava-devicekit/backend/ava_devicekit/apps/ava_box.py` |
| DeviceKit Contracts | 干净 manifest、schema、示例、安全模型、参考应用元数据 | `ava-devicekit/` |
| Reference Apps | 基于框架构建的具体硬件应用 | `ava-devicekit/apps/ava_box/`, `ava-devicekit/examples/` |

## Ava Box 参考应用

| 范围 | 行为 |
|---|---|
| 链范围 | feed、搜索、spotlight、watchlist、portfolio、orders、交易草稿均固定为 Solana |
| 平台 feed | 仅保留 Pump.fun：`pump_in_hot` 和 `pump_in_new` |
| 原生单位 | 市价买卖、限价单、paper balance 和语音金额使用 SOL |
| 屏幕层 | feed、spotlight、watchlist、portfolio、confirm、result 同时服务固件和模拟器 |
| 助手路由 | Ava 保留当前页面和光标选中上下文，并把语音命令路由到 Solana 动作 |
| 确认机制 | 高风险动作以草稿形式展示，并要求显式确认 |

## 目录说明

| 目录 | 作用 |
|---|---|
| `ava-devicekit/` | 干净 Ava DeviceKit 框架实现，包含 backend package、adapter、schema、example 和 Ava Box app |
| `devicekit/` | 早期框架说明，作为迁移参考保留 |
| `apps/ava_box/` | 早期 Ava Box 参考说明，作为迁移参考保留 |
| `firmware/` | ESP32 固件 runtime、板级适配、音频链路、OTA、协议和设备集成 |
| `server/` | 后端栈、管理服务、action gateway、AI 路由/工具逻辑、部署文档和测试 |
| `shared/` | 同时编译进固件和模拟器的共享 LVGL 屏幕 |
| `simulator/` | 桌面验证工具，用于 DeviceKit UI 和真实 gateway 交互流程 |
| `docs/` | 当前架构和产品/参考文档 |
| `config/` | 仓库级共享资产和小型配置 |
| `data/` | 本地运行数据占位，不提交运行状态 |
| `tmp/` | 调试日志、本地探针和临时产物 |

## 从这里开始

| 任务 | 入口 |
|---|---|
| 理解干净框架 | [`ava-devicekit/README.md`](ava-devicekit/README.md) |
| 查看 Ava Box 参考应用 | [`ava-devicekit/apps/ava_box/manifest.json`](ava-devicekit/apps/ava_box/manifest.json), [`ava-devicekit/backend/ava_devicekit/apps/ava_box.py`](ava-devicekit/backend/ava_devicekit/apps/ava_box.py) |
| 启动 ESP32 runtime | [`firmware/README.md`](firmware/README.md), [`firmware/main/README.md`](firmware/main/README.md) |
| 修改 Solana 后端行为 | [`server/README_en.md`](server/README_en.md), [`server/main/README_en.md`](server/main/README_en.md) |
| 桌面预览页面 | [`simulator/README.md`](simulator/README.md), [`ava-devicekit/reference_apps/ava_box/ui/README.md`](ava-devicekit/reference_apps/ava_box/ui/README.md) |
| 理解共享 UI contract | [`shared/README.md`](shared/README.md) |
| 查看架构说明 | [`docs/README.md`](docs/README.md), [`docs/architecture/xiaozhi-extraction.md`](docs/architecture/xiaozhi-extraction.md) |
| 确认 legacy 能力取舍 | [`ava-devicekit/docs/legacy-capability-inventory.md`](ava-devicekit/docs/legacy-capability-inventory.md) |

## 架构概览

```text
语音 + 物理输入
  -> firmware/ (ESP32 runtime、板级驱动、transport)
  -> ava-devicekit/backend (AvaBoxApp、session gateway、model router)
  -> ChainAdapter(SolanaAdapter 优先，后续可接其他 adapter)
  -> ScreenPayload / ActionDraft contract
       -> 当前 LVGL 参考在 ava-devicekit/reference_apps/ava_box/ui
       -> 未来干净 runtime 在 ava-devicekit/shared_ui
```

关键连接点：

| 连接点 | 目的 |
|---|---|
| `ava-devicekit/apps/ava_box/manifest.json` | 参考应用身份、设备能力、adapter、动作、屏幕和安全策略 |
| `ava-devicekit/schemas/` | 硬件应用、action draft、screen payload 的稳定框架 contract |
| `ava-devicekit/reference_apps/ava_box/ui/` | 当前 Ava Box 屏幕层的单一来源，供 simulator 和 firmware 使用 |
| `firmware/main/boards/scratch-arcade/` | 当前 Scratch Arcade ESP32-S3 硬件目标 |
| `firmware/main/ave_transport_idf.cc` | 把设备事件桥接到共享屏幕/runtime 层 |
| `ava-devicekit/backend/ava_devicekit/adapters/base.py` | chain/helper adapter 接口 |
| `ava-devicekit/backend/ava_devicekit/adapters/solana.py` | 干净 Solana 市场、watchlist、portfolio 和 action draft adapter |
| `simulator/` | 烧录硬件前的布局、导航、gateway 和回归验证 |

## 安全口径

ESP32 是物理交互和确认层，不是用户资产的默认托管层。

| 原则 | 实现方向 |
|---|---|
| AI 不盲执行 | 模型输出生成草稿，高风险动作必须确认 |
| 屏幕可见风险 | 设备展示 action 摘要、token/amount、chain 和结果状态 |
| 物理确认 | 用按键确认/取消敏感动作 |
| 外部托管路径 | 用户主资产密钥可以保留在外部钱包或安全钱包层 |
| 设备身份路径 | ESP32 device key 可用于设备身份、heartbeat 或 sensor proof，与用户资金密钥分离 |

## 上游来源

这个 monorepo 以 Ava DeviceKit 为产品边界，但若干主要目录来自上游项目：

| 目录 | 来源 |
|---|---|
| `firmware/` | `78/xiaozhi-esp32` runtime lineage，正在收窄为 Ava 硬件应用需要的部分 |
| `server/` | `xinnan-tech/xiaozhi-esp32-server` runtime lineage，加入 Ava action gateway 和模型路由 |
| `simulator/` | `lvgl/lv_port_pc_vscode` |
| 云端能力层 | [`AveCloud/ave-cloud-skill`](https://github.com/AveCloud/ave-cloud-skill) |

公开的框架表面是 `ava-devicekit/`。xiaozhi-derived runtime 只作为 legacy 参考保留，等价能力会迁移到我们自己的 app、adapter、transport、screen 和 confirmation contract。
