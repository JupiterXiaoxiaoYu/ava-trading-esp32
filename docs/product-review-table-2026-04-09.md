# AVE 产品审查正式版（表格版，2026-04-09）

> 角色：产品总监（PD）审查
>
> 审查目标：基于当前 `ave-xiaozhi` 已实现代码、页面、路由、模拟器与验证资产，形成一份可直接用于产品决策的正式审查文档。
>
> 范围：
> - `docs/ave-full-capability-matrix-2026-04-09.md`
> - `docs/ave-feature-map.md`
> - `docs/simulator-ui-guide.md`
> - `docs/product-surface-audit-2026-04-08.md`
> - `docs/xiaozhi-ave-architecture-2026-04-09.md`
> - `shared/ave_screens/*`
> - `server/main/xiaozhi-server/core/handle/textHandler/*`
> - `server/main/xiaozhi-server/plugins_func/functions/*`
> - 相关测试与模拟器 gate

---

## 1. 审查结论摘要

| 维度 | 结论 | 判断 |
|---|---|---|
| 产品定位 | 当前产品已经形成“手持交易助手/交易遥控器”形态，而不是 AVE 全量客户端 | 正向成立 |
| 主路径闭环 | `FEED -> SPOTLIGHT -> CONFIRM/LIMIT_CONFIRM -> RESULT -> FEED/PORTFOLIO` 已完整跑通 | 已成立 |
| 页面数量 | 当前主页面集合已经足够，默认不建议扩张顶层页面 | 不建议扩张 |
| 交互一致性 | `A/B/Y` 整体一致；`X` 存在最高风险的跨页面语义跳变 | 部分成立 |
| 产品边界 | 适合做“短路径、高确定性、低误触”的交易产品，不适合做全量能力拼盘 | 应明确收边界 |
| 当前最大缺口 | 不是 UI 缺页，而是同名币消歧、确认超时解释、搜索闭环、资产身份强化、真机证据链 | 必须收口 |
| 继续集成方向 | 优先补 wallet/pair/tx detail 这类能强化既有心智模型的能力；不优先接 approve/transfer/self-custody 等改写产品边界的能力 | 有选择地集成 |
| 发布判断 | 工程上可跑通；产品上仍未达到 launch-grade | 暂不建议按“完整产品”对外承诺 |

---

## 2. 当前产品形态总评

| 评估项 | 当前状态 | 评价 | 证据 |
|---|---|---|---|
| 产品一句话定义 | 手持 AVE 交易助手 | 清晰 | `docs/ave-full-capability-matrix-2026-04-09.md`、`docs/product-surface-audit-2026-04-08.md` |
| 首页形态 | FEED 列表 + 本地 Explore 浮层 | 正确 | `docs/simulator-ui-guide.md`、`shared/ave_screens/screen_feed.c` |
| 决策页形态 | SPOTLIGHT 单币详情页 | 正确 | `shared/ave_screens/screen_spotlight.c` |
| 交易风险控制 | CONFIRM / LIMIT_CONFIRM 有倒计时、防误触、watchdog | 正确 | `shared/ave_screens/screen_confirm.c`、`shared/ave_screens/screen_limit_confirm.c` |
| 交易结果页 | RESULT 手动停留，不自动跳走 | 正确 | `docs/ave-feature-map.md`、`shared/ave_screens/screen_result.c` |
| 资产页 | PORTFOLIO 支持 watch/sell/summary | 正确 | `shared/ave_screens/screen_portfolio.c` |
| 通知层 | NOTIFY 为顶层 overlay，任意键关闭并消费按键 | 有利有弊 | `shared/ave_screens/ave_screen_manager.c`、`shared/ave_screens/screen_notify.c` |
| 语音/按键路由 | 确定性路由与 LLM handoff 共存 | 成熟 | `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py` |
| 模拟器/验证体系 | 截图 gate、路由测试、交易流测试、输入同步测试齐备 | 强 | `simulator/mock/run_screenshot_test.sh`、`server/main/xiaozhi-server/test_*` |
| 真机闭环 | 硬件 transport / FN/PTT / 麦克风证据不足 | 风险项 | `shared/ave_screens/ave_transport.c`、`docs/xiaozhi-ave-architecture-2026-04-09.md` |

