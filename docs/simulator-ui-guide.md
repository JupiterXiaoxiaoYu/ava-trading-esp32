# AVE Xiaozhi 模拟器 UI 指南（按当前代码对齐）

> 硬件：Scratch Arcade 创客版 ESP32-S3（320x240 横屏）  
> 模拟器：SDL2 窗口 + WebSocket（`ws://127.0.0.1:8000`）  
> 最后更新：2026-04-10（对齐 `shared/ave_screens/`、`simulator/src/main.c`、`simulator/src/sim_keymap.c`、`aveCommandRouter.py`、`receiveAudioHandle.py`、`keyActionHandler.py`、`tradeActionHandler.py`、`ave_tools.py`、`ave_wss.py`）

---

## 1) 按键映射（硬件 AVE_KEY vs 模拟器键盘）

### 1.1 硬件按键 → AVE_KEY

| 硬件键 | GPIO | AVE_KEY |
|---|---:|---|
| D-pad Left | 13 | `AVE_KEY_LEFT` |
| D-pad Right | 15 | `AVE_KEY_RIGHT` |
| D-pad Up | 16 | `AVE_KEY_UP` |
| D-pad Down | 14 | `AVE_KEY_DOWN` |
| X 按钮 | 9 | `AVE_KEY_X` |
| Y 按钮 | 4 | `AVE_KEY_Y` |
| A 按钮 | 39 | `AVE_KEY_A` |
| B 按钮 | 5 | `AVE_KEY_B` |

### 1.2 模拟器键盘 → AVE_KEY

| 键盘输入 | 触发 AVE_KEY | 说明 |
|---|---|---|
| `←`（Left Arrow） | `AVE_KEY_LEFT` | 方向左 |
| `↑`（Up Arrow） | `AVE_KEY_UP` | 方向上 |
| `→`（Right Arrow） | `AVE_KEY_RIGHT` | 方向右 |
| `↓`（Down Arrow） | `AVE_KEY_DOWN` | 方向下 |
| `X` | `AVE_KEY_X` | 对应 X 按钮 |
| `Y` | `AVE_KEY_Y` | 对应 Y 按钮（全局快捷） |
| `A` | `AVE_KEY_A` | 对应 A 按钮（确认/详情） |
| `B` | `AVE_KEY_B` | 对应 B 按钮（返回/取消） |
| `P` | (无 AVE_KEY) | 仅模拟器：切换 `mock/mock_scenes` |
| 终端输入 + Enter | (文本命令) | 语音替代：模拟器把整行文本直接发给服务端（见 §1.4） |

**重要提示**
- 方向只由四个方向键映射，其他字母不会触发方向动作。
- `A/B/X/Y` 各自 1:1 映射到对应的 AVE_KEY，模拟器不再复用其他字母。
- `X` 没有第三种隐藏语义：它只在标准 FEED 表示“切换来源”，在 `SPOTLIGHT` / `PORTFOLIO` 表示“卖出”；其余页面不是禁用，就是只弹解释型 NOTIFY。
- `P` 继续作为仅模拟器的 mock 场景切换器。
- 终端输入保持文本命令/语音替代的角色，触发服务端逻辑。

### 1.3 FN（GPIO0）系统/语音键

`FN`（GPIO0）对硬件来说是系统/语音快捷键。模拟器当前把 `F1` 作为 FN/PTT，并走协议级 `listen` 状态切换：

| 键盘输入 | 行为 | 说明 |
|---|---|---|
| `F1` 按下 | FN/PTT start | 发送 `{"type":"listen","state":"start","mode":"manual"}` |
| `F1` 松开 | FN/PTT stop | 发送 `{"type":"listen","state":"stop","mode":"manual"}` |

说明：
- `F1` **不是** `AVE_KEY_*`，不会和方向键或 `A/B/X/Y` 冲突。
- `F1` 走独立的 listen JSON 协议事件，不复用 stdin 文本注入链路。
- 若宿主系统或 IDE 抢占 `F1`，SDL 侧可能收不到该按键。

