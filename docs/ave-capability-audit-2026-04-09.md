# AVE 能力全面审计对照表（2026-04-09）

> 对照来源：
> 1. `C:\Users\72988\Desktop\AVE\ave-cloud-skill`
> 2. `/home/jupiter/ave-xiaozhi`
> 3. 官方文档：`https://ave-cloud.gitbook.io/data-api`、`https://docs-bot-api.ave.ai/`

## 0. 结论摘要

- `ave-xiaozhi` 已实现：交易主路径、核心行情/搜索/持仓、Data WSS `price/kline`、Trade WSS `botswap`、完整设备 UI 与强验证层。
- `ave-cloud-skill` / 官方文档已覆盖但 `ave-xiaozhi` 尚未接入的最大差距：钱包地址分析、Pair/Tx detail、Liquidity tx、Signals、Smart Wallet、Chain Wallet 全链路、Approve/Transfer、更多 wallet lifecycle。
- 当前最值得补的不是再扩交易按钮，而是：`address/tx`、`address/pnl`、`address/walletinfo/tokens`、`address/walletinfo`、`pairs/{pair}`、`txs/detail`。
- Data WSS `tx/multi_tx/liq` 仍是明确已知缺口，但这条线会把产品带向实时异动/监控型产品，不一定是当前最优先。

## 1. 审计基线

| 对象 | 当前状态 | 备注 |
|---|---|---|
| `ave-cloud-skill` | 已同步到 `origin/main` | 头提交 `542b1a7` |
| `ave-cloud-skill` skill 版本 | `2.3.0` | `ave-wallet-suite` / `data-rest` / `data-wss` / `trade-chain-wallet` / `trade-proxy-wallet` |
| `ave-xiaozhi` | 当前工作区实现态 | 以 `docs/ave-feature-map.md` + 代码 + tests 为准 |
| 官方 Data API 文档 | 已核对 | 以 Data API 公共页面与 skill references 交叉确认 |
| 官方 Trade API 文档 | 已核对 | 以 `docs-bot-api.ave.ai` 可访问页面 + `ave-cloud-skill/references/trade-api-doc.md` 交叉确认 |

## 2. 顶层能力域对照

| 能力域 | ave-cloud-skill | 官方文档 | ave-xiaozhi 当前实现 | 判定 |
|---|---|---|---|---|
| Router / Meta skill | 有 | 无 | 有运行时 router，但不是 skill 形态 | 我们有 runtime，不是 skill 套件 |
| Data REST 基础行情 | 全 | 全 | 已实现核心子集 | 主路径够用 |
| Data REST 钱包地址分析 | 有 | 有 | 基本未实现 | 最大缺口 |
| Data REST Pair / Tx detail / Liquidity | 有 | 有 | 未实现 | 第二梯队缺口 |
| Data WSS `price` | 有 | 有 | 已实现 | 已接 |
| Data WSS `kline` | 有 | 有 | 已实现 | 已接 |
| Data WSS `tx/multi_tx/liq` | 有 | 有 | 未实现 | 已知缺口 |
| Trade REST Proxy Wallet | 全 | 全 | 已实现核心主链路 | 主交易闭环已成立 |
| Trade REST Chain Wallet | 全 | 全 | 未作为产品能力实现 | 可用但未集成 |
| Delegate wallet lifecycle | 有 | 有 | 未实现 | 缺口 |
| Approve / Transfer | 有 | 有 | 未实现 | 缺口 |
| Trade WSS order monitor | 有 | 有 | 已实现 `botswap` 结果流 | 已接核心子集 |
| UI/Product Surface | 无设备 UI | 无设备 UI | 已实现 | 我们强项 |
| Simulator / Verification | 有操作约定 | 无 | 很强 | 我们验证层更完整 |

## 3. Data REST 端点级对照

