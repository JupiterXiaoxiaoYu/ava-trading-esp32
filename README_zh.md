# Ava Box Solana ESP32 单仓库

([English](README.md) | 中文)

这个分支是 Ava Box 的 Solana 专用版本，包含 ESP32 固件、Python 后端、共享 LVGL 页面层，以及用于复用同一套产品流程的桌面模拟器。

Ava Box 是一台语音驱动的加密掌上终端，运行在 Scratch Arcade 风格的 ESP32-S3 设备上：`320x240` 横屏、摇杆导航、物理确认按键、唤醒词 / PTT 语音输入、扬声器输出，以及名为 Ava 的 AI 设备人格。本分支把产品表面收敛到 Solana：SOL 原生动作、Solana 代币发现、Pump.fun hot/new feed、钱包理解、watchlist、portfolio 和交易确认流程。

Ava Box 的后端与设备运行时栈中有一部分代码基于 [`nulllaborg/xiaozhi-esp32`](https://github.com/nulllaborg/xiaozhi-esp32)。这套架构不仅服务于当前的 Scratch Arcade 目标板，也可以继续扩展到各种 ESP32 形态的硬件设备上，例如手表、触摸显示屏、机器人以及其他带语音能力的终端。

云端能力层与 Skills 扩展仓库可参考 [`AveCloud/ave-cloud-skill`](https://github.com/AveCloud/ave-cloud-skill)。

## 设备预览

![Ava Box 硬件预览](docs/assets/readme/ava-box-device-preview.png)

## Ava IP

Ava 是 Ava Box 的产品 IP 和设备操作者人格：以语音作为入口、以屏幕作为真相源，目标是形成一个始终在线的加密终端体验。

![Ava IP 角色设定图](docs/assets/readme/ava-ip-character-sheet.png)

## Solana 分支行为

| 范围 | 行为 |
|---|---|
| 链范围 | feed、search、spotlight、watchlist、portfolio、orders、trading 全部固定为 `solana` |
| 平台 feed | 仅保留 Pump.fun：`pump_in_hot` 和 `pump_in_new` |
| 原生单位 | market buy/sell、limit order、paper balance 和语音金额全部使用 SOL |
| 页面层 | 固件和模拟器共享 Solana feed、spotlight、watchlist、portfolio、confirm、result 页面 |
| 助手路由 | Ava 在语音路由时保留当前页面上下文和光标选中上下文 |

## 仓库内容

| 目录 | 作用 |
|---|---|
| `firmware/` | ESP32 固件运行时、板级适配、音频链路、OTA、协议实现和 Ava Box 设备集成 |
| `server/` | 后端栈、管理服务、Ava Box 路由 / 工具逻辑、部署文档和服务端测试 |
| `shared/` | 被固件和模拟器共同编译使用的共享 Ava Box LVGL 页面层 |
| `simulator/` | 共享 Ava Box UI 的桌面验证环境和 mock 交互环境 |
| `docs/` | 当前产品 / 参考文档 |
| `config/` | 仓库内维护的共享资产和小型配置文件 |
| `data/` | 本地运行时数据占位目录 |
| `tmp/` | 调试过程中产生的日志、探针结果和临时产物 |

## 从哪里开始

| 任务 | 入口 |
|---|---|
| 做 ESP32 设备运行时相关工作 | [`firmware/README.md`](firmware/README.md)、[`firmware/main/README.md`](firmware/main/README.md) |
| 做 Solana 后端行为相关工作 | [`server/README_en.md`](server/README_en.md)、[`server/main/README_en.md`](server/main/README_en.md) |
| 在桌面上预览页面 | [`simulator/README.md`](simulator/README.md)、[`shared/ave_screens/README.md`](shared/ave_screens/README.md) |
| 理解共享 UI 契约 | [`shared/README.md`](shared/README.md) |
| 查看产品 / 参考文档 | [`docs/README.md`](docs/README.md) |

## 架构概览

```text
speech + input
  -> firmware/ (ESP32 运行时、板级驱动、传输层)
  -> server/main/xiaozhi-server/ (ASR、路由、工具、Solana-only Ava Box 后端逻辑)
  -> shared/ave_screens/ (feed、spotlight、portfolio、watchlist、orders、result 等页面)
       -> 编译进 firmware 用于真机渲染
       -> 编译进 simulator 用于桌面验证
```

与 Ava Box 直接相关的关键耦合点：

| 耦合点 | 作用 |
|---|---|
| `shared/ave_screens/` | Ava Box 页面层的单一事实来源 |
| `firmware/main/boards/scratch-arcade/` | 当前 Scratch Arcade ESP32-S3 目标硬件 |
| `firmware/main/ave_transport_idf.cc` | 把设备事件桥接到共享页面运行时 |
| `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py` | Solana-only 市场、钱包、watchlist、portfolio 和订单工具 |
| `simulator/` | 在烧录前验证布局、导航、mock 场景和页面回归 |

## 上游来源

这个仓库是 Ava Box-first 的主仓库，但几个主要目录仍然来自上游项目：

| 目录 | 来源 |
|---|---|
| `firmware/` | `78/xiaozhi-esp32` |
| `server/` | `xinnan-tech/xiaozhi-esp32-server` |
| `simulator/` | `lvgl/lv_port_pc_vscode` |
| 云端能力层 | [`AveCloud/ave-cloud-skill`](https://github.com/AveCloud/ave-cloud-skill) |

本仓库里的 README 统一从 Ava Box 如何组织和使用这些目录来说明 Solana 版本。
