# Ava DeviceKit 技术架构与开发者构建指南

本文档描述当前 `ava-devicekit/` 框架的技术架构、后台能力、固件/硬件/UI/AI 的协作关系，以及开发者如何从 0 到 1 基于框架构建一个类似 Ava Box 的 AI 硬件产品。

## 1. 当前定位

Ava DeviceKit 是一个面向 ESP32 类硬件的 AI 设备应用框架。它把“硬件交互、屏幕 UI、设备协议、后台控制台、AI Provider、链/数据 Adapter、动作确认、OTA、设备运营”拆成清晰边界，让开发者可以把 Ava Box 作为参考应用，构建自己的 AI DePIN、AI 交易、支付、提醒、传感器、审批终端等硬件产品。

| 层级 | 框架负责 | 应用负责 | Ava Box 示例 |
|---|---|---|---|
| 硬件运行时 | 网络状态、设备状态、hello/listen/wake JSON、音频/显示/输入接口边界 | 具体板子的 GPIO、屏幕、麦克风、扬声器、电源、按键/摇杆映射 | Scratch Arcade / ESP32-S3 掌机形态 |
| UI 运行时 | 屏幕 payload 合约、通用 key/input/context 事件、可注册屏幕 vtable | 具体页面布局、业务字段、选中项、返回栈、滚动行为 | Feed、Spotlight、Portfolio、Orders、Confirm、Result |
| 后台 Gateway | HTTP/WebSocket 入口、设备 session、admin API、OTA、事件、设备认证 | App 路由、业务技能、交易/支付/数据逻辑 | AvaBoxApp + Ava Box skills |
| AI Provider | ASR/LLM/TTS 接口、runtime 配置、健康检查、自定义 provider class | prompt、业务意图、确定性动作和 LLM fallback 策略 | Qwen ASR、Qwen/OpenAI-compatible LLM、AliBL/CosyVoice TTS |
| 链/数据 Adapter | `ChainAdapter` 接口和运行时选择 | 接哪条链、哪个数据源、业务数据结构 | Solana adapter + market data service |
| 高风险动作 | `ActionDraft`、物理确认、结果 payload | 买入/卖出/支付/签名/注册设备等业务语义 | 买入、卖出、限价单、watchlist |
| 运营后台 | 设备、客户、项目、provider、服务、OTA、usage、logs | 产品定价、客户管理规则、业务服务配置 | 自托管 Ava Box 服务后台 |

核心原则：

| 原则 | 说明 |
|---|---|
| 硬件无关 | 框架不规定按钮、摇杆、触摸、屏幕尺寸；硬件通过 board port 映射成通用事件 |
| 链无关 | 框架只定义 adapter 边界；当前 reference 是 Solana，后续可接其他链 |
| Provider 可配置 | ASR、LLM、TTS、chain、execution 都通过 runtime config / admin 控制台配置 |
| 设备是确认层 | ESP32 负责物理交互和确认，不要求把主钱包私钥放在设备里 |
| 业务在 app 层 | 交易、watchlist、portfolio、payment、sensor proof 等属于应用逻辑，不写死在框架核心 |
| Context 优先 | 页面当前数据、cursor、selected、visible rows 必须进入 context，AI 和确定性路由才能正确操作 |

## 2. 总体架构

```text
┌──────────────────────────────────────────────────────────────────┐
│                         C-end Hardware Device                     │
│ ESP32 / display / input / mic / speaker / Wi-Fi / OTA             │
│                                                                  │
│  Board Port        Shared UI Runtime        Firmware Runtime      │
│  GPIO/Touch  ───>  Screen vtable/context ─> hello/listen/wake     │
│  Audio I/O   ───>  PCM/OPUS frames        ─> JSON/WebSocket/HTTP  │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                │ device frames / context / audio / display payloads
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Ava DeviceKit Backend Gateway                 │
│                                                                  │
│  HTTP Gateway      Firmware WS Bridge      Runtime Manager        │
│  /device/*         /ava/v1/               session per device      │
│  /admin/*          deployed device frames outbox + event log      │
│                                                                  │
│  Control Plane     Provider Registry      OTA / Services          │
│  devices/users     ASR/LLM/TTS            firmware + API registry │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                │ DeviceMessage / AppContext / ActionDraft
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                         Hardware App Layer                        │
│                                                                  │
│  HardwareApp interface        App skills           Chain Adapter  │
│  boot() / handle()            trade/payment/etc    feed/search    │
│  deterministic routes         portfolio/watchlist  token detail   │
│  LLM fallback                 execution provider   market stream  │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                │ provider calls / backend APIs / chain RPC
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                         External Services                         │
│ ASR / LLM / TTS vendors, Solana RPC, market data, proxy wallet,   │
│ payment API, order router, custom developer services              │
└──────────────────────────────────────────────────────────────────┘
```

### 2.1 关键代码目录

| 路径 | 作用 |
|---|---|
| `ava-devicekit/backend/ava_devicekit/apps/base.py` | `HardwareApp` 最小接口：`boot()` 和 `handle()` |
| `ava-devicekit/backend/ava_devicekit/apps/registry.py` | app manifest 和 app 实例创建 |
| `ava-devicekit/backend/ava_devicekit/gateway/http_server.py` | HTTP gateway、admin API、device API、OTA API |
| `ava-devicekit/backend/ava_devicekit/gateway/websocket_server.py` | DeviceKit WebSocket gateway |
| `ava-devicekit/backend/ava_devicekit/gateway/firmware_compat.py` | 已部署设备的 WebSocket 协议适配桥；内部兼容层，不是框架主叙事 |
| `ava-devicekit/backend/ava_devicekit/gateway/runtime_manager.py` | 多设备 session、outbox、connection、event log |
| `ava-devicekit/backend/ava_devicekit/control_plane/store.py` | 本地控制面：users/projects/customers/devices/plans/usage/runtime config |
| `ava-devicekit/backend/ava_devicekit/runtime/settings.py` | runtime 配置模型和 sanitized 输出 |
| `ava-devicekit/backend/ava_devicekit/providers/` | ASR、LLM、TTS provider 接口和内置实现 |
| `ava-devicekit/backend/ava_devicekit/adapters/` | chain adapter 接口、Solana adapter、adapter registry |
| `ava-devicekit/backend/ava_devicekit/streams/` | market stream adapter、polling/live stream runtime |
| `ava-devicekit/backend/ava_devicekit/services/` | developer backend service registry 和 allowlisted invoke |
| `ava-devicekit/backend/ava_devicekit/ota/` | firmware catalog、OTA 响应、firmware publish |
| `ava-devicekit/firmware/include/ava_devicekit_runtime.h` | C 侧硬件运行时接口 |
| `ava-devicekit/shared_ui/include/ava_devicekit_ui.h` | C 侧 shared UI / input / context 接口 |
| `ava-devicekit/schemas/` | manifest、screen payload、input event、context snapshot、action draft、device identity、telemetry、transport profile、developer service 合约 |
| `ava-devicekit/userland/` | 开发者模板：app、provider、adapter、hardware port、UI、runtime config |
| `ava-devicekit/reference_apps/ava_box/` | Ava Box reference app UI/产品资产边界 |
| `ava-devicekit/backend/ava_devicekit/apps/ava_box.py` | Ava Box app 路由和 reference app 主逻辑 |
| `ava-devicekit/backend/ava_devicekit/apps/ava_box_skills/` | Ava Box app 层交易、watchlist、portfolio、execution 逻辑 |