| 端点 / 能力 | ave-cloud-skill | 官方文档 | ave-xiaozhi | 主要落点 / 备注 |
|---|---|---|---|---|
| `GET /v2/tokens` | 有 | 有 | 已实现 | 搜索 token，驱动 `FEED_SEARCH` |
| `GET /v2/tokens/platform?tag=` | 有 | 有 | 已实现 | 平台 feeds 已接，tag 子集有限 |
| `GET /v2/tokens/trending` | 有 | 有 | 已实现 | FEED 默认首页 |
| `GET /v2/ranks/topics` | 有 | 有 | 未实现为产品入口 | `ave-xiaozhi` 只直接使用 `ranks?topic=` |
| `GET /v2/ranks?topic=` | 有 | 有 | 已实现 | FEED topic feeds |
| `GET /v2/tokens/{token}-{chain}` | 有 | 有 | 已实现 | SPOTLIGHT detail |
| `POST /v2/tokens/price` | 有 | 有 | 已实现 | 买入 USD 估算、portfolio valuation |
| `GET /v2/klines/token/{token}-{chain}` | 有 | 有 | 已实现 | SPOTLIGHT chart |
| `GET /v2/klines/pair/{pair}-{chain}` | 有 | 有 | 未实现 | 我们当前 chart 不是 pair-klines 路线 |
| `GET /v2/klines/pair/ondo/...` | 有 | 有 | 未实现 | 专题能力 |
| `GET /v2/contracts/{token}-{chain}` | 有 | 有 | 已实现 | risk check / honeypot / critical gate |
| `GET /v2/tokens/main` | 有 | 有 | 未实现 | skill 有，产品未接 |
| `GET /v2/supported_chains` | 有 | 有 | 未实现 | skill 有，产品未接 |
| `GET /v2/txs/{pair}-{chain}` | 有 | 有 | 未实现为产品能力 | 我们文档未列入 feature-map implemented |
| `GET /v2/tokens/holders/{token}-{chain}` | 有 | 有 | 未实现 | 之前明确偏低优先级 |
| `POST /v2/tokens/search` | 有 | 有 | 未实现 | 新批量 detail 能力 |
| `GET /v2/pairs/{pair}-{chain}` | 有 | 有 | 未实现 | 值得补 |
| `GET /v2/txs/detail` | 有 | 有 | 未实现 | 值得补 |
| `GET /v2/txs/liq/{pair}-{chain}` | 有 | 有 | 未实现 | 可做 liquidity 异动 |
| `GET /v2/address/tx` | 有 | 有 | 未实现 | 高价值缺口 |
| `GET /v2/address/pnl` | 有 | 有 | 未实现 | 高价值缺口 |
| `GET /v2/address/walletinfo/tokens` | 有 | 有 | 未实现 | 高价值缺口 |
| `GET /v2/address/walletinfo` | 有 | 有 | 未实现 | 高价值缺口 |
| `GET /v2/address/smart_wallet/list` | 有 | 有 | 未实现 | 策略/聪明钱方向 |
| `GET /v2/signals/public/list` | 有 | 有 | 未实现 | 信号流方向 |

### 3.1 当前 `ave-xiaozhi` 已实现的 Data REST 代码落点

- `GET /tokens/trending`、`GET /ranks?topic=`、`GET /tokens/platform?tag=`：`server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- `GET /tokens?keyword=`：`ave_search_token()`
- `GET /tokens/{addr}-{chain}` + `GET /klines/token/{addr}-{chain}` + `GET /contracts/{addr}-{chain}`：`ave_token_detail()`
- `POST /tokens/price`：买入估值与 portfolio 估值

## 4. Data WSS 对照

| 能力 | ave-cloud-skill | 官方文档 | ave-xiaozhi | 判定 |
|---|---|---|---|---|
| `price` subscribe | 有 | 有 | 已实现 | FEED live price |
| `kline` subscribe | 有 | 有 | 已实现 | SPOTLIGHT live chart |
| `tx` subscribe | 有 | 有 | 未实现 | 缺口 |
| `multi_tx` subscribe | 有 | 有 | 未实现 | 缺口 |
| `liq` subscribe | 有 | 有 | 未实现 | 缺口 |
| REPL / daemon server mode | 有 | N/A | 无 | skill 侧运维能力，不是产品必需 |

### 4.1 `ave-xiaozhi` 当前 WSS 实现重点

- Data WSS：`wss://wss.ave-api.xyz`
- 已做：unsubscribe + subscribe `price` / `kline`
- FEED live updates、SPOTLIGHT live price/chart 已落地
- holders/liquidity 当前是 5 秒 REST poll，不是独立 WSS stream
- Trade WSS：`wss://bot-api.ave.ai/thirdws?...`，已接 `botswap`

## 5. Trade REST / Trade WSS 对照

### 5.1 Proxy Wallet / Bot Trade

