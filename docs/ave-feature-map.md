# AVE Xiaozhi - feature map (implementation-aligned)

> Last reconciled: 2026-04-10
> 
> Evidence baseline:
> - Python regression/integration: `python3 -m pytest -q server/main/xiaozhi-server/test_ave_router.py server/main/xiaozhi-server/test_surface_input_sync.py server/main/xiaozhi-server/test_p3_trade_flows.py server/main/xiaozhi-server/test_p3_orders.py server/main/xiaozhi-server/test_portfolio_surface.py server/main/xiaozhi-server/test_p3_batch1.py server/main/xiaozhi-server/test_ave_skill_tools.py`
> - Simulator screenshot gate: `cd /home/jupiter/ave-xiaozhi/simulator && ./mock/run_screenshot_test.sh`
> - Simulator fallback probe: `cc -std=c99 -Wall -Wextra -I/home/jupiter/ave-xiaozhi/simulator -I/home/jupiter/ave-xiaozhi/shared/ave_screens mock/verify_p3_5_minimal.c /home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.c /home/jupiter/ave-xiaozhi/shared/ave_screens/screen_disambiguation.c -o /tmp/verify_p3_5_minimal && /tmp/verify_p3_5_minimal`
> - Code paths under `shared/ave_screens/` and `server/main/xiaozhi-server/plugins_func/functions/`
>
> This file tracks the **current implemented state**. Historical planning drafts and outdated protocol notes were removed.

---

## 1) Current keymap behavior

| Screen | UP | DOWN | LEFT | RIGHT | A | B | X | Y |
|---|---|---|---|---|---|---|---|---|
| FEED | select up | select down | standard: refresh current source; SEARCH/SPECIAL/ORDERS: disabled | standard/SEARCH/SPECIAL: open SPOTLIGHT; ORDERS: disabled | standard/SEARCH/SPECIAL: open SPOTLIGHT; ORDERS: disabled | standard: open Explore panel; SEARCH/SPECIAL: restore standard source; ORDERS: exit orders | standard: cycle source; SEARCH/SPECIAL/ORDERS: disabled | global -> PORTFOLIO |
| DISAMBIGUATION | select up | select down | `key_action back` | `disambiguation_select` | `disambiguation_select` | `key_action back` | locked: info NOTIFY only; no action | global -> PORTFOLIO |
| SPOTLIGHT | timeframe + | timeframe - | previous token in feed list | next token in feed list | buy -> CONFIRM | `key_action back` | quick sell -> CONFIRM | global -> PORTFOLIO |
| CONFIRM | - | - | - | - | confirm (`trade_action confirm`) | cancel (`trade_action cancel`) | - | cancel trade then -> PORTFOLIO |
| LIMIT_CONFIRM | - | - | - | - | confirm (`trade_action confirm`) | cancel (`trade_action cancel`) | - | cancel trade then -> PORTFOLIO |
| RESULT | any key -> `key_action back` | - | - | - | same as any key | same as any key | - | global -> PORTFOLIO |
| PORTFOLIO | select up | select down | - | - | watch selected holding | `key_action back` | sell selected holding | (already here) |
| NOTIFY | overlay dismiss on key | - | - | - | - | - | - | - |

Notes:
- FEED mode labels in the row map to `FEED` (standard), `FEED_SEARCH` (SEARCH), `FEED_SPECIAL_SOURCE` (SPECIAL), and `FEED_ORDERS` (ORDERS).
- Standard FEED `B` now opens a local Explore overlay with `Search`, `Orders`, and `Sources`; `Search` stays guidance-only (`FN 说币名`) and does not rebind `F1/FN`.
- Explore keeps existing semantics outside standard FEED: SEARCH/SPECIAL still use `B` to restore the remembered source, and ORDERS remains browse-only with `B` as exit.
- `X` is frozen to two meanings only: standard FEED source-cycle, or sell on token-focused pages (`SPOTLIGHT` / `PORTFOLIO`). Explore, DISAMBIGUATION, SEARCH/SPECIAL/ORDERS FEED, and confirm/result flows do not introduce a third `X` meaning.
- RESULT is manual-only: any non-`Y` key sends `key_action back`, while `Y` goes to PORTFOLIO.

