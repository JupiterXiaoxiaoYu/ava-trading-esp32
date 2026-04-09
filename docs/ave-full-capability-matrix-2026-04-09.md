# AVE 全量能力对照总表（2026-04-09）

> 目的：对 `ave-cloud-skill/`、`ave-xiaozhi/` 当前实现、以及官方 AVE API 文档做一次尽可能完整的三方对照。
>
> 审计对象：
> 1. `C:\Users\72988\Desktop\AVE\ave-cloud-skill`
> 2. `/home/jupiter/ave-xiaozhi`
> 3. 官方文档：`https://ave-cloud.gitbook.io/data-api`、`https://docs-bot-api.ave.ai/`
>
> 审计日期：2026-04-09

---

## 0. 结论先看

- `ave-xiaozhi` 已经具备完整的 AVE 产品主闭环：`FEED -> SPOTLIGHT -> CONFIRM/LIMIT_CONFIRM -> RESULT -> FEED/PORTFOLIO`，并且服务端、模拟器、截图 gate、router/context、trade flow tests 都比较完整。
- `ave-cloud-skill` 的能力面已经明显大于 `ave-xiaozhi` 当前接入面，尤其是 Data REST 的钱包地址分析、pair/tx detail、signals、Ondo kline、holders 新路径，以及 Trade 的 approve/transfer/wallet lifecycle/chain wallet。
- 官方 live docs 与 `ave-cloud-skill` 并不完全一致：
  - 部分官方文档明显滞后于 repo / local references；
  - 部分地方官方 live docs 与 repo 参数/路径不一致，需要标成高风险差异；
  - 官方 release notes 还有少量 repo 尚未跟进的新能力。
- 当前最大缺口不是 UI，而是“官方能力完整映射”：钱包分析、pair/tx detail、更多交易周边能力、以及官方最新能力和本地封装之间的差异收敛。

---

## 1. 审计基线与证据来源

### 1.1 `ave-cloud-skill`

- 仓库：`C:\Users\72988\Desktop\AVE\ave-cloud-skill`
- 当前同步头：`542b1a7`
- 关键 skill：
  - `skills/ave-wallet-suite/SKILL.md`
  - `skills/data-rest/SKILL.md`
  - `skills/data-wss/SKILL.md`
  - `skills/trade-chain-wallet/SKILL.md`
  - `skills/trade-proxy-wallet/SKILL.md`
- 关键脚本：
  - `scripts/ave_data_rest.py`
  - `scripts/ave_data_wss.py`
  - `scripts/ave_trade_rest.py`
  - `scripts/ave_trade_wss.py`
- 关键本地 reference：
  - `references/data-api-doc.md`
  - `references/trade-api-doc.md`

### 1.2 `ave-xiaozhi`

- 功能地图：`/home/jupiter/ave-xiaozhi/docs/ave-feature-map.md`
- 架构审计：`/home/jupiter/ave-xiaozhi/docs/xiaozhi-ave-architecture-2026-04-09.md`
- 产品面审计：
  - `/home/jupiter/ave-xiaozhi/docs/product-surface-audit-2026-04-08.md`
  - `/home/jupiter/ave-xiaozhi/docs/product-review-2026-04-07.md`
  - `/home/jupiter/ave-xiaozhi/docs/simulator-ui-guide.md`
