# AVE Trading ESP32 单仓库

([English](README.md) | 中文)

这个仓库是 AVE 硬件、后端和模拟器的一体化主仓库。

AVE 是一个语音驱动的交易助手，建立在 XiaoZhi 系固件、Python 后端以及可同时运行在硬件和桌面模拟器上的共享 LVGL 界面层之上。当前产品重点是 Scratch Arcade 风格的 ESP32-S3 板卡：320x240 屏幕、摇杆输入、语音唤醒，以及 AVE 的 feed、spotlight、portfolio、watchlist 和订单等页面。

## 仓库内容

- `firmware/` - ESP32 固件运行时、板级适配、音频链路、OTA、协议实现和 AVE 设备集成层
- `server/` - 后端栈、管理服务、AVE 路由/工具逻辑、部署文档和服务端测试
- `shared/` - 被固件和模拟器共同编译使用的共享 AVE LVGL 页面层
- `simulator/` - 共享 AVE 界面的桌面验证环境和 mock 交互环境
- `docs/` - 当前仍保留的产品/参考文档
- `config/` - 仓库内维护的共享资产和小型配置文件
- `data/` - 本地运行时数据占位目录
- `tmp/` - 调试过程中产生的日志、探针结果和临时产物

## 从哪里开始

### 如果你想...

- 做 ESP32 设备运行时相关工作：先看 [`firmware/README.md`](firmware/README.md) 和 [`firmware/main/README.md`](firmware/main/README.md)
- 做服务端 AVE 行为相关工作：先看 [`server/README_en.md`](server/README_en.md) 和 [`server/main/README_en.md`](server/main/README_en.md)
- 在桌面上预览或调试 AVE 页面：先看 [`simulator/README.md`](simulator/README.md) 和 [`shared/ave_screens/README.md`](shared/ave_screens/README.md)
- 理解共享 UI 层：先看 [`shared/README.md`](shared/README.md)
- 查看剩余产品/参考文档：先看 [`docs/README.md`](docs/README.md)

## 架构概览

```text
speech + input
  -> firmware/ (ESP32 运行时、板级驱动、传输层)
  -> server/main/xiaozhi-server/ (ASR、路由、工具、AVE 后端逻辑)
  -> shared/ave_screens/ (feed、spotlight、portfolio、orders、result 等页面)
       -> 编译进 firmware 用于真机渲染
       -> 编译进 simulator 用于桌面验证
```

与 AVE 直接相关的关键耦合点：

- `shared/ave_screens/` 是 AVE 页面层的单一事实来源
- `firmware/main/boards/scratch-arcade/` 是当前仓库里最重要的目标硬件
- `firmware/main/ave_transport_idf.cc` 负责把设备事件桥接到共享页面运行时
- `server/main/xiaozhi-server/` 包含 AVE 专用的 router、WSS、交易和上下文逻辑
- `simulator/` 用于在烧录前验证布局、导航、mock 场景和页面回归

## 仓库导航

### 产品界面层

- [`shared/README.md`](shared/README.md) - 共享跨端 AVE UI 层说明
- [`shared/ave_screens/README.md`](shared/ave_screens/README.md) - 页面文件、manager、工具和扩展方式
- [`simulator/README.md`](simulator/README.md) - AVE 模拟器的桌面构建/运行入口

### 设备运行时

- [`firmware/README.md`](firmware/README.md) - 上游固件能力说明 + AVE 单仓库补充说明
- [`firmware/main/README.md`](firmware/main/README.md) - 固件运行时内部结构、板级适配、显示/音频/协议入口

### 后端栈

- [`server/README_en.md`](server/README_en.md) - 带 AVE 单仓库语境的后端部署总览
- [`server/main/README_en.md`](server/main/README_en.md) - `xiaozhi-server`、`manager-api`、`manager-web`、`manager-mobile` 的模块地图

### 参考文档和本地支持目录

- [`docs/README.md`](docs/README.md) - 当前仍保留的产品/参考文档说明
- [`config/README.md`](config/README.md) - 共享资产和配置说明
- [`data/README.md`](data/README.md) - 运行时数据占位目录说明
- [`tmp/README.md`](tmp/README.md) - 临时日志和探针产物说明

## 上游来源

这个仓库是 AVE-first 的主仓库，但几个主要目录仍然来自上游项目：

- `firmware/` 源自 `78/xiaozhi-esp32`
- `server/` 源自 `xinnan-tech/xiaozhi-esp32-server`
- `simulator/` 源自 `lvgl/lv_port_pc_vscode`

本仓库里的 README 统一从 AVE 当前如何使用和改造这些目录的角度进行说明。