### 1.4 终端文本命令（语音替代）与路由（已落地）

模拟器会启动一个 stdin 线程：你在终端输入一行文本并回车后，会通过 WebSocket 发送到服务端（用于绕过“麦克风 + ASR”）。在服务端，文本会先尝试走 `aveCommandRouter.try_route_ave_command()` 的“命令直达”路由；命中后会直接调用对应工具函数并推送 display（不经过 LLM）。未命中则返回 `False`，交由后续文本处理链路继续处理；在进入 LLM 对话前，`receiveAudioHandle.startToChat()` 会先基于本次上行 payload 的 `selection` 构造一份 authoritative `turn_ave_context`，再由 `connection.chat()` 临时注入成 `[AVE_CONTEXT]...[/AVE_CONTEXT]` 提示块，帮助模型理解“这个/确认/取消”等页面内指代。

**当前 client-authoritative 合约**
- 本轮命令里的 `selection` 是命令时刻的唯一选中真相源（source of truth）。
- 服务端不会与模拟器做“持续 cursor/selection 同步”；没有单独的常驻 cursor push 通道。
- `feed_cursor` 仍会出现在本轮 `ave_context` 里；只有当本轮 `selection.screen=="feed"` 且同时带了 `selection.cursor` 时，它才会反映客户端本轮显式选中的 feed 光标，否则保留为服务端 feed UI 快照。`portfolio_cursor` 只存在于服务端内部 state，不在当前 emitted context schema 中。两者都不会被重新解释成这轮语音里的“这个”。
- 对于 `"看这个"` / `"买这个"` / `"这个能买吗"` / `"这只币怎么样"` / `"聊聊这只币"` 这类 deictic 指令，只有本轮同时带了显式 `selection.screen + selection.token.addr + selection.token.chain` 才算可信 selection；如果缺任一字段（或 payload 畸形），行为会 fail closed，而不是回退到陈旧的 `ave_state.current_token`、服务端旧 `screen` 或 cursor，更不会把缺失的 `chain` 默认为 `solana`。当前真实 client emitter 会直接省略整段 `selection`，不会伪造一个 `token.chain="solana"` 的 listen payload。
- `DISAMBIGUATION` 是刻意的“未确认中间态”：客户端此时只会发 `selection.screen="disambiguation"` 与 cursor，不会把候选 token 当成 trusted selection；只有 `A/RIGHT` 触发 `disambiguation_select` 后，才进入真正的 token 详情。

**当前已支持的直达口令（按 `aveCommandRouter.py`）**

| 口令（归一化后） | 触发 | 约束/说明 |
|---|---|---|
| `看热门` / `刷新热门` / `热门代币` | `ave_get_trending` | 推 FEED |
| `我的持仓` / `持仓` | `ave_portfolio` | 推 PORTFOLIO |
| `看这个` / `详情` / `进入` | `ave_token_detail` | 依赖本轮显式 `selection.screen + selection.token.addr + selection.token.chain`；缺少任一字段时直接拒绝 |
| `买这个` | `ave_buy_token` | 仅在本轮 `selection.screen=spotlight` 且同时带显式 `selection.token.addr + selection.token.chain` 时允许 |
| `确认` / `确认购买` / `执行` | `ave_confirm_trade` | 仅在 `screen=confirm/limit_confirm` 且存在 pending trade |
| `取消` / `算了` / `不买了` | `ave_cancel_trade` | 仅在 `screen=confirm/limit_confirm` 且存在 pending trade |
| `返回` / `回去` / `首页` / `回到热门` | “返回”逻辑 | confirm/limit_confirm：先取消交易；否则按 `nav_from` 回 PORTFOLIO 或按 `feed_source/feed_platform` 回 FEED |
| `看<symbol>` / `看看<symbol>`（示例：`看BONK`） | 先 token_detail / 否则 search | `<symbol>`：`[A-Za-z][A-Za-z0-9._-]{1,15}` |
| `买<symbol>`（示例：`买BONK`） | 先 buy / 否则 search | 同上；若 symbol 不在 state 的 feed token map 中则走 search |

