# Ava Box 产品文档

## 1. 产品定义

`Ava Box` 是一款面向链上生态的 AI 掌上交易设备。它把这些能力整合在一个产品里：

- 摇杆 + 按键的硬件交互方式
- 基于 `320x240` 屏幕的交易界面
- 语音唤醒与语音指令入口
- 基于页面上下文的确定性路由
- 实时 token 数据与 K 线
- `paper trading` 与 `real trading`
- portfolio、watchlist、signals、orders 等完整交易相关能力

这个产品要解决的核心问题是：大多数 crypto 工具把监控、发现、分析和执行拆散在太多网页标签、太多路径和太多心智负担里。Ava Box 希望把这些流程压缩进一个专用的掌机体验中。

产品的人格化角色是 `Ava`：一个以语音为入口、但以屏幕为真相源的链上交易助手。其背后的平台层是 `AVE Claw`，负责给这台设备提供能力栈和 Skills。

同时，因为我们的底层运行时建立在 `ESP32` 之上，这个项目本质上也可以理解为一个面向 `AVE Skills` 的智能硬件框架。也就是说，AVE 的交易系统并不只适用于当前这一台掌机，任何基于 ESP32 芯片的设备，包括手表、机器人、触摸显示屏以及其他嵌入式终端，都可以进一步接入到同一套 AVE 交易能力中。

## 2. 为什么它适合这次黑客松

这次黑客松把 `AVE Claw` 定义为一个面向链上生态的 AI 能力平台，重点包括：

- 资产监控
- 链上预警
- 自动化交易策略执行

`Ava Box` 是这个平台最清晰、最产品化的一种表达。它已经把这些能力真正做成了用户可使用的终端产品：

- 基于多来源的 token 发现
- 链上 signal 浏览
- watchlist 监控
- portfolio 跟踪
- AI 辅助的搜索与交易入口
- 带确认环节的 market / limit 执行路径
- 基于后端 Skills 的钱包分析能力

简单说：

- `Ava Box` 是产品
- `AVE Claw` 是支撑它的能力平台
- `AVE Skills` 是驱动这个产品、也可以继续复用给开发者应用的能力模块

## 3. 硬件形态

当前 Ava Box 使用的产品硬件画像是：

| 项目 | 当前配置 |
|---|---|
| 芯片 | ESP32-S3 |
| 存储 | 8MB Flash，8MB PSRAM |
| 屏幕 | 2.0 英寸，320x240 横屏 |
| 连接 | Wi-Fi，Bluetooth 5 |
| 电池 | 800mAh |
| 左侧 | 摇杆 / 方向控制 |
| 右侧 | 5 个可编程按钮 |
| 音频 | 麦克风、扬声器 |
| 接口 | USB Type-C、扩展口 |

对产品来说，真正重要的不只是硬件参数，而是交互结构：

- 左手负责持续导航
- 右手负责确认和动作
- 语音作为并行交互通道
- 屏幕始终是高风险操作的最终真相源

所以 Ava Box 的体验更像一个专用链上终端，而不是一个缩小版网页。

## 4. 控制模型

当前按键映射定义在 `shared/ave_screens/ave_screen_manager.h` 中：

| 物理控制 | 逻辑键 | 当前含义 |
|---|---|---|
| 摇杆左 | `AVE_KEY_LEFT` | 返回、刷新、或切到前一个 token，取决于当前页面 |
| 摇杆右 | `AVE_KEY_RIGHT` | 进入、打开详情、或切到下一个 token，取决于当前页面 |
| 摇杆上 | `AVE_KEY_UP` | 上移 / 上一个条目 / 上一个周期 |
| 摇杆下 | `AVE_KEY_DOWN` | 下移 / 下一个条目 / 下一个周期 |
| X | `AVE_KEY_X` | 快速卖出，或在某些页面中作为切链 |
| Y | `AVE_KEY_Y` | 全局 portfolio 快捷键；但在 Portfolio 页面内部用于切链 |
| A | `AVE_KEY_A` | 主确认 / 打开 / 买入动作 |
| B | `AVE_KEY_B` | 返回 / 取消 |
| FN | 系统 / 语音唤醒 / PTT | 语音唤醒、按住说话、系统语音入口 |

## 5. 当前产品页面结构

当前代码里的页面路由包括：

- `feed`
- `explorer`
- `browse`
- `spotlight`
- `confirm`
- `limit_confirm`
- `result`
- `portfolio`
- `notify`
- `disambiguation`

几个重要的实现事实：

- `Orders` 不是独立路由页面，而是 `Feed` 内的一个模式
- `Signals` 和 `Watchlist` 不是独立 screen 文件，而是 `Browse` 的两种模式
- `Portfolio detail` 不是独立页面，而是 `Portfolio` 内部的 detail 子视图
- `Notify` 是 overlay，不会替换当前主页面