## 3. 后台后端架构

后台后端由四个主要部分组成：Gateway、Runtime Manager、Control Plane、Provider/Adapter/Service Registry。

### 3.1 Gateway

Gateway 是设备、后台前端和外部调用进入框架的入口。

| 模块 | 职责 | 典型输入 | 典型输出 |
|---|---|---|---|
| HTTP Gateway | 提供 `/device/*`、`/admin/*`、`/ava/ota/*` API | HTTP JSON、admin 操作、device message | screen payload、action result、runtime JSON |
| Firmware WebSocket Bridge | 适配已部署设备的 hello/listen/key_action 帧 | WebSocket text/binary/audio frames | display/TTS/ACK/command frames |
| Runtime Server | 单进程运行 HTTP + WS + background tasks | CLI `run-server` | 8788 HTTP + 8787 WS |
| Firmware Protocol Bridge | 把已部署设备 wire protocol 转成 DeviceKit `DeviceMessage` | `hello`、`listen`、`key_action`、audio | app session handle 结果 |

常用启动方式：

```bash
cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32

cp ava-devicekit/userland/env.example ava-devicekit/.env.local
./scripts/run-devicekit-local.sh
```

`ava-devicekit/.env.local` 是 DeviceKit 本地运行的唯一默认密钥入口，文件被 git ignore，不应提交。旧 runtime 的 `.env` 只能作为迁移密钥来源，不能作为 DeviceKit 启动入口。

### 3.2 Runtime Manager

Runtime Manager 负责多设备运行时隔离。

| 能力 | 说明 |
|---|---|
| 多设备 session | 每个 `device_id` 有独立 app session、screen、context、outbox |
| outbox | 存储后台发给设备的 display/action/TTS payload |
| event log | 记录 server-wide 和 per-device runtime events |
| connection state | 记录 WebSocket 连接、在线状态、最后活动时间 |
| OTA command | 后台可给在线设备 queue `ota_check`，设备执行正常 pull OTA |
| admin diagnostics | Device Detail 页面可读取 state、connection、events、config、usage |

设备 ID 来源：

| 通道 | device id 来源 |
|---|---|
| HTTP device API | Header `X-Ava-Device-Id` |
| WebSocket firmware bridge | hello/device metadata 或默认 session |
| Admin 调试 | `/admin/devices/{device_id}/...` 路径 |

### 3.3 Control Plane

Control Plane 是当前自托管后台的数据层，默认存储在 JSON 文件中：

```json
{
  "control_plane_store_path": "data/devicekit_control_plane/control_plane.json"
}
```

它当前管理：

| 数据对象 | 用途 |
|---|---|
| users | 运营/开发/查看者账号记录；不是 C 端用户注册系统 |
| projects | app 的内部 backing record，用于 app id、chain、owner、device config 默认值 |
| customers | C 端硬件客户，绑定激活码后的设备 |
| devices | 已 provision / registered / active / suspended / revoked 的硬件 |
| purchases | 硬件订单/激活卡，连接 app、device、plan、activation code、可选 wallet lock |
| runtime_config | 后台持久化 provider/adapter/execution/services 配置 |
| default_device_config | 设备默认 AI name、language、wake phrases、volume、wallet mode、risk mode |
| service_plans | 设备套餐和 usage limits |
| usage_counters / usage_events | 按设备、周期记录 ASR/LLM/TTS/API 使用量 |

`revoke` 和 `delete` 的语义不同：

| 操作 | 作用 | 什么时候用 |
|---|---|---|
| `POST /admin/devices/{device_id}/status` with `revoked` | 清空设备 token，保留库存/售后记录 | 设备丢失、被盗、停用但仍需保留记录 |
| `POST /admin/devices/{device_id}/delete` | 删除设备库存记录、相关 purchase/activation card、usage counters | 需要释放同一个 `device_id`，重新 provision / 重新绑定 / 重新激活 |

设备生命周期：

```text
Operator creates/selects app_id
  -> Backend resolves or creates the backing project record
  -> Operator provisions device for that app_id
  -> Backend returns provisioning_token + activation_code
  -> Operator creates purchase/activation card for app_id + device_id + plan_id
  -> Device registers with provisioning_token
  -> Backend returns per-device bearer token
  -> C-end user signs in at `/customer` with wallet signature and activates device with activation_code
  -> Device pulls resolved config and starts normal operation
  -> Operator monitors logs/usage/OTA/provider health
```

App 是产品单元，Project 是内部控制面记录。后台和 API 的正常操作应该围绕 `app_id`，不是让运营手填 `project_id`。当前对应关系如下：

| 对应关系 | 当前实现 |
|---|---|
| App -> Project | `POST /admin/projects` 创建 app/project record；`POST /admin/devices/register` 也可以只传 `app_id` 并自动创建 backing project |
| App -> Provider/Service | 当前为 server default，所有 app 继承 ASR/LLM/TTS/chain/execution 和 services 配置 |
| App -> Hardware | 设备的 `board_model` 形成 hardware profile，用于后台 inventory 和后续 OTA targeting |
| App -> Device | 每个 device 必须有一个 `app_id`，`/admin/apps/{app_id}/devices` 查看该 app 的硬件 |
| App -> Order | `POST /admin/purchases` 记录 `app_id + device_id + plan_id + activation_code + customer_wallet` |
| App -> Customer | 钱包登录并激活设备后，customer 通过 `app_ids` 和绑定设备进入 app 用户列表 |

C 端用户闭环：

| 步骤 | API / 后台入口 | 结果 |
|---|---|---|
| 创建/选择 app | Apps -> Create app/project record 或 `POST /admin/projects` | 生成 app 运营记录；project 是 backing record |
| 预制硬件 | Fleet Setup -> Provision device 或 `POST /admin/devices/register` | 按 `app_id` 生成 device、provisioning token 和 activation code |
| 创建激活卡 | Fleet Setup -> Create purchase 或 `POST /admin/purchases` | 生成订单/激活 URL，可绑定 plan 和 buyer wallet |
| 设备注册 | `POST /device/register` | 设备换取 per-device bearer token |
| 用户登录/验证 | `/customer` -> wallet signature -> activation code | 创建/复用 customer，验证 wallet session，并绑定 activation code |
| App 用户管理 | Apps -> App users 或 `GET /admin/apps/{app_id}/customers` | 查看该 app 下的 C 端用户和已绑定设备 |
| 运营支持 | Device Detail / Usage / Events | 查看单设备 config、usage、logs、OTA 状态 |