---

## 3. 页面体系审查表

| 页面 | 当前职责 | 是否合理 | 当前问题 | 是否需要新增顶层页替代 |
|---|---|---|---|---|
| `FEED` | 热门/榜单/来源浏览，作为产品首页 | 合理 | 来源切换与搜索入口已可发现，但 Search 闭环仍弱 | 否 |
| `FEED_SEARCH` | 承接搜索结果 | 合理 | 返回后搜索上下文恢复不足 | 否 |
| `FEED_SPECIAL_SOURCE` | 平台/专题来源列表 | 合理 | 来源宇宙边界表达不够强 | 否 |
| `FEED_ORDERS` | 未完成挂单浏览 | 暂可接受 | 已进入首页，但仍是 browse-only，产品承诺感偏强 | 否 |
| `SPOTLIGHT` | 单币详情与买卖决策入口 | 合理 | 卖出快捷过重，资产身份信息仍可加强 | 否 |
| `CONFIRM` | 市价交易确认 | 合理 | 超时/回退解释不够产品化 | 否 |
| `LIMIT_CONFIRM` | 限价单确认 | 合理 | 同上，且“市价/限价差异”提示可更强 | 否 |
| `RESULT` | 成功/失败终态展示 | 合理 | 缺少明确 next step 文案 | 否 |
| `PORTFOLIO` | 持仓总览、watch/sell | 合理 | 缺少 wallet/pnl 解释层，P&L 多为 `N/A` | 否 |
| `NOTIFY` | 轻量系统解释层 | 必要 | 任意键消费会吞掉连续操作 | 否 |

### 页面扩张结论

| 结论 | 说明 |
|---|---|
| 默认不扩张顶层页面 | 当前 7 个主页面已经能承载清晰心智模型 |
| 可以接受 1 个新增过渡页 | 仅在“同名币消歧/资产身份确认”必要时，考虑新增 `DISAMBIGUATION` |
| 不建议新增的页面 | 独立 Search 页、独立 Orders 管理中心、独立 Wallet 分析页、独立 Signals/Whale 页、独立 Approve/Transfer 页 |

---

## 4. 已有能力 / 缺失项 / 是否应集成 / 是否需要新页面

### 4.1 交易主路径相关

| 能力 | 当前状态 | 缺失/问题 | 是否应集成/继续做 | 是否需要新页面 |
|---|---|---|---|---|
| 热门/榜单 FEED | 已实现 | 来源边界说明不足 | 继续保留 | 否 |
| 平台来源 FEED | 已实现 | 来源覆盖子集未显式告知 | 应补文案 | 否 |
| 搜索 token | 已实现 | 入口有了，闭环未完成 | 必须继续做 | 否 |
| Token detail + kline + risk | 已实现 | 资产身份信息不足 | 必须继续做 | 否 |
| 市价买入 | 已实现 | 资产身份确认仍弱 | 继续做 | 否 |
| 市价卖出 | 已实现 | 快捷卖出风险高 | 必须加护栏 | 否 |
| 限价买入 | 已实现 | 解释层不足 | 继续做 | 否 |
| 挂单列表/撤单 | 已实现（浏览 + 语音/工具侧撤单） | 首页 orders 仍是 browse-only，用户心智未完全对齐 | 应补解释层 | 否 |
| 结果页/通知页 | 已实现 | 缺少 next step | 应继续做 | 否 |
| Portfolio watch/sell | 已实现 | 资产解释层不足 | 应继续做 | 否 |

### 4.2 可补但应并入现有页的能力