## 6. 页面 / 功能 / 按钮总表

下面这张表是按当前代码整理出来的产品真相表。

| 页面 / 模式 | 页面用途 | 用户可见功能 | 按钮 |
|---|---|---|---|
| `Feed` - 标准首页 | 主市场发现页面 | 浏览 token 列表；进入 token 详情；刷新当前 source；切换标准 source；跳转到 Explorer | `UP/DOWN`：移动选择<br>`RIGHT` 或 `A`：打开当前 token 的 `Spotlight`<br>`LEFT`：刷新当前 source<br>`X`：在 `TRENDING / GAINER / LOSER / NEW / MEME / AI / DEPIN / GAMEFI` 间切换 source<br>`B`：打开 `Explorer`<br>`Y`：全局进入 `Portfolio`<br>`FN`：语音唤醒 / PTT |
| `Feed` - search / special source | 搜索结果页或特殊 source 列表 | 浏览结果；进入 token 详情；回到标准 feed source | `UP/DOWN`：移动选择<br>`RIGHT` 或 `A`：打开 `Spotlight`<br>`LEFT`：当前代码里禁用，会弹 notify<br>`X`：当前代码里禁用，会弹 notify<br>`B`：恢复到记忆中的标准 feed source<br>`Y`：全局进入 `Portfolio`<br>`FN`：语音唤醒 / PTT |
| `Feed` - orders mode | 在 Feed 内显示 limit orders | 只浏览挂单；退出回标准 feed | `UP/DOWN`：移动选择<br>`RIGHT`、`A`、`LEFT`、`X`：当前代码里禁用<br>`B`：发送 back 并退出 orders mode<br>`Y`：全局进入 `Portfolio`<br>`FN`：语音唤醒 / PTT |
| `Explorer` - menu | 顶层导航中心 | 进入 Search guide、Orders、Trading Mode、Sources、Signals、Watchlist | `UP/DOWN`：移动菜单选择<br>`RIGHT` 或 `A`：激活选中项<br>`LEFT` 或 `B`：回到缓存的 `Feed`<br>`Y`：全局进入 `Portfolio`<br>`FN`：语音唤醒 / PTT |
| `Explorer` - search guide | 语音搜索引导页 | 告诉用户直接说 token 名；设备上没有键盘式搜索输入 | `LEFT` 或 `B`：回到 Explorer 菜单<br>`Y`：全局进入 `Portfolio`<br>`FN`：语音唤醒 / PTT，用于搜索 token |
| `Explorer` - sources | Source / platform 选择页 | 加载 topic feed 和 platform feed | `UP/DOWN`：移动 source 选择<br>`RIGHT` 或 `A`：把该 source 加载到 `Feed`<br>`LEFT` 或 `B`：回到 Explorer 菜单<br>`Y`：全局进入 `Portfolio`<br>`FN`：语音唤醒 / PTT |
| `Explorer` - trading mode | 执行模式切换页 | 在 `real` 和 `paper` 之间切换 | `UP/DOWN`：选择模式<br>`RIGHT` 或 `A`：应用 `real` 或 `paper`<br>`LEFT` 或 `B`：回到 Explorer 菜单<br>`Y`：全局进入 `Portfolio`<br>`FN`：语音唤醒 / PTT |
| `Browse` - signals | 公开 signal 浏览页 | 浏览 signal 列表；进入 token 详情；切换 signal 链 | `UP/DOWN`：移动选择<br>`RIGHT` 或 `A`：打开所选 token 的 `Spotlight`<br>`X`：切换 signal 链，当前服务端实现是 `solana <-> bsc`<br>`LEFT` 或 `B`：返回 `Explorer`<br>`Y`：全局进入 `Portfolio`<br>`FN`：语音唤醒 / PTT |
| `Browse` - watchlist | 自选列表浏览页 | 浏览 watchlist；进入 token 详情；切换 watchlist 链 | `UP/DOWN`：移动选择<br>`RIGHT` 或 `A`：打开所选 token 的 `Spotlight`<br>`X`：切换 watchlist 链，当前服务端实现是 `all / solana / base / eth / bsc`<br>`LEFT` 或 `B`：返回 `Explorer`<br>`Y`：全局进入 `Portfolio`<br>`FN`：语音唤醒 / PTT |
| `Disambiguation` | 搜索歧义选择页 | 当多个 token 匹配时，选择正确资产 | `UP/DOWN`：移动光标<br>`RIGHT` 或 `A`：选择当前候选项并进入 token 详情<br>`LEFT` 或 `B`：返回<br>`X`：锁定，不可操作，会弹 notify<br>`Y`：全局进入 `Portfolio`<br>`FN`：语音唤醒 / PTT |
| `Spotlight` | Token 详情和操作页 | 显示 token 详情、K 线、价格、合约信息；切换周期；买入；卖出；切换前后 token | `LEFT`：切到当前 feed 上下文中的前一个 token<br>`RIGHT`：切到后一个 token<br>`UP`：切到下一个 K 线周期<br>`DOWN`：切到上一个 K 线周期<br>`A`：发起 market buy，进入 `Confirm`<br>`X`：发起 quick sell，进入 `Confirm`<br>`B`：返回，并带服务端恢复 + 本地 fallback timer<br>`Y`：全局进入 `Portfolio`<br>`FN`：语音唤醒 / PTT |
| `Confirm` | Market trade 确认页 | 查看已起草的 market trade，并显式确认或取消 | `A`：确认交易并等待服务端 ack<br>`B`：取消交易<br>`Y`：全局逻辑会先取消交易，再进入 `Portfolio`，但若 ack 已在等待中则忽略<br>`LEFT/RIGHT/UP/DOWN/X`：当前代码无页面动作<br>`FN`：语音唤醒 / PTT |
| `Limit Confirm` | Limit order 确认页 | 查看已起草的 limit order，并显式确认或取消 | `A`：确认 limit order<br>`B`：取消 limit order<br>`Y`：全局逻辑会先取消交易，再进入 `Portfolio`，但若 ack 已在等待中则忽略<br>`LEFT/RIGHT/UP/DOWN/X`：当前代码无页面动作<br>`FN`：语音唤醒 / PTT |
| `Result` | 交易结果页 | 展示 success、failure、timeout、cancellation 或 deferred / reconciled result | `任意键`：立即请求 back<br>`Y`：如果先被全局逻辑截获则仍按全局快捷键规则处理，否则 Result 页面本身按任意键退出<br>`FN`：语音唤醒 / PTT |
| `Portfolio` - holdings list | 持仓总览页 | 查看 holdings；切链；进入 Spotlight；进入 token activity detail；卖出持仓 | `UP/DOWN`：移动持仓选择<br>`RIGHT`：打开所选 token 的 `Spotlight`<br>`A`：打开 token activity detail 子视图<br>`X`：卖出当前 holding<br>`B`：返回，并带服务端恢复 + 本地 fallback timer<br>`Y`：切换 portfolio 链，当前服务端实现是 `solana / base / eth / bsc`<br>`FN`：语音唤醒 / PTT |
| `Portfolio` - activity detail | 单个 token 的交易聚合详情 | 展示 Buy Avg、Buy Tot、Sell Avg、Sell Tot、P&L、Open、First Buy、Last Buy、First Sell、Last Sell | `RIGHT`：从 detail 视图跳到该 token 的 `Spotlight`<br>`B`：通过服务端恢复 + 本地 fallback timer 返回 portfolio 列表<br>`Y`：当前 detail 视图无单独本地动作；仍在 portfolio 页面体系内<br>`FN`：语音唤醒 / PTT |
| `Notify` overlay | 非阻塞消息层 | 展示 info / warning / error / 交易状态消息，不替换当前页面 | `任意键`：先关闭 overlay；同一次按键不会继续透传到底下页面 |