---

## 2) AVE Data REST coverage (`https://data.ave-api.xyz/v2`)

| Endpoint | Status | Current use |
|---|---|---|
| `GET /tokens/trending` | implemented | FEED default trending source |
| `GET /tokens/platform?tag=` | implemented | voice/platform feeds (`pump_in_hot`, `pump_in_new`, `fourmeme_in_hot`, `fourmeme_in_new`) |
| `GET /ranks?topic=` | implemented | FEED/voice topics |
| `GET /tokens?keyword=` | implemented | token search |
| `GET /tokens/{addr}-{chain}` | implemented | SPOTLIGHT token detail |
| `GET /klines/token/{addr}-{chain}` | implemented | SPOTLIGHT chart (`interval=5/60/240/1440`) |
| `GET /contracts/{addr}-{chain}` | implemented | risk checks |
| `POST /tokens/price` | implemented | buy USD estimate, portfolio valuation |

Topic status:
- Currently wired topics: `trending`, `gainer`, `loser`, `new`, `meme`, `ai`, `depin`, `gamefi`.
- `rwa`/`l2` are not currently wired in key-action source cycling.

### 2.1 Text-first AVE server skill tools

These are server-side tool-call abilities for the agent path. They do **not** introduce new device screens; responses are text-first unless an existing AVE screen already covers the task better.

| Tool | Backing endpoint(s) | Current use |
|---|---|---|
| `ave_wallet_overview` | `GET /address/walletinfo` | wallet/address overview via agent tool call |
| `ave_wallet_tokens` | `GET /address/walletinfo/tokens` | wallet holdings summary via agent tool call |
| `ave_wallet_history` | `GET /address/tx` | wallet recent trade history via agent tool call |
| `ave_wallet_pnl` | `GET /address/pnl` | wallet-token PnL via agent tool call |

Notes:
- These tools can resolve the configured proxy wallet address when `wallet_address` is omitted.
- `ave_wallet_pnl` can reuse the current AVE token context when `token_address` is omitted.
- This integration intentionally stays text-first; it does not add new top-level display surfaces for wallet analytics.

---

## 3) AVE Trade REST coverage (`https://bot-api.ave.ai`)

| Endpoint | Status | Current use |
|---|---|---|
| `POST /v1/thirdParty/chainWallet/getAmountOut` | implemented | buy quote before CONFIRM (current quote contract) |
| `POST /v1/thirdParty/tx/sendSwapOrder` | implemented | market buy/sell execution |
| `POST /v1/thirdParty/tx/sendLimitOrder` | implemented | limit buy execution |
| `GET /v1/thirdParty/tx/getSwapOrder` | implemented | submit-only swap ACK reconciliation (`reconcile_swap_order`) |
| `GET /v1/thirdParty/user/getUserByAssetsId` | implemented | portfolio holdings/wallet lookup |
| `GET /v1/thirdParty/tx/getLimitOrder` | implemented | list pending limit orders (`ave_list_orders`) |
| `POST /v1/thirdParty/tx/cancelLimitOrder` | implemented | cancel pending limit orders (`ave_cancel_order`) |

Not currently integrated:
- `GET /v1/thirdParty/tx/history` (kept out of scope in pending decisions)

---

## 4) WSS protocol and endpoint state

### 4.1 Data WSS

- URL: `wss://wss.ave-api.xyz`
- Auth: `X-API-KEY` header
- Protocol: JSON-RPC 2.0 frames
  - unsubscribe all: `{"jsonrpc":"2.0","method":"unsubscribe","params":[],"id":N}`
  - subscribe prices: `{"jsonrpc":"2.0","method":"subscribe","params":["price",["addr-chain", ...]],"id":N}`
  - subscribe kline: `{"jsonrpc":"2.0","method":"subscribe","params":["kline","pair","k60","solana"],"id":N}`
- Implemented streams: `price`, `kline`
- Not integrated: `tx`, `multi_tx`, `liq`

### 4.2 Trade WSS