| 能力 | 当前状态 | 产品价值 | 是否建议集成 | 最佳落位 | 是否需要新页面 |
|---|---|---|---|---|---|
| `GET /v2/address/walletinfo` | 未接 | 强化“我的钱包是什么” | 建议 | `PORTFOLIO` 解释层 | 否 |
| `GET /v2/address/walletinfo/tokens` | 未接 | 强化持仓数据来源与构成 | 建议 | `PORTFOLIO` 下钻信息 | 否 |
| `GET /v2/address/pnl` | 未接 | 改善持仓心智 | 建议 | `PORTFOLIO` 汇总/解释层 | 否 |
| `GET /v2/address/tx` | 未接 | 可解释钱包近期行为 | 可做 | `PORTFOLIO` 二级解释 | 否 |
| `GET /v2/pairs/{pair}-{chain}` | 未接 | 强化 `SPOTLIGHT` 的交易池视角 | 建议 | `SPOTLIGHT` 增强信息区 | 否 |
| `GET /v2/txs/detail` | 未接 | 强化结果/事件解释 | 建议 | `SPOTLIGHT` / `RESULT` 解释层 | 否 |

### 4.3 不建议进入当前主产品表面的能力

| 能力 | 当前状态 | 为什么不建议进入当前产品主表面 | 结论 |
|---|---|---|---|
| approve / getApprove | 未接 | 改写产品边界，从交易助手变成 token allowance 管理器 | 不集成 |
| transfer / getTransfer | 未接 | 改写心智模型，进入资金转账产品域 | 不集成 |
| delegate wallet lifecycle | 未接 | 会引入钱包管理流程与状态负担 | 暂不集成 |
| chain wallet / self-custody signed tx | 未接 | 风险模型完全不同，显著增加输入复杂度 | 暂不集成 |
| `tx/multi_tx/liq` 实时流 | 未接 | 噪声高，与当前 anti-抢屏原则冲突 | 暂不集成 |
| smart wallet / signals / whale / holders 全量页 | 未接 | 会把产品从“操作助手”拖向“研究终端” | 暂不集成 |
| 多钱包切换 | 未接 | 当前屏幕、按钮与路由都不适合承载 | 暂不集成 |

---

## 5. 按键冲突正式审查表

### 5.1 系统级键位规则

| 键位 | 当前语义 | 风险等级 | 是否允许复用 | 正式产品结论 |
|---|---|---|---|---|
| `Y` | 全局去 `PORTFOLIO`；在确认页先取消再跳转 | 低 | 不允许 | 系统保留键，绝不复用 |
| `FN/PTT/F1` | 监听 start/stop | 中 | 不允许 | 系统保留键，绝不复用 |
| `P` | 仅模拟器 mock scene switch | 中 | 不允许进入真机产品契约 | 仅模拟器保留 |
| `A` | 主进入/确认/买入 | 中 | 可复用 | 仅允许做“主前进/主确认” |
| `B` | 返回/取消/关闭局部层/标准 FEED 打开 Explore | 中 | 可复用 | 仅允许做“返回家族”语义 |
| `X` | FEED 切来源；SPOTLIGHT/PORTFOLIO 卖出 | 高 | 仅限受控复用 | 冻结为两族语义，不得再增加第三语义 |
| `UP/DOWN` | 列表选择 / K 线周期 / 浮层选择 | 低 | 可复用 | 保持“线性移动” |
| `LEFT/RIGHT` | 页内导航 / 刷新 / 进入下一层 | 中 | 可复用 | 保持“页内横向控制” |

### 5.2 当前最重要冲突点

| 冲突项 | 表现 | 产品风险 | 结论 |
|---|---|---|---|
| `X` 在 FEED vs SPOTLIGHT/PORTFOLIO 语义跳变 | FEED 是 source switch，资产页是 sell | 高误触、高心理负担 | 当前最重要按钮冲突，必须收口 |
| `B` 多义 | 返回/取消/打开 Explore/回来源 | 可接受但需规范 | 仍属同一家族，可保留 |
| NOTIFY 消费任意键 | 老用户连续操作时会被吞 | 中 | 可保留，但需解释 |
| Orders 上首页但 browse-only | 用户以为可管理订单 | 中 | 需加强入口层文案与边界说明 |

### 5.3 按键冲突处理结论

| 项目 | 产品判断 |
|---|---|
| `Y` | 永久全局保留，不做任何页面复用 |
| `FN/PTT/F1` | 永久语音保留，不允许被 Search / 页面操作借用 |
| `X` | 冻结，不再新增语义；未来仅允许维持“FEED=来源切换 / 资产上下文页=卖出”两种现状之一 |
| `A` | 维持主正向动作，不做工具类功能 |
| `B` | 维持返回/取消/关闭语义；Explore 作为标准 FEED 的局部入口仍可接受 |