- 关键代码：
  - `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
  - `server/main/xiaozhi-server/plugins_func/functions/ave_trade_mgr.py`
  - `server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`
  - `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py`
  - `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`
  - `shared/ave_screens/*`
  - `simulator/src/*`
- 关键测试：
  - `server/main/xiaozhi-server/test_ave_api_matrix.py`
  - `server/main/xiaozhi-server/test_ave_router.py`
  - `server/main/xiaozhi-server/test_p3_trade_flows.py`
  - `server/main/xiaozhi-server/test_p3_orders.py`
  - `server/main/xiaozhi-server/test_surface_input_sync.py`
  - `server/main/xiaozhi-server/test_ave_voice_protocol.py`
  - `server/main/xiaozhi-server/test_portfolio_surface.py`
  - `server/main/xiaozhi-server/test_ave_e2e.py`
  - `simulator/mock/run_screenshot_test.sh`
  - `simulator/mock/verify_p3_5_minimal.c`

### 1.3 官方 API / WSS 基址

| 域 | 协议 / 基址 | 备注 |
|---|---|---|
| Data REST | `https://data.ave-api.xyz/v2` | `ave-cloud-skill/scripts/ave_data_rest.py` 使用该基址 |
| Data WSS | `wss://wss.ave-api.xyz` | JSON-RPC 2.0；需要 `X-API-KEY` |
| Trade REST | `https://bot-api.ave.ai` | proxy wallet 与 chain wallet 均在此域名下 |
| Trade WSS | `wss://bot-api.ave.ai/thirdws?ave_access_key={AVE_API_KEY}` | 目前主要订阅 `botswap` |

---

## 2. 顶层能力域总对照

| 能力域 | ave-cloud-skill | 官方文档 | ave-xiaozhi | 结论 |
|---|---|---|---|---|
| Router / Meta skill | 有 | 无 | 有 runtime router | 我们不是 skill 形态，但功能上已做 |
| Data REST 基础行情 | 很全 | 有 | 已接核心子集 | `ave-xiaozhi` 主路径够用 |
| Data REST 钱包地址分析 | 很全 | 有 | 基本未接 | 当前最大缺口 |
| Data REST pair / tx detail / liq | 有 | 有 | 未接 | 第二梯队缺口 |
| Data WSS `price` | 有 | 有 | 已接 | 已落地 |
| Data WSS `kline` | 有 | 有 | 已接 | 已落地 |
| Data WSS `tx/multi_tx/liq` | 有 | 有 | 未接 | 已知缺口 |
| Trade REST proxy wallet 主交易 | 有 | 有 | 已接核心闭环 | 主路径成立 |
| Trade REST wallet lifecycle | 有 | 有 | 未接 | 创建/删除 delegate wallet 未接 |
| Trade REST approve / transfer | 有 | 有 | 未接 | 明确缺口 |
| Trade REST chain wallet | 有 | 有 | 未产品化 | 自托管未集成 |
| Trade WSS `botswap` | 有 | 有 | 已接 | RESULT / NOTIFY 已落地 |
| 设备 UI / 状态机 | 无 | 无 | 有 | 我们强项 |
| 模拟器 / 截图回归 / router tests | 无 | 无 | 有 | 我们强项 |
| 真机 AVE bridge 证据 | N/A | N/A | 证据仍偏弱 | 仍需硬件链路确认 |

---

## 3. `ave-cloud-skill` 能力面：逐 skill 审计

| Skill | 版本 | 主要职责 | 关键结论 |
|---|---|---|---|
| `ave-wallet-suite` | `2.3.0` | 路由到 data-rest / data-wss / proxy-wallet / chain-wallet | proxy-wallet-first 的顶层路由 skill |
| `data-rest` | `2.3.0` | token / rank / kline / risk / holders / tx / wallet / signals / pair detail / tx detail | 当前能力面最宽 |
| `data-wss` | `2.3.0` | `price` / `tx` / `multi_tx` / `liq` / `kline` + REPL/daemon | 实时流封装比较完整 |
| `trade-chain-wallet` | `2.3.0` | quote / create signed tx / send signed tx / one-step swap | 自托管交易完整面 |
| `trade-proxy-wallet` | `2.3.0` | wallet lifecycle / market / limit / approve / transfer / WSS | 与官方交易主面最对齐 |

### 3.1 `ave-cloud-skill` 脚本命令面

| 脚本 | 命令面 |
|---|---|
| `scripts/ave_data_rest.py` | `search`, `platform-tokens`, `token`, `price`, `kline-token`, `kline-pair`, `kline-ondo`, `holders`, `search-details`, `txs`, `trending`, `rank-topics`, `ranks`, `risk`, `chains`, `main-tokens`, `address-txs`, `address-pnl`, `wallet-tokens`, `wallet-info`, `smart-wallets`, `signals`, `liq-txs`, `tx-detail`, `pair` |
| `scripts/ave_data_wss.py` | `watch-tx`, `watch-kline`, `watch-price`, `wss-repl`, `serve`, `start-server`, `stop-server` |
| `scripts/ave_trade_rest.py` | chain wallet: `quote`, `create-evm-tx`, `send-evm-tx`, `create-solana-tx`, `send-solana-tx`, `swap-evm`, `swap-solana`; proxy wallet: `list-wallets`, `create-wallet`, `delete-wallet`, `market-order`, `limit-order`, `get-swap-orders`, `get-limit-orders`, `cancel-limit-order`, `approve-token`, `get-approval`, `transfer`, `get-transfer` |
| `scripts/ave_trade_wss.py` | `watch-orders` (`botswap`) |

---

## 4. Data REST：全量三方对照

### 4.1 Token / Discovery / Ranking

| 端点 / 能力 | ave-cloud-skill | 官方 live docs | ave-xiaozhi | 结论 / 备注 |
|---|---|---|---|---|
| `GET /v2/tokens` | 有 | 有 | 已实现 | token search；驱动 FEED_SEARCH |
| `POST /v2/tokens/search` | 有 | 有 | 未实现 | batch detail；当前我们没接 |
| `GET /v2/tokens/platform?tag=` | 有 | 有 | 已实现 | 平台 feed 已接；tag 子集有限 |
| `GET /v2/tokens/{token}-{chain}` | 有 | 有 | 已实现 | SPOTLIGHT 主 detail |
| `POST /v2/tokens/price` | 有 | 有 | 已实现 | 买入估值 / portfolio valuation |
| `GET /v2/tokens/main` | 有 | 有 | 未实现 | skill 有；产品未接 |
| `GET /v2/tokens/trending` | 有 | 有 | 已实现 | FEED 默认首页 |
| `GET /v2/ranks/topics` | 有 | 官方 GitBook 未展示 | 未实现为产品入口 | repo / local ref 有，但 live docs 未显示 |
| `GET /v2/ranks?topic=` | 有 | 官方 GitBook 未展示 | 已实现 | FEED topic feeds 已接 |
| `GET /v2/supported_chains` | 有 | 官方 GitBook 未展示 | 未实现 | skill / local ref 有，官方 live docs 未展示 |
| `GET /v2/signals/public/list` | 有 | 官方 GitBook 未展示 | 未实现 | signals 能力未接 |
| `GET /v2/pairs/{pair}-{chain}` | 有 | 有 | 未实现 | 值得补的 pair detail |

### 4.2 Risk / Holders / Kline / Tx

| 端点 / 能力 | ave-cloud-skill | 官方 live docs | ave-xiaozhi | 结论 / 备注 |
|---|---|---|---|---|
| `GET /v2/contracts/{token}-{chain}` | 有 | 有 | 已实现 | risk / honeypot / critical gate |
| `GET /v2/tokens/top100/{token}-{chain}` | 无 | 有 | 未实现 | 官方 GitBook 仍写旧 holders 路径 |
| `GET /v2/tokens/holders/{token}-{chain}` | 有 | 官方 GitBook 未展示 | 未实现 | repo 已切到新 holders 路径 |
| `GET /v2/klines/token/{token}-{chain}` | 有 | 有 | 已实现 | SPOTLIGHT chart |
| `GET /v2/klines/pair/{pair}-{chain}` | 有 | 有 | 未实现 | 当前 chart 不是 pair klines 路线 |
| `GET /v2/klines/pair/ondo/{pair-or-ticker}` | 有 | 官方 GitBook 未展示 | 未实现 | 专题能力 |
| `GET /v2/txs/swap/{pair-id}` | 无 | 有 | 未实现 | 官方 live docs 当前是这个路径 |
| `GET /v2/txs/{pair}-{chain}` | 有 | 官方 GitBook 未展示 | 未实现为产品能力 | repo/local ref 使用此路径；与官方 live docs 有冲突 |
| `GET /v2/txs/liq/{pair}-{chain}` | 有 | 有 | 未实现 | liquidity tx 仍未接 |
| `GET /v2/txs/detail` | 有 | 官方 GitBook 未展示 | 未实现 | 值得补 |

### 4.3 Wallet / Address Analytics

| 端点 / 能力 | ave-cloud-skill | 官方 live docs | ave-xiaozhi | 结论 / 备注 |
|---|---|---|---|---|
| `GET /v2/address/tx` | 有 | 有 | 未实现 | 高价值缺口；参数面与官方 live docs 存差异 |
| `GET /v2/address/pnl` | 有 | 有 | 未实现 | 高价值缺口 |
| `GET /v2/address/walletinfo/tokens` | 有 | 有 | 未实现 | 高价值缺口 |
| `GET /v2/address/walletinfo` | 有 | 有 | 未实现 | 高价值缺口 |
| `GET /v2/address/smart_wallet/list` | 有 | 有 | 未实现 | strategy / smart money 能力 |
| `walletinfo --self_address` | 有 | 官方 live docs 未写全 | 未实现 | repo 比官方文档宽 |
| `walletinfo/tokens --blue_chips` | 有 | 官方 live docs 未写全 | 未实现 | repo 比官方文档宽 |
| smart wallet 高级 profit filters | 有 | 官方 live docs 未写全 | 未实现 | repo 比官方文档宽 |

### 4.4 `ave-xiaozhi` 当前已实现的 Data REST 落点

| 当前能力 | 主要代码落点 |
|---|---|
| `GET /tokens/trending` / `GET /tokens/platform?tag=` / `GET /ranks?topic=` | `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py` |
| `GET /tokens?keyword=` | `ave_search_token()` |
| `GET /tokens/{addr}-{chain}` + `GET /klines/token/{addr}-{chain}` + `GET /contracts/{addr}-{chain}` | `ave_token_detail()` |
| `POST /tokens/price` | 买入估值与 portfolio valuation 逻辑 |
| holders / liquidity 显示 | 来自 token detail 字段与后续 REST poll，不是 holders/liq API 独立接入 |

---

## 5. Data REST：官方文档 vs repo 的高风险差异

| 差异项 | repo / local ref | 官方 live docs | 风险判断 |
|---|---|---|---|
| swap tx list 路径 | `/v2/txs/{pair}-{chain}` | `/v2/txs/swap/{pair-id}` | P0，高风险路径差异 |
| `address/tx` 时间游标参数 | `last_time` | `to_time` | P0，高风险参数差异 |
| `address/tx` `token_address` | 可选 | 官方页显示 Required | P0，高风险参数差异 |
| holders 路径 | `/v2/tokens/holders/...` | 官方 GitBook 仍写 `/v2/tokens/top100/...` | P1，官方文档滞后可能性高 |
| `ranks/topics`, `ranks`, `supported_chains`, `signals`, `kline-ondo`, `tx-detail` | repo / local ref 有 | 官方 GitBook 未展示 | P1，需确认是未公开还是文档滞后 |

---

## 6. Data WSS：全量三方对照

| Stream / 能力 | ave-cloud-skill | 官方文档 | ave-xiaozhi | 结论 / 备注 |
|---|---|---|---|---|
| `price` subscribe | 有 | 有 | 已实现 | FEED live price |
| `kline` subscribe | 有 | 有 | 已实现 | SPOTLIGHT live chart |
| `tx` subscribe | 有 | 有 | 未实现 | 缺口 |
| `multi_tx` subscribe | 有 | 有 | 未实现 | 缺口 |
| `liq` subscribe | 有 | 有 | 未实现 | 缺口 |
| `switch_main_pair` push | 原样透传/未专门建模 | 有 | 未实现 | skill/脚本部分支持，产品未接 |
| `ping` | 官方有 | 有 | 未实现 | 非产品关键项 |
| REPL / daemon | skill 有 | N/A | 无 | 这是 repo 包装能力，不是产品功能 |

### 6.1 `ave-cloud-skill` vs 官方 WSS 细差异

| 项目 | repo / skill | 官方 | 备注 |
|---|---|---|---|
| `multi_tx` 语义 | 文案容易理解为 pair 级 | 官方是 token address 级 | P1，skill 文案不准 |
| `unsubscribe` frame | repo 常发空 `params: []` | 官方样例带 topic-specific params | P1，未证实行为 |
| `price` token/pair 支持 | skill 帮助主要写 token-id | 官方价格流支持 token-id 与 pair-id | P1，skill 文案低估能力 |

### 6.2 `ave-xiaozhi` 当前 WSS 实现状态

| 当前能力 | 状态 |
|---|---|
| Data WSS 基址 `wss://wss.ave-api.xyz` | 已实现 |
| `unsubscribe` + `subscribe price` | 已实现 |
| `subscribe kline` | 已实现 |
| FEED live price throttled push | 已实现 |
| SPOTLIGHT live price / live kline | 已实现 |
| holders/liquidity 实时感 | 部分实现，来自 5 秒 REST poll，不是独立 WSS |
| `tx` / `multi_tx` / `liq` | 未实现 |
| `API_PLAN=pro` gating | 已实现 |

---

## 7. Trade REST：Proxy Wallet 三方对照

| 端点 / 能力 | ave-cloud-skill | 官方文档 | ave-xiaozhi | 结论 / 备注 |
|---|---|---|---|---|
| `GET /v1/thirdParty/user/getUserByAssetsId` | 有 | 有 | 已实现 | portfolio wallet lookup / holdings |
| `POST /v1/thirdParty/user/generateWallet` | 有 | 有 | 未实现 | delegate wallet lifecycle 缺口 |
| `POST /v1/thirdParty/user/deleteWallet` | 有 | 有 | 未实现 | delegate wallet lifecycle 缺口 |
| `POST /v1/thirdParty/tx/sendSwapOrder` | 有 | 有 | 已实现 | market buy/sell |
| `POST /v1/thirdParty/tx/sendLimitOrder` | 有 | 有 | 已实现 | 当前是 limit buy 主路径 |
| `GET /v1/thirdParty/tx/getSwapOrder` | 有 | 有 | 已实现 | submit-only ACK reconciliation |
| `GET /v1/thirdParty/tx/getLimitOrder` | 有 | 有 | 已实现 | orders list |
| `POST /v1/thirdParty/tx/cancelLimitOrder` | 有 | 有 | 已实现 | cancel order |
| `POST /v1/thirdParty/tx/approve` | 有 | 有 | 未实现 | approve 管理未接 |
| `GET /v1/thirdParty/tx/getApprove` | 有 | 有 | 未实现 | 未接 |
| `POST /v1/thirdParty/tx/transfer` | 有 | 有 | 未实现 | transfer 未接 |
| `GET /v1/thirdParty/tx/getTransfer` | 有 | 有 | 未实现 | transfer 查询未接 |
| `GET /v1/thirdParty/tx/history` | 官方历史上有 | 有 | 未实现 | feature map 里明确 not integrated |
| `autoSlippage` / `autoGas` | 有 | 有 | 部分依赖服务端透传能力，但未单独产品化 | 主要体现在交易参数体系 |
| `autoSellConfig` / TP/SL / trailing | 有 | 有 | 部分实现 | 主路径里已有 TP/SL 相关表面 |

### 7.1 `ave-xiaozhi` 当前 proxy-wallet 已落地能力

- 市价买 / 市价卖：已实现
- 限价买：已实现
- swap order query / reconcile：已实现
- limit order list / cancel：已实现
- portfolio wallet lookup：已实现
- pending trade / submit-only ack / deferred result / botswap terminal handling：已实现
- approve / transfer / wallet lifecycle：未实现

---

## 8. Trade REST：Chain Wallet / Self-custody 三方对照

| 端点 / 能力 | ave-cloud-skill | 官方文档 | ave-xiaozhi | 结论 / 备注 |
|---|---|---|---|---|
| `POST /v1/thirdParty/chainWallet/getAmountOut` | 有 | 有 | 已实现核心 quote 用途 | 当前主要用于买入前 quote / amount estimation |
| `POST /v1/thirdParty/chainWallet/createEvmTx` | 有 | 有 | 未实现 | 未产品化 |
| `POST /v1/thirdParty/chainWallet/sendSignedEvmTx` | 有 | 有 | 未实现 | 未产品化 |
| `POST /v1/thirdParty/chainWallet/createSolanaTx` | 有 | 有 | 未实现 | 未产品化 |
| `POST /v1/thirdParty/chainWallet/sendSignedSolanaTx` | 有 | 有 | 未实现 | 未产品化 |
| `swap-evm` | skill orchestration 有 | 官方 endpoint 无 | 未实现 | repo 封装能力 |
| `swap-solana` | skill orchestration 有 | 官方 endpoint 无 | 未实现 | repo 封装能力 |
| 本地私钥 / 助记词签名 | 有 | 有 | 未实现 | 产品路线当前明显偏 proxy wallet |
| `feeRecipientRate` | repo/local ref 有 | 官方 release note 有，但英文页滞后 | 未实现 | repo 比英文文档更新 |
| `autoSlippage` | repo/local ref 有 | 官方 release note 有 | 未实现 | repo 已跟进，`ave-xiaozhi` 未接 |
| query auto-slippage by token | repo 无 | 官方 release note 有 | 未实现 | repo 本身也没跟进，是额外 gap |

### 8.1 官方英文页与 repo 的已知差异

| 项目 | repo / local ref | 官方英文页 | 判断 |
|---|---|---|---|
| EVM `txContent` | 对象 `{data,to,value}` | 仍有旧 string 表述 | 官方英文页滞后可能性高 |
| `signedTx` 编码 | hex | 英文页有 base64 表述 | 官方英文页疑似旧 / 错 |
| Solana create response | repo 兼容 `txContext` | 英文页偏旧 | repo 更贴近 PROD |
| `feeRecipientRate` | repo 已支持 | 英文参数页滞后 | 官方 release notes 更新更可信 |

---

## 9. Trade WSS：三方对照

| 能力 | ave-cloud-skill | 官方文档 | ave-xiaozhi | 结论 |
|---|---|---|---|---|
| `botswap` subscribe | 有 | 有 | 已实现 | 已接核心结果流 |
| ack/error control frame | 有 | 有 | 已实现 | 已处理 |
| confirmed/error trade result | 有 | 有 | 已实现 | RESULT |
| TP/SL/trailing/auto-cancelled notify | 有 | 有 | 已实现 | NOTIFY |
| REST as final truth / reconcile | skill/operator 层强调 | 官方未强调 | 已实现 | 我们做了 submit-only ack reconciliation |

---

## 10. `ave-xiaozhi` 当前产品 / UI / 状态机能力

### 10.1 页面能力

| 页面 / 状态 | 当前能力 | 状态 |
|---|---|---|
| `FEED` | trending/topic/platform/search/orders/explore panel | 已实现 |
| `SPOTLIGHT` | token detail、chart、risk、holders/liquidity summary、左右切 token | 已实现 |
| `CONFIRM` | 市价交易确认、倒计时、A/B/Y、watchdog | 已实现 |
| `LIMIT_CONFIRM` | 限价交易确认、目标价/现价、A/B/Y、watchdog | 已实现 |
| `RESULT` / `RESULT_FAIL` | 成功/失败结果页、手动停留、any key back、Y->portfolio | 已实现 |
| `PORTFOLIO` | holdings、watch、sell、summary | 已实现 |
| `NOTIFY` | overlay dismiss | 已实现 |
| `FEED_ORDERS` | browse-only 订单列表 | 部分实现 |

### 10.2 输入 / 导航 / 语义上下文

| 能力 | 状态 | 备注 |
|---|---|---|
| `feed_token_list + feed_cursor` | 已实现 | 供 SPOTLIGHT 左右切 token |
| `nav_from` | 已实现 | portfolio-origin 能正确回 portfolio |
| `feed_source + feed_platform` 恢复 | 已实现 | 返回时保留来源上下文 |
| RESULT 手动返回 | 已实现 | 非 Y 键 back，Y 到 portfolio |
| trusted selection fail-closed | 已实现 | “这个/买这个”必须带本轮可信 selection |
| per-turn `AVE_CONTEXT` 注入 LLM | 已实现 | 当前页面语义和数据上下文会传入 |
| Explore / Orders browse-only 约束 | 已实现 | 不做不可信 fallback |

### 10.3 语音 / FN / PTT / 模拟器

| 能力 | 状态 | 备注 |
|---|---|---|
| 模拟器 `F1` -> `listen start/stop` | 已实现 | manual listen mode |
| 模拟器 stdin 文本注入 | 已实现 | 调试用途 |
| deterministic text router | 已实现 | `看这个/买这个/确认/取消/返回/我的持仓` 等 |
| 真机 FN/PTT + 真麦克风全链 | 证据不足 | 当前仓库仍缺强真机闭环证据 |
| `shared/ave_screens/ave_transport.c` 硬件分支 | 部分实现 / TODO | 模拟器分支完整，硬件桥接证据不足 |

### 10.4 测试 / 验证能力

| 维度 | 状态 |
|---|---|
| API / contract matrix | 已实现 |
| router / selection / context tests | 已实现 |
| trade flow / pending / result / portfolio nav tests | 已实现 |
| orders flow tests | 已实现 |
| portfolio surface tests | 已实现 |
| surface input sync tests | 已实现 |
| voice protocol tests | 已实现 |
| simulator screenshot regression | 已实现 |
| fallback probe / local state-machine verification | 已实现 |
| live websocket E2E | 有，但更偏 smoke script |
| 真机 E2E | 证据不足 |

---

## 11. 当前新增能力清单：相对 `ave-xiaozhi` 的确凿缺口

### 11.1 官方/skill 都有，但 `ave-xiaozhi` 未接

#### Data REST

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
- `GET /v2/tokens/main`
- `GET /v2/supported_chains`
- `GET /v2/ranks/topics`

#### Data WSS

- `tx`
- `multi_tx`
- `liq`
- `switch_main_pair` 事件处理

#### Trade REST / Wallet

- `generateWallet`
- `deleteWallet`
- `approve`
- `getApprove`
- `transfer`
- `getTransfer`
- chain-wallet signed tx flows
- self-custody swap flows

### 11.2 官方 release notes 有，但 `ave-cloud-skill` 自己都没跟进

- wallet trading auto-slippage query by token

---

## 12. 优先级建议

### 12.1 P0：必须先澄清的官方/skill 差异

1. `/v2/txs/{pair}-{chain}` vs `/v2/txs/swap/{pair-id}`
2. `address/tx` 的 `last_time` vs `to_time`
3. `address/tx` 中 `token_address` 到底是 required 还是 optional

### 12.2 P1：最值得尽快集成进 `ave-xiaozhi` 的能力

1. `GET /v2/address/tx`
2. `GET /v2/address/pnl`
3. `GET /v2/address/walletinfo/tokens`
4. `GET /v2/address/walletinfo`
5. `GET /v2/pairs/{pair}-{chain}`
6. `GET /v2/txs/detail`

### 12.3 P2：记录即可、暂不优先

- `GET /v2/address/smart_wallet/list`
- `GET /v2/signals/public/list`
- `GET /v2/klines/pair/ondo/...`
- `GET /v2/tokens/holders/{token}-{chain}`
- `GET /v2/txs/liq/{pair}-{chain}`
- Data WSS `tx/multi_tx/liq`
- chain-wallet 全自托管路线

---

## 13. 一句话判断

- `ave-xiaozhi` 已经不是“能力没有”，而是“产品主路径已做深，但官方能力完整性映射还没补齐”。
- 当前最真实的差距不是前端，而是：钱包分析、pair/tx detail、wallet lifecycle / approve / transfer，以及官方 live docs / repo / 本地封装三者之间的差异收敛。
- 如果要准备进入更稳定的烧录/真机阶段，除了继续人工测 UI，最关键的是把这些能力差异和接口差异先在 feature map / capability map 里固定清楚。
