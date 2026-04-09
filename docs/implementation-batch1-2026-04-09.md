# AVE 第一批实现任务拆解（2026-04-09）

> 上游文档：
> - `docs/product-review-table-2026-04-09.md`
> - `docs/page-blueprint-key-constitution-2026-04-09.md`
>
> 目标：从产品蓝图中拆出第一批真正应该落地的实现任务，优先覆盖：
> 1. `DISAMBIGUATION`
> 2. 搜索闭环 / 资产身份强化
> 3. 确认超时解释
> 4. Wallet / Order 解释层

---

## 1. 批次目标

| 目标 | 说明 |
|---|---|
| 先收 P0/P1 产品风险 | 本批不追求能力面扩张，先修产品主路径 |
| 不改产品定位 | 继续保持“手持交易助手”，不扩成全量研究终端 |
| 优先收口用户心智 | 解决“看的是谁、搜完去哪、为什么没成交、我的钱包/订单到底是什么意思” |
| 以现有页面体系为主 | 默认不扩顶层页，只有 `DISAMBIGUATION` 允许作为条件新增页 |

---

## 2. 批次范围与非范围

### 2.1 本批范围

| 范围 | 是否纳入 |
|---|---|
| `DISAMBIGUATION` 页面/状态机/路由 | 是 |
| `FEED` / `SPOTLIGHT` / `CONFIRM` / `PORTFOLIO` 资产身份强化 | 是 |
| Search 首次闭环与返回恢复 | 是 |
| Confirm / Limit confirm timeout / watchdog / submitted explain layer | 是 |
| Wallet explanation layer | 是 |
| Orders explanation layer | 是 |
| 相关截图 / 路由 / 状态机 / 输入同步测试 | 是 |

### 2.2 本批不纳入

| 非范围项 | 原因 |
|---|---|
| approve / transfer / wallet lifecycle | 超出当前产品边界 |
| self-custody / chain-wallet signed tx | 超出当前产品风险模型 |
| tx/multi_tx/liq 主表面实时流 | 与当前信息密度和 anti-抢屏原则冲突 |
| 多钱包切换 | 会重写 portfolio 与确认链路 |
| 大规模视觉重做 | 本批目标是产品收口，不是视觉翻新 |

---

## 3. 实施优先级总表

| 优先级 | Epic | 目标结果 |
|---|---|---|
| P0 | E1. 资产身份与 `DISAMBIGUATION` | 用户不会因重名/弱身份而看错或买错资产 |
| P0 | E2. 确认超时解释层 | 用户理解“为什么没成交/为什么回退/现在处于什么状态” |
| P1 | E3. 搜索闭环与返回恢复 | Search 从“可发现”升级到“可完成” |
| P1 | E4. Wallet / Order 解释层 | 用户理解 `N/A`、wallet 来源、orders 仅查看边界 |
| P1 | E5. 测试与文档同步 | 让新规则可验证、可回归、可维护 |

---

## 4. Epic 拆解

### E1. 资产身份与 `DISAMBIGUATION`

#### E1-A 新增条件页面：`DISAMBIGUATION`

| 项目 | 内容 |
|---|---|
| 目标 | 在 symbol 重名、搜索候选冲突、交易前身份不清时，强制用户确认目标资产 |
| 优先级 | P0 |
| 类型 | 页面/状态机/路由 |
| 建议触达文件 | `shared/ave_screens/ave_screen_manager.h`, `shared/ave_screens/ave_screen_manager.c`, `shared/ave_screens/screen_disambiguation.c`(新), `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`, `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`, `docs/simulator-ui-guide.md`, `docs/ave-feature-map.md` |
| 触发条件 | 1) 搜索命中多个高相似资产；2) FEED / SEARCH 进入 detail 前身份不足；3) buy/sell 前仍需二次身份确认 |
| 输入规则 | `UP/DOWN` move，`A/RIGHT` select，`B/LEFT` back，`Y` global portfolio，`X` disabled |
| 非目标 | 不承担分析、不承担下单、不承担设置 |