**输入格式补充**
- 如果终端输入的是一个 JSON 字符串形如 `{"content":"看热门"}`，路由会优先抽取 `content` 字段作为口令（用于对齐某些 STT 上行格式）。
- 口令会做一次“去标点/长度处理”的归一化（具体规则见 `remove_punctuation_and_length`），因此建议使用短句、少标点的指令式输入。

**AVE context（`conn.ave_context`）语义（已落地，并用于 LLM handoff）**

`try_route_ave_command()` / `startToChat()` 每次都会基于**当前上行命令**刷新 `conn.ave_context = build_ave_context(conn, selection_payload=...)`，其结构用于让后续链路（尤其是 LLM handoff）拿到“这一轮 authoritative UI 上下文”。当前 schema 如下（以 `aveCommandRouter.build_ave_context()` 为准）：

```json
{
  "screen": "feed|disambiguation|spotlight|confirm|limit_confirm|result|portfolio",
  "nav_from": "portfolio|",
  "current_token": null,
  "has_trusted_selection": false,
  "selection_source": "",
  "pending_trade": {"trade_id":"...","trade_type":"","action":"TRADE","symbol":"TOKEN","amount_native":"","amount_usd":""},
  "feed_source": "trending|gainer|loser|new|meme|ai|depin|gamefi",
  "feed_platform": "",
  "feed_cursor": 0,
  "feed_visible_symbols": ["BONK","..."],
  "allowed_actions": ["back_to_feed","open_feed","open_portfolio","search_symbol","watch_current", "..."]
}
```

注意点：
- `current_token` 只会来自**本轮同时带 `selection.screen + selection.token.addr + selection.token.chain` 的显式选择**；如果本轮没有可信 selection，它就是 `null`，不会从陈旧的 `ave_state.current_token`、`feed_cursor` 或任何服务端内部 cursor（例如 `portfolio_cursor`）反推。
- `has_trusted_selection=true` / `selection_source="explicit"` 才表示当前回合真的带了可信 token 选择；缺 `selection.screen`、缺 `selection.token`、缺 `selection.token.addr` 或缺 `selection.token.chain` 都不算 trusted selection，因此 deictic 行为默认 fail closed。
- `ORDERS`（`screen=feed` 且 `mode=orders`）是 browse-only：客户端在该模式下的 `listen.detect` 会**刻意省略整段 `selection`**（即使本地有高亮项），避免 `"看这个"/"买这个"` 等指代命令借用 FEED trusted selection 造成“口令绕过”。
- `feed_cursor` 仍会保留在 context 里，但只有 `selection.screen=="feed"` 时才会吸收本轮 `selection.cursor`；其他 screen 下它仍表示服务端 feed 界面状态快照，不是语音指代的 authority，也没有持续 client->server 同步保证。`portfolio_cursor` 当前不会出现在 emitted `ave_context` schema 中。
- `allowed_actions` 是“基于当前 screen + 本轮是否有 trusted selection/pending_trade”的集合；它描述“当前页面理论上允许的意图”，不是强制执行的权限系统。
- 未命中直达口令时，这份 context 会在 `connection.chat()` 中以临时消息方式注入 LLM 上下文，并在本轮结束后清理，不会长期污染对话历史。

---

## 2) 各页面当前按键行为（以代码为准）

说明：页面按键触发后，客户端会发送 `key_action` 或 `trade_action` JSON 给服务端；服务端分别由 `keyActionHandler.py` / `tradeActionHandler.py` 处理，属于“绕过 LLM 的确定性链路”，用于保证 UI 响应及时可预测。

## S1 · FEED（feed）

### 当前键行为