本地 customer demo 可以把“购买硬件”也跑通：

```text
/customer -> Demo buy Ava hardware
  -> POST /customer/demo-purchase
  -> create_purchase()
  -> 自动 provision demo device
  -> 返回 activation_card
  -> 用户钱包签名登录
  -> POST /customer/activate
  -> 后台 Apps / Hardware / Orders 可看到激活后的 app-device-customer 关系
```

真实生产环境应由支付/履约后端调用 `/admin/purchases` 或服务 webhook 创建 purchase，而不是让 customer 直接调用 demo endpoint。`/customer/demo-purchase` 在 production mode 下默认禁用，除非显式设置 `AVA_DEVICEKIT_ENABLE_DEMO_CHECKOUT=1`。

Customer portal 的当前信息架构：

| 区域 | 显示时机 | 作用 |
|---|---|---|
| 左侧主区域 | 默认显示 | 产品说明、三步流程、购买硬件 demo |
| Buy hardware 横排区域 | 默认显示；移动端折叠为竖排 | 展示开发者/运营预设的产品、plan、board profile；C 端用户只能发起 checkout，并可选择是否 wallet lock |
| Activation card | demo buy 后或 URL 带 activation code 时 | 展示 activation code、device、app、wallet lock 状态和 activation URL |
| 右侧激活面板 | demo buy 后、activation URL 进入、或本地已有 customer session 时显示 | 钱包签名、激活码绑定、查看已绑定设备 |

这个布局的原则是：用户先看到“购买/获得硬件”，buy 后再出现“钱包验证/激活/设备列表”，避免 customer 入口看起来像单纯登录页。

后台会通过 `GET /admin/onboarding` 和 Dashboard 的 Setup checklist 返回当前闭环进度。这个 checklist 不依赖前端状态，而是由服务端根据 control plane、provider health、service plan、device registration、customer registration、activation、online session、developer services、firmware catalog 计算，用于告诉开发者/运营下一步该补什么。

框架级 DePIN/设备合约：

| 合约 | 文件 | 作用 |
|---|---|---|
| Device identity | `schemas/device_identity.schema.json` | 描述 `device_id`、设备公钥、challenge、signature、secure element profile，用于注册、认证、证明和可选链上设备身份 |
| Device telemetry | `schemas/device_telemetry.schema.json` | 描述设备 readings、transport、signature、location、metadata，用于 sensor oracle、reward claim、data anchor |
| Transport profile | `schemas/transport_profile.schema.json` | 描述 WebSocket、HTTP fallback、heartbeat、reconnect、ACK、OTA check、context snapshot 等 board port 能力 |
| Developer service | `schemas/developer_service.schema.json` | 描述后端服务类型、base URL、env secret、capabilities、allowlisted paths，用于 Solana RPC、payment、oracle、reward、data anchor、gasless tx、device ingest |

### 3.4 Provider Registry

Provider Registry 根据 runtime config 创建 AI pipeline。

| Provider | 框架接口 | 当前内置/支持 | 配置字段 |
|---|---|---|---|
| ASR | `ASRProvider` | Qwen realtime、OpenAI-compatible transcription、自定义 class | `provider`、`base_url`、`model`、`api_key_env`、`language`、`sample_rate`、`options` |
| LLM | `LLMProvider` | OpenAI-compatible chat、自定义 class | `provider`、`base_url`、`model`、`api_key_env`、`timeout_sec`、`options` |
| TTS | `TTSProvider` | mock、OpenAI-compatible speech、AliBL/CosyVoice stream、自定义 class | `provider`、`base_url`、`model`、`api_key_env`、`voice`、`format`、`timeout_sec`、`options` |
| Audio decoder | `AudioDecoder` | 部署/板级 hook | `decoder_class`、`options` |

配置原则：

| 规则 | 说明 |
|---|---|
| 不存储原始 secret | JSON 和后台前端只保存 env var name，例如 `DASHSCOPE_API_KEY` |
| 可热更新 provider 引用 | `/admin/runtime/providers` 会写入 control plane runtime config 并 apply 到当前进程 |
| 可自定义 class | `class` / `class_path` 指向 Python provider 实现 |
| 配置和健康检查分离 | `/admin/runtime` 看 effective config，`/admin/providers/health` 看 env 是否齐全 |

### 3.5 Adapter / Stream / Execution

| 类型 | 框架还是应用 | 作用 |
|---|---|---|
| ChainAdapter | 框架扩展点 | `get_feed`、`search_tokens`、`get_token_detail` 等基础链/市场数据能力 |
| MarketStreamAdapter | 框架扩展点 | 实时价格、kline、行情事件进入 app session |
| DeveloperService | 框架控制台能力 | 配置 proxy wallet、market API、payment API、order router 等服务引用 |
| TradeExecutionProvider | Ava Box app 层 | 市价/限价/托管钱包/纸交易等业务执行逻辑 |

这里的边界很重要：框架不应该内置“Ava Box 才需要的交易逻辑”。框架只提供“服务注册、adapter 接口、确认机制、设备协议”，具体交易/支付/portfolio/watchlist 放在 app 层。

## 4. 固件、硬件、硬件 UI 和后台的关系

### 4.1 固件运行时

C 侧运行时入口是：

```c
#include "ava_devicekit_runtime.h"
```

核心职责：

| API | 作用 |
|---|---|
| `ava_dk_runtime_init` | 初始化 app id、transport、protocol、audio 参数 |
| `ava_dk_runtime_set_transport` | 注入发送 JSON 的 transport 回调 |
| `ava_dk_runtime_on_network_event` | 把 Wi-Fi/网络状态变更写入 runtime state |
| `ava_dk_runtime_send_hello` | 启动后向服务端声明设备和音频能力 |
| `ava_dk_runtime_start_listening` / `stop_listening` | 控制 listen 状态 |
| `ava_dk_runtime_send_wake_detect` | 把唤醒词和当前页面 context 发给后台 |
| `ava_dk_runtime_build_listen_json` | 构造 listen/text/context JSON |

固件状态模型：

| 状态 | 含义 |
|---|---|
| `STARTING` | 启动中 |
| `WIFI_CONFIGURING` | Wi-Fi 配网 |
| `ACTIVATING` | 设备激活 |
| `IDLE` | 待命 |
| `CONNECTING` | 连接后台 |
| `LISTENING` | 录音/识别中 |
| `SPEAKING` | 播放 TTS |
| `UPGRADING` | OTA |
| `ERROR` | 错误状态 |

### 4.2 硬件 Port

框架不假设硬件长什么样。开发者需要在 board port 中实现：

| 硬件能力 | Board port 负责 | 发给框架的形式 |
|---|---|---|
| 按键/摇杆/旋钮 | GPIO 扫描、去抖、长按/短按识别 | `key_action` 或 `input_event` |
| 触摸屏 | x/y、gesture、focus 计算 | `input_event` + `semantic_action` |
| 麦克风 | 采样、编码、分帧 | binary audio 或 listen frame |
| 扬声器 | 解码 TTS 音频并播放 | 接收 TTS frame |
| 屏幕 | 初始化 LVGL/driver、渲染 display payload | shared UI screen vtable |
| Wi-Fi | 配网、连接、重连 | network event + hello |
| OTA | 下载、校验、烧录、重启 | OTA pull response |