**验收标准**

| 编号 | 标准 |
|---|---|
| AC-E1A-1 | 重名资产场景下，不再直接进入 `SPOTLIGHT`，而是先进入 `DISAMBIGUATION` |
| AC-E1A-2 | `DISAMBIGUATION` 的每个候选项都至少展示 symbol + chain + contract tail |
| AC-E1A-3 | 从 `DISAMBIGUATION` 选中后进入正确资产详情 |
| AC-E1A-4 | `B/LEFT` 可无损返回上一个列表/搜索结果 |
| AC-E1A-5 | `X` 在该页无语义，不可触发其他动作 |

#### E1-B 资产身份强化（不等同于新页面）

| 项目 | 内容 |
|---|---|
| 目标 | 在 `FEED`、`SPOTLIGHT`、`CONFIRM`、`PORTFOLIO` 中统一强化资产身份表达 |
| 优先级 | P0 |
| 类型 | 页面信息架构 |
| 建议触达文件 | `shared/ave_screens/screen_feed.c`, `shared/ave_screens/screen_spotlight.c`, `shared/ave_screens/screen_confirm.c`, `shared/ave_screens/screen_limit_confirm.c`, `shared/ave_screens/screen_portfolio.c`, `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py` |
| 目标字段 | chain、contract tail、必要时 source/issuer short tag |
| 非目标 | 不做大面积视觉重排 |

**验收标准**

| 编号 | 标准 |
|---|---|
| AC-E1B-1 | FEED 列表项可分辨同名不同链资产 |
| AC-E1B-2 | SPOTLIGHT 顶区能明确表达当前是哪个资产 |
| AC-E1B-3 | CONFIRM/LIMIT_CONFIRM 页显示的资产身份足以降低误买风险 |
| AC-E1B-4 | PORTFOLIO 列表项不再只靠 symbol 区分资产 |

---

### E2. 确认超时解释层

#### E2-A 倒计时超时解释

| 项目 | 内容 |
|---|---|
| 目标 | 用户在 `CONFIRM` / `LIMIT_CONFIRM` 页面超时后，明确理解“本次未成交、系统已取消、下一步去哪” |
| 优先级 | P0 |
| 类型 | 结果/通知解释 |
| 建议触达文件 | `shared/ave_screens/screen_confirm.c`, `shared/ave_screens/screen_limit_confirm.c`, `shared/ave_screens/screen_result.c`, `server/main/xiaozhi-server/plugins_func/functions/ave_trade_mgr.py`, `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py` |
| 方案建议 | timeout 从“直接回 FEED”升级为“带明确解释的 NOTIFY 或 RESULT_FAIL 过渡” |
| 非目标 | 改变交易引擎或超时时长 |

**验收标准**

| 编号 | 标准 |
|---|---|
| AC-E2A-1 | 倒计时超时后，用户能看到“自动取消/未成交”的清晰说明 |
| AC-E2A-2 | watch dog 超时与 confirm 倒计时超时的文案区分清楚 |
| AC-E2A-3 | 用户在看到解释后，能自然回到 FEED 或 PORTFOLIO |

#### E2-B submit-only / deferred / waiting-chain 解释

| 项目 | 内容 |
|---|---|
| 目标 | 把现有技术态 `trade_submitted`、`deferred_result_queue`、botswap 延迟终态转成用户听得懂的状态表达 |
| 优先级 | P0 |
| 类型 | 状态解释层 |
| 建议触达文件 | `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`, `server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`, `shared/ave_screens/screen_result.c`, `shared/ave_screens/screen_notify.c` |
| 方案建议 | 统一状态词：已提交 / 等待链上确认 / 结果延后展示 / 已失败 |
| 非目标 | 改 botswap 协议或 reconcile 机制 |

**验收标准**

