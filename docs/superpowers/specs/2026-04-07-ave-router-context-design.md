# AVE Router And Context Design

## Goal

Make AVE device commands deterministic by introducing a dedicated AVE command router for high-certainty utterances, while also exposing standardized `ave_context` to the LLM for open-ended language understanding.

## Problem

The current behavior relies too heavily on prompt-following and LLM tool choice for commands that are really UI-state actions: `看这个`, `买这个`, `确认`, `取消`, `返回`, `看 <symbol>`, `买 <symbol>`. In practice, the effective runtime config also drifted from `config.yaml`, causing missing tools and mismatched prompt semantics.

## Design

### 1. Deterministic AVE command router

Add a router in the listen text path that runs before `startToChat()`.

It handles high-certainty device actions directly from `conn.ave_state`, including:
- feed entry: `看热门`, `刷新热门`, `热门代币`
- portfolio entry: `我的持仓`, `持仓`
- current-item navigation: `看这个`, `详情`, `进入`
- current-item trade: `买这个`
- pending-trade actions: `确认`, `确认购买`, `执行`, `取消`, `算了`, `不买了`
- navigation: `返回`, `回去`, `首页`, `回到热门`
- symbol-based direct intents: `看 <symbol>`, `买 <symbol>`

If the utterance matches one of these command families and required state exists, the router executes the corresponding AVE tool directly. If required state is missing, it returns a deterministic rejection response instead of letting the LLM guess.

### 2. Standardized ave_context

Create a helper that builds a normalized AVE context object from `conn.ave_state`. This includes:
- `screen`
- `nav_from`
- `current_token`
- `pending_trade`
- `feed_source`, `feed_platform`, `feed_cursor`
- `feed_visible_symbols`
- `allowed_actions`

The helper is used both by the deterministic router and by the LLM handoff path.

### 3. LLM handoff remains for open-ended language

If the router does not claim the utterance, the request continues to the normal LLM flow, but now with `ave_context` attached to the connection/session context so the model can interpret under-specified language with more UI awareness.

### 4. No heuristic fallback chains

This design explicitly avoids layering more prompt-only fallback behavior. Symbol resolution and state-sensitive commands become first-class router behavior, not repair logic.

## Testing

Add deterministic tests for:
- `screen + utterance -> tool/action`
- `spotlight + 买这个 -> buy path`
- `confirm + 确认/取消 -> confirm/cancel trade path`
- `feed + 看这个 -> token detail path`
- `看ROCKET` / `买ROCKET` -> symbol-directed route behavior
- missing-context rejections for commands that require current screen state

## Files

Likely files to modify:
- `server/main/xiaozhi-server/core/handle/textHandler/listenMessageHandler.py`
- `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py` (new)
- `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py` (context helpers if needed)
- focused tests under `server/main/xiaozhi-server/`