开发模板：

```bash
PYTHONPATH=ava-devicekit/backend \
python3 -m ava_devicekit.cli init-board ./my-esp32-board
```

### 4.3 Shared UI Runtime

C 侧 UI 入口是：

```c
#include "ava_devicekit_ui.h"
```

它解决三个问题：

| 问题 | 机制 |
|---|---|
| 后台下发页面，设备如何渲染 | `ava_dk_ui_handle_display_json()` 分发到 screen vtable |
| 不同硬件输入如何统一 | `ava_dk_input_event_t` 和 `ava_dk_ui_emit_input_event()` |
| AI 怎么知道当前页面选中了什么 | 每个 screen 实现 `selection_context_json()` |

屏幕 vtable：

```c
typedef struct {
    void (*show)(const char *json_data, void *user);
    void (*key)(ava_dk_key_t key, void *user);
    int (*selection_context_json)(char *out, size_t out_n, void *user);
    void (*cancel_timers)(void *user);
    void *user;
} ava_dk_screen_vtable_t;
```

每个页面都应该输出 AI 可读 context：

```json
{
  "app_id": "ava_box",
  "chain": "solana",
  "screen": "spotlight",
  "cursor": 0,
  "selected": {
    "symbol": "SOL",
    "addr": "...",
    "chain": "solana",
    "source": "spotlight"
  },
  "visible_rows": [],
  "page_data": {
    "price": "123.45",
    "change_24h": "+3.1%",
    "kline_interval": "5m"
  }
}
```

这就是“AI 能回答当前选中哪个币、介绍这个币、收藏、买入、返回正确页面”的基础。

### 4.4 后台到设备的显示协议

后台 app 返回 `ScreenPayload`：

```json
{
  "type": "display",
  "screen": "spotlight",
  "data": {
    "title": "SOL",
    "price": "$123.45",
    "rows": []
  },
  "context": {
    "screen": "spotlight",
    "selected": {"symbol": "SOL"}
  }
}
```

设备收到后：

1. `shared_ui` 根据 `screen` 找到对应 screen vtable。
2. 调用 `show(json_data)` 渲染。
3. 用户移动 cursor、按键、说话时，页面输出最新 `selection_context_json()`。
4. 固件把 context 一起发回后台。

## 5. AI 链路

### 5.1 标准语音链路

```text
用户说话 / wake phrase
  -> 设备录音
  -> audio frames
  -> gateway audio buffer
  -> AudioDecoder 输出 PCM16
  -> ASRProvider 输出 transcript
  -> DeviceMessage(type=listen_detect, text=..., context=当前页面)
  -> HardwareApp.handle()
  -> deterministic route 或 LLM fallback
  -> ScreenPayload / ActionDraft / ActionResult
  -> TTSProvider 输出音频
  -> 设备播放
```

### 5.2 Deterministic Route 与 LLM Fallback

| 路由类型 | 适用场景 | 示例 |
|---|---|---|
| deterministic route | 明确动作、必须可靠、可被上下文直接决定 | 收藏当前币、买入当前币、切换 K 线、返回、确认订单 |
| LLM fallback | 开放问题、自然语言解释、无法硬编码的回答 | “介绍一下这个币”、“这个代币有什么风险”、“总结当前 portfolio” |
| hybrid | LLM 解析参数，动作仍走确定性确认 | “目标价降低 10% 挂 0.2 SOL 限价买单” |

高风险动作必须生成 `ActionDraft`：

```json
{
  "action": "trade.limit_buy",
  "chain": "solana",
  "summary": {
    "spend": "0.2 SOL",
    "target_price": "current * 0.9",
    "token": "..."
  },
  "risk": {"level": "high", "reason": "trade_execution"},
  "requires_confirmation": true
}
```

设备屏幕展示确认页，用户按确认后，后台才调用执行 provider。

### 5.3 Provider 配置示例

```json
{
  "providers": {
    "asr": {
      "provider": "qwen",
      "base_url": "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
      "model": "qwen3-asr-flash-realtime",
      "api_key_env": "DASHSCOPE_API_KEY",
      "language": "zh",
      "sample_rate": 16000,
      "options": {
        "context": "常用词：Ava、Solana、SOL、买入、卖出、watchlist"
      }
    },
    "llm": {
      "provider": "openai-compatible",
      "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
      "model": "qwen3.5-flash",
      "api_key_env": "DASHSCOPE_API_KEY",
      "options": {
        "temperature": 0.7,
        "max_tokens": 500
      }
    },
    "tts": {
      "provider": "alibl",
      "base_url": "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference/",
      "model": "cosyvoice-v3-flash",
      "voice": "longanyang",
      "format": "opus",
      "api_key_env": "DASHSCOPE_API_KEY"
    }
  }
}
```

环境变量：

```bash
export DASHSCOPE_API_KEY=...
export AVE_API_KEY=...
export AVE_SECRET_KEY=...
export AVE_PROXY_WALLET_ID=...
```

## 6. 后台前端功能

后台前端是 `http://127.0.0.1:8788/admin`，当前是无需前端构建步骤的 self-hosted operator dashboard。它不是面向第三方开发者的 SaaS 控制台，而是“一个硬件服务运营者”管理自己的 app、设备、C 端用户、provider、OTA 和日志的后台。

### 6.1 左侧导航分区

| 分区 | 页面 | 作用 |
|---|---|---|
| Command | Dashboard | server-wide 当前状态、关键指标、最近事件 |
| Command | Server Timeline | 全服务器事件日志，支持按 device/event filter |
| Product | Apps | 创建 app/project record、查看 CLI app template、查 app logs |
| Product | Providers | 查看和编辑 ASR/LLM/TTS/chain/execution provider config |
| Product | Services | 查看 backend service registry，测试 allowlisted service invoke |
| Hardware Ops | Fleet Setup | 创建 operator、按 app provision device、创建 purchase/activation card |
| Hardware Ops | Hardware | 按 app/hardware profile 查看 device inventory |
| Hardware Ops | Orders | 查看 purchase/order、wallet lock、activation card、plan、status |
| Hardware Ops | Device Detail | 查询单设备 config、diagnostics、runtime session、usage |
| Hardware Ops | Firmware | 发布固件、查看 firmware catalog、触发 OTA check |
| Customers | Customer Support | 运营 support/import customer；C 端入口是 `/customer` |
| Customers | Usage | 创建 service plan、分配 entitlement、记录/查看 usage |
| Support | Raw | 完整 dashboard JSON，用于 debug/support |

### 6.2 Dashboard

展示 server-wide 指标：

