# AVE 产品表面审计（按当前代码实现）

> 审计日期：2026-04-08
> 范围：`shared/ave_screens/`、`simulator/`、`server/main/xiaozhi-server/`、现有产品文档
> 立场：以“产品总监 + 交互审查”视角盘点当前已经落地的页面、功能、输入方式和用户路径，不把规划项当成已实现。
> 口径说明：`docs/pending-tasks.md` 的工程交付项已大体清空；本审计文档继续用于跟踪“已上线表面中的剩余产品/UX问题”，两者不再等同。

---

## Executive Summary

当前产品已经形成一个可跑通的“手持交易助手”最小闭环：

- 主路径已经完整：`FEED -> SPOTLIGHT -> CONFIRM/LIMIT_CONFIRM -> RESULT -> 返回 FEED/PORTFOLIO`
- 次路径也已成形：`PORTFOLIO -> WATCH/SELL -> RESULT -> 返回 PORTFOLIO`
- 用户侧输入体系以三类为主：方向/确认按键、全局 `Y -> PORTFOLIO`、`FN/PTT(F1)` 监听控制（终端文本仅用于模拟器调试，不属于面向用户的产品表面）
- 当前 UI 的优势是确定性强、路径短、交易确认有防误触和超时保护
- 当前 UI 的主要短板不是“不能用”，而是“剩余产品细节未收口”：FEED Explore 已把 `Search / Orders / Sources` 暴露到首页，但首次使用引导、返回语义和结果后引导仍不够自解释

当前未解决 Top 3 产品问题（按用户影响）：

1. `R1`：重复 symbol 歧义仍可能把“看详情/买入”导向错误资产。
2. `R4`：`CONFIRM/LIMIT_CONFIRM` 超时后静默回退，用户难以理解“为什么没成交”。
3. `R6`：`X` 键在 FEED 与 SPOTLIGHT/PORTFOLIO 间语义切换风险仍高。

产品总评：

- 可用性：`B`
- 确定性与安全性：`A-`
- 可发现性：`B-`
- 新手友好度：`C`
- 继续演进建议：优先补“表面文档化、页面 affordance、输入矩阵一致性”，而不是继续堆新 API

---

## 1) 页面 / 状态产品表