| AVE_KEY | 行为 | 发送到服务端 |
|---|---|---|
| `UP` | 选中上一项（循环） | - |
| `DOWN` | 选中下一项（循环） | - |
| `RIGHT` | 标准/SEARCH/特殊来源：进入所选 token 详情；ORDERS：禁用 | 标准/SEARCH/特殊来源：`{"type":"key_action","action":"watch","token_id","chain"}`；ORDERS：- |
| `A` | 同 `RIGHT` | 同上 |
| `LEFT` | 标准：刷新当前来源（不切换索引）；SEARCH/特殊来源/ORDERS：禁用（NOTIFY 解释） | 标准：`{"type":"key_action","action":"feed_source","source":...}`；其他：- |
| `X` | 标准：切换来源（trending/gainer/loser/new/meme/ai/depin/gamefi）；SEARCH/特殊来源/ORDERS：禁用（NOTIFY 解释） | 标准：同上（source=下一项）；其他：- |
| `B` | 标准：打开 Explore 面板；SEARCH/特殊来源：恢复记住的标准来源并刷新；ORDERS：退出 orders | SEARCH/特殊来源：`feed_source`；ORDERS：`{"type":"key_action","action":"back"}` |

### FEED 特殊模式限制
- 顶栏会显示模式标识（`FEED` / `SEARCH` / `SPECIAL` / `ORDERS`），避免用户靠记忆判断“为何有些键不可用”。
- 底栏提示（affordance）用于降低 `X/Y` 歧义：
  - 标准 FEED：`< REFRESH  X SOURCE`（`X` 明确是“切换来源”） + `> DETAIL  Y PORTFOLIO`（`Y` 作为全局去持仓入口显式呈现）。
  - `SEARCH`/特殊来源：`< X SOURCE OFF` + `> DETAIL  Y PORTFOLIO`。
  - `ORDERS`：`Orders: view only` + `B BACK  Y PORT`（browse-only，保留全局 `Y`，同时明确 `A/RIGHT/X` 都没有新增动作）。
- `SEARCH`（`source_label=SEARCH` 或 `mode=search`）：`LEFT`/`X` 禁用；`B` 恢复记住的标准来源（若无则回落默认）并刷新；`A/RIGHT` 仍可进详情。
- 从 `FEED_SEARCH` 进入 `SPOTLIGHT` 或 `DISAMBIGUATION` 后，服务端会保存 `search_session`（query / items / cursor）；随后 `back` 会优先恢复这份搜索会话，而不是直接丢回普通热门源。
- 特殊来源（非标准 `source_label`，且非 `SEARCH`/`ORDERS`）：行为同 `SEARCH`（`LEFT`/`X` 禁用，`B` 恢复标准来源并刷新，`A/RIGHT` 可进详情）。
- `ORDERS`（`mode=orders`）：浏览-only 列表，`LEFT`/`X` 禁用且会弹 NOTIFY；`A/RIGHT` 禁用；`B` 退出 orders 模式；同时 listen/text deictic selection 被禁用（不会 emit trusted `selection`）。

### FEED Explore（标准首页本地浮层）
- Explore 只在标准 FEED 首页可用；`B` 打开轻量面板，不切屏、不刷新来源，也不移动当前高亮 token。
- 面板条目固定为 `Search / Orders / Sources`。
- `UP/DOWN` 移动条目；`A/RIGHT` 激活；`B/LEFT` 本地关闭；`Y` 仍按全局规则进入 `PORTFOLIO`；`X` 没有新增语义。
- `Search` 只展示引导文案 `FN 说币名`，`F1/FN` 继续使用既有手动 `listen start/stop` 语义。
- `Orders` 复用现有 orders 列表入口，进入后仍是 browse-only。
- `Sources` 只打开浅层来源选择器，用现有 FEED topic/platform 加载逻辑；不是新的顶层 screen，也不改变 `feed_platform`/返回语义约定。
- Explore 中的 `X` 继续冻结：不会被重新解释成确认、刷新或别的第三种动作。