| 指标 | 来源 |
|---|---|
| provisioned devices | Control Plane devices count |
| active devices | active / online_seen devices |
| customers | customer count |
| live sessions | Runtime Manager connection state |
| providers ok | Provider health report |

还展示 Operating workflow：

```text
Configure app providers
  -> Create app/project and service plan
  -> Provision hardware before shipment
  -> C-end user activates device
  -> Monitor usage, logs, OTA and support
```

### 6.3 Apps

当前功能：

| 功能 | 说明 |
|---|---|
| Create app/project record | 创建 `project_id`、`app_id`、chain、owner |
| App relationship map | 展示 app -> project -> hardware -> device -> order -> customer，以及 providers/services 当前 scope |
| Code templates | 展示 `ava-devicekit init-app` 模板命令 |
| Current app records | 查看 control plane 中的 app/project |
| App users | 调用 `/admin/apps/{app_id}/customers` 查看 app 下的 C 端用户和绑定设备 |
| App logs | 按 app id 或 device id 聚合事件日志 |

开发者真正创建代码仍通过 CLI：

```bash
PYTHONPATH=ava-devicekit/backend python3 -m ava_devicekit.cli init-app ./my-device --type depin
```

后台中的 app record 用于运营和设备绑定，不直接生成代码。

### 6.4 Providers

当前支持编辑：

| Kind | 字段 | 说明 |
|---|---|---|
| `asr` | provider、model、base_url、api_key_env、class、language、sample_rate、options_json | 语音识别 |
| `llm` | provider、model、base_url、api_key_env、class、timeout_sec、options_json | 大模型 |
| `tts` | provider、model、base_url、api_key_env、class、voice、format、timeout_sec、options_json | 语音合成 |
| `chain` | provider、class、options_json | 链/数据 adapter |
| `execution` | provider/mode、base_url、api_key_env、secret_key_env、class、options_json | app 执行 provider，例如托管钱包/订单路由 |

行为：

| 操作 | 效果 |
|---|---|
| Load selected | 从当前 effective runtime 加载对应 kind 配置 |
| Save provider | POST 到 `/admin/runtime/providers`，写入 control plane runtime config，并 apply 到当前进程 |
| Runtime JSON | 查看 sanitized `/admin/runtime` |

安全规则：后台只保存 env var name，不保存 API key 原文。

### 6.5 Services

Services 是 developer backend service registry。它描述后台可调用或可检查的外部服务：

| 服务类型 | 示例 | 用途 |
|---|---|---|
| `custodial_wallet` | proxy wallet | 托管钱包余额、交易、订单状态 |
| `market_data_api` | market data | feed/search/detail/price stream |
| `payment_api` | payment provider | 支付、收款、invoice |
| `order_router` | order service | 限价单、市价单、状态查询 |
| `solana_rpc` | RPC provider | Solana RPC / account subscribe / transaction submit |
| `solana_pay` | payment request | Solana Pay transaction request、QR、wallet handoff |
| `oracle` | proof verifier | 设备 telemetry/proof 验证、eligibility signature |
| `reward_distributor` | reward API | DePIN reward check、claim draft、status |
| `data_anchor` | blob/proof anchor | 批量传感器数据、proof、reward summary 上链锚定 |
| `gasless_tx` | fee payer | gasless/sponsored transaction |
| `device_ingest` | telemetry ingest | WSS 上报、HTTP fallback、heartbeat、fanout |
| `custom` | 自定义 app 服务 | 开发者业务 API |

后台前端支持 allowlisted invoke test。只有服务 config 中允许的 path 才应该被调用。

### 6.6 Fleet Setup

用于硬件出厂/发货前准备。

| 功能 | 说明 |
|---|---|
| Create operator user | 创建运营/开发/查看者账号记录 |
| Provision device | 创建设备，生成 `provisioning_token` 和 `activation_code` |
| Rotate provisioning token | 重新生成注册 token |
| Revoke device | 吊销设备 token 和 provisioning token |
| Fleet inventory | 查看所有已 provision/registered/active 设备 |

Provision result 会返回：

| 字段 | 用途 |
|---|---|
| `device_id` | 硬件身份 |
| `provisioning_token` | 设备注册时换取 per-device bearer token |
| `activation_code` | C 端用户激活绑定设备 |

### 6.7 Customer Portal And Support

C 端用户路径：

```text
用户购买/收到硬件
  -> 打开激活入口
  -> 输入 activation code
  -> 后台创建或匹配 customer
  -> device.customer_id 被绑定
```

后台当前提供：

| 功能 | 说明 |
|---|---|
| `/customer` portal | C 端用户登录、验证 session、绑定 activation code |
| Create/import customer | 运营手工创建客户 |
| Activate purchased device | 用 activation code 绑定设备和 customer |
| Customers table | 查看 customer_id、email、wallet、status |

### 6.8 Device Detail

用于支持、排障和单设备管理。

| 功能 | 说明 |
|---|---|
| Open device | 读取 diagnostics |
| Resolved config | 查看/修改 AI name、language、wake phrases、voice、volume、app_id、firmware channel、wallet mode、risk mode |
| Diagnostics | 显示 device record、runtime state、connection、events、config、usage |
| Live runtime sessions | 查看在线 session 的 screen、context、outbox 等 |

Resolved config 合并顺序：

```text
default_device_config
  -> project.device_config
  -> device.config
```

### 6.9 Firmware

当前 OTA 是 pull-based：

| 功能 | 说明 |
|---|---|
| Publish firmware | 把服务器已有 `.bin` 复制到 configured OTA bin dir |
| Firmware catalog | 查看可用固件 |
| OTA response | `/ava/ota/` 返回 websocket URL、server_time、可选 update |
| Trigger OTA check | 后台 queue `ota_check` command，在线设备执行正常 OTA pull |

CLI：

```bash
PYTHONPATH=ava-devicekit/backend python3 -m ava_devicekit.cli firmware list --config runtime.local.json
PYTHONPATH=ava-devicekit/backend python3 -m ava_devicekit.cli firmware publish \
  --config runtime.local.json \
  --model scratch-arcade \
  --version 1.0.0 \
  --source ./build/app.bin
```

### 6.10 Usage

Usage 用于 C 端硬件服务的成本控制。

| 功能 | 说明 |
|---|---|
| Create service plan | 创建套餐、限制 ASR seconds、LLM tokens、TTS chars、API calls |
| Assign entitlement | 给设备分配 plan/status/expires_at |
| Record usage | 手工或设备上报 usage |
| Usage by device | 查看 usage、limits、limit status |

设备可通过 `/device/usage` 上报：

```json
{
  "metric": "llm_tokens",
  "amount": 120,
  "source": "device"
}
```

## 7. 主要后端 API

### 7.1 Device API

