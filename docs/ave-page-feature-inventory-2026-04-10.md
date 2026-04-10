# AVE 页面/功能统一总表（2026-04-10）

> 目的：把当前实现下的页面、功能、UI 区块、按键、服务端 action、语音直达、返回逻辑、测试覆盖统一收敛到一份总表里。  
> 原则：本文件以当前代码实现为准；旧文档保留不改。  
> 适用范围：`shared/ave_screens/`、`server/main/xiaozhi-server/core/handle/textHandler/`、`server/main/xiaozhi-server/core/handle/receiveAudioHandle.py`、`simulator/src/`、`simulator/mock/`。  
> 互补文档：`docs/simulator-ui-guide.md`、`docs/ave-feature-map.md`、`docs/product-review-table-2026-04-09.md`。

---

## 1. 页面总览矩阵

| 页面 | 页面角色 | 主要 UI 区块 | 主操作 | 返回方式 | 主要服务端链路 | 当前测试覆盖 |
|---|---|---|---|---|---|---|
| `FEED` | 首页榜单/来源浏览 | 顶栏模式、token 列表、底栏 affordance、本地 Explore 浮层 | 选 token、进详情、切来源、打开 Explore | 常驻首页；部分模式 `B` 回标准 FEED | `watch` / `feed_source` / `feed_platform` / `orders` | screenshot、payload、state-machine、keymap |
| `DISAMBIGUATION` | 同名币候选确认 | 顶栏说明、候选列表、overflow 提示、底栏说明 | 选候选、确认进入详情 | `B/LEFT -> back` | `disambiguation_select` / `back` | screenshot、state-machine |
| `SPOTLIGHT` | 单币详情与交易入口 | 资产身份区、价格与涨跌、K 线、风险/流动性/持有人信息、底栏交易 affordance | 买入、快速卖出、切币、切 K 线周期 | `B -> back`，并有本地 fallback timer | `buy` / `quick_sell` / `feed_prev` / `feed_next` / `kline_interval` / `back` | screenshot、payload、loading-timeout、server API 回归 |
| `CONFIRM` | 市价交易确认 | 标题、倒计时、交易参数、风险与说明、ack watchdog | 确认或取消交易 | `B` 取消；`Y` 先取消再去持仓 | `trade_action confirm` / `trade_action cancel` / `cancel_trade` / `portfolio` | screenshot、trade flow、surface/input sync |
| `LIMIT_CONFIRM` | 限价单确认 | 标题、倒计时、挂单参数、说明、ack watchdog | 确认或取消挂单 | `B` 取消；`Y` 先取消再去持仓 | `trade_action confirm` / `trade_action cancel` / `cancel_trade` / `portfolio` | screenshot、trade flow、surface/input sync |
| `RESULT` | 交易成功/失败终态 | 标题、结果主文案、金额/哈希或错误、下一步手动离开 | 查看结果、手动离开 | 除 `Y` 外任意键 `back`；`Y` 去持仓 | `back` / `portfolio` | screenshot、state-machine |
| `PORTFOLIO` | 持仓总览与 watch/sell | 钱包来源说明、P&L 汇总、持仓列表、底栏 affordance | 查看持仓详情、卖出当前持仓 | `B -> back`，并有本地 fallback timer | `portfolio_watch` / `portfolio_sell` / `back` / `portfolio` | screenshot、payload、state-machine |
| `NOTIFY` | 顶层解释型 overlay | 顶部通知条、等级颜色、标题/正文 | 只解释，不承载业务主操作 | 任意键关闭并消费按键 | 无页面内 outbound action | 行为覆盖存在；当前无单独 screenshot baseline |

---

## 2. 全局键与模拟器输入总表

### 2.1 AVE_KEY 全局原则