- URL template: `wss://bot-api.ave.ai/thirdws?ave_access_key={AVE_API_KEY}`
- Protocol: JSON-RPC 2.0
  - subscribe: `{"jsonrpc":"2.0","method":"subscribe","params":["botswap"],"id":0}`
- Implemented handling:
  - ack/error control frames
  - `botswap` confirmed/error events -> RESULT
  - TP/SL/trailing/auto-cancelled notifications -> NOTIFY

---

## 5) Navigation/state contracts in use

- `feed_token_list` + `feed_cursor`: server and client cooperate for SPOTLIGHT LEFT/RIGHT navigation.
- `search_session` + `search_cursor`: search-origin detail flows restore the exact `FEED_SEARCH` query/result list/cursor when `back` exits SPOTLIGHT or DISAMBIGUATION.
- `disambiguation_items` + `disambiguation_cursor`: ambiguous symbol matches stay inert until explicit `disambiguation_select`; listen/context payloads expose only screen/cursor while the user is choosing.
- `nav_from`: server-side return origin (`feed` default, `portfolio` when entering from portfolio actions).
- `feed_source` + `feed_platform`: back handler restores feed context correctly after RESULT/SPOTLIGHT exits.
- `reason` / `subtitle` / `explain_state`: user-facing trade explanations use normalized keys `trade_submitted`, `ack_timeout`, `confirm_timeout`, and `deferred_result` across FEED/NOTIFY/RESULT transitions.
- `wallet_source_label` + `pnl_reason`: PORTFOLIO explains where holdings come from and why P&L is `N/A`; order-state results reuse `subtitle` to clarify that cancel-order success changed an order, not wallet balance.
- RESULT screen is manual-only: non-`Y` keys request server `back`, and `Y` uses the global PORTFOLIO path.

---

## 6) Navigation verification status

Portfolio-origin navigation is now covered by three evidence layers:
- server/unit regression for `nav_from` and `back` routing
- WebSocket E2E for:
  - `PORTFOLIO -> SPOTLIGHT -> back -> PORTFOLIO`
  - `PORTFOLIO -> SELL -> RESULT -> back -> PORTFOLIO`
- simulator fallback probe `simulator/mock/verify_p3_5_minimal.c` for:
  - `SPOTLIGHT -> back timeout fallback -> PORTFOLIO`

This is sufficient to close `P3-5` on the current branch.

## 7) Visual verification status

- Simulator screenshot regression now covers:
  - `FEED`
  - `FEED_SEARCH`
  - `FEED_SPECIAL_SOURCE`
  - `FEED_ORDERS`
  - `DISAMBIGUATION`
  - `DISAMBIGUATION_OVERFLOW`
  - `FEED_EXPLORE_PANEL`
  - `FEED_EXPLORE_SEARCH_GUIDE`
  - `FEED_EXPLORE_SOURCES`
  - `SPOTLIGHT`
  - `CONFIRM`
  - `FEED_ORDERS_PRESS_A`
  - `FEED_ORDERS_PRESS_B`
  - `LIMIT_CONFIRM`
  - `RESULT` (success)
  - `RESULT_FAIL` (failure)
  - `PORTFOLIO`
- Gate command:
  - `cd /home/jupiter/ave-xiaozhi/simulator && ./mock/run_screenshot_test.sh`
- Baselines live under:
  - `simulator/mock/screenshot/baselines/`
- Current limitation:
  - the gate runs each screen in a fresh process for determinism; transition/animation continuity is intentionally out of scope for this gate.
  - `DISAMBIGUATION` now has deterministic baselines for both the standard chooser and the overflow-refine hint; router/surface/state-machine tests still provide the deeper behavior coverage.

## 8) Remaining open item

No endpoint/protocol mismatch is currently tracked as open in this file.

Release-readiness risks that are not pure endpoint/protocol mismatches remain tracked in `docs/pending-tasks.md` and `docs/product-review-2026-04-07.md`.

---

## 9) Intentionally out of scope

- FEED A-key quick buy shortcut (safety/mis-trigger risk)
- key-only mode switching into orders list
- whale alerts via `tx`/`multi_tx`/`liq`
- top holders list
- approve management and multi-wallet switching
- pure key-driven limit order entry without numeric input path
