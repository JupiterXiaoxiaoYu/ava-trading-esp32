# AVE Cloud Skill 能力缺口清单（2026-04-11）

> 目标：基于最新 `ave-cloud-skill` 主线、当前 `ava-trading-esp32` 实现，以及 2026-04-11 的实时 API/WSS 探测，给出一份“现在还没接哪些 AVE 能力”的准确清单。

## 0. 本次基线

- `C:\Users\72988\Desktop\AVE\ave-cloud-skill` 已再次 `git pull --ff-only`，当前 HEAD 为 `5eaef99e151aeb595416f50294152f09d2201556`
- 本轮对照以当前代码为准，不再沿用 2026-04-09 那批旧文档里的旧结论
- 关键证据来源：
  - `ave-cloud-skill/scripts/ave/data/parsers.py`
  - `ave-cloud-skill/scripts/ave/trade/parsers.py`
  - `ave-cloud-skill/scripts/ave/wss/parsers.py`
  - `ava-trading-esp32/server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
  - `ava-trading-esp32/server/main/xiaozhi-server/plugins_func/functions/ave_skill_tools.py`
  - `ava-trading-esp32/server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`
  - `ava-trading-esp32/docs/ave-feature-map.md`
  - `ava-trading-esp32/docs/ave-api-live-probe-2026-04-11.raw.json`
  - `ava-trading-esp32/docs/ave-wss-live-probe-2026-04-11.raw.json`

## 1. 当前已经接入的 AVE 能力

### 1.1 Data REST

当前项目已经实际接入：

- `GET /tokens/trending`
- `GET /tokens/platform?tag=`
- `GET /ranks?topic=`
- `GET /tokens?keyword=`
- `GET /tokens/{token}-{chain}`
- `GET /contracts/{token}-{chain}`
- `GET /klines/token/{token}-{chain}`
- `POST /tokens/price`
- `GET /address/walletinfo`
- `GET /address/walletinfo/tokens`
- `GET /address/tx`
- `GET /address/pnl`
- 以及项目自用的 `GET /tokens/top100/{token}-{chain}`（用于 spotlight 的 top100 concentration 汇总）

### 1.2 Trade REST

当前项目已经实际接入：

- `POST /v1/thirdParty/chainWallet/getAmountOut`
- `POST /v1/thirdParty/tx/sendSwapOrder`
- `POST /v1/thirdParty/tx/sendLimitOrder`
- `GET /v1/thirdParty/tx/getSwapOrder`
- `GET /v1/thirdParty/user/getUserByAssetsId`
- `GET /v1/thirdParty/tx/getLimitOrder`
- `POST /v1/thirdParty/tx/cancelLimitOrder`

### 1.3 WSS

当前项目已经实际接入：

- Data WSS: `price`, `kline`
- Trade WSS: `botswap`

## 2. 旧结论里已经过时的部分

以下几项在旧文档里曾被列成“未接”，但现在已经不是缺口：

- `GET /address/walletinfo`
- `GET /address/walletinfo/tokens`
- `GET /address/tx`
- `GET /address/pnl`

它们已经通过 text-first server tools 接进当前项目，不再应被归类为“未接 API”。

## 3. 现在仍然没接的能力

## 3.1 Data REST：明确未接

### A. 发现与辅助信息

- `GET /ranks/topics`
- `GET /supported_chains`
- `GET /tokens/main`
- `POST /tokens/search`

说明：
- 这些接口当前都能在最新 `ave-cloud-skill` 和实测里工作，但项目里没有入口或复用逻辑
- 它们不会改写产品边界，属于“低风险可补”类能力

### B. 更完整的 token / pair / tx 数据面

- `GET /tokens/holders/{token}-{chain}`
- `GET /klines/pair/{pair}-{chain}`
- `GET /klines/pair/ondo/{pair-or-ticker}`
- `GET /pairs/{pair}-{chain}`
- `GET /txs/{pair}-{chain}`
- `GET /txs/liq/{pair}-{chain}`
- `GET /txs/detail`
- `GET /signals/public/list`

说明：
- 这是当前最主要的数据能力缺口
- 项目现在有 `top100` 汇总，但没有接 `holders` 列表接口，所以 holders 能力是“部分覆盖”，不是“完整接入”
- `pair / tx / liq / tx_detail` 这组接口对 `SPOTLIGHT`、`RESULT`、解释层最有价值
- `signals` 已经可以实时返回结构化公共信号，但当前产品没有任何接入

### C. 钱包策略/聪明钱能力

- `GET /address/smart_wallet/list`

说明：
- 这是当前确实没接的一条 address/data 能力
- 它已经能 live probe 成功返回 100 条结构化 smart wallet 数据
- 但它会把产品引向“聪明钱/策略发现”方向，不是当前主交易助手的最短路径

## 3.2 Data WSS：明确未接

- `tx`
- `multi_tx`
- `liq`

说明：
- 这三条 topic 在 2026-04-11 的 live WSS probe 中都能订阅到真实消息
- 当前设备端只消费 `price` 和 `kline`
- 如果后续要做实时异动、whale alert、池子流动性提醒，这三条就是现成入口

## 3.3 Trade REST：明确未接

### A. 非破坏性 / 能力扩展类

- `POST /v1/thirdParty/chainWallet/getAutoSlippage`
- `GET /v1/thirdParty/chainWallet/getGasTip`
- `POST /v1/thirdParty/chainWallet/createEvmTx`
- `POST /v1/thirdParty/chainWallet/createSolanaTx`
- `POST /v1/thirdParty/chainWallet/sendSignedEvmTx`
- `POST /v1/thirdParty/chainWallet/sendSignedSolanaTx`

说明：
- 这组属于 self-custody / chain-wallet 能力面
- 当前项目明确偏 proxy-wallet + device UI，不走本地私钥签名路线，因此尚未接入
- 其中 `getAutoSlippage` / `getGasTip` 本身是安全的扩展型能力，不一定要等 self-custody 才能复用

### B. Proxy wallet 管理 / allowance / transfer

- `POST /v1/thirdParty/user/generateWallet`
- `POST /v1/thirdParty/user/deleteWallet`
- `POST /v1/thirdParty/tx/approve`
- `GET /v1/thirdParty/tx/getApprove`
- `POST /v1/thirdParty/tx/transfer`
- `GET /v1/thirdParty/tx/getTransfer`

说明：
- 这组能力当前没有接入，是明确缺口
- 但它们会把产品边界从“交易助手”扩到“钱包管理 / allowance 管理 / 资金划转”
- 从产品方向上看，这些能力不一定应该优先接

## 4. 当前最准确的“缺口地图”

| 能力族 | 当前状态 | 备注 |
|---|---|---|
| 钱包 overview / tokens / tx / pnl | 已接 | text-first，不是新 screen |
| rank topics / supported chains / main tokens | 未接 | 低风险信息增强 |
| search-details | 未接 | 适合批量 enrich |
| holders list | 未接 | 但已有 `top100` 汇总做部分替代 |
| pair / tx / liq / tx_detail | 未接 | 当前最值得补的一组 |
| signals | 未接 | 已可 live 返回结构化数据 |
| smart wallets | 未接 | 方向偏策略发现 |
| data WSS `tx/multi_tx/liq` | 未接 | live WSS 已证实可用 |
| chain-wallet auto-slippage / gas-tip | 未接 | 可单独复用，不必整套 self-custody |
| chain-wallet create/send tx | 未接 | self-custody 能力面 |
| generate/delete wallet | 未接 | 产品边界外扩 |
| approve / transfer / getApprove / getTransfer | 未接 | 产品边界外扩 |

## 5. 建议优先级

### P1：最值得补的“已有产品心智增强项”

- `POST /tokens/search`
- `GET /pairs/{pair}-{chain}`
- `GET /txs/{pair}-{chain}`
- `GET /txs/detail`
- `GET /txs/liq/{pair}-{chain}`
- `GET /tokens/holders/{token}-{chain}`

原因：
- 不改当前主产品边界
- 直接增强 `FEED / SPOTLIGHT / RESULT` 的解释力
- 与现在的 UI 表面和交易路径最贴近

### P2：可作为增强插件，但不该抢主路径优先级

- `GET /ranks/topics`
- `GET /supported_chains`
- `GET /tokens/main`
- `GET /signals/public/list`
- `GET /address/smart_wallet/list`
- WSS `tx / multi_tx / liq`

### P3：暂不建议优先推进的边界扩展项

- `generateWallet` / `deleteWallet`
- `approve` / `getApprove`
- `transfer` / `getTransfer`
- chain-wallet 自托管 create/send/swap/approve-chain 整套流程

## 6. 这份清单与旧文档相比的关键修正

相对 2026-04-09 的旧文档，本轮最重要的修正有三点：

1. 钱包四件套已经不再是缺口
- `walletinfo`
- `walletinfo/tokens`
- `address/tx`
- `address/pnl`

2. `holders` 应改成“部分缺口”而不是“完全没做”
- 项目现在直接用了 `/tokens/top100/{token}-{chain}` 做 concentration 汇总
- 但没接 `/tokens/holders/{token}-{chain}` 的列表能力

3. 当前 `ave-cloud-skill` 最新主线比旧文档更大
- 现在应把 `getAutoSlippage`、`getGasTip`、chain-wallet create/send 等都纳入对照范围

## 7. 结论

当前项目最真实的 API 差距，不再是钱包分析层，而是：

- `pair / tx / liq / tx_detail` 这一组交易解释型数据
- `holders` 列表能力
- `signals` 与 `smart_wallets` 这类新方向数据
- Data WSS 的 `tx / multi_tx / liq`
- 以及 trade 侧尚未接入的 allowance / transfer / self-custody 能力面

如果只按“最划算、最不改产品边界”的原则继续，下一批最推荐的是：

1. `POST /tokens/search`
2. `GET /pairs/{pair}-{chain}`
3. `GET /txs/{pair}-{chain}`
4. `GET /txs/detail`
5. `GET /txs/liq/{pair}-{chain}`
6. `GET /tokens/holders/{token}-{chain}`