### 模拟器可直接触发
- 上下左右箭头对应 `UP`/`DOWN`/`LEFT`/`RIGHT`，`A/B/X/Y` 可直接触发对应 `AVE_KEY` 行为。
- 在标准 FEED 中可用 `B -> Explore`，再用 `A` 或方向键进入 `Search` / `Orders` / `Sources`。
- `P` 继续用于模拟器 mock 场景切换；终端文本命令仍是语音替代。

---

## S1.5 · DISAMBIGUATION（disambiguation）

### 当前键行为

| AVE_KEY | 行为 | 发送到服务端 |
|---|---|---|
| `UP` | 上移候选项 | - |
| `DOWN` | 下移候选项 | - |
| `LEFT` | 返回上一个页面 | `{"type":"key_action","action":"back"}` |
| `RIGHT` | 确认当前候选项 | `{"type":"key_action","action":"disambiguation_select","token_id","chain","cursor","symbol"}` |
| `A` | 同 `RIGHT` | 同上 |
| `B` | 返回上一个页面 | `{"type":"key_action","action":"back"}` |
| `X` | 锁定提示 | 本地 `NOTIFY`：`Locked / Use A to confirm a choice.` |

### 当前 payload / 状态约定
- 每个候选项至少带 `symbol` / `chain` / `contract_tail` / `token_id`，并可附带 `source_tag`。
- 顶栏 `cursor` 与可选的 `total_candidates` / `overflow_count` 一起表达“当前只是候选选择”，不是最终 token 上下文。
- 若同名结果超过本地可见上限，页面会显示 `Showing first 12. Refine search.`，要求用户缩小搜索范围；当前截图 gate 已单独覆盖该 overflow 提示态。
- `nav_from` 继续决定后续 `back` 的目标；当前批次里搜索歧义默认从 `feed` 进入。
- `DISAMBIGUATION -> A/RIGHT -> SPOTLIGHT -> back` 时，如果来源是 `FEED_SEARCH`，服务端会优先恢复保存的 `search_session`（查询词、结果列表、cursor）。

---

## S2 · SPOTLIGHT（spotlight）

### 当前键行为

| AVE_KEY | 行为 | 发送到服务端 |
|---|---|---|
| `B` | 返回（并启动 3s 本地回退定时器） | `{"type":"key_action","action":"back"}` |
| `LEFT` | 上一个 FEED token（不循环，边界静默） | `{"type":"key_action","action":"feed_prev"}` |
| `RIGHT` | 下一个 FEED token（不循环，边界静默） | `{"type":"key_action","action":"feed_next"}` |
| `A` | 买入当前 token | `{"type":"key_action","action":"buy","token_id","chain"}` |
| `UP` | K 线周期前进（5M/1H/4H/1D） | `{"type":"key_action","action":"kline_interval",...}` |
| `DOWN` | K 线周期后退（1D/4H/1H/5M） | 同上 |
| `X` | 快速卖出 | `{"type":"key_action","action":"quick_sell","token_id","chain"}` |

### 补充
- 接收新 SPOTLIGHT 数据后会清除 loading 标记；loading 时 `A`/`X`会被忽略。
- 若 `feed_prev` / `feed_next` / `kline_interval` 后服务端长时间无响应，客户端有约 `2.5s` 的 loading fail-safe，会自动释放 loading，避免 `A`/`X` 被永久锁死。
- 底栏 affordance 固定显式：`[B] BACK` / `[X] SELL` / `[A] BUY` / `[Y] PORTFOLIO`（降低 `X` 在不同页面含义切换的风险）。
- `cursor/total` 存在时会显示 `<N/M>` 位置计数（显示在底栏上方，避免与动作键提示挤在同一行）。

### 模拟器限制
- `A`/`B` 在 SPOTLIGHT 中仍按实际逻辑触发买入/返回，按键即可生效。
- 方向由箭头键触发，按箭头即可翻页。
- 模拟器的 `P` 和终端输入保持原位：`P` 切 mock 场景，终端发语音替代命令。

