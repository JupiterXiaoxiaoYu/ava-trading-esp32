# Xiaozhi × AVE 架构归属结论（2026-04-09）

> 状态：当前仓库证据下的架构归属判断（非“历史唯一真相”）
> 
> 适用范围：`/home/jupiter/ave-xiaozhi` 工作区（含多个子仓库）

## 0. 结论（先看这个）

- 本项目是 **Xiaozhi 基座 + AVE 业务层叠加** 的形态，而不是 AVE 独立替代 Xiaozhi。
- **Xiaozhi 负责**：设备联网/传输协议、会话连接生命周期、语音助手核心运行时。
- **AVE 负责**：交易产品层、AVE API/WSS 对接、交易相关 UI/状态机、对应服务端业务逻辑。
- 当前建议：**不做“大规模联网能力迁移”**；优先做边界内的轻量收敛与接口清理。

---

## 1. 三层拆分（按“可能归属”）

> 说明：以下为“高置信度归属 + 显式不确定点”。

### 1.1 Likely Xiaozhi base（基础底座）

1) 设备侧协议/联网/OTA
- `firmware/main/protocols/websocket_protocol.cc`
- `firmware/main/protocols/mqtt_protocol.cc`
- `firmware/main/ota.cc`
- `firmware/main/application.cc`
- `firmware/main/device_state_machine.cc`
- 原因：文件职责直接覆盖连接建立、协议收发、OTA 下发配置、设备运行状态机。

2) 服务端连接与会话运行时
- `server/main/xiaozhi-server/core/websocket_server.py`
- 原因：承载 WebSocket 接入与基础连接入口；更细粒度会话编排已与 AVE 能力发生交叉（见胶水层）。

3) MCP / IoT 通道基础能力
- `server/main/xiaozhi-server/core/handle/textHandler/mcpMessageHandler.py`
- `server/main/xiaozhi-server/core/handle/textHandler/iotMessageHandler.py`
- `server/main/xiaozhi-server/core/providers/tools/device_mcp/mcp_handler.py`
- `server/main/xiaozhi-server/core/providers/tools/device_iot/iot_handler.py`
- 原因：属于设备控制通用能力，不限于 AVE 交易场景。

### 1.2 Likely AVE custom layer（AVE 定制层）

1) AVE API / 交易 / 行情对接
- `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- `server/main/xiaozhi-server/plugins_func/functions/ave_trade_mgr.py`
- `server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`
- 原因：直接绑定 `data.ave-api.xyz`、`bot-api.ave.ai` 以及交易签名与订单流程。

2) 交易产品 UI 与状态表达
- `shared/ave_screens/ave_screen_manager.c`
- `shared/ave_screens/screen_feed.c`
- `shared/ave_screens/screen_spotlight.c`
- `shared/ave_screens/screen_confirm.c`
- `shared/ave_screens/screen_limit_confirm.c`
- `shared/ave_screens/screen_result.c`
- `shared/ave_screens/screen_portfolio.c`
- 原因：屏幕模型、交易路径、结果回显都显著是 AVE 产品语义。

3) AVE 专项测试资产
- `server/main/xiaozhi-server/test_ave_api_matrix.py`
- `server/main/xiaozhi-server/test_p3_trade_flows.py`
- `server/main/xiaozhi-server/test_ave_e2e.py`
- 原因：覆盖对象是 AVE 业务链路，而非 Xiaozhi 通用运行时。

### 1.3 Glue / integration layer（胶水整合层）

1) 输入动作到 AVE 业务动作映射
- `server/main/xiaozhi-server/core/connection.py`
- `server/main/xiaozhi-server/core/handle/textHandler/listenMessageHandler.py`
- `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
- `server/main/xiaozhi-server/core/handle/textHandler/tradeActionHandler.py`
- `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py`
- 原因：这些文件把“会话/监听/按键/语音命令”与 AVE 业务动作对接（如 AVE 路由与 AVE 运行态注入），属于平台与业务交界的混合所有权。

2) 设备展示通道与 AVE UI payload 对接
- `shared/ave_screens/ave_transport.c`
- `shared/ave_screens/ave_transport.h`
- `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`（display payload 生成）
- 原因：一端是服务端业务结构，一端是设备渲染协议，中间是结构适配。

3) 模拟器验证桥
- `simulator/mock/ws_client.c`
- `simulator/mock/run_screenshot_test.sh`
- `simulator/mock/mock_scenes/*.json`
- 原因：用于验证“服务器消息 -> 设备 UI”链路，但不是生产连接主链本身。

---

## 2. “联网能力”专题

## 2.1 本仓库里“联网能力”按层的含义

- Xiaozhi 基座层联网：设备拿到 OTA 配置后，按 WebSocket 或 MQTT 建链，并维护会话与心跳。
- AVE 业务层联网：服务端以 HTTP/WSS 对接 AVE 数据与交易服务，消费回包并转为 AVE UI/交易状态。
- 胶水层联网：把 Xiaozhi 会话通道承载的数据，路由/转换成 AVE 可执行动作和可渲染结果。