| 编号 | 标准 |
|---|---|
| AC-E2B-1 | submit-only ack 时，用户看到的是“订单已提交，等待链上确认”，而不是工程态占位文案 |
| AC-E2B-2 | deferred result 时，用户知道“当前结果未丢失，只是稍后显示” |
| AC-E2B-3 | 失败态统一带 next step |

---

### E3. 搜索闭环与返回恢复

#### E3-A Search guide 从“知道入口”升级到“完成搜索”

| 项目 | 内容 |
|---|---|
| 目标 | 让首次用户在标准 FEED 的 Search 入口中知道下一步如何完成一次搜索 |
| 优先级 | P1 |
| 类型 | 首页入口解释 |
| 建议触达文件 | `shared/ave_screens/screen_feed.c`, `docs/simulator-ui-guide.md`, `simulator/mock/run_screenshot_test.sh` |
| 方案建议 | Search guide 增加示例词、最近一次查询、失败时提示下一步 |
| 非目标 | 把 Search 变成独立页面或键盘输入系统 |

**验收标准**

| 编号 | 标准 |
|---|---|
| AC-E3A-1 | Search guide 不再只有单句 `FN 说币名` |
| AC-E3A-2 | 用户在不知道口令时，也能从页面示例理解搜索方式 |
| AC-E3A-3 | screenshot gate 覆盖新的 Search guide 状态 |

#### E3-B 搜索 session restore

| 项目 | 内容 |
|---|---|
| 目标 | 从 `FEED_SEARCH -> SPOTLIGHT -> back` 返回时，恢复原搜索结果与 cursor |
| 优先级 | P1 |
| 类型 | 导航/上下文恢复 |
| 建议触达文件 | `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`, `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`, `shared/ave_screens/screen_feed.c`, `server/main/xiaozhi-server/test_ave_router.py`, `server/main/xiaozhi-server/test_surface_input_sync.py` |
| 方案建议 | 在 `ave_state` 中单独保留 search session，而不是只靠通用 `feed_source` |
| 非目标 | 让所有 special source 都永久 session 化 |

**验收标准**

| 编号 | 标准 |
|---|---|
| AC-E3B-1 | 搜索后进入详情再返回，可回到原结果集 |
| AC-E3B-2 | 返回后高亮仍落在原 cursor |
| AC-E3B-3 | Search 模式下的 trusted selection 规则保持不变，不引入新串线 |

---

### E4. Wallet / Order 解释层

#### E4-A Wallet explanation

| 项目 | 内容 |
|---|---|
| 目标 | 让 `PORTFOLIO` 用户理解钱包来源、持仓来源、为什么 P&L 是 `N/A` |
| 优先级 | P1 |
| 类型 | 解释层 + 数据落位 |
| 建议触达文件 | `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`, `shared/ave_screens/screen_portfolio.c`, `server/main/xiaozhi-server/test_portfolio_surface.py`, `server/main/xiaozhi-server/test_ave_api_matrix.py` |
| 建议能力 | `walletinfo`、`walletinfo/tokens`、`address/pnl` 先做解释型接入 |
| 非目标 | 多钱包切换、钱包管理 |

**验收标准**

| 编号 | 标准 |
|---|---|
| AC-E4A-1 | `PORTFOLIO` 能说明数据来自哪个 wallet source |
| AC-E4A-2 | 当 P&L 为 `N/A` 时，产品有解释，不再只显示冷值 |
| AC-E4A-3 | 新解释不改变 `A=watch`、`X=sell`、`Y=portfolio` 的交互契约 |

#### E4-B Order explanation

| 项目 | 内容 |
|---|---|
| 目标 | 让用户明白 `FEED_ORDERS` 当前是“仅查看”而不是完整订单管理中心 |
| 优先级 | P1 |
| 类型 | 订单边界解释 |
| 建议触达文件 | `shared/ave_screens/screen_feed.c`, `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`, `server/main/xiaozhi-server/test_p3_orders.py`, `docs/simulator-ui-guide.md` |
| 方案建议 | 在 Explore 入口、ORDERS 页头、相关 NOTIFY/RESULT 中统一说明“当前仅查看/管理动作边界” |
| 非目标 | 本批直接做完整 order management screen |