---

## S3 · CONFIRM（confirm）

### 当前键行为

| AVE_KEY | 行为 | 发送到服务端 |
|---|---|---|
| `B` | 取消交易并回 FEED | `{"type":"trade_action","action":"cancel","trade_id"}` |
| `A` | 确认交易（展示后 500ms 内忽略，防误触） | `{"type":"trade_action","action":"confirm","trade_id"}` |

### 当前倒计时与超时逻辑
- 倒计时到 0：自动发送 `trade_action cancel`，本地回 FEED。
- 按 `A` 后会启动 15s ack watchdog；若 15s 内无响应，推送 NOTIFY（交易超时）并回 FEED。
- 当服务端随后推送新的主屏（如 `feed` / `result` / `portfolio`）时，屏幕管理器会主动取消 confirm 页计时器与 ack watchdog，避免旧定时器串到新页面。
- `trade_id`、`action`、`symbol`、`amount_native`、`amount_usd`、`out_amount`（可选）、`tp_pct/sl_pct/slippage_pct/timeout_sec` 均按 payload 渲染。
- 若 `tp_pct/sl_pct` 在 payload 中为 `null`（典型如 sell/cancel 类确认），当前 UI 会把对应项显示为 `--`，而不是伪默认值。
- 当用户在 CONFIRM 页发语音或终端 listen.detect 文本时，客户端会显式携带 `selection.screen="confirm"`，让服务端按本轮 authoritative screen 处理 `确认/取消/返回`，而不是依赖可能滞后的服务端 `ave_state.screen`。

### 与 `Y` 全局快捷的关系
- 在 CONFIRM 页按 `Y` 会先发 `cancel_trade`，再发 `portfolio`，即“取消后切持仓”。

### 模拟器限制
- `A`/`B` 可以直接触发确认/取消（键盘字母即硬件按键），所以没有专门的绕道。
- 可用替代：终端输入继续作为语音替代，`Y` 全局快捷（`Y` 键）仍会取消并进入持仓。

---

## S4 · LIMIT_CONFIRM（limit_confirm）

### 当前键行为

| AVE_KEY | 行为 | 发送到服务端 |
|---|---|---|
| `B` | 取消限价单并回 FEED | `{"type":"trade_action","action":"cancel","trade_id"}` |
| `A` | 确认挂单 | `{"type":"trade_action","action":"confirm","trade_id"}` |

### 当前倒计时与超时逻辑
- 倒计时结束：自动 `trade_action cancel` 并回 FEED。
- 按 `A` 后同样有 15s ack watchdog；超时推 NOTIFY 并回 FEED。
- 当服务端推送新的主屏后，屏幕管理器同样会取消 limit confirm 页遗留计时器，避免超时回调误伤后续页面。
- 当用户在 LIMIT_CONFIRM 页发语音或终端 listen.detect 文本时，客户端会显式携带 `selection.screen="limit_confirm"`，让服务端仍按当前确认页语义处理 `确认/取消/返回`。

### 与 `Y` 全局快捷的关系
- 在 LIMIT_CONFIRM 页按 `Y` 同样会先 `cancel_trade` 后 `portfolio`。

### 模拟器限制
- 无额外限制；`A/B` 可直接触发确认/取消。

---

## S5 · RESULT（result）

### 当前行为
- 显示成功或失败结果。
- 不自动返回，也没有本地 fallback 定时器。
- `Y` 仍先走全局快捷：直接进入 PORTFOLIO，而不是走 RESULT 的 back 逻辑。
- 除 `Y` 外，任意按键都会立即发送 `{"type":"key_action","action":"back"}`。
- 当用户停留在 RESULT 页说话时，客户端 listen.detect 也会显式携带 `selection.screen="result"`，让本轮 `turn_ave_context.screen` 与客户端所见页面保持一致。

### RESULT 字段（当前后端实发）