## 2.2 归属判断：谁拥有什么

- **Xiaozhi-owned（不应迁出）**
  - 设备到后端的协议连接能力（`firmware/main/protocols/*`）。
  - OTA 引导连接地址与协议入口（`firmware/main/ota.cc`，`server/.../core/api/ota_handler.py`）。
  - 服务端连接接入框架（`core/websocket_server.py`）。

- **Mixed / glue-owned（按接口边界协同演进）**
  - `core/connection.py`、`core/handle/textHandler/listenMessageHandler.py` 已承载 AVE 相关运行态与路由前置逻辑，不宜按“纯 Xiaozhi”或“纯 AVE”单边定义。

- **AVE-owned（可在 AVE 层收敛）**
  - AVE 第三方数据/交易 REST 与 WSS 客户端实现（`ave_tools.py`、`ave_trade_mgr.py`、`ave_wss.py`）。
  - AVE 交易状态机与交易屏渲染协议。

## 2.3 迁移判断

- 结论：**不建议做“大迁移”**（例如把设备主连接栈整体从 Xiaozhi 抽到 AVE）。
- 建议：做“轻量收敛”——在 AVE 侧统一自己的外部 API/WSS 访问边界、减少分散模块与重复状态，而保持 Xiaozhi 连接底座不动。

---

## 3. 当前风险 / caveats（显式不确定）

1) 固件桥接证据不完整
- 现有工作区可见 AVE 屏幕渲染、模拟器链路和服务端交易链路；但“真机端完整桥接闭环”证据并不充分。
- 参考：`docs/scratch-arcade-local-server-notes-2026-04-08.md` 已明确当前版本有硬件输入链路限制（如麦克风占位实现）。

2) 模拟器与真机漂移风险
- `simulator/` 提供较强可重复验证，但不等价于真机时序、网络抖动与硬件输入。
- 该风险在交易回报、按键边界行为上尤其需要持续抽样真机验证。

3) AVE 上游联网实现分散
- 当前 AVE 联网职责分布在 `ave_tools.py`、`ave_trade_mgr.py`、`ave_wss.py`，并与 handler 层交错调用。
- 结果是边界清晰度一般，后续维护成本偏高。

4) MCP vs 旧 IoT 双路径语义存在歧义
- `mcpMessageHandler.py` 与 `iotMessageHandler.py` 并存，且都接入设备控制相关流程。
- 在 AVE 场景下，哪些能力走 MCP、哪些走旧 IoT 路径，仍缺少单一权威说明。

5) 工作区并非单一干净 git 祖先
- 顶层 `ave-xiaozhi` 不是一个统一 `.git` 仓库；`firmware/`、`server/`、`simulator/` 等各自独立。
- 因此本结论的“血缘判断”主要基于命名、职责、文档与可见远端线索，而非单仓历史追溯。

---

## 4. 实操建议（下一步）

## 4.1 应继续保持 Xiaozhi-owned 的部分

- 设备联网与协议主栈：`firmware/main/protocols/`。
- OTA 下发连接参数与设备建链入口：`firmware/main/ota.cc` + `server/.../core/api/ota_handler.py`。
- 连接接入基础框架：`core/websocket_server.py`。

## 4.2 AVE 侧下一步应做的轻量收敛

- 在 `plugins_func/functions/` 与 AVE 已触达的 core seam（`core/connection.py`、`core/handle/textHandler/listenMessageHandler.py`、`core/handle/textHandler/aveCommandRouter.py`）联合收敛联网与路由边界：统一外部 API/WSS 客户端入口、错误码与重试策略。
- 减少 `ave_tools.py` 与 `ave_trade_mgr.py` 的状态散落，明确“行情态 / 交易态 / 展示态”的最小共享结构。
- 为 AVE 联网层补一页内部契约文档（请求/响应模型、超时、幂等、事件优先级）。

## 4.3 现在最重要的 bridge gap

- **首要缺口**：补齐“真机证据链”——至少覆盖一次端到端：
  1) 设备通过 OTA 获取连接参数；
  2) 建立 Xiaozhi 会话；
  3) 触发 AVE 交易流程；
  4) 收到并展示真实交易事件。
- 在此证据补齐前，不建议启动任何“大规模联网迁移”议题。

---

## 5. 证据来源（本次判断用到）

- `docs/ave-feature-map.md`
- `docs/scratch-arcade-local-server-notes-2026-04-08.md`
- `docs/pending-tasks.md`
- `firmware/README_zh.md`
- `server/README.md`
- `firmware/main/protocols/websocket_protocol.cc`
- `firmware/main/protocols/mqtt_protocol.cc`
- `server/main/xiaozhi-server/core/connection.py`
- `server/main/xiaozhi-server/core/websocket_server.py`
- `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- `server/main/xiaozhi-server/plugins_func/functions/ave_trade_mgr.py`
- `server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`