| 端点 / 能力 | ave-cloud-skill | 官方文档 | ave-xiaozhi | 备注 |
|---|---|---|---|---|
| `POST /v1/thirdParty/chainWallet/getAmountOut` | 有 | 有 | 已实现 | 买入 quote 前置 |
| `POST /v1/thirdParty/tx/sendSwapOrder` | 有 | 有 | 已实现 | 市价买/卖 |
| `POST /v1/thirdParty/tx/sendLimitOrder` | 有 | 有 | 已实现 | 限价买 |
| `GET /v1/thirdParty/tx/getSwapOrder` | 有 | 有 | 已实现 | submit-only ACK reconciliation |
| `GET /v1/thirdParty/user/getUserByAssetsId` | 有 | 有 | 已实现 | portfolio wallet lookup |
| `GET /v1/thirdParty/tx/getLimitOrder` | 有 | 有 | 已实现 | orders list |
| `POST /v1/thirdParty/tx/cancelLimitOrder` | 有 | 有 | 已实现 | cancel order |
| `GET /v1/thirdParty/tx/history` | skill docs未主推 | 官方历史有 | 未实现 | feature map 已明确 not integrated |
| `generateWallet` | 有 | 有 | 未实现 | delegate wallet lifecycle 缺口 |
| `deleteWallet` | 有 | 有 | 未实现 | delegate wallet lifecycle 缺口 |
| `approve` / `getApprove` | 有 | 有 | 未实现 | 当前产品未做 approve 管理 |
| `transfer` / `getTransfer` | 有 | 有 | 未实现 | 当前产品未做 wallet transfer |
| `botswap` WSS 监控 | 有 | 有 | 已实现 | RESULT / NOTIFY |

### 5.2 Chain Wallet / Self-custody Trade

| 能力 | ave-cloud-skill | 官方文档 | ave-xiaozhi | 判定 |
|---|---|---|---|---|
| `createEvmTx` / `sendSignedEvmTx` | 有 | 有 | 未实现 | 未做产品集成 |
| `createSolanaTx` / `sendSignedSolanaTx` | 有 | 有 | 未实现 | 未做产品集成 |
| 本地私钥/助记词签名 | 有 | 有 | 未实现 | 当前产品明显偏 proxy-wallet |
| `swap-evm` / `swap-solana` 一步到位 | 有 | 有 | 未实现 | 未做产品集成 |

## 6. 钱包能力对照

| 钱包能力 | ave-cloud-skill | 官方文档 | ave-xiaozhi | 结论 |
|---|---|---|---|---|
| proxy wallet holdings | 有 | 有 | 已实现 | 基于 `getUserByAssetsId` |
| 钱包交易历史 | 有 | 有 | 未实现 | 高价值缺口 |
| 钱包 PnL | 有 | 有 | 未实现 | 高价值缺口 |
| 钱包 overview | 有 | 有 | 未实现 | 高价值缺口 |
| 钱包 token 明细 | 有 | 有 | 未实现 | 高价值缺口 |
| smart wallet list | 有 | 有 | 未实现 | 可选能力 |
| delegate wallet create/delete | 有 | 有 | 未实现 | 运维/交易能力缺口 |
| transfer | 有 | 有 | 未实现 | 功能缺口 |
| approve management | 有 | 有 | 未实现 | 功能缺口 |
| multi-wallet UX | skill 可支持 | 官方可支持 | 未实现 | 现有产品围绕单 `AVE_PROXY_WALLET_ID` |

## 7. UI / 产品表面对照

| 维度 | ave-cloud-skill | 官方文档 | ave-xiaozhi |
|---|---|---|---|
| 设备 UI | 无 | 无 | 有完整 FEED / SPOTLIGHT / CONFIRM / LIMIT_CONFIRM / RESULT / PORTFOLIO / NOTIFY |
| FEED Explore | 无 | 无 | 已实现 `Search / Orders / Sources` |
| Search guidance | 无 | 无 | 已实现，但仍偏 voice-guided |
| Orders surface | 无 | 无 | 已实现 browse-only |
| Portfolio surface | 无 | 无 | 已实现持仓列表、watch、sell |
| Result / Notify | 无 | 无 | 已实现，但产品引导仍弱 |
| Simulator keymap/FN-PTT | 无 | 无 | 已实现并有验证 |

