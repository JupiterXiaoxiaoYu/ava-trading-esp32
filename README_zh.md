# Ava DeviceKit

([English](README.md) | 中文)

Ava DeviceKit 是一个面向 ESP32 的 Solana AI 硬件应用全栈框架，提供设备端 UI、物理输入、语音交互、后端 Solana Action API、模型路由和确认流程，让开发者可以把 Solana 链上动作带到真实硬件设备里。

Ava Box 是基于这个框架构建的第一个参考应用：运行在 ESP32-S3 Scratch Arcade 类掌机上的 Solana AI 终端，支持代币发现、收藏列表、组合查看和交易草稿确认。

当前设备/runtime 栈的一部分基于 [`nulllaborg/xiaozhi-esp32`](https://github.com/nulllaborg/xiaozhi-esp32)。框架化工作的方向是只保留 Ava 硬件应用需要的 runtime 能力，并把应用行为拆到更小的 DeviceKit contract 和 reference app 中。

云端能力层和 Skills 集成也可参考 [`AveCloud/ave-cloud-skill`](https://github.com/AveCloud/ave-cloud-skill)。

## 设备预览

![Ava Box hardware preview](docs/assets/readme/ava-box-device-preview.png)

## Ava IP

Ava 是 Ava 硬件应用的产品 IP 和设备端操作员人格：语音优先、基于屏幕上下文，并面向常驻式 crypto 硬件体验设计。

![Ava IP character sheet](docs/assets/readme/ava-ip-character-sheet.png)

## 框架层次

| 层 | 作用 | 当前代码 |
|---|---|---|
| Device Runtime | ESP32 固件、板级驱动、显示/音频生命周期、Wi-Fi、OTA、设备状态、传输 | `firmware/` |
| Screen Contracts | 固件和模拟器共用的 LVGL payload | `shared/ave_screens/` |
| Solana Action Gateway | 后端 Action API、屏幕 payload 推送、交易/挂单草稿、确认和结果处理 | `server/main/xiaozhi-server/plugins_func/functions/` |
| AI Router | ASR/TTS、唤醒/PTT、模型路由、确定性动作、LLM fallback | `server/main/xiaozhi-server/core/` |
| DeviceKit Contracts | manifest、schema、示例、安全模型、参考应用元数据 | `devicekit/` |
| Reference Apps | 基于框架构建的具体硬件应用 | `apps/ava_box/`, `devicekit/examples/` |

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
| `devicekit/` | Ava DeviceKit contract、manifest、schema、示例和框架说明 |
| `apps/ava_box/` | Ava Box 参考应用说明和应用级 contract |
| `firmware/` | ESP32 固件 runtime、板级适配、音频链路、OTA、协议和设备集成 |
| `server/` | 后端栈、管理服务、action gateway、AI 路由/工具逻辑、部署文档和测试 |
| `shared/` | 同时编译进固件和模拟器的共享 LVGL 屏幕 |
| `simulator/` | 桌面验证工具，用于 UI 和 mock 交互流程 |
| `docs/` | 当前架构和产品/参考文档 |
| `config/` | 仓库级共享资产和小型配置 |
| `data/` | 本地运行数据占位，不提交运行状态 |
| `tmp/` | 调试日志、本地探针和临时产物 |

## 从这里开始

| 任务 | 入口 |
|---|---|
| 理解框架 | [`devicekit/README.md`](devicekit/README.md) |
| 查看 Ava Box 参考应用 | [`apps/ava_box/README.md`](apps/ava_box/README.md), [`devicekit/manifests/ava_box.solana.json`](devicekit/manifests/ava_box.solana.json) |
| 启动 ESP32 runtime | [`firmware/README.md`](firmware/README.md), [`firmware/main/README.md`](firmware/main/README.md) |
| 修改 Solana 后端行为 | [`server/README_en.md`](server/README_en.md), [`server/main/README_en.md`](server/main/README_en.md) |
| 桌面预览页面 | [`simulator/README.md`](simulator/README.md), [`shared/ave_screens/README.md`](shared/ave_screens/README.md) |
| 理解共享 UI contract | [`shared/README.md`](shared/README.md) |
| 查看架构说明 | [`docs/README.md`](docs/README.md), [`docs/architecture/xiaozhi-extraction.md`](docs/architecture/xiaozhi-extraction.md) |

## 架构概览

```text
语音 + 物理输入
  -> firmware/ (ESP32 runtime、板级驱动、transport)
  -> server/ (AI router、action gateway、Solana tool/provider 逻辑)
  -> shared/ave_screens/ (feed、spotlight、portfolio、confirm、result 等)
       -> 编译进固件，用于硬件渲染
       -> 编译进 simulator，用于桌面验证
  -> devicekit/ (可复用硬件应用的 manifest/schema/action contract)
```

关键连接点：

| 连接点 | 目的 |
|---|---|
| `devicekit/manifests/ava_box.solana.json` | 参考应用身份、设备能力、动作、屏幕和安全策略 |
| `devicekit/schemas/` | 硬件应用、action、screen payload 的稳定框架 contract |
| `shared/ave_screens/` | 当前 Ava Box 屏幕层的单一来源 |
| `firmware/main/boards/scratch-arcade/` | 当前 Scratch Arcade ESP32-S3 硬件目标 |
| `firmware/main/ave_transport_idf.cc` | 把设备事件桥接到共享屏幕/runtime 层 |
| `server/main/xiaozhi-server/plugins_func/functions/ava_devicekit.py` | DeviceKit payload 的轻量后端 helper 边界 |
| `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py` | Ava Box Solana 市场、钱包、watchlist、portfolio 和订单工具 |
| `simulator/` | 烧录硬件前的布局、导航、mock scene 和回归验证 |

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

公开的框架表面是 `devicekit/`、`apps/`、共享 screen contract 和后端 action gateway。xiaozhi-derived runtime 是实现层，不是产品边界。
