# AVE API / WSS 实时探测记录（2026-04-11）

> 目标：对 2026-04-11 当前仍未接入、或值得复核的 AVE API / WSS 能力做一次真实探测，记录返回结构、字段、协议细节和容易踩坑的规范。

## 0. 执行上下文

- `ave-cloud-skill` 当前 HEAD：`5eaef99e151aeb595416f50294152f09d2201556`
- 凭据来源：
  - `ava-trading-esp32/server/.env.ave`
  - `ava-trading-esp32/server/main/xiaozhi-server/.env`
- 本轮实际环境：
  - `AVE_API_KEY` 已配置
  - `AVE_SECRET_KEY` 已配置
  - `AVE_PROXY_WALLET_ID` 已配置
  - `API_PLAN=pro`
- 原始探测结果：
  - `ava-trading-esp32/docs/ave-api-live-probe-2026-04-11.raw.json`
  - `ava-trading-esp32/docs/ave-wss-live-probe-2026-04-11.raw.json`

## 1. 安全边界

本轮只对以下两类接口做 live probe：

- 读接口
- 不会直接产生链上/钱包副作用的 non-destructive 接口

本轮刻意没有执行的 mutating 接口：

- `POST /v1/thirdParty/user/generateWallet`
- `POST /v1/thirdParty/user/deleteWallet`
- `POST /v1/thirdParty/tx/approve`
- `POST /v1/thirdParty/tx/transfer`
- `POST /v1/thirdParty/tx/cancelLimitOrder`
- `POST /v1/thirdParty/tx/sendSwapOrder`
- `POST /v1/thirdParty/tx/sendLimitOrder`
- `approve-chain` 本地签名路径
- `swap-evm` / `swap-solana` 的真正发送路径

也就是说，这份文档里的“全部测试”是指：当前缺口里所有安全可测的接口都已真实探测；带资产/钱包副作用的写接口只做了 schema 级说明，不做 live 执行。

## 2. Data REST 探测结果

## 2.1 `GET /ranks/topics`

- 结果：成功
- 响应包裹：`status`, `msg`, `data_type`, `data`
- `data[]` 字段：
  - `id`
  - `name_en`
  - `name_zh`
- 用途：给前端或设备端枚举可用 topics，比当前硬编码 topic 更稳

## 2.2 `POST /tokens/search`

- 结果：成功
- 入参：`token_ids: ["address-chain", ...]`
- 返回特点：
  - `data[]` 是 rich token detail，不只是轻量搜索结果
  - 除基础 token 字段外，还带大量短周期指标
- 典型字段：
  - `token`, `symbol`, `name`, `chain`
  - `main_pair`, `main_pair_tvl`
  - `current_price_usd`, `market_cap`, `fdv`, `holders`
  - `token_price_change_1m / 5m / 1h / 4h / 24h`
  - `token_tx_count_*`, `token_tx_volume_usd_*`
  - `token_buy_tx_*`, `token_sell_tx_*`
  - `bundle_wallet_rate`, `cluster_wallet_rate`, `insider_wallet_rate`
  - `phishing_wallet_rate`, `rag_risk_rate`, `rug_risk_rate`
- 结论：非常适合做 FEED / watchlist / result enrich 的批量补全接口

## 2.3 `GET /tokens/holders/{token}-{chain}`

- 结果：成功
- 当前实测返回条目数：10（本次 probe 使用 `limit=10`）
- `data[]` 典型字段：
  - `address`, `holder`, `addr_alias`
  - `balance_ratio`, `balance_usd`, `amount_cur`
  - `avg_purchase_price`, `avg_sale_price`
  - `buy_amount_cur`, `sell_amount_cur`
  - `buy_tx_count_cur`, `sell_tx_count_cur`
  - `realized_profit`, `realized_profit_ratio`
  - `unrealized_profit`, `unrealized_profit_ratio`
  - `total_profit`, `total_profit_ratio`
  - `trade_first_at`, `trade_last_at`, `last_txn_time`
  - `transfer_in`, `transfer_out`, `total_transfer_in_usd`
- 结论：这不是简单 top holders 排名，而是带收益/行为维度的 holder analytics

## 2.4 `GET /pairs/{pair}-{chain}`