| Method | Path | 用途 |
|---|---|---|
| `POST` | `/device/register` | provisioning token 换 per-device bearer token |
| `POST` | `/device/activate` | activation code 绑定 C 端 customer |
| `GET` | `/device/config` | 设备拉取 resolved config |
| `POST` | `/device/boot` | 启动 app session |
| `POST` | `/device/message` | 发送 key/listen/input/confirm/cancel 等消息 |
| `GET` | `/device/state` | 获取当前 app state |
| `GET` | `/device/outbox` | 获取 session outbox |
| `POST` | `/device/usage` | 设备上报 usage |

### 7.2 Admin API

| Method | Path | 用途 |
|---|---|---|
| `GET` | `/admin` | 后台前端 |
| `GET` | `/admin/dashboard.json` | 后台聚合数据 |
| `GET` | `/admin/runtime` | sanitized effective runtime |
| `GET/POST` | `/admin/runtime/config` | 查看/更新 runtime config |
| `POST` | `/admin/runtime/providers` | 更新单个 provider/adapter/execution |
| `GET` | `/admin/providers/health` | provider health |
| `GET/POST` | `/admin/projects` | app/project records |
| `GET/POST` | `/admin/users` | operator users |
| `GET/POST` | `/admin/customers` | C 端 customers |
| `GET/POST` | `/admin/service-plans` | service plans |
| `GET/POST` | `/admin/usage` | usage report / record |
| `POST` | `/admin/devices/register` | provision device |
| `GET` | `/admin/registered-devices` | fleet inventory |
| `GET/POST` | `/admin/devices/{device_id}/config` | 设备配置 |
| `POST` | `/admin/devices/{device_id}/status` | 改状态 |
| `POST` | `/admin/devices/{device_id}/entitlement` | 分配套餐 |
| `GET` | `/admin/devices/{device_id}/diagnostics` | 单设备诊断 |
| `GET` | `/admin/events` | server timeline |
| `GET/POST` | `/admin/ota/firmware` | firmware catalog / publish |
| `POST` | `/admin/devices/{device_id}/ota-check` | 触发设备 OTA 检查 |
| `GET` | `/admin/developer/services` | backend services |
| `POST` | `/admin/developer/services/{service_id}/invoke` | allowlisted service invoke |

### 7.3 OTA API

| Method | Path | 用途 |
|---|---|---|
| `GET` | `/ava/ota/` | 兼容 OTA health 文本 |
| `POST` | `/ava/ota/` | 返回 OTA JSON，包括 websocket、server_time、firmware update |
| `GET` | `/ava/ota/download/{filename}` | 下载固件 bin |

## 8. 从 0 到 1 构建类似 Ava Box 的产品

以下流程适合构建一个“有屏幕、有输入、有语音、有后台、有 AI、有链上/业务动作”的硬件产品。

### 8.1 第一步：定义产品和 app contract

先写清楚：

| 问题 | 示例 |
|---|---|
| 产品是什么 | Solana AI payment terminal / token alert device / DePIN sensor / trading terminal |
| 用户是谁 | C 端硬件用户、运营者、开发者 |
| 设备形态 | 手表、掌机、触摸屏、机器人、桌面终端 |
| 输入方式 | 按键、摇杆、触摸、语音、传感器 |
| 输出方式 | 屏幕、扬声器、LED、震动 |
| AI 参与什么 | intent parsing、解释、摘要、风险提示、参数补全 |
| 哪些动作必须确认 | 支付、交易、签名、设备注册、隐私数据上传 |
| 数据源和链 | Solana RPC、market data API、自定义后端 |

产物：

| 文件 | 内容 |
|---|---|
| `manifest.json` | app id、chain、screens、actions、capabilities |
| `runtime.example.json` | provider、adapter、service、OTA、server 配置 |
| `screen_contracts` | 每个页面 payload schema、context schema、accepted actions |

### 8.2 第二步：生成 app 模板

```bash
cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32

PYTHONPATH=ava-devicekit/backend \
python3 -m ava_devicekit.cli init-app ./my-solana-device --type depin
```

可选模板：

| 类型 | 适用产品 |
|---|---|
| `starter` | 空白硬件 app |
| `payment` | 支付终端 |
| `alert` | Token / price alert device |
| `sensor` | 传感器注册/上报 |
| `depin` | Solana AI DePIN device |

### 8.3 第三步：实现 HardwareApp

最小接口：

```python
class HardwareApp:
    manifest: HardwareAppManifest
    context: AppContext

    def boot(self) -> ScreenPayload:
        ...

    def handle(self, message: DeviceMessage | dict) -> ScreenPayload | ActionDraft | ActionResult:
        ...
```

推荐路由结构：

```python
def handle(self, message):
    msg = DeviceMessage.from_dict(message) if isinstance(message, dict) else message

    if msg.context:
        self.context = msg.context

    if msg.type == "key_action":
        return self._handle_key_action(msg.action, msg.payload)

    if msg.type == "input_event":
        return self._handle_input_event(msg.payload, msg.context)

    if msg.type == "listen_detect":
        return self._handle_voice(msg.text, msg.context)

    if msg.type == "confirm":
        return self._confirm_pending_action(msg.payload)

    if msg.type == "cancel":
        return self._cancel_pending_action()

    return self._notify("Unknown action")
```

语音处理建议：

| 动作 | 路由方式 |
|---|---|
| “收藏这个币” | deterministic，依赖 `context.selected` |
| “买 0.1 SOL” | deterministic + 参数解析 + confirmation |
| “介绍这个币” | LLM fallback，带当前 page context |
| “切换到 portfolio” | deterministic navigation |
| “帮我下一个目标价低 10% 的限价买单” | hybrid：解析参数 -> `ActionDraft` -> confirm -> execution |

### 8.4 第四步：实现 ChainAdapter

如果你的产品需要链/市场数据，先实现基础 adapter：

```bash
PYTHONPATH=ava-devicekit/backend \
python3 -m ava_devicekit.cli init-adapter ./my-adapter
```

接口职责：

| 方法 | 返回 |
|---|---|
| `get_feed` | 首页列表、trending/new/gainer/loser 等 |
| `search_tokens` | 搜索结果 |
| `get_token_detail` | 单 token 详情 |

运行时配置：

```json
{
  "adapters": {
    "chain": {
      "provider": "custom",
      "class": "my_app.adapters.MyChainAdapter",
      "options": {
        "rpc_url": "https://...",
        "api_key_env": "MY_API_KEY"
      }
    }
  }
}
```

### 8.5 第五步：实现 app skills

把业务动作放在 app 层，不要塞进 framework core。

| 业务能力 | app skill 负责 |
|---|---|
| Watchlist | add/remove/list、本地或远端持久化 |
| Portfolio | position、value、PnL、cost basis |
| Trading | market/limit draft、参数解析、确认后执行 |
| Payment | invoice、recipient、amount、confirm、result |
| Sensor | device proof、heartbeat、on-chain registration |
| Notification | alert rule、trigger、ack |

Ava Box 参考路径：