| 字段 | 说明 |
|---|---|
| `success` | 成功/失败 |
| `title` | 标题 |
| `out_amount` / `amount` | 数量主文案（成功） |
| `amount_usd` | 金额（成功） |
| `tx_id` | 交易哈希（成功，截断） |
| `error` | 失败原因（失败） |

> `tp_price` / `sl_price` 在 UI 代码有兼容，但当前 `ave_tools.py` / `ave_wss.py` 不作为标准 RESULT 字段下发。

---

## S6 · PORTFOLIO（portfolio）

### 当前键行为

| AVE_KEY | 行为 | 发送到服务端 |
|---|---|---|
| `B` | 返回（并启动 3s 本地回退定时器） | `{"type":"key_action","action":"back"}` |
| `UP` | 选中上一持仓 | - |
| `DOWN` | 选中下一持仓 | - |
| `A` | 查看选中持仓详情 | `{"type":"key_action","action":"portfolio_watch","token_id","chain"}` |
| `X` | 卖出选中持仓（100%） | `{"type":"key_action","action":"portfolio_sell","addr","chain","symbol","balance_raw"}` |

### 底栏 affordance
- 固定显式：`[B] BACK` / `[X] SELL` / `[A] DETAIL` / `[Y] PORTFOLIO`（与 SPOTLIGHT 口径对齐）。

### holdings 当前关键字段
- 显示字段：`symbol` / `value_usd` / `pnl_pct` / `pnl_positive` / `contract_tail`（必要时）/ `source_tag`（必要时）。
- 行为字段：`addr` / `chain` / `balance_raw`（A 详情、X 卖出会用到）。
- 当前 `pnl`/`pnl_pct` 在工具侧默认 `N/A`（无成本基准）。
- 顶部说明字段：`wallet_source_label`（例如 `Proxy wallet`）与 `pnl_reason`（例如 `Cost basis unavailable`）。
- 顶部汇总 P&L 对 `N/A` 采用中性灰色，不再误显示成红色亏损。

### 模拟器限制
- 方向由箭头键控制，`A/B/X/Y` 各自对应硬件按键，按键行为与实机保持一致。
- `P` 仍用于 mock 场景切换，终端文本命令继续作为语音/系统替代。

---

## S7 · NOTIFY（notify，顶层浮层）

### 当前行为
- 叠加显示（不改变 `s_current`）。
- `level=error` 红、`warning` 橙，其余（含 `info/success`）绿。
- 不自动消失。
- **任意按键都会立即关闭 NOTIFY，并消费该键**（包括 `Y`，不会继续传给底层页面）。

---

## 3) 交易确认链路（按当前代码）

## 实际链路
1. CONFIRM/LIMIT_CONFIRM 按确认（或语音 `ave_confirm_trade`）后，服务端执行 `trade_mgr.confirm(trade_id)`。  
2. 若返回是**提交成功但无链上执行凭证**（submit-only ack）：  
   - 立即推 `NOTIFY`（`Order Submitted` / `Limit Order Submitted`，subtitle=`Waiting for chain confirmation.`）  
   - 清理 pending trade，并将服务端 `ave_state.screen` 标记为 `feed`  
   - 紧接着推 `display.feed`，payload 为 `{"reason":"trade_submitted"}`；因此设备端会离开 CONFIRM/LIMIT_CONFIRM，不会继续卡在确认页等待  
   - 由于主屏已经切回 FEED，确认页的 15s ack watchdog 会在后续主屏切换时被取消，不会再误弹本地“交易超时”  
3. 若返回已含执行结果（含 tx/order 证据），直接推 `RESULT`。  
4. 后续真实成交通常由 `ave_wss` 的 botswap 事件到达：  
   - `takeprofit/stoploss/trailing` → `NOTIFY`  
   - `market_buy/market_sell/limit_buy/cancel_order` 的 confirmed/error → `RESULT`（或延迟 RESULT）

