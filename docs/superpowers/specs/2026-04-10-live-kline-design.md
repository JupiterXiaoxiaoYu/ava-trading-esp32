# Spotlight Live Kline Design

## Goal
为 `spotlight` 增加两个显式实时模式：`Live 1s` 和 `Live 1m`，并与现有 `5M / 1H / 4H / 1D` 共存；实时模式只在用户主动切换时启用，不再自动接管普通 timeframe。

## UX
- 上下切换序列改为：`L1S -> L1M -> 5M -> 1H -> 4H -> 1D`
- 右上角 timeframe 标签显示 `L1S` / `L1M`
- `L1S`：进入后展示秒级滚动线图；后续用实时流持续刷新
- `L1M`：进入后展示分钟级滚动线图；后续用实时流持续刷新
- 普通 `5M / 1H / 4H / 1D` 继续保持静态 REST chart + price live update，不自动切换到最近窗口

## Data Model
- UI 向服务端发送 interval：`s1`, `1`, `5`, `60`, `240`, `1440`
- `s1` 代表显式 live-second 模式
- `1` 代表显式 live-minute 模式，REST 使用 `interval=1`，WSS 使用 `k1`
- `5/60/240/1440` 保持现有模式

## Server Behavior
- `ave_token_detail(interval="s1")`
  - 不调用 token kline REST
  - 复用当前 token 基础详情 + 风险信息
  - 用 live buffer 或当前价格构造初始秒级图
  - 设置 WSS subscription interval=`s1`
- `ave_token_detail(interval="1")`
  - 调用 token kline REST `interval=1`
  - 设置 WSS subscription interval=`k1`
- live 模式下，`_on_kline_event()` 在收到匹配 interval 的数据后，重建 chart 并推送新的 `spotlight` payload
- 非 live 模式下，`_on_kline_event()` 继续只缓存，不改当前 chart

## Constraints
- 不新增按键，不改现有 BUY / SELL / BACK / PORTFOLIO 绑定
- 不让 live buffer 污染普通 timeframe 的 chart
- 不把 source / chain 再拼回 top-bar symbol

## Testing
- Python:
  - `ave_token_detail(interval="s1")` 不走 REST kline，走 live 初始化
  - `ave_token_detail(interval="1")` 使用 REST `interval=1` 且 WSS `k1`
  - `_on_kline_event()` 在 `s1/k1` 选中时会刷新 spotlight chart
  - `_on_kline_event()` 在普通 timeframe 时仍不替换 chart
- C/UI:
  - `screen_spotlight_show()` 能把 `s1` / `1` 映射为 `L1S` / `L1M`
  - `AVE_KEY_UP/DOWN` 发出的 `kline_interval` payload 带新 interval 值
- Screenshot:
  - 更新 `spotlight` baseline，确认 `L1S/L1M` 标签排版无冲突