| 键 | 当前语义 | 说明 |
|---|---|---|
| `Y` | 全局去 `PORTFOLIO` | 由屏幕管理器统一拦截；若当前在 `CONFIRM/LIMIT_CONFIRM`，先发 `cancel_trade` 再发 `portfolio` |
| `FN/PTT` | 语音监听 start/stop | 不属于 `AVE_KEY_*`；模拟器用 `F1` 发送 `listen` JSON |
| `P` | 仅模拟器切 mock scene | 不属于产品键位契约 |
| `A` | 主确认/主进入 | 进入详情、确认选择、确认交易、买入 |
| `B` | 返回/取消/关闭局部层 | FEED 标准态例外：打开 Explore |
| `X` | 来源切换或卖出 | FEED 标准态是切来源；`SPOTLIGHT/PORTFOLIO` 是卖出 |
| `UP/DOWN` | 线性移动 | 列表移动、候选移动、K 线周期切换 |
| `LEFT/RIGHT` | 页内横向控制 | FEED 刷新/进入；SPOTLIGHT 切前后 token |

### 2.2 模拟器键盘映射

| 模拟器键盘 | 当前行为 |
|---|---|
| `Left Arrow` | `AVE_KEY_LEFT` |
| `Right Arrow` | `AVE_KEY_RIGHT` |
| `Up Arrow` | `AVE_KEY_UP` |
| `Down Arrow` | `AVE_KEY_DOWN` |
| `A` | `AVE_KEY_A` |
| `B` | `AVE_KEY_B` |
| `X` | `AVE_KEY_X` |
| `Y` | `AVE_KEY_Y` |
| `F1` 按下/松开 | `listen start/stop` |
| `P` | mock scene next |
| 终端输入 + Enter | 发送 `listen.detect` 文本，先走确定性 AVE router，未命中才进 LLM |

### 2.3 全局例外

| 场景 | 例外行为 |
|---|---|
| `NOTIFY` 可见时 | 任意键先 dismiss overlay，并消费该按键；`Y` 不会继续触发去持仓 |
| `PORTFOLIO` 页面按 `Y` | 仍会再次触发全局 `portfolio` action；不是 no-op |
| `FEED` 标准态按 `B` | 打开本地 Explore，不发服务端 action |

---

## 3. 服务端确定性 action 总表

### 3.1 `key_action`

| action | 典型来源页面 | 服务端行为 |
|---|---|---|
| `watch` | `FEED` | `ave_token_detail` |
| `buy` | `SPOTLIGHT` | `ave_buy_token(... in_amount_sol=0.1)` |
| `portfolio` | 全局 `Y` | `ave_portfolio` |
| `kline_interval` | `SPOTLIGHT` | `ave_token_detail(... interval=...)` |
| `quick_sell` | `SPOTLIGHT` | `ave_sell_token(... sell_ratio=1.0)` |
| `cancel_trade` | `Y` in `CONFIRM/LIMIT_CONFIRM` | `ave_cancel_trade` |
| `orders` | `FEED` Explore | `ave_list_orders(...)` |
| `feed_source` | `FEED` | `ave_get_trending(topic=...)` |
| `feed_platform` | `FEED` Explore Sources | `ave_get_trending(platform=...)` |
| `feed_prev` / `feed_next` | `SPOTLIGHT` | 调整 `feed_cursor` 后 `ave_token_detail` |
| `back` | 多页面 | 取消待确认交易，或按 `nav_from/search_session/feed_source` 恢复上下文 |
| `portfolio_watch` | `PORTFOLIO` | `ave_token_detail` |
| `portfolio_sell` | `PORTFOLIO` | `ave_sell_token(... holdings_amount=balance_raw, sell_ratio=1.0)` |
| `disambiguation_select` | `DISAMBIGUATION` | 设 cursor/state 后 `ave_token_detail` |

### 3.2 `trade_action`