| 路径 | 能力 |
|---|---|
| `backend/ava_devicekit/apps/ava_box_skills/watchlist.py` | watchlist |
| `backend/ava_devicekit/apps/ava_box_skills/portfolio.py` | portfolio |
| `backend/ava_devicekit/apps/ava_box_skills/trading.py` | trading draft |
| `backend/ava_devicekit/apps/ava_box_skills/execution.py` | execution provider |
| `backend/ava_devicekit/apps/ava_box_skills/paper.py` | paper trading |

### 8.6 第六步：设计屏幕和 context

每个页面都需要两个东西：

| 产物 | 目的 |
|---|---|
| display payload | 设备怎么展示 |
| context snapshot | AI 和后台怎么理解当前页面 |

页面设计模板：

| 页面 | 必须包含的 context |
|---|---|
| 列表页 | `screen`、`cursor`、`visible_rows`、当前选中 row |
| 详情页 | `screen`、`selected`、详情字段、当前 tab/kline interval |
| Portfolio | 当前持仓、cursor、账户总额、选择的 position |
| Confirm | action draft、spend/get、risk、request_id |
| Result | action result、tx/order id、status |
| Settings | 当前设置项、可修改范围 |

关键规则：

| 规则 | 原因 |
|---|---|
| 语音上行必须带 context | 否则 AI 不知道“这个币”指谁 |
| cursor 变化后 context 要更新 | 否则收藏/买入/介绍会作用到过期对象 |
| 返回栈应在 app/UI 层维护 | 否则从 portfolio 进 spotlight 返回可能回错页面 |
| 高风险动作页面必须展示 spend/get/risk | 用户需要物理确认具体动作 |

### 8.7 第七步：移植硬件

生成 board port：

```bash
PYTHONPATH=ava-devicekit/backend \
python3 -m ava_devicekit.cli init-board ./my-board-port
```

开发者需要实现：

| 模块 | 需要做的事 |
|---|---|
| transport | WebSocket/HTTP send JSON、接收 display/TTS/command |
| network | Wi-Fi connect/reconnect、状态上报 |
| input | 按键/摇杆/触摸 -> `ava_dk_input_event_t` |
| audio capture | 麦克风采样、OPUS/PCM frame、listen start/stop |
| audio playback | 播放 TTS 音频 |
| display | LVGL 初始化、screen vtable |
| OTA | 调 `/ava/ota/`、下载 bin、校验、烧录 |
| activation | 设备注册、保存 per-device token、拉取 config |

### 8.8 第八步：配置后台和 provider

复制 runtime config：

```bash
cp ava-devicekit/userland/runtime.example.json runtime.local.json
```

配置：

| 区域 | 必填 |
|---|---|
| server | `public_base_url`、`websocket_url`、ports |
| providers.asr | provider/model/base_url/api_key_env/language/sample_rate |
| providers.llm | provider/model/base_url/api_key_env/options |
| providers.tts | provider/model/base_url/api_key_env/voice/format |
| adapters.chain | provider/class/options |
| execution | mode/base_url/api_key_env/secret_key_env/proxy_wallet_id_env |
| services | proxy_wallet、market_data、solana_rpc、solana_pay、oracle、reward_distributor、data_anchor、gasless_tx、device_ingest 等 |

校验：

```bash
PYTHONPATH=ava-devicekit/backend \
python3 -m ava_devicekit.cli validate --config runtime.local.json
```

启动：

```bash
PYTHONPATH=ava-devicekit/backend \
python3 -m ava_devicekit.cli run-server \
  --host 0.0.0.0 \
  --port 8788 \
  --ws-port 8787 \
  --config runtime.local.json
```

打开后台：

```text
http://127.0.0.1:8788/admin
```

### 8.9 第九步：运营闭环

后台操作顺序：

| 步骤 | 页面 |
|---|---|
| 配置 ASR/LLM/TTS/chain/execution | Providers |
| 创建 app/project record | Apps |
| 创建 service plan | Usage |
| provision 设备 | Fleet Setup |
| 烧录固件，设备 register | Device API |
| 用户输入 activation code | `/customer` portal；运营兜底在 Customer Support |
| 查看设备在线和 config | Device Detail |
| 发布固件 | Firmware |
| 查 AI/业务日志 | Server Timeline / App logs |

## 9. Framework 当前支持能力清单

| 能力 | 当前状态 |
|---|---|
| 多设备 session | 支持，按 `device_id` 隔离 |
| HTTP device API | 支持 |
| Firmware WebSocket bridge | 支持，用于已部署设备协议适配 |
| Admin dashboard | 支持，无需前端 build |
| Control plane JSON store | 支持 users/projects/customers/devices/plans/usage/runtime config |
| Per-device bearer token | 支持 |
| Production admin/device auth | 支持 `AVA_DEVICEKIT_ADMIN_TOKEN`、`AVA_DEVICEKIT_DEVICE_TOKEN` |
| Provider config | 支持 ASR/LLM/TTS/chain/execution |
| Provider health | 支持 env presence / status |
| ASR provider boundary | 支持 Qwen realtime、OpenAI-compatible、自定义 class |
| LLM provider boundary | 支持 OpenAI-compatible、自定义 class |
| TTS provider boundary | 支持 mock、OpenAI-compatible、AliBL stream、自定义 class |
| Chain adapter | 支持 Solana、mock_solana、自定义 class |
| Market stream boundary | 支持 stream interface、mock、polling、AVE data WSS parser |
| Action draft / confirmation | 支持 |
| OTA firmware catalog/publish/download | 支持 |
| Developer services registry | 支持 |
| Usage / entitlement | 支持 |
| Generic screen/input/context contracts | 支持 |
| C firmware runtime API | 支持基础 runtime boundary |
| Shared UI C runtime API | 支持 screen vtable、input event、context snapshot |
| CLI templates | 支持 app/board/adapter/provider |

## 10. Ava Box 如何基于框架实现

| Ava Box 能力 | 使用的框架能力 | App 层实现 |
|---|---|---|
| Feed / Trending / New / Gainer / Loser | ChainAdapter + ScreenPayload | AvaBoxApp feed route |
| Spotlight | ChainAdapter token detail + context snapshot | Ava Box spotlight screen payload |
| Watchlist | DeviceMessage + app skill + local store | `ava_box_skills/watchlist.py` |
| Portfolio | app skill + paper/proxy wallet data | `ava_box_skills/portfolio.py` |
| Market Buy/Sell | ActionDraft + Confirm screen + execution provider | `trading.py` + `execution.py` |
| Limit Order | ActionDraft + order status + app state | app-level order logic |
| Voice “介绍这个币” | ASR + context + LLM fallback + TTS | AvaBoxApp voice route |
| Voice “收藏/买入这个币” | ASR + deterministic route + context.selected | AvaBoxApp action route |
| OTA | Framework OTA | firmware build output |
| 多设备后台 | Control Plane + Runtime Manager | app_id=`ava_box` |

## 11. 开发者需要改哪些，不能改哪些

### 11.1 应该在 app/userland 改

