# AVE Cloud Skill 更新差异与能力缺口清单（2026-04-09）

> 目的：记录 `C:\Users\72988\Desktop\AVE\ave-cloud-skill` 同步到最新远端后的能力变化，并对照当前 `ave-xiaozhi` 实现，明确“哪些 AVE 能力还没接”“哪些应补进 feature map”。

## 0. 同步结果

- 本次已将本地 `C:\Users\72988\Desktop\AVE\ave-cloud-skill` 直接同步到远端 `origin/main`。
- 当前同步后的头提交：`542b1a7 chore: remove docs/ and add to gitignore`
- 同步方式：`git fetch origin main && git reset --hard origin/main`
- 结论：后续对 `ave-cloud-skill` 的能力判断应以远端最新主线为准，而不是本地旧历史。

---

## 1. 本次值得关注的更新内容

真正与“AVE 新能力”最相关的更新是：

- `e4fe9a3 Feat/data rest api expansion (#17)`
- `733199b docs: correct data API error status wording`

其余更新大多属于：

- skill 结构整理
- 文档抽离/压缩
- router / response contract / operator playbook 优化
- CI / metadata / packaging 调整

这些对 `ave-xiaozhi` 的直接产品能力影响较小；真正影响“我们是否少接了 AVE 能力”的，主要是 Data REST 扩展。

---

## 2. 当前 `ave-xiaozhi` 已实现能力基线

按 `docs/ave-feature-map.md` 当前口径，`ave-xiaozhi` 已实现的数据能力主要是：

- `GET /tokens/trending`
- `GET /tokens/platform?tag=`
- `GET /ranks?topic=`
- `GET /tokens?keyword=`
- `GET /tokens/{addr}-{chain}`
- `GET /klines/token/{addr}-{chain}`
- `GET /contracts/{addr}-{chain}`
- `POST /tokens/price`

Trade 侧已实现：

- `getAmountOut`
- `sendSwapOrder`
- `sendLimitOrder`
- `getSwapOrder`
- `getUserByAssetsId`
- `getLimitOrder`
- `cancelLimitOrder`

Data WSS 当前口径：

- 已实现：`price`、`kline`
- 未实现：`tx`、`multi_tx`、`liq`

以上是当前 feature map 的实现态，不代表官方能力全集。

---

## 3. `ave-cloud-skill` 新暴露、但 `ave-xiaozhi` 目前未应用的能力

以下能力来自最新 `ave-cloud-skill` 的 `references/data-api-doc.md` / `scripts/ave_data_rest.py`，但当前 `ave-xiaozhi` 的 `feature map` 与代码搜索中尚未看到实际接入。

### 3.1 钱包 / 地址维度能力

1. `GET /v2/address/tx`
- 作用：按钱包地址查询 swap / tx 历史
- 价值：可补“历史记录”“最近操作”“钱包行为回看”
- 当前状态：`ave-xiaozhi` 未接

2. `GET /v2/address/pnl`
- 作用：查询某钱包对某 token 的 PnL
- 价值：可补足当前 `PORTFOLIO` 中 PnL 表达不完整的问题
- 当前状态：未接

3. `GET /v2/address/walletinfo/tokens`
- 作用：查询钱包 token 持仓明细
- 价值：比当前只依赖 trade 侧 `getUserByAssetsId` 更接近数据侧完整资产视图
- 当前状态：未接

4. `GET /v2/address/walletinfo`
- 作用：查询钱包总览
- 价值：可补充 portfolio summary / wallet overview / aggregate stats
- 当前状态：未接

5. `GET /v2/address/smart_wallet/list`
- 作用：查询 smart wallet 列表
- 价值：偏策略/跟单/聪明钱方向
- 当前状态：未接

### 3.2 补充市场数据能力

6. `POST /v2/tokens/search`
- 作用：按 `token_ids` 批量查 token detail
- 价值：适合批量补全 FEED / watchlist / result enrich
- 当前状态：未接

7. `GET /v2/tokens/holders/{token_address}-{chain}`
- 作用：更完整的 holders 数据
- 价值：比当前单纯 risk 展示更适合做 holders 相关详情页
- 当前状态：未接

8. `GET /v2/pairs/{pair_address}-{chain}`
- 作用：pair detail
- 价值：适合补 pair 级交易/流动性视角
- 当前状态：未接

9. `GET /v2/txs/detail`
- 作用：单笔交易 detail
- 价值：适合 result / history drill-down / debug / operator view
- 当前状态：未接

10. `GET /v2/txs/liq/{pair_address}-{chain}`
- 作用：liquidity transactions
- 价值：适合池子异动 / 流动性变化分析
- 当前状态：未接

11. `GET /v2/signals/public/list`
- 作用：public trading signals
- 价值：偏策略/信号流产品线
- 当前状态：未接