| action | 来源页面 | 服务端行为 |
|---|---|---|
| `confirm` | `CONFIRM` / `LIMIT_CONFIRM` | `trade_mgr.confirm(trade_id)`；submit-only ack 走 FEED/NOTIFY 过渡，否则推 `RESULT` |
| `cancel` | `CONFIRM` / `LIMIT_CONFIRM` | `trade_mgr.cancel(trade_id)`，清 pending trade，并推 `FEED` |

### 3.3 语音/文本直达口令

| 口令类别 | 示例 | 结果 |
|---|---|---|
| 热门/刷新 | `看热门` / `刷新热门` / `热门代币` | `ave_get_trending` |
| 持仓 | `我的持仓` / `持仓` | `ave_portfolio` |
| 当前选中详情 | `看这个` / `详情` / `进入` | `ave_token_detail`，要求 trusted selection |
| 当前选中买入 | `买这个` | `ave_buy_token`，要求 trusted selection |
| 确认 | `确认` / `确认购买` / `执行` | `ave_confirm_trade` |
| 取消 | `取消` / `算了` / `不买了` | `ave_cancel_trade` |
| 返回 | `返回` / `回去` / `首页` / `回到热门` | 服务端 back 逻辑 |
| 指定 symbol 查看 | `看BONK` / `看看BONK` | 先 detail，找不到则 search |
| 指定 symbol 买入 | `买BONK` | 先 buy，找不到则 search |

### 3.4 可信选择（trusted selection）约束

- `看这个` / `买这个` / `这个能买吗` 这类指代命令，只有在本轮 payload 同时带了可信 `selection.screen + selection.token.addr + selection.token.chain` 时才成立。
- `DISAMBIGUATION` 明确是“未确认中间态”；客户端不会把候选项直接当成 trusted selection。
- `ORDERS` 是 browse-only；当前 listen.detect 不会把 orders 高亮项当成 trusted selection 发给服务端。

---

## 4. 页面附录（逐页）

## 4.1 FEED

### 页面职责
- 首页榜单浏览页。
- 承接标准热门、搜索结果、特殊来源、orders 浏览四种 FEED 模式。
- 标准态下承接本地 Explore 浮层。

### 本地 UI 组成
- 顶栏：模式标签（`FEED` / `SEARCH` / `SPECIAL` / `ORDERS` / `EXPLORE`）。
- 主区：token 列表或 Explore 条目。
- 底栏：按当前 surface/mode 变化的 affordance。

### 当前 FEED 子形态

| 子形态 | 是否独立 server screen | 作用 |
|---|---|---|
| `FEED` 标准态 | 否 | 默认榜单浏览 |
| `FEED_SEARCH` | 否 | 搜索结果浏览 |
| `FEED_SPECIAL_SOURCE` | 否 | 特殊专题/平台来源浏览 |
| `FEED_ORDERS` | 否 | 未完成订单浏览，browse-only |
| `EXPLORE_PANEL` | 否 | 标准 FEED 本地浮层入口 |
| `EXPLORE_SEARCH_GUIDE` | 否 | 只提示 `FN 说币名` |
| `EXPLORE_SOURCES` | 否 | 本地来源选择器 |

### 标准态按键

| 键 | 行为 | outbound |
|---|---|---|
| `UP/DOWN` | 本地循环移动高亮 | - |
| `A/RIGHT` | 看当前 token 详情 | `watch` |
| `LEFT` | 刷新当前 source | `feed_source` |
| `X` | 切到下一个标准 source | `feed_source` |
| `B` | 打开 Explore | - |
| `Y` | 全局去持仓 | `portfolio` |

### SEARCH / SPECIAL / ORDERS 特殊规则

| 模式 | 受限点 | `B` 行为 |
|---|---|---|
| `SEARCH` | `LEFT/X` 禁用，只弹本地 NOTIFY | 恢复记住的标准 source |
| `SPECIAL` | `LEFT/X` 禁用，只弹本地 NOTIFY | 恢复记住的标准 source |
| `ORDERS` | `A/RIGHT/LEFT/X` 禁用；browse-only | 发 `back` 并本地回 FEED |