| 页面/状态 | 目标 | 入口 | 主要信息 | 可执行操作 | 按键/输入 | 成功路径 | 失败/空态 | 已知问题 | 代码参考 |
|---|---|---|---|---|---|---|---|---|---|
| `FEED` | 展示热门/榜单代币并作为主首页 | 启动默认进入；语音/文本“看热门”；`back` 返回默认落点 | 来源标签、列表项、价格、涨跌幅、计数、底栏提示，以及标准首页上的 Explore 浮层入口 | 上下选中、右/A 看详情、左刷新、X 切来源、Y 去持仓；标准 FEED `B` 打开 Explore（`Search / Orders / Sources`） | `UP/DOWN/RIGHT/A/LEFT/X/Y/B`；文本“看热门”“看<symbol>”“买<symbol>` | 进入 `SPOTLIGHT`；切换来源；进入 `PORTFOLIO`；或经 Explore 进入 Search 引导 / Orders / Sources | 空 payload 时显示占位；special source / orders 模式禁用部分操作并弹 `NOTIFY`；只有标准 FEED 有 Explore，非标准 FEED 仍保留既有 `B` 语义 | 首页可发现性已明显好于“只提示已在首页”的版本，但 Search 仍是 copy-only（`FN 说币名`），方向键移动也不会建立服务端可信的去指 authority；listen/text 的“看这个/买这个”仍必须携带显式 `selection` payload，否则 fail-close（不会依赖旧 `feed_cursor` 误指 token） | `shared/ave_screens/screen_feed.c`, `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`, `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py` |
| `FEED_SEARCH` | 承接 symbol 搜索结果 | 文本/语音“看BONK”“买BONK”且未命中当前 feed map 时 | 与 FEED 复用同一列表布局，但 `source_label=SEARCH`（或 `mode=search`） | 浏览结果、进入详情、通过 `B` 回上一次标准来源并刷新 | `LEFT/X` 禁用；`A/RIGHT` 仍可进详情；`B` 很关键 | 搜到 token 后进 `SPOTLIGHT` | 若搜索失败通常走 `NOTIFY`，不是独立空搜索页 | “搜索态”是 FEED 变体；通过顶栏 `SEARCH` 身份标识 + 底栏禁用提示降低理解成本 | `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py:1289`, `shared/ave_screens/screen_feed.c` |
| `FEED_SPECIAL_SOURCE` | 承接平台/特殊来源列表 | 平台筛选、特殊 topic、其他非标准来源 | 仍为 FEED 列表，但 `source_label` 非标准 | 浏览、看详情、`B` 返回记住的标准来源并刷新 | `LEFT/X` 禁用；`A/RIGHT` 仍可进详情 | 回到普通 FEED 或进入 `SPOTLIGHT` | 若无记住来源则回默认来源 | 入口仍偏隐式，但页面身份已更显性（顶栏 `SPECIAL` + 底栏禁用提示） | `shared/ave_screens/screen_feed.c` |
| `FEED_ORDERS` | 展示订单列表 | 首页 `B` -> Explore -> `Orders`；语音/文本订单相关入口 | 复用 FEED 列表布局，`mode=orders` | 上下浏览、`B` 退出 orders 模式 | browse-only：`UP/DOWN/B`；`LEFT/X/A/RIGHT` 禁用；listen/text deictic（如“看这个/买这个”）不提供 trusted selection（`selection` 省略，fail closed） | 返回普通 FEED | 不支持刷新/切源，靠 `NOTIFY` 解释 | 入口已产品化露出，但能力边界仍是“只浏览 + 返回”（`A/RIGHT` 明确禁用，底栏提示 back-only） | `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py:1383`, `shared/ave_screens/screen_feed.c` |
| `SPOTLIGHT` | 展示单个 token 详情并承接买卖决策 | FEED 右/A；持仓 A；文本“看这个/详情/进入” | 顶栏价格与涨跌、K 线、时间周期、风险徽标、holders、liquidity、位置计数 | 左右切换 feed token、上下切 K 线周期、A 买入、X 快速卖出、B 返回 | `LEFT/RIGHT/UP/DOWN/A/X/B/Y`；文本“买这个” | 买入到 `CONFIRM`；快速卖出到 `CONFIRM`；返回 FEED/PORTFOLIO | loading guard 超时会释放卡死，但不会给明显用户反馈；详情获取失败走 `NOTIFY` | 信息密度高但结构清楚；不过“X=快速卖出”风险高，且缺少更强的金额/风险提示 | `shared/ave_screens/screen_spotlight.c`, `keyActionHandler.py` |
| `CONFIRM` | 承接市价交易确认 | `SPOTLIGHT` 买入/快速卖出；语音/文本“确认/取消” | 交易标题、trade_id、数量、美元价值、可选 TP/SL/slippage/timeout | A 确认，B 取消，Y 取消后去持仓 | `A/B/Y`；文本“确认/取消/返回” | 成功直接到 `RESULT`，或 submit-only ack 先 `NOTIFY` 再回 FEED，后续由 botswap 推终态 | 倒计时到 0 自动取消；15s ack watchdog 超时弹 `NOTIFY` 并回 FEED | 安全性较好，但信息是“看了就按”；没有修改数量的次级确认或再编辑路径 | `shared/ave_screens/screen_confirm.c`, `tradeActionHandler.py` |
| `LIMIT_CONFIRM` | 承接限价单确认 | 限价下单链路 | 与 CONFIRM 相似，但语义是挂单 | A 确认，B 取消，Y 取消后去持仓 | `A/B/Y`；文本“确认/取消/返回” | 成功挂单；后续由 trade/WSS 推送终态 | 同 CONFIRM：倒计时、ack watchdog、超时回退 | 与普通 CONFIRM 结构接近，降低学习成本；但“市价/限价”的差异提示仍可更强 | `shared/ave_screens/screen_limit_confirm.c`, `tradeActionHandler.py` |
| `RESULT` | 给出交易结果并等待手动返回 | confirm 成功、botswap confirmed/error、deferred flush | 标题、数量或错误、金额、哈希/错误信息 | 除 `Y` 外任意键立即返回；`Y` 直接去持仓 | “任意键”+ `Y`；文本可继续发新命令 | 通常回 FEED；若带 `nav_from=portfolio` 则回 PORTFOLIO | 失败态与成功态共用一页；需手动离开 | 手动停留更利于看清 tx hash 或失败原因，但仍缺少下一步建议 | `shared/ave_screens/screen_result.c`, `shared/ave_screens/ave_screen_manager.c` |
| `RESULT_FAIL` | 承接失败结果 | RESULT 的失败变体 | 错误主文案、失败标题、回退逻辑与 RESULT 相同 | 同 RESULT | 同 RESULT | 手动返回 FEED/PORTFOLIO | 若错误信息过长会被截断 | 当前失败页是正确存在的，但在产品心智上仍像“成功页染红”，缺少下一步建议 | `shared/ave_screens/screen_result.c:267`, screenshot baseline `result_fail` |
| `PORTFOLIO` | 展示代理钱包持仓并支持 watch/sell | 全局 `Y`；文本“我的持仓/持仓”；`back` 带 `nav_from=portfolio` | 总资产、顶部 P&L、持仓行、每行 symbol/value/P&L | 上下选中、A 看详情、X 卖出、B 返回 | `UP/DOWN/A/X/B/Y`；文本“持仓”“看这个” | 看详情到 `SPOTLIGHT`；卖出到 `CONFIRM`；返回 FEED | 空 payload 会显示空白/占位而不是完整空态指导 | 当前最强的二级页面，但成本基准不足，P&L 多为 `N/A`；方向键选中仅更新本地高亮，不建立服务端可信的去指 authority；deictic（如“看这个/买这个/卖这个/关注这个”）必须携带显式 `selection` payload，否则 fail-close（不会依赖旧 `portfolio_cursor` 指错持仓） | `shared/ave_screens/screen_portfolio.c`, `keyActionHandler.py`, `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py` |
| `NOTIFY` | 轻量提示、告警、补充解释 | trade submit ack、禁用提示、错误提示、风控提示 | 标题、正文、level 颜色 | 不自动消失；任意键立即关闭并消费按键（含 `Y`） | 任意键 | 手动关闭后回到底层页面继续 | 消费按键后立即关闭 | 作为系统解释层很有用，但“消费按键”会造成连续操作被吞，老用户可能困惑 | `shared/ave_screens/screen_notify.c`, `shared/ave_screens/ave_screen_manager.c` |

---

## 2) 按键与输入矩阵

| 输入表面 | 真机/模拟器映射 | 当前语义 | 主要可达功能 | 当前限制 |
|---|---|---|---|---|
| 方向键 | 真机 D-pad / 模拟器方向键 | 列表导航、周期切换、feed token 切换 | FEED 浏览、SPOTLIGHT 翻 token、K 线周期切换、PORTFOLIO 选中 | 只有边沿触发，无长按连续滚动 |
| `A` | 真机 A / 模拟器 `A` | 主确认/详情/买入 | FEED 看详情、SPOTLIGHT 买入、CONFIRM 确认、PORTFOLIO 看详情 | 不同页面语义不同，靠页面心智切换 |
| `B` | 真机 B / 模拟器 `B` | 返回/取消/入口 | SPOTLIGHT 返回、CONFIRM/LIMIT_CONFIRM 取消、PORTFOLIO 返回、FEED 特殊模式退出；标准 FEED：打开 Explore | 在不同状态下会触发“取消交易”“回来源”“打开 Explore”，仍有多义性，但比“已在首页”提示更有产品价值 |
| `X` | 真机 X / 模拟器 `X` | 次级动作（FEED: source switch；SPOTLIGHT/PORTFOLIO: sell） | FEED 切来源、SPOTLIGHT 快速卖出、PORTFOLIO 卖出 | 高风险动作和低风险动作共用同一键，认知切换大；需依赖页面底栏 affordance 显式区分 |
| `Y` | 真机 Y / 模拟器 `Y` | 全局去持仓 | 任何主页面跳 `PORTFOLIO`；在 confirm 类页面会先取消交易 | 强力快捷键，安全性不错；通过底栏显式 `[Y] PORTFOLIO` 降低“隐藏快捷键”学习成本 |
| `FN/PTT` | 真机 `FN(GPIO0)` / 模拟器 `F1` | 监听控制 | 当前至少用于 `listen start/stop` 控制态 | 模拟器没有真音频；真机链路依赖板级适配 |
| 终端文本 | 仅模拟器 stdin | 语音替代、命令直达 | 看热门、持仓、看/买 symbol、确认、取消、返回 | 是开发/调试能力，不是面向最终用户的表面 |
| 语音文本路由 | 服务端 `listen detect` / `listen start-stop` | 自然语言意图入口 | 命令直达、LLM handoff、带当前页面上下文 | 当前很多能力更依赖“知道该说什么”，而不是 UI 自解释 |

---

## 3) 关键用户路径

| 路径 | 当前体验 | 评价 |
|---|---|---|
| 首页看榜单 -> 看详情 -> 买入 -> 确认 -> 结果 | 最短、最清晰、最成熟 | 当前最佳主路径 |
| 持仓 -> 看详情 -> 卖出 -> 确认 -> 返回持仓 | 已可闭环，且 `nav_from=portfolio` 处理较好 | 当前次主路径，可作为二号演示路径 |
| 搜索 symbol -> 看详情 / 买入 | 可用，但入口依赖文本/语音命令 | 强能力、弱发现 |
| 特殊来源/平台流 -> 看详情 -> 返回普通来源 | 逻辑已实现 | 对普通用户来说偏隐式 |
| 订单列表 -> 返回首页 | 可用；现在可从标准 FEED Explore 进入 | 仍是 browse-only，但入口已产品化一层 |

---

## 4) FEED Explore 落地后：剩余产品问题清单（严格口径）

> 说明：本节仅记录“工程已可交付，但产品体验仍未达发布标准”的剩余项；不再与工程 pending 混写。

| ID | Severity | Surface/Page | 用户问题 | 触发路径 | 当前行为 | 期望行为 | Recommendation | 状态建议 |
|---|---|---|---|---|---|---|---|---|
| R1 | P0 | `FEED` / `SPOTLIGHT` | 重复 symbol（同名不同 token）下，用户以为在看/买 A，实际可能落到 B | 首页或搜索看到同 symbol 列表项后直接 `A`/“买这个” | 缺少足够强的 disambiguation（合约/链/发行方级别） | 进入详情和下单前可明确区分“你正在操作哪一个” | 在列表与确认链路增加“同名资产消歧层”（短标签 + 合约尾号 + 必要时二次确认） | 本轮必须进入发布阻断清单 |
| R2 | P1 | `FEED` Explore / `FEED_SEARCH` | Search 可发现但对新手不自洽：知道有入口，不知道下一步如何完成一次搜索 | 首页 `B` 打开 Explore 后进入 Search | 主要依赖“`FN` 说币名”文案，按键自闭环不足 | 首次用户无需记忆语音指令，也能完成一次 symbol 搜索 | 增加显式首屏引导（示例词 + 可执行按键入口或候选热词） | 进入近期产品修复 |
| R3 | P1 | `FEED_SEARCH` -> `SPOTLIGHT` -> 返回 | 用户从搜索结果进详情再返回时，常丢失原搜索上下文，需要重新找 | 搜索命中后进详情，按 `B` 返回 | 返回落点可能回普通 FEED 或重刷，搜索上下文不稳 | 返回后保持搜索结果与选中位置，避免重复操作 | 建立“search session restore”策略（source + query + cursor） | 进入近期产品修复 |
| R4 | P0 | `CONFIRM` / `LIMIT_CONFIRM` | 倒计时或 ack watchdog 超时时，用户看到的是“回退了”，但不理解“为什么取消” | 进入确认页后等待超时 | 交易被取消并回退，但解释不够直接，感知为静默失败 | 明确提示“超时自动取消”的原因、影响与下一步 | 超时分支统一进入可读 `NOTIFY/RESULT_FAIL` 文案，并给出下一步动作 | 本轮必须进入发布阻断清单 |
| R5 | P1 | `Sources` 入口（Explore） | Sources 像“全部来源地图”，但实际并非完整真实宇宙，用户预期被抬高 | 首页 `B` -> `Sources` | 展示为可切换来源入口，但覆盖范围与真实来源不完全一致 | 用户可理解“这是当前可用来源子集”，不是全市场全量 | 文案改为“可用来源/当前支持来源”，并补充边界说明 | 进入文案与信息架构修复 |
| R6 | P0 | `FEED` vs `SPOTLIGHT` / `PORTFOLIO` | `X` 在不同页面语义跳变（切来源 vs 卖出），误触风险和心理负担仍高 | 页面切换后延续按键习惯按 `X` | FEED 低风险动作与交易高风险动作复用同一键 | 高风险动作应有更强防错和更一致的按键语义预期 | 保留快捷键前提下，强化底栏高风险标识 + 首次确认护栏 + 教程提示 | 本轮必须进入发布阻断清单 |
| R7 | P1 | `RESULT` / `RESULT_FAIL` / `NOTIFY` | 结果页与通知页“告知有了”，但“下一步做什么”仍弱，失败后尤其明显 | 任意交易完成或失败、系统提示弹出 | 主要提供结果信息，动作建议弱，用户要自己判断后续 | 成功/失败都给出明确 next step（返回看单/重试/查看持仓） | 为成功与失败分别提供 1-2 个明确 CTA 文案路径 | 进入近期产品修复 |
| R8 | P2 | `FEED_ORDERS` | Orders 已上首页但仍是 browse-only，用户会感到“入口已承诺能力，实际未完成” | 首页 `B` -> `Orders` | 可浏览、可返回，但不可进一步管理/操作 | 至少让用户在入口层知道“仅浏览”与后续计划 | 明示“当前仅查看”状态，并定义下一阶段能力里程碑 | 作为后续版本规划项（非当前发布阻断） |

## 5) 测试信心与发布判断

- 工程回归信心：高。主路径与关键状态机覆盖较完整，`docs/pending-tasks.md` 对应交付项已基本清空。
- 产品旅程信心：中低。当前还未达到 launch-grade，主要缺口集中在跨页面心智连续性和失败解释充分性。
- 当前缺失的产品信心点：发布阻断级问题仍集中在重复 symbol 消歧（R1）、确认超时解释（R4）、`X` 键跨页面语义风险（R6）；其次是搜索返回恢复（R3）与首页暴露后的 Search/Orders 可用性闭环（R2/R8）。
- 发布口径建议：工程可宣告“已交付可跑通”；产品应宣告“仍有剩余体验问题待收口”，避免对外过度承诺。

---

## 6) 建议的产品文档使用方式

这份表建议后续作为三个基准文档的上层索引：

- 页面行为明细：`docs/simulator-ui-guide.md`
- 实现与 API 对齐：`docs/ave-feature-map.md`
- 风险与优先级：`docs/product-review-2026-04-07.md`

如果后续继续做产品梳理，建议把新增页面或输入方式统一追加到本文件，而不是只散落在实现文档里。