- 结果：成功
- `data` 典型字段：
  - 基础标识：`pair`, `chain`, `amm`, `target_token`
  - 价格：`open_price`, `high_u`, `low_u`, `price_ath_u`
  - 变化：`price_change_1m / 5m / 15m / 1h / 4h / 24h`
  - TVL / liquidity：`tvl`, `reserve0`, `reserve1`, `reserve_change`
  - 交易量：`volume_u_1m / 5m / 15m / 1h / 4h / 24h`
  - 买卖量：`buy_volume_u_*`, `sell_volume_u_*`
  - 买卖笔数：`buys_tx_*_count`, `sells_tx_*_count`
  - 买卖人数：`buyers_*`, `sellers_*`, `makers_*`
  - token 元信息：`token0_address`, `token1_address`, `token0_symbol`, `token1_symbol`
- 结论：这就是当前 `SPOTLIGHT` 最缺的 pair 语义来源

## 2.5 `GET /txs/{pair}-{chain}`

- 结果：成功
- 响应结构：`data.limit`, `data.pair_id`, `data.to_time`, `data.total_count`, `data.txs[]`
- 本次 live probe 采样到的 `data.txs[]` 字段：
  - `amount_usd`
  - `pair_liquidity_usd`
  - `from_token_price_usd`, `to_token_price_usd`
  - `from_token_amount`, `to_token_amount`
  - `from_token_reserve`, `to_token_reserve`
  - `tx_time`, `block_number`
  - `amm`, `chain`
  - `sender_address`, `wallet_address`, `wallet_tag`
  - `to_address`
  - `pair_address`
  - `from_token_address`, `from_token_symbol`
  - `to_token_address`, `to_token_symbol`
  - `tx_hash`
- 结论：可以直接驱动“最近成交”“买卖流向”“结果页补充解释”

## 2.6 `GET /txs/detail`

- 结果：成功
- 说明：本次通过上一条 `txs` 的真实样本取到 `tx_hash + sender_address` 做了二次探测
- 返回形态：`data` 是 list，不是 dict
- `data[0]` 典型字段：
  - `account_address`
  - `tx_hash`
  - `block_number`, `block_time`, `date`
  - `event_type`, `flow_type`
  - `token_address`, `token_price_u`
  - `pair_address`, `amm`
  - `amount`, `volume`, `profit`
  - `balance_after`
  - `tx_seq`
  - `opponent_address`, `opponent_token_account_address`
  - `token_account_address`, `contract`
- 结论：`RESULT` / debug / operator 视角都很适合用它做单笔解释

## 2.7 `GET /txs/liq/{pair}-{chain}`

- 结果：成功
- 响应结构：与 `txs` 类似，核心是 `data.txs[]`
- 本次 live probe 采样到的 `data.txs[]` 字段：
  - `amount0`, `amount1`
  - `amount_eth`, `amount_usd`
  - `tx_time`, `block_number`
  - `amm`, `chain`, `type`
  - `sender`, `wallet_address`
  - `transaction`
  - `token0_address`, `token1_address`
  - `token0_symbol`, `token1_symbol`
  - `token0_price_usd`, `token1_price_usd`
- 结论：适合做池子流动性异常、建池/撤池解释

## 2.8 `GET /signals/public/list`

- 结果：成功
- 当前实测条目数：3（probe 使用 `pageSize=3`）
- `data[]` 典型字段：
  - `id`
  - `symbol`, `token`, `chain`
  - `signal_type`, `signal_time`, `headline`
  - `action_type`, `action_wallet_type`, `action_count`, `actions`
  - `first_signal_price`, `first_signal_mc`, `mc`, `mc_cur`
  - `max_price_change`, `price_change_24h`, `tx_volume_u_24h`
  - `holders_cur`, `top10_ratio`, `dev_ratio`, `insider_ratio`
  - `issue_platform`, `token_tag`, `tag`
  - `twitter_url`, `logo`
- 结论：`signal` 接口当前是可用的，而且字段面比“简单信号列表”丰富得多

## 2.9 `GET /supported_chains`

- 结果：成功
- 用途：当前项目如果要从硬编码链名单转向 server-side truth，这个接口可直接使用

## 2.10 `GET /tokens/main`

- 结果：成功
- 返回条目里除了基础 token 信息外，还带短周期交易强度字段：
  - `token_buy_tx_count_5m`
  - `token_sell_tx_count_5m`
  - `token_buyers_5m`
  - `token_sellers_5m`
  - `token_tx_volume_usd_5m / 1h / 4h / 24h`
- 结论：很适合做默认主币入口或链内“主资产导航”

## 2.11 `GET /address/smart_wallet/list`