### Explore 规则

| Explore 项 | `A/RIGHT` 行为 |
|---|---|
| `Search` | 进入本地 search guide，不发服务端 action |
| `Orders` | 发 `orders` |
| `Sources` | 打开本地 sources chooser |

### 主要进入/离开路径
- 进入：服务端推 `display.feed`。
- 离开：`watch -> SPOTLIGHT`，`Y -> PORTFOLIO`。
- 恢复：`SEARCH/SPECIAL` 用 `B` 恢复标准来源。

### 测试覆盖
- screenshot：`feed` / `feed_search` / `feed_special_source` / `feed_orders` / `feed_explore_panel` / `feed_explore_search_guide` / `feed_explore_sources` / `feed_orders_press_a` / `feed_orders_press_b`
- payload：`verify_ave_json_payloads.c`
- 行为/状态机：`verify_p3_5_minimal.c`

---

## 4.2 DISAMBIGUATION

### 页面职责
- 同名币/歧义搜索结果的候选确认页。
- 明确把“挑候选”与“真正进入 token 详情”分开。

### UI 组成
- 顶栏说明。
- 候选列表。
- 可选 overflow 提示：`Showing first 12. Refine search.`
- 底栏确认/返回说明。

### 按键

| 键 | 行为 | outbound |
|---|---|---|
| `UP/DOWN` | 本地移动候选 | - |
| `A/RIGHT` | 确认当前候选 | `disambiguation_select` |
| `B/LEFT` | 返回上一上下文 | `back` |
| `X` | 锁定提示，不执行选择 | - |
| `Y` | 全局去持仓 | `portfolio` |

### 进入/离开路径
- 进入：搜索命中多个候选，服务端推 `display.disambiguation`。
- 离开：确认后进 `SPOTLIGHT`；返回则恢复原上下文。

### 测试覆盖
- screenshot：`disambiguation` / `disambiguation_overflow`
- 行为：`verify_p3_5_minimal.c`

---

## 4.3 SPOTLIGHT

### 页面职责
- 单币详情页。
- 当前最重要的决策页与交易入口页。

### UI 组成
- 顶部：symbol、chain、身份信息。
- 中部：price、change、K 线。
- 辅助信息：risk、holders、liquidity 等。
- 底部：`BACK / SELL / BUY / PORTFOLIO` affordance。
- 若存在 `cursor/total`，显示 `<N/M>` 位置计数。

### 当前 K 线周期

| 内部 interval | 显示标签 |
|---|---|
| `s1` | `L1S` |
| `1` | `L1M` |
| `5` | `5M` |
| `60` | `1H` |
| `240` | `4H` |
| `1440` | `1D` |

### 按键

| 键 | 行为 | outbound |
|---|---|---|
| `B` | 返回，并启动 3s 本地 fallback | `back` |
| `LEFT` | 前一个 feed token | `feed_prev` |
| `RIGHT` | 后一个 feed token | `feed_next` |
| `A` | 买入当前 token | `buy` |
| `UP/DOWN` | 切 K 线周期 | `kline_interval` |
| `X` | 快速卖出 | `quick_sell` |
| `Y` | 全局去持仓 | `portfolio` |

### 运行时注意点
- `A/X` 在 loading guard 期间会被阻塞。
- `feed_prev/feed_next/kline_interval` 若长时间无响应，会由本地 timeout 释放 loading。
- 当前 live 行为：
  - `L1S` 允许 live 秒线直接重画。
  - `L1M` 只允许 poll-loop 刷新 chart，不允许 `k1` live 再覆写 chart。
  - `5M/1H/4H/1D` 保持静态 REST 图，不做 live takeover。

### 测试覆盖
- screenshot：`spotlight`
- payload：`verify_ave_json_payloads.c`
- loading guard：`verify_spotlight_loading_timeout.c`
- server API 回归：`test_ave_api_matrix.py`、`test_p3_batch1.py`、`test_surface_input_sync.py`、`test_trade_contract_fixes.py`

