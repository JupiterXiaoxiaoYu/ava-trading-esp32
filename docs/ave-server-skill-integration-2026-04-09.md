# AVE 服务端 Skill 集成（2026-04-09）

## 目标

把 `ave-cloud-skill` 里最值得复用、且适合当前 server agent/tool 模式的能力直接接进 `xiaozhi-server`，但不引入新的 skill registry，也不新增设备页面。

本轮选择 **text-first** 路线：

- 钱包/地址分析能力先作为服务端 tool-call 文本能力接入
- 只复用已有 `FEED / SPOTLIGHT / PORTFOLIO / ORDERS` 表面，不为钱包分析新造 screen
- 保持现有扩展路径：`plugins_func/register.py` → `server_plugins/plugin_executor.py` → `config.yaml` function list / prompt

## 本轮接入能力

| Tool | 来源能力 | 后端接口 | 备注 |
|---|---|---|---|
| `ave_wallet_overview` | `ave-data-rest` wallet overview | `GET /v2/address/walletinfo` | 文本摘要 |
| `ave_wallet_tokens` | `ave-data-rest` wallet holdings | `GET /v2/address/walletinfo/tokens` | 文本摘要 |
| `ave_wallet_history` | `ave-data-rest` wallet txs | `GET /v2/address/tx` | 文本摘要 |
| `ave_wallet_pnl` | `ave-data-rest` wallet pnl | `GET /v2/address/pnl` | 文本摘要 |

## 接入模式

1. 新增 `plugins_func/functions/ave_skill_tools.py`
2. 用现有 `@register_function(...)` 注册为 server plugin tools
3. 通过 `config.yaml -> Intent.function_call.functions` 暴露给 function-calling LLM
4. 在系统 prompt 中追加自然语言路由提示
5. 不改 `aveCommandRouter.py`，因为这些能力不是高确定性的设备按键口令

## 本轮明确不接

- 新 skill registry
- 新 display screen / 新状态机
- `signals` / `smart_wallets`
- `approve` / `transfer`
- chain-wallet self-custody
- 不稳定的 proxy `tx/history` 接口封装

## 设计约束

- 若 `wallet_address` 省略，优先解析 `AVE_PROXY_WALLET_ID` 对应代理钱包地址
- 若 `ave_wallet_pnl` 的 `token_address` 省略，优先复用当前 `AVE` token context
- 若显式地址缺链信息且无法从当前上下文推断，不做危险默认值猜测

## 测试覆盖

- 新工具已被 `ServerPluginExecutor` 暴露
- 钱包概览、持仓、历史、PnL 的核心参数拼装与文本摘要均有回归测试