- 结果：成功
- 当前实测返回条目：100
- `data[]` 典型字段：
  - `wallet_address`, `chain`
  - `total_profit`, `total_profit_rate`
  - `total_purchase`, `total_sold`, `total_volume`, `total_trades`
  - `buy_trades`, `sell_trades`
  - `token_profit_rate`
  - 多段收益分桶：
    - `profit_above_900_percent_num`
    - `profit_300_900_percent_num`
    - `profit_100_300_percent_num`
    - `profit_10_100_percent_num`
    - `profit_neg10_10_percent_num`
    - `profit_neg50_neg10_percent_num`
    - `profit_neg100_neg50_percent_num`
  - `last_trade_time`, `tag`, `tag_items`, `remark`, `extra_info`
- 结论：这是完整的 smart money / strategist 数据面，不是简单地址列表

## 2.12 `GET /klines/pair/ondo/{pair-or-ticker}`

- 结果：成功
- 本次 probe 方式：ticker 直接传 `ONDO`
- 返回：本次 `data` 为空数组，但接口本身返回成功 envelope
- 结论：接口可用；但 ticker 模式下是否有数据，取决于当前映射与时段

## 3. 钱包与代理读接口探测结果

## 3.1 `GET /v1/thirdParty/user/getUserByAssetsId`

- 结果：成功
- 响应 envelope：`status=200`
- `data[]` 字段：
  - `assetsId`
  - `assetsName`
  - `status`
  - `type`
  - `addressList`
- 说明：`addressList` 中实际返回了多链地址，包含至少 `bsc / base / eth / solana`

## 3.2 `GET /v1/thirdParty/tx/getLimitOrder`

- 结果：成功
- 本次返回：空数组
- envelope：`status=200`, `data=[]`
- 说明：接口可用；只是当前代理钱包在 probe 时没有待查询 limit order

## 3.3 `GET /v1/thirdParty/tx/getSwapOrder`

- 结果：占位只读 probe 返回业务错误
- 本次占位返回：`status=3011`, `msg="transaction not found"`
- 结论：接口可用，错误语义明确；需要真实 order id 才能继续取结构

## 3.4 `GET /v1/thirdParty/tx/getApprove`

- 结果：占位只读 probe 返回业务错误
- 本次占位返回：`status=3011`, `msg="approve not found"`

## 3.5 `GET /v1/thirdParty/tx/getTransfer`

- 结果：占位只读 probe 返回业务错误
- 本次占位返回：`status=3011`, `msg="transaction not found"`

## 4. Chain-wallet 非破坏性探测结果

## 4.1 `POST /v1/thirdParty/chainWallet/getAutoSlippage`

- 结果：成功
- 本次返回 envelope：`status=200`, `msg="Success"`
- `data` 字段：
  - `chain`
  - `tokenAddress`
  - `useMev`
  - `slippage`
- 当前 probe 实测：Solana meme token 返回 `slippage="1000"`

## 4.2 `GET /v1/thirdParty/chainWallet/getGasTip`

- 结果：成功
- `data[]` 字段：
  - `chain`
  - `low`
  - `average`
  - `high`
  - `mev`
  - `gasLimit`
- 说明：这是当前还没接、但非常容易单独复用的一条 trade 辅助能力

## 4.3 `POST /v1/thirdParty/chainWallet/getAmountOut`

- 结果：失败，但暴露了一个重要规范
- 本次返回：`status=2001`, `msg="inTokenAddress must be 'sol' or 'usdt' for Solana chain"`
- 关键结论：
  - 对 Solana 链，`getAmountOut` 不接受原生 SOL mint 地址
  - 需要传字面值 `sol` 或 `usdt`
- 这和项目当前直接使用 mint address 的习惯不一样，属于很容易踩的协议细节

## 4.4 `POST /v1/thirdParty/chainWallet/createSolanaTx`

- 结果：失败，但暴露了创建交易的参数约束
- 本次返回：`status=2001`, `msg="Invalid create transaction parameters: inTokenAddress must be 'sol' 'usdt' or 'usdc' for Solana chain"`
- 关键结论：
  - Solana create tx 路线同样要求 `inTokenAddress` 使用 `sol / usdt / usdc` 这样的符号值
  - 不能直接用原生 mint 地址代替

## 4.5 `POST /v1/thirdParty/chainWallet/createEvmTx`

- 结果：业务失败
- 本次返回：`status=3024`, `msg="Insufficient token balance"`
- 结论：
  - EVM create tx 路线在参数形态正确时会继续走余额校验
  - 说明接口不是“只做 schema 校验”，而是已经会进入真实资金上下文判断

## 4.6 `POST /v1/thirdParty/chainWallet/sendSignedEvmTx`

- 结果：占位发送 probe 返回业务错误
- 本次返回：`status=3011`, msg 语义为找不到占位 transaction / request

## 4.7 `POST /v1/thirdParty/chainWallet/sendSignedSolanaTx`