---

## 4.4 CONFIRM

### 页面职责
- 市价交易确认页。
- 承担防误触、倒计时和 ack watchdog。

### UI 组成
- 标题与交易方向。
- 交易数量 / 估值 / 滑点等参数。
- 倒计时。
- 状态解释与错误兜底。

### 按键

| 键 | 行为 | outbound |
|---|---|---|
| `A` | 确认交易；前 500ms 防误触 | `trade_action confirm` |
| `B` | 取消交易并回 FEED | `trade_action cancel` |
| `Y` | 全局先取消再去持仓 | `cancel_trade` + `portfolio` |

### 当前本地时序
- `A` 后启动 15s ack watchdog。
- 倒计时到 0 时，当前实现会本地切到失败 `RESULT` 文案。
- 倒计时到 0 不会自动发 `trade_action cancel`。

### 测试覆盖
- screenshot：`confirm`
- 服务端确认流：trade flow / input sync 测试

---

## 4.5 LIMIT_CONFIRM

### 页面职责
- 限价单确认页。
- 与 `CONFIRM` 类似，但承载挂单语义。

### 按键

| 键 | 行为 | outbound |
|---|---|---|
| `A` | 确认挂单；前 500ms 防误触 | `trade_action confirm` |
| `B` | 取消挂单并回 FEED | `trade_action cancel` |
| `Y` | 全局先取消再去持仓 | `cancel_trade` + `portfolio` |

### 当前本地时序
- 有 15s ack watchdog。
- 倒计时到 0 时当前实现同样是本地失败 `RESULT`。
- 不会自动发 `trade_action cancel`。

### 测试覆盖
- screenshot：`limit_confirm`
- 服务端确认流：trade flow / input sync 测试

---

## 4.6 RESULT

### 页面职责
- 交易成功/失败终态展示。
- 当前采用手动离开，不做自动跳转。

### UI 组成
- 标题。
- 成功态：数量、金额、tx_id。
- 失败态：错误原因。

### 按键

| 键 | 行为 | outbound |
|---|---|---|
| 任意非 `Y` 键 | 返回上一路由 | `back` |
| `Y` | 全局去持仓 | `portfolio` |

### 说明
- `RESULT` 没有本地 fallback timer。
- 当前 listen.detect 停留在 `RESULT` 时，也会显式带 `selection.screen="result"`。

### 测试覆盖
- screenshot：`result` / `result_fail`
- state-machine：`verify_p3_5_minimal.c`

---

## 4.7 PORTFOLIO

### 页面职责
- 钱包持仓总览页。
- 提供 watch 和卖出入口。

### UI 组成
- 顶部：钱包来源说明、P&L 汇总、P&L 原因说明。
- 中部：持仓列表。
- 底部：`BACK / SELL / DETAIL / PORTFOLIO` affordance。

### 关键字段

| 字段 | 用途 |
|---|---|
| `symbol` / `value_usd` | 展示 |
| `pnl_pct` / `pnl_positive` | 展示 |
| `contract_tail` / `source_tag` | 身份辅助显示 |
| `addr` / `chain` / `balance_raw` | 详情与卖出动作 |
| `wallet_source_label` / `pnl_reason` | 顶部解释信息 |

### 按键

| 键 | 行为 | outbound |
|---|---|---|
| `UP/DOWN` | 本地移动选中，clamp 不循环 | - |
| `A` | 查看选中持仓详情 | `portfolio_watch` |
| `X` | 卖出选中持仓（100%） | `portfolio_sell` |
| `B` | 返回，并启动 3s 本地 fallback | `back` |
| `Y` | 全局 portfolio action | `portfolio` |

### 测试覆盖
- screenshot：`portfolio`
- payload：`verify_ave_json_payloads.c`
- 状态机：`verify_p3_5_minimal.c`