---

## 6. 产品边界正式定义

| 边界项 | 当前应保持的边界 |
|---|---|
| 产品核心任务 | 看榜单、看详情、买入、卖出、确认、看结果、看持仓 |
| 不承担的任务 | 钱包管理、转账、approve 管理、自托管签名、研究终端、全量链上流噪声监控 |
| 输入哲学 | 八键 + 语音；短路径、低误触、高确定性 |
| 页面哲学 | 少页面、强状态机、弱自由编辑 |
| 实时数据哲学 | 为当前页面服务，不为了“实时而实时”；遵守 anti-抢屏原则 |
| 语音哲学 | 只有 authoritative selection 才允许“看这个/买这个”；缺字段 fail-closed |
| 验证哲学 | 模拟器与截图 gate 可强覆盖，但发布前仍需真机证据链 |

---

## 7. 当前必须补的产品缺口（发布阻断视角）

| ID | 问题 | 用户影响 | 优先级 | 建议 |
|---|---|---|---|---|
| P0-1 | 同名币/资产身份消歧不足 | 用户可能看错/买错资产 | P0 | 增加资产身份强化；必要时引入 `DISAMBIGUATION` |
| P0-2 | CONFIRM/LIMIT_CONFIRM 超时解释不足 | 用户不理解为什么没成交/为什么回退 | P0 | 建立 timeout/result/notify 解释层 |
| P0-3 | `X` 跨页面语义冲突 | 误触卖出风险 | P0 | 冻结键位宪法并加显式护栏 |
| P1-1 | Search 可发现但不自闭环 | 新手不会完成搜索路径 | P1 | 做搜索闭环与返回恢复 |
| P1-2 | RESULT/NOTIFY 缺 next step | 用户看到结果但不知下一步做什么 | P1 | 增加下一步动作建议 |
| P1-3 | Orders 首页承诺感高于实际能力 | 认知落差 | P1 | 加“仅查看”说明与解释层 |
| P1-4 | PORTFOLIO 缺 wallet/pnl 解释层 | 用户不理解 `N/A` 与数据来源 | P1 | 接入 wallet/pnl 解释能力 |
| P0-HW | 真机 bridge 证据不足 | 无法做稳定发布承诺 | P0 | 补真机链路验证 |

---

## 8. 正式产品建议清单

### 8.1 必须做

| 类别 | 建议 |
|---|---|
| 资产安全 | 做资产身份强化与同名币消歧 |
| 交易解释 | 做确认超时/提交中/延迟结果/失败结果的解释层 |
| 交互治理 | 固化键位宪法，尤其冻结 `X`/`Y`/`FN` |
| 搜索闭环 | 补 Search 首次完成路径与返回恢复 |
| 发布门槛 | 补真机证据链 |

### 8.2 应该做

| 类别 | 建议 |
|---|---|
| `SPOTLIGHT` 增强 | 补 pair / tx detail 的解释信息 |
| `PORTFOLIO` 增强 | 补 walletinfo / wallet tokens / pnl 解释层 |
| Orders 体验 | 做“当前仅查看”的解释与后续路标 |
| 结果页体验 | 成功/失败统一给 next step |

### 8.3 不该做

| 类别 | 建议 |
|---|---|
| 页面扩张 | 不要为每个 API 新开顶层页 |
| 能力泛化 | 不要把 approve/transfer/self-custody 拉进当前主产品 |
| 实时噪声 | 不要把 `tx/multi_tx/liq` 直接塞进首页主表面 |
| 键位滥用 | 不要复用 `Y/FN`，不要给 `X` 增加第三语义 |

---

## 9. 最终产品判断

| 问题 | 判断 |
|---|---|
| 当前产品形态是否成立 | 成立 |
| 当前是否缺很多页面 | 不缺 |
| 当前应优先补页面还是补体验收口 | 优先补体验收口 |
| 当前是否应继续扩能力面 | 应选择性集成，不应无边界扩张 |
| 当前最该守住的产品原则 | 少而准、低误触、强确定性 |