## 7. 当前用户可见功能

按当前代码，Ava Box 已经具备以下产品能力。

### 7.1 发现与浏览

- trending feed
- topic feeds：`trending`、`gainer`、`loser`、`new`、`meme`、`ai`、`depin`、`gamefi`
- platform feeds：`pump_in_hot`、`pump_in_new`、`fourmeme_in_hot`、`fourmeme_in_new`
- token search
- 多结果 disambiguation
- signals 浏览
- watchlist 浏览

### 7.2 分析

- `Spotlight` 中的 token detail
- K 线周期切换
- 合约和 token 身份信息展示
- 在当前列表上下文中切换前后 token
- 后端风险检查路径

### 7.3 交易

- `paper trading`
- `real trading`
- market buy
- market sell
- quick sell
- limit buy
- order list
- cancel order
- 执行前确认的 guarded confirm flow

### 7.4 Portfolio 与钱包理解

- holdings list
- 按链查看 portfolio
- portfolio detail 中的单 token 交易聚合
- 后端 wallet overview
- 后端 wallet token list
- 后端 wallet history
- 后端 wallet PnL

### 7.5 实时能力

- live feed price updates
- live spotlight price updates
- live kline updates
- 通过 websocket 进行交易结果对账和补全

## 8. Ava Box 中的语音与 AI

AI 模型本身不是 UI 控制器。Ava Box 当前使用的是混合模式：

1. 已知产品动作走确定性路由
2. 开放式问题走 LLM fallback 和 tool calling

这点很重要，因为它让产品既快又安全。