---

## 4.8 NOTIFY

### 页面职责
- 顶层解释层，不承担主业务流。
- 用于提示、风险、超时、延迟结果等轻量说明。

### 行为

| 项目 | 当前实现 |
|---|---|
| 是否切换主页面 | 否 |
| 是否自动消失 | 否 |
| 按键行为 | 任意键关闭并消费该键 |
| 颜色 | `error` 红、`warning` 橙，其余绿 |

### 测试覆盖
- 行为覆盖存在于 state-machine / flow 测试链路中。
- 当前没有单独 screenshot baseline。

---

## 5. 测试覆盖总表

| 覆盖类型 | 当前覆盖内容 |
|---|---|
| 键盘映射测试 | 箭头/A/B/X/Y、遗留键不再映射、`F1` 的 start/stop state machine |
| JSON payload 测试 | FEED `watch`、PORTFOLIO `portfolio_watch/portfolio_sell`、SPOTLIGHT `buy/kline_interval/quick_sell` |
| 页面状态机测试 | FEED Explore、SEARCH/SPECIAL 恢复、ORDERS browse-only、`PORTFOLIO -> SPOTLIGHT -> back`、`RESULT -> Y` 等 |
| Spotlight loading 测试 | `feed_prev/feed_next/kline_interval` loading 阻塞与恢复 |
| 截图回归 | `feed`、`feed_search`、`feed_special_source`、`feed_orders`、`disambiguation`、`disambiguation_overflow`、`feed_explore_panel`、`feed_explore_search_guide`、`feed_explore_sources`、`feed_orders_press_a`、`feed_orders_press_b`、`spotlight`、`confirm`、`limit_confirm`、`result`、`result_fail`、`portfolio` |
| Python 服务端回归 | AVE API matrix、surface/input sync、trade contract fixes、batch1/live-kline 相关 |

### 当前未覆盖为独立截图基线的页面/状态
- `NOTIFY`
- 更细粒度的 confirm/limit timeout 本地失败态
- 更细粒度的 live `L1S/L1M` 动态视觉差异

---

## 6. 现有文档与实现的已知偏差

> 本节不修改旧文档，只记录当前已发现的偏差，便于后续同步。

| 文档 | 偏差点 | 当前以什么为准 |
|---|---|---|
| `docs/simulator-ui-guide.md` | `SPOTLIGHT` 的 `UP/DOWN` 仍写成只循环 `5M/1H/4H/1D` | 实现以 `L1S/L1M/5M/1H/4H/1D` 为准 |
| `docs/ave-feature-map.md` | K 线 REST 用法仍只写 `5/60/240/1440` | 实现已支持 `s1` 与 `1` |
| `docs/simulator-ui-guide.md` | `CONFIRM/LIMIT_CONFIRM` 倒计时结束写成“自动发 `trade_action cancel` 回 FEED” | 当前实现是本地切失败 `RESULT`，不自动发 `trade_action cancel` |
| `docs/ave-feature-map.md` | `PORTFOLIO` 行把 `Y` 写成 `(already here)` | 当前实现里 `Y` 仍会发全局 `portfolio` |
| `simulator/src/main.c` / `simulator/mock/ws_client.h` 注释 | 仍写“终端文本直接进 LLM” | 当前实现是先走 `listen.detect` + 确定性 AVE router，未命中才进 LLM |

---

## 7. 本文件的使用建议

- 要查“某个页面现在到底有什么键”，先看第 1 节和第 4 节。
- 要查“某个键会发什么 action”，先看第 2 节和第 3 节。
- 要查“这个行为有没有测试”，先看第 5 节。
- 要做产品审查或人工测试脚本，优先以本文件为入口，再下钻到：
  - `docs/simulator-ui-guide.md`
  - `docs/ave-feature-map.md`
  - `docs/product-review-table-2026-04-09.md`