**验收标准**

| 编号 | 标准 |
|---|---|
| AC-E4B-1 | 用户从 FEED Explore 进入 Orders 时，明确知道当前模式是 browse-only |
| AC-E4B-2 | 订单相关结果页能区分“撤单成功/失败”和“资产成交成功/失败” |
| AC-E4B-3 | Orders 说明层不破坏现有 trusted selection fail-closed 规则 |

---

### E5. 测试与文档同步

| 项目 | 内容 |
|---|---|
| 目标 | 为本批新增规则建立最小可回归验证闭环 |
| 优先级 | P1 |
| 类型 | 测试 / 文档同步 |
| 建议触达文件 | `server/main/xiaozhi-server/test_surface_input_sync.py`, `server/main/xiaozhi-server/test_ave_router.py`, `server/main/xiaozhi-server/test_p3_trade_flows.py`, `server/main/xiaozhi-server/test_p3_orders.py`, `server/main/xiaozhi-server/test_portfolio_surface.py`, `simulator/mock/run_screenshot_test.sh`, `docs/ave-feature-map.md`, `docs/simulator-ui-guide.md` |
| 重点验证 | 新页面状态、搜索恢复、timeout explain、wallet/order explanation、`X/Y/FN` 键位宪法未破坏 |

**验收标准**

| 编号 | 标准 |
|---|---|
| AC-E5-1 | 新增/变更的页面状态进入 screenshot gate |
| AC-E5-2 | 新增导航恢复逻辑进入路由测试 |
| AC-E5-3 | timeout / submit-only / deferred 解释进入 trade flow 测试 |
| AC-E5-4 | 文档与实现不再背离 |

---

## 5. 推荐落地顺序（工程执行顺序）

| 顺序 | 任务 | 理由 |
|---|---|---|
| 1 | E1-B 资产身份强化最小版 | 先在现有页降低误识别风险 |
| 2 | E1-A `DISAMBIGUATION` | 解决最高风险的重名资产问题 |
| 3 | E2-A / E2-B 确认超时与提交解释 | 解决“为什么没成交”的 P0 问题 |
| 4 | E3-A Search guide 升级 | 先把入口变得真正可用 |
| 5 | E3-B 搜索返回恢复 | 补足闭环连续性 |
| 6 | E4-A Wallet explanation | 修复 `PORTFOLIO` 的认知断层 |
| 7 | E4-B Order explanation | 修复 Orders 的承诺边界 |
| 8 | E5 测试与文档同步 | 收口并准备回归 |

---

## 6. 批次完成定义（Definition of Done）

| 条件 | 说明 |
|---|---|
| 页面层 | 至少完成资产身份强化、Search guide 升级、timeout explain、wallet/order explanation |
| 路由层 | 搜索返回恢复、disambiguation 跳转和 back 语义正确 |
| 键位层 | `Y/FN` 未复用，`X` 无新增语义 |
| 文案层 | timeout / submitted / deferred / `N/A` / browse-only 均有产品话术 |
| 测试层 | 对应 screenshot / router / flow / input sync 测试补齐 |
| 文档层 | `ave-feature-map.md` 与 `simulator-ui-guide.md` 同步更新 |

---

## 7. 本批次后的下一批候选

| 候选项 | 是否建议进入下一批 |
|---|---|
| `walletinfo` / `address/pnl` 深化接入 | 是 |
| `pairs/{pair}` / `tx/detail` 到 `SPOTLIGHT` | 是 |
| Orders 的轻管理动作 | 视本批结果决定 |
| 真机证据链专项 | 强烈建议 |
| approve / transfer / self-custody | 否 |