## 8. 验证 / 测试能力对照

| 维度 | ave-cloud-skill | ave-xiaozhi |
|---|---|---|
| operator playbook / safe defaults | 强 | 有部分，但主要在产品文档 |
| CLI / script smoke | 强 | 有 server pytest + simulator verifier |
| screenshot regression | 无 | 强 |
| device-surface state-machine verification | 无 | 强 |
| router/context tests | 无 | 强 |
| live websocket E2E | 有运维路径 | 有产品级 E2E |

## 9. 新增能力清单（相对我们当前实现最重要）

### 9.1 必须进入 feature map 的“官方可用但当前未集成”能力

- `GET /v2/address/tx`
- `GET /v2/address/pnl`
- `GET /v2/address/walletinfo/tokens`
- `GET /v2/address/walletinfo`
- `GET /v2/address/smart_wallet/list`
- `POST /v2/tokens/search`
- `GET /v2/tokens/holders/{token}-{chain}`
- `GET /v2/pairs/{pair}-{chain}`
- `GET /v2/txs/detail`
- `GET /v2/txs/liq/{pair}-{chain}`
- `GET /v2/signals/public/list`
- `GET /v2/klines/pair/ondo/...`
- `generateWallet`
- `deleteWallet`
- `approve` / `getApprove`
- `transfer` / `getTransfer`
- Chain-wallet signed tx flows

### 9.2 最值得近期优先集成的能力

1. `GET /v2/address/tx`
2. `GET /v2/address/pnl`
3. `GET /v2/address/walletinfo/tokens`
4. `GET /v2/address/walletinfo`
5. `GET /v2/pairs/{pair}-{chain}`
6. `GET /v2/txs/detail`

### 9.3 暂不建议优先推进，但应记录为可用能力

- `GET /v2/address/smart_wallet/list`
- `GET /v2/signals/public/list`
- `GET /v2/klines/pair/ondo/...`
- `GET /v2/tokens/holders/{token}-{chain}`
- `GET /v2/txs/liq/{pair}-{chain}`
- Data WSS `tx/multi_tx/liq`（除非产品明确转向实时监控/whale alerts）
- Chain-wallet 自托管整套流程（除非产品战略改向 self-custody）

## 10. feature map 应如何更新

建议在 `docs/ave-feature-map.md` 新增一节：

- `Additional official AVE capabilities not yet integrated`

该节应拆为：
- Data REST 未集成能力
- Trade / Wallet 未集成能力
- WSS 已知未集成能力

必须注意：
- 这些不能写进 `implemented`
- 应标记为：`available in latest ave-cloud-skill / official docs, not integrated in ave-xiaozhi`

## 11. 当前最准确的整体判断

- **我们强的地方**：产品 UI、交易主路径、状态机、模拟器、验证与文档闭环。
- **我们弱的地方**：钱包分析层、交易补充能力层、更多官方 API 的“能力完整性映射”。
- **最现实的下一步**：先把新增官方能力补入 feature map 的 not-integrated 区，再决定是否推进 `address/tx + pnl + walletinfo` 这一批。

## 12. 证据来源

- `C:\Users\72988\Desktop\AVE\ave-cloud-skill`（同步后 `542b1a7`）
- `C:\Users\72988\Desktop\AVE\ave-cloud-skill\skills\*`
- `C:\Users\72988\Desktop\AVE\ave-cloud-skill\scripts\ave_data_rest.py`
- `C:\Users\72988\Desktop\AVE\ave-cloud-skill\scripts\ave_data_wss.py`
- `C:\Users\72988\Desktop\AVE\ave-cloud-skill\scripts\ave_trade_rest.py`
- `C:\Users\72988\Desktop\AVE\ave-cloud-skill\scripts\ave_trade_wss.py`
- `C:\Users\72988\Desktop\AVE\ave-cloud-skill\references\data-api-doc.md`
- `C:\Users\72988\Desktop\AVE\ave-cloud-skill\references\trade-api-doc.md`
- `/home/jupiter/ave-xiaozhi/docs/ave-feature-map.md`
- `/home/jupiter/ave-xiaozhi/docs/simulator-ui-guide.md`
- `/home/jupiter/ave-xiaozhi/docs/xiaozhi-ave-architecture-2026-04-09.md`
- `/home/jupiter/ave-xiaozhi` 代码与 tests 全局审计