| 需求 | 修改位置 |
|---|---|
| 新产品页面 | `userland/ui/`、app UI package、screen contract |
| 新业务动作 | app `handle()` 和 app skills |
| 新链/数据源 | `userland/adapter/` 自定义 `ChainAdapter` |
| 新 provider | `userland/provider/` 自定义 ASR/LLM/TTS |
| 新硬件 | `userland/hardware_port/` board port |
| 新后台服务 | runtime `services[]` 和 app service client |
| 新套餐/设备配置 | Admin dashboard 或 Control Plane API |

### 11.2 一般不应该改 framework core

| Core 区域 | 什么时候才改 |
|---|---|
| `core/types.py` | 只有协议合约确实需要扩展 |
| `gateway/http_server.py` | 只有新增通用平台 API，而不是某个 app 专用功能 |
| `runtime/settings.py` | 只有新增通用 runtime 配置字段 |
| `providers/base.py` | 只有 provider 抽象不够表达 |
| `shared_ui/include/` | 只有所有硬件/app 都需要的新 UI primitive |

判断标准：如果只有 Ava Box 或某个产品需要，就放 app 层；如果所有 DeviceKit app 都需要，才进入 framework core。

## 12. 测试和验证

### 12.1 Python framework tests

```bash
cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32

PYTHONPATH=ava-devicekit/backend \
python3 -m pytest -q ava-devicekit/tests ava-devicekit/tests/conformance
```

### 12.2 编译检查

```bash
PYTHONPATH=ava-devicekit/backend \
python3 -m compileall -q ava-devicekit/backend ava-devicekit/examples ava-devicekit/tests
```

### 12.3 本地 server smoke test

```bash
PYTHONPATH=ava-devicekit/backend \
python3 -m ava_devicekit.cli run-server \
  --host 127.0.0.1 \
  --port 8788 \
  --ws-port 8787 \
  --config /tmp/ava_devicekit_runtime.real.json \
  --skill-store data/ava_box_app_state.json

curl http://127.0.0.1:8788/health
curl http://127.0.0.1:8788/admin/runtime
```

### 12.4 Device message smoke test

```bash
curl -X POST http://127.0.0.1:8788/device/boot \
  -H 'Content-Type: application/json' \
  -H 'X-Ava-Device-Id: dev_local' \
  -d '{}'

curl -X POST http://127.0.0.1:8788/device/message \
  -H 'Content-Type: application/json' \
  -H 'X-Ava-Device-Id: dev_local' \
  -d '{
    "type": "listen_detect",
    "text": "介绍一下这个币",
    "context": {
      "app_id": "ava_box",
      "chain": "solana",
      "screen": "spotlight",
      "selected": {
        "symbol": "SOL",
        "addr": "So11111111111111111111111111111111111111112",
        "chain": "solana"
      }
    }
  }'
```

## 13. 安全和部署边界

| 风险 | 处理方式 |
|---|---|
| Admin 未授权访问 | 生产设置 `production_mode=true` 和 `AVA_DEVICEKIT_ADMIN_TOKEN` |
| Device 冒充 | 使用 `/device/register` 发放 per-device bearer token |
| 设备被盗 | 后台 `revoke` 清空 token |
| Secret 泄露 | runtime/admin 只保存 env var name，不保存 key 原文 |
| 高风险动作误执行 | `ActionDraft` + 设备物理确认 |
| ESP32 私钥安全 | 默认把 ESP32 作为交互/确认层，不强制托管主资产私钥 |
| 外部服务滥用 | `developer_services` 使用 allowlisted paths |
| OTA 投毒 | 固件目录、版本、下载路径受控；生产应增加签名校验 |

## 14. 当前开发者心智模型

开发一个新 AI 硬件产品时，把它拆成下面几块：

| 你要回答的问题 | 对应工程位置 |
|---|---|
| 我的硬件有什么输入/输出？ | board port + shared UI |
| 我的页面长什么样？ | screen payload + screen vtable |
| AI 需要知道页面哪些数据？ | context snapshot |
| 用户会说哪些话、按哪些键？ | app `handle()` route |
| 哪些是确定性动作？ | app deterministic routes |
| 哪些需要 LLM？ | LLM fallback with context |
| 哪些动作需要确认？ | ActionDraft + confirm screen |
| 数据从哪里来？ | ChainAdapter / DeveloperService |
| 交易/支付/签名怎么做？ | app execution provider |
| 设备怎么运营？ | Admin dashboard + Control Plane |
| 固件怎么更新？ | OTA publish + device OTA pull |

最小可用闭环：

```text
manifest
  -> app boot screen
  -> board sends input_event/listen_detect with context
  -> backend routes to adapter/provider
  -> app returns screen/action draft
  -> device displays result
  -> high-risk action requires physical confirm
  -> admin can see device/log/provider/OTA/usage
```

这就是用 Ava DeviceKit 构建 Ava Box 类产品的核心路径。

## C 端购买、钱包签名与激活闭环

| 层 | 职责 | 当前实现 |
|---|---|---|
| Admin / Operator | 创建 app、服务计划、硬件库存、purchase/order、activation card | `/admin/projects`、`/admin/service-plans`、`/admin/devices/register`、`/admin/purchases` |
| Customer Portal | C 端用户钱包签名登录、输入激活码、查看自己设备 | `/customer`、`/customer/wallet/challenge`、`/customer/wallet/login`、`/customer/activate` |
| Control Plane | 保存 customers/devices/purchases/auth challenges/entitlements | `ControlPlaneStore` 本地 JSON store |
| Device Runtime | 设备使用自己的 device token 拉配置、发消息、上报 usage/OTA | `/device/register`、`/device/config`、`/device/message`、`/device/usage` |

### 关键对象

| 对象 | 说明 |
|---|---|
| `purchase` | 一次硬件购买/发货记录，包含 order ref、device id、app id、buyer wallet/email、plan id、activation URL。 |
| `activation_card` | 给 C 端用户的交付物，包含 activation code、activation URL、QR payload 和操作说明。 |
| `auth_challenge` | 钱包登录 nonce，5 分钟有效，使用后作废。 |
| `customer_token` | 钱包签名验证后发给浏览器的 portal session token，服务端只保存 hash。 |

### 推荐真实业务流程

| 步骤 | 动作 |
|---|---|
| 1 | 运营在 `/admin` 创建 app/project 和 service plan。 |
| 2 | 运营在 Fleet Setup 创建 purchase activation card；如果知道买家钱包，填写 `customer_wallet`。 |
| 3 | 工厂/设备用 `provisioning_token` 调 `/device/register`，换取 device token。 |
| 4 | 用户收到设备和 activation card，打开 `/customer`。 |
| 5 | 用户连接 Solana wallet，签名 Ava login message。 |
| 6 | 用户输入 activation code，后台校验 purchase wallet、绑定 device、激活 plan entitlement。 |
| 7 | 运营在 `/admin/apps/{app_id}/customers`、Device Detail、Usage、Events 查看售后状态。 |

如果 purchase 已指定 `customer_wallet`，则激活必须由同一个钱包签名登录后完成；单独泄露 activation code 不能绑定设备。