12. `GET /v2/klines/pair/ondo/{pair_address-chain or ticker}`
- 作用：Ondo 特定 pair kline
- 价值：专题性较强，不是通用主路径能力
- 当前状态：未接

---

## 4. 哪些能力应该补进 `docs/ave-feature-map.md`

这里分成两种口径：

### 4.1 应立即补进 feature map 的“未集成能力清单”

这些能力即使暂时不做产品接入，也建议在 `docs/ave-feature-map.md` 新增一节（例如“Additional AVE Data capabilities not yet integrated”）明确记上，避免团队误以为官方没有：

- `GET /v2/address/tx`
- `GET /v2/address/pnl`
- `GET /v2/address/walletinfo/tokens`
- `GET /v2/address/walletinfo`
- `GET /v2/address/smart_wallet/list`
- `POST /v2/tokens/search`
- `GET /v2/tokens/holders/{token_address}-{chain}`
- `GET /v2/pairs/{pair_address}-{chain}`
- `GET /v2/txs/detail`
- `GET /v2/txs/liq/{pair_address}-{chain}`
- `GET /v2/signals/public/list`
- `GET /v2/klines/pair/ondo/...`

原因：
- 这类信息属于“官方能力边界”，不是纯产品规划
- 即使当前未接，也应让 feature map 对“已知官方能力全集”更完整
- 但应明确标注为 `not integrated`，不能写成 `implemented`

### 4.2 最值得进入近期集成候选的能力

如果按产品价值排优先级，我建议优先关注以下几项，并在 feature map 中额外标记为“recommended next integration candidates”：

1. `GET /v2/address/tx`
- 原因：最直接补历史能力

2. `GET /v2/address/pnl`
- 原因：直接增强 portfolio / position understanding

3. `GET /v2/address/walletinfo/tokens`
- 原因：提升持仓列表的完整性与数据解释力

4. `GET /v2/address/walletinfo`
- 原因：补总览与 summary

5. `GET /v2/pairs/{pair_address}-{chain}`
- 原因：为交易详情和 pair 视角扩展打基础

6. `GET /v2/txs/detail`
- 原因：适合结果页和 operator/debug 深挖

### 4.3 暂时不建议优先推进、但应在 feature map 记录为可用能力

- `GET /v2/address/smart_wallet/list`
- `GET /v2/signals/public/list`
- `GET /v2/klines/pair/ondo/...`
- `GET /v2/tokens/holders/{token_address}-{chain}`
- `GET /v2/txs/liq/{pair_address}-{chain}`

原因：
- 更偏信号流/策略流/分析增强
- 与当前 `FEED -> SPOTLIGHT -> CONFIRM -> RESULT` 主路径关系没那么直接
- 一旦接入，容易把产品带向新方向，而不是补当前主体验缺口

---

## 5. 关于 WSS 能力：这次没有新增结论，但我们仍没接全

`ave-cloud-skill` 对 Data WSS 的表达依然明确支持：

- `price`
- `tx`
- `multi_tx`
- `liq`
- `kline`

而当前 `ave-xiaozhi` 的 feature map 已经写明：

- 已实现：`price`, `kline`
- 未实现：`tx`, `multi_tx`, `liq`

因此这部分**不属于这次新发现的能力缺口**，但仍然是现有已知未集成能力。

建议：
- feature map 维持现状即可
- 不需要因为这次同步再新增一遍
- 但如果未来走“实时异动/提醒/whale alerts”方向，这里会成为直接可用入口

---

## 6. 建议动作

### A. 文档动作

建议后续把 `docs/ave-feature-map.md` 增加一节：

- `Additional official AVE Data capabilities not yet integrated`

并把本文件第 4.1 节列出的 endpoint 全部纳入，统一标注为：

- `available in latest ave-cloud-skill / not integrated in ave-xiaozhi`

### B. 产品动作

如果只选一批近期值得做的能力，优先顺序建议是：

1. `address/tx`
2. `address/pnl`
3. `address/walletinfo/tokens`
4. `address/walletinfo`
5. `pairs/{pair}`
6. `txs/detail`

### C. 不建议误判的点

- 不要把这些能力直接补进 feature map 的 `implemented` 区域
- 应该补进 feature map 的“官方可用但当前未集成”区域
- 否则会污染当前实现态与未来候选态的边界

---

## 7. 本次判断的证据来源

- `C:\Users\72988\Desktop\AVE\ave-cloud-skill` 同步后头提交：`542b1a7`
- `C:\Users\72988\Desktop\AVE\ave-cloud-skill\references\data-api-doc.md`
- `C:\Users\72988\Desktop\AVE\ave-cloud-skill\scripts\ave_data_rest.py`
- `/home/jupiter/ave-xiaozhi/docs/ave-feature-map.md`
- `/home/jupiter/ave-xiaozhi` 全局代码搜索（用于判断是否已有实际接入）