- 结果：占位发送 probe 返回业务错误
- 本次返回：`status=3011`, msg 语义为找不到占位 transaction / request

## 5. 当前已接钱包 data 接口的 live 复核

虽然它们不再是缺口，但本轮也顺手复核了 live 可用性：

### `GET /address/walletinfo`

- 成功
- `data` 字段：
  - `wallet_age`
  - `wallet_chain_info`
  - `total_balance`
  - `total_profit`
  - `total_profit_ratio`
  - `total_purchase`
  - `total_sold`
  - `total_win_ratio`
  - `main_token_symbol`
  - `main_token_price`

### `GET /address/walletinfo/tokens`

- 成功
- 本次返回空列表，但 envelope 正常

### `GET /address/tx`

- 成功
- 响应结构：`data.result[]`, `data.tx_count`
- 本次 probe 的配置钱包返回 `tx_count=0`

### `GET /address/pnl`

- 成功
- `data` 字段：
  - `account_address`
  - `token_address`
  - `average_purchase_price_usd`
  - `average_sold_price_usd`
  - `first_purchase_time`, `last_purchase_time`
  - `first_sold_time`, `last_sold_time`
  - `max_single_purchase_usd`, `max_single_sold_usd`
  - `profit_realized`
  - `total_purchase`, `total_purchase_amount`, `total_purchased_usd`
  - `total_sold`, `total_sold_amount`, `total_sold_usd`

## 6. WSS 探测结果

本轮在 `API_PLAN=pro` 下，对 `wss://wss.ave-api.xyz` 做了 live probe。

## 6.1 `price`

- 成功收到消息
- 当前观察到的 ack / result 结构包含：
  - `jsonrpc`
  - `id`
  - `sent_time`
  - `result.topic`
  - `result.prices[]`

## 6.2 `kline`

- 本次 8 秒窗口内没有收到消息
- 不能据此判定接口不可用，只能说明 sampled pair + time window 下没有事件推送

## 6.3 `tx`

- 成功收到消息
- 采样到的 `result.tx` 字段包括：
  - `amm`
  - `amount_eth`, `amount_usd`
  - `block_number`
  - `chain`
  - `direction`
  - `from_address`, `to_address`
  - `from_amount`, `to_amount`
  - `from_price_eth`, `from_price_usd`
  - `to_price_eth`, `to_price_usd`
  - `from_reserve`, `to_reserve`
  - `from_symbol`, `to_symbol`
  - `id`
  - `pair_address`, `pair_liquidity_eth`, `pair_liquidity_usd`, `pair_type`
  - `profile`
  - `sender`
  - `target_token`
  - `time`
  - `transaction`
  - `tvl`
  - `tx_seq`
  - `wallet_address`, `wallet_tag`

## 6.4 `multi_tx`

- 成功收到消息
- 当前样本字段面与 `tx` 基本同级，说明可作为“聚合交易流”直接利用

## 6.5 `liq`

- 成功收到消息
- 当前样本里也能观察到 `result.tx` 结构，表明 liquidity 事件与 tx topic 至少共享一部分字段模型

## 6.6 WSS 实测发现的一个实现注意点

在同一条 socket 上连续 probe `tx / multi_tx / liq` 时，除了目标 topic 的消息，还混入了：

- `result.kline.*`
- `result.prices[]`

这意味着消费端不能只靠“我刚刚订阅了什么”来假定消息形态，必须显式按：

- `result.topic`
- 以及 `result.tx` / `result.kline` / `result.prices`

做防御式分支。

## 7. 本轮最重要的协议结论

1. `signal` 接口已经真实可用，而且字段比预期更丰富
2. `pair / tx / tx_detail / liq` 这组接口都已真实可用，适合做下一批集成
3. `smart_wallets` 也真实可用，但属于新产品方向
4. `tx / multi_tx / liq` 三条 Data WSS topic 都能在 live 环境收到消息
5. Solana 的 chain-wallet 路线有一个很关键的协议坑：
   - `inTokenAddress` 不能直接传原生 mint
   - 必须传 `sol` / `usdt` / `usdc` 这种符号值

## 8. 建议如何使用这份文档

如果下一步是补缺口，最推荐直接拿这份 live probe 结果推进：

1. `POST /tokens/search`
2. `GET /pairs/{pair}-{chain}`
3. `GET /txs/{pair}-{chain}`
4. `GET /txs/detail`
5. `GET /txs/liq/{pair}-{chain}`
6. `GET /tokens/holders/{token}-{chain}`
7. WSS `tx / multi_tx / liq`

它们都已经过 live probe，不是纸面能力。