## 延迟 RESULT（deferred）机制
- 若 botswap 最终事件到达时，仍存在 pending trade，则不会立即抢屏：
  - 先入 `deferred_result_queue`
  - 同时推一个 `NOTIFY`：`title="Result Deferred"`，`subtitle="Another confirmation flow is active. Result will appear next."`
- 当 pending 被清理且当前屏幕不在 confirm/result 后，队列会自动 flush，按顺序推 `RESULT`；flush 时保留原结果文案，并补 `explain_state="deferred_result"`。

## 本地 timeout / explain-state 速查

| 状态键 | 触发位置 | 当前用户可见表达 |
|---|---|---|
| `trade_submitted` | 服务端 submit-only ack 过渡 | `NOTIFY` + FEED refresh，提示链上确认仍在等待 |
| `ack_timeout` | `CONFIRM` / `LIMIT_CONFIRM` 本地 15s watchdog | `NOTIFY: Still Pending / We did not receive a final confirmation yet.` |
| `confirm_timeout` | `CONFIRM` / `LIMIT_CONFIRM` 本地倒计时归零 | `RESULT_FAIL: Trade Cancelled / Confirmation timed out. Nothing was executed.` |
| `deferred_result` | WSS 终态撞上另一笔 active confirm | 先 `NOTIFY: Result Deferred`，稍后再补 `RESULT` |

---

## 4) 实时数据与路由（当前实现）

| 项目 | 来源 | 当前实现 |
|---|---|---|
| FEED 初始列表 | `ave_get_trending` / `ave_search_token` / `ave_list_orders` | 推 `display.feed` |
| FEED 实时价格 | `ave_wss._on_price_event` | `API_PLAN=pro`，节流 0.5s 合并推送，`live=true` |
| SPOTLIGHT 实时价跌幅 | `ave_wss._on_price_event` | `API_PLAN=pro`，只更新 price/change，不直接用 kline close 改价 |
| SPOTLIGHT 实时 K 线 | `ave_wss._on_kline_event` | 订阅 interval 跟随当前周期（k5/k60/k240/k1440） |
| SPOTLIGHT 持有人/流动性 | `ave_wss._spotlight_poll_loop` | 每 5s 轮询并推 `live=true` |
| 交易事件 | `ave_wss._trade_loop`（botswap） | `API_PLAN>=normal`，推 NOTIFY / RESULT |

### live 推送防“抢屏”
- FEED：`live=true` 且当前不在 FEED 时丢弃；在 FEED 但处于 `ORDERS` / `SEARCH` / `special source` 时也会丢弃（避免在“非标准 FEED 浏览态”被实时刷新抢走注意力）。
- SPOTLIGHT：`live=true` 仅在当前仍是 SPOTLIGHT 时应用。

### 返回路由补充
- `key_action back` 的服务端目标由状态决定：`nav_from=portfolio` 时回 PORTFOLIO，否则回 FEED（保留 feed_source/feed_platform）。
- 客户端本地的 3 秒回退定时器仅用于 SPOTLIGHT / PORTFOLIO 返回流；RESULT 仅支持手动返回，没有自动返回或本地回退定时器。

---

## 5) 当前已知限制（明确记录）

- 模拟器键盘已实现方向键与 `A/B/X/Y` 的 1:1 映射；系统/语音 `FN` 也已有 `F1` 映射（见 §1.3）。
- `P` 继续作为纯模拟器的 mock 场景切换器，真实机上暂无等价动作。
- 终端输入仍是独立文本注入路径（stdin 一行文本 + Enter 直发服务端），可在需要语音替代、系统调试、或未映射功能时继续使用。
- 模拟器按键为“边沿触发”（edge-detect）：按住按键不会连续触发；需要重复动作时请多次点按。
- 当前截图 gate 覆盖 FEED/EXPLORE/ORDERS/DISAMBIGUATION（常规态 + overflow 提示态）/SPOTLIGHT/CONFIRM/LIMIT_CONFIRM/RESULT/PORTFOLIO；行为细节仍由 router/surface/state-machine 回归测试兜底。