### 8.1 当前唤醒词

`server/main/xiaozhi-server/config.yaml` 中配置的唤醒词包括：

- `Hey Ava`
- `Hi Ava`
- `Hello Ava`
- `Ava`
- 各种小写变体
- `Eva`、`Ai Wa` 等发音近似变体
- 中文近似，如 `你好Ava`、`嗨Ava`、`嘿Ava`、`艾娃`

### 8.2 当前语音已经能做什么

从当前 router 和 config 来看，语音已经支持：

- 打开 trending feed
- 打开 portfolio
- 打开 orders
- 打开 signals
- 打开 watchlist
- token search
- token detail
- 在 trusted selection 存在时处理 “watch this” / “buy this” 这类指代命令
- market buy drafting
- limit buy drafting
- 当交易参数不完整时进行追问
- confirm / cancel / back 流程

### 8.3 这意味着什么

这说明 Ava Box 不是简单的“屏幕上叠一层语音”。它是一个 screen-native 的设备产品，语音已经进入了产品逻辑：

- 语音可以直接驱动导航
- 语音可以直接进入交易 draft
- 但执行仍然必须经过 confirm screen

## 9. AVE Claw 和 AVE Skills 在产品里是怎么被用到的

在这份文档里，`Ava Box` 是产品主体。`AVE Claw` 和 `AVE Skills` 是它所调用的能力后端。

### 9.1 AVE Claw 作为产品后端

这台设备当前用到的 AVE 后端能力包括：

- token feeds
- token detail
- kline data
- contract / risk data
- live updates
- order 与 trade execution
- portfolio 与 wallet information

### 9.2 AVE Skills 在助手层中的使用

当前服务端暴露出来的 AVE 相关 callable tools 包括：

- `ave_get_trending`
- `ave_token_detail`
- `ave_risk_check`
- `ave_buy_token`
- `ave_limit_order`
- `ave_list_orders`
- `ave_cancel_order`
- `ave_sell_token`
- `ave_portfolio`
- `ave_confirm_trade`
- `ave_cancel_trade`
- `ave_back_to_feed`
- `ave_search_token`
- `ave_wallet_overview`
- `ave_wallet_tokens`
- `ave_wallet_history`
- `ave_wallet_pnl`

实际意义就是：

- Ava Box 用 AVE Skills 作为动作层和智能层
- 掌机界面是产品表面
- Skill 层未来可以继续复用到其他应用和开发者场景里

## 10. 当前架构，用一句话说清楚

当前代码库把 Ava Box 实现成：

- `shared/ave_screens/` 中的共享 screen system
- `server/main/xiaozhi-server/core/handle/textHandler/` 中的服务端路由和动作层
- `server/main/xiaozhi-server/plugins_func/functions/` 中的 AVE 市场 / 交易 / 钱包 tools
- `simulator/` 中的桌面模拟器
- `firmware/` 中的 ESP32 固件目标

这也是为什么它不只是一个 demo mockup：

- UI 已经存在
- 路由已经存在
- 交易逻辑已经存在
- 实时更新已经存在
- 语音逻辑已经存在
- 设备运行时已经存在

从平台角度看，这也意味着 Ava Box 不只是一个单一形态的产品，而是一个更大范围 ESP32 原生 AVE 硬件框架的第一种产品化落点。同一套能力栈未来可以继续迁移到不同的 ESP32 设备形态里，例如可穿戴屏幕、机器人、触摸显示设备以及其他嵌入式硬件终端，而不需要改变 AVE 交易后端本身。

## 11. Ava Box 和普通 crypto 产品的区别

这个产品有三个最突出的不同点。

### 11.1 它是一个专用设备，不是浏览器依赖物

Ava Box 是围绕掌机控制回路设计的，所以它的交互节奏和 web trading tools 不一样。

### 11.2 AI 已经进入产品逻辑

这个助手不是装饰性的。它已经能搜索、路由、追问缺失参数，并准备交易动作。

### 11.3 它有明确的执行护栏

产品不会因为“模型听懂了”就直接执行交易，而是通过 selection-aware routing 和 confirm surfaces 进行控制。

这点对 DeFi 和链上产品尤其重要。

## 12. 总结

`Ava Box` 应该是这次黑客松提交里最先被看到的产品主体。

它已经是一个真实、完整的链上掌机产品，具备：

- feed
- search
- signals
- watchlist
- spotlight
- portfolio
- orders
- paper mode
- real mode
- market buy
- limit buy
- voice routing
- guarded confirmation

`AVE Claw` 和 `AVE Skills` 让这个产品具备可扩展性。  
但对评委来说，最清晰的结论应该是：

`Ava Box` 是一台面向链上世界的 AI 掌上交易终端，而且它已经是设备原生产品，不是概念原型。
