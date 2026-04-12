# AVE Screen and Feature Inventory

Date: 2026-04-12
Repo snapshot basis: local code in `ava-trading-esp32`

This document is a code-grounded inventory of the current AVE product surface: screens, navigation, trading flows, AI and voice behavior, backend tools, and live-update capabilities.

It is based on the current implementation in:

- `shared/ave_screens/`
- `server/main/xiaozhi-server/core/handle/textHandler/`
- `server/main/xiaozhi-server/plugins_func/functions/`
- `server/main/xiaozhi-server/config.yaml`

## 1. Product shape at a glance

AVE is an ESP32 handheld trading assistant with three tightly-coupled layers:

1. GUI screens rendered on the device / simulator.
2. Backend tool functions that return display payloads and execute actions.
3. Voice + LLM orchestration that can either directly route known AVE commands or fall back to normal chat with function calling.

The code currently exposes:

- 9 primary routed screens:
  - `feed`
  - `explorer`
  - `browse`
  - `disambiguation`
  - `spotlight`
  - `confirm`
  - `limit_confirm`
  - `result`
  - `portfolio`
- 1 overlay screen:
  - `notify`
- 2 important screen sub-modes that are not separate screen IDs:
  - feed `orders` mode inside `feed`
  - portfolio activity/detail mode inside `portfolio`

Important implementation notes:

- `signals` and `watchlist` are rendered by `browse`, not by separate screen files.
- `orders` are rendered by `feed`, not by a dedicated order screen.
- `notify` is an overlay and does not replace the current primary screen.

## 2. Screen routing model

The screen manager lives in `shared/ave_screens/ave_screen_manager.c` and `shared/ave_screens/ave_screen_manager.h`.

Current routed screen IDs:

- `AVE_SCREEN_FEED`
- `AVE_SCREEN_EXPLORER`
- `AVE_SCREEN_BROWSE`
- `AVE_SCREEN_SPOTLIGHT`
- `AVE_SCREEN_CONFIRM`
- `AVE_SCREEN_LIMIT_CONFIRM`
- `AVE_SCREEN_RESULT`
- `AVE_SCREEN_PORTFOLIO`
- `AVE_SCREEN_NOTIFY`
- `AVE_SCREEN_DISAMBIGUATION`

String screen payloads accepted by the screen manager:

- `feed`
- `spotlight`
- `confirm`
- `limit_confirm`
- `result`
- `portfolio`
- `explorer`
- `browse`
- `disambiguation`
- `notify`

Routing behavior:

- `feed` is the default root screen.
- `notify` is handled as an overlay only.
- The manager tracks a back fallback target with three main restore buckets:
  - `feed`
  - `browse`
  - `portfolio`
- Global shortcut:
  - `Y` opens `portfolio` from any non-portfolio screen.
- Special safety behavior:
  - if the current screen is `confirm` or `limit_confirm`, pressing `Y` first sends `cancel_trade`, then opens `portfolio`.

## 3. Full screen inventory

### 3.1 `explorer`

File:

- `shared/ave_screens/screen_explorer.c`

Purpose:

- Top-level launcher / mode picker / side navigation hub.

Visible menu groups and entries from current code:

- `Search`
- `Orders`
- `Trading Mode`
- `Sources`
- `Signals`
- `Watchlist`

What the user can do here:

- jump into orders view
- switch trading mode:
  - `real`
  - `paper`
- open signals browser
- open watchlist browser
- select feed source / platform entry points

Key-driven behavior:

- directional navigation through the menu
- confirm into selected section
- sends backend actions such as:
  - `orders`
  - `trade_mode_set`
  - signals open
  - watchlist open
  - source selection synchronization

Why it matters:

- `explorer` is the main "capability switchboard" for browsing, order review, and mode switching.

### 3.2 `feed`

File:

- `shared/ave_screens/screen_feed.c`

Purpose:

- Main token list screen for discovery and browsing.

Current feed content families supported by the backend:

- generic trending / hot feed
- platform feeds:
  - `pump_in_hot`
  - `pump_in_new`
  - `fourmeme_in_hot`
  - `fourmeme_in_new`
- topic feeds:
  - `ai`
  - `depin`
  - `gamefi`
- search-result feed mode
- orders feed mode

Current behavior patterns:

- standard discovery list browsing
- live price refresh patches
- local "explore" panel behavior for:
  - search
  - orders
  - sources

Typical controls from code:

- `UP` / `DOWN`: move list cursor
- `A` / `RIGHT`: watch selected token
- `LEFT`: refresh or restore current source context
- `X`: cycle standard source
- `B`: open local explore panel or back out of special mode

Backend state associated with `feed`:

- `feed_source`
- `feed_platform`
- `feed_mode`
- remembered search session
- current feed cursor and feed navigation state

Visual/data traits:

- chain coloring exists for supported chains
- can be updated live from websocket price pushes

Important implementation note:

- `orders` are displayed as a `feed` mode, not as a separate routed screen.

### 3.3 `browse`

File:

- `shared/ave_screens/screen_browse.c`

Purpose:

- Shared browser screen for list-style product surfaces that are not the main feed.

Current uses:

- `signals`
- `watchlist`

What the user can do:

- browse entries in the current list
- open the selected token in `spotlight`
- cycle chain filter

Controls:

- `A` / `RIGHT`: enter selected token detail
- `X`: cycle chain
  - `signals_chain_cycle`
  - `watchlist_chain_cycle`
- `B` / `LEFT`: return to `explorer`

Important implementation note:

- There is no dedicated `signals` screen or `watchlist` screen file; both are `browse` modes backed by different payloads and actions.

### 3.4 `disambiguation`

File:

- `shared/ave_screens/screen_disambiguation.c`

Purpose:

- Selection screen used when search returns multiple possible token matches.

What the user can do:

- move selection
- choose one candidate
- back out

Controls:

- `UP` / `DOWN`: move cursor
- `A` / `RIGHT`: select candidate
- `B` / `LEFT`: back

Backend state associated with this screen:

- `disambiguation_items`
- `disambiguation_cursor`
- `nav_from`

What happens after selection:

- selected token is resolved to address + chain
- backend opens `spotlight` for the chosen token

### 3.5 `spotlight`

File:

- `shared/ave_screens/screen_spotlight.c`

Purpose:

- Token detail page with chart, metadata, and trade entry actions.

Core functions:

- display selected token
- show price / market context
- show chart / kline data
- support interval switching
- support direct buy / sell actions
- support previous / next token browsing within the current list context

Bottom bar behavior in current code:

- `[B] BACK [X] SELL [A] BUY [Y] PORTFOLIO`

Controls:

- `LEFT` / `RIGHT`: previous / next token from current browsing context
- `UP` / `DOWN`: change kline interval
- `A`: open buy flow
- `X`: quick sell flow
- `B`: back
- `Y`: portfolio shortcut

Data/live traits:

- kline interval can be switched
- live spotlight price / chart patches are supported via websocket manager

Entry paths:

- from `feed`
- from `browse` (`signals` / `watchlist`)
- from `portfolio`
- from search disambiguation
- from voice tool calls

### 3.6 `confirm`

File:

- `shared/ave_screens/screen_confirm.c`

Purpose:

- Market trade confirmation page.

Current uses:

- market buy
- market sell
- cancel-like trade confirmations when applicable

Controls:

- `A`: confirm
- `B`: cancel

Backend behavior:

- confirmation emits `trade_action confirm`
- cancel emits `trade_action cancel`

Execution model:

- AI / GUI does not execute the trade immediately at intent parse time
- it stages a pending trade first
- user confirmation is the final commit step

### 3.7 `limit_confirm`

File:

- `shared/ave_screens/screen_limit_confirm.c`

Purpose:

- Limit order confirmation page.

Current use:

- limit buy order setup confirmation

Controls:

- `A`: set order
- `B`: cancel

Backend behavior:

- confirmation emits `trade_action confirm`
- cancel emits `trade_action cancel`

Execution model:

- limit orders are staged first, then committed only after explicit confirmation

### 3.8 `result`

File:

- `shared/ave_screens/screen_result.c`

Purpose:

- Terminal trade outcome page.

Typical uses:

- trade success
- trade failure
- cancellation
- timeout

Behavior:

- shows the result payload returned by the backend
- any key can be used to back out according to current result handling

Data source:

- trade manager result payloads
- deferred / reconciled websocket trade outcomes

### 3.9 `portfolio`

File:

- `shared/ave_screens/screen_portfolio.c`

Purpose:

- Holdings screen plus per-token activity detail view.

This screen currently contains two major subviews.

#### Portfolio list subview

Primary functions:

- show current holdings
- support chain switching
- open token spotlight
- open order/activity detail for one token
- quick sell a holding

Bottom bar in current code:

- `[B] BACK [X] SELL [A] DETAIL [Y] CHAIN`

Controls:

- `RIGHT`: open spotlight for selected holding
- `A`: open portfolio activity/detail subview
- `X`: sell selected holding
- `Y`: cycle portfolio chain
- `B`: back

#### Portfolio activity/detail subview

Purpose:

- show trade aggregation for one token, using fields intended to match real backend availability.

Current fields shown by code:

- `Buy Avg`
- `Buy Tot`
- `Sell Avg`
- `Sell Tot`
- `P&L`
- `Open`
- `First Buy`
- `Last Buy`
- `First Sell`
- `Last Sell`

Current controls:

- `B`: back to portfolio list
- `RIGHT` / `>` style action: jump to spotlight for the token

Important implementation note:

- This detail view is a subview inside `portfolio`, not a separately routed screen ID.

### 3.10 `notify`

File:

- `shared/ave_screens/screen_notify.c`

Purpose:

- transient overlay for info / warning / error notifications.

Behavior:

- overlays current primary screen
- does not replace the current routed screen
- used for brief alerts and trade-state related notices

## 4. Navigation and key action inventory

The backend key-action bridge is handled in:

- `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`

This is important because many device interactions bypass the LLM entirely for immediate deterministic behavior.

Observed action families in code:

- token viewing and movement
  - `watch`
  - `feed_prev`
  - `feed_next`
  - `kline_interval`
  - `back`
- trade actions
  - `buy`
  - `quick_sell`
  - `cancel_trade`
  - `portfolio_sell`
  - `trade_mode_set`
- navigation surfaces
  - `portfolio`
  - `orders`
  - `signals`
  - `watchlist`
  - `explorer_sync`
- feed/source actions
  - `feed_source`
  - `feed_platform`
- chain cycling
  - `signals_chain_cycle`
  - `watchlist_chain_cycle`
  - `portfolio_chain_cycle`
- watchlist maintenance
  - `watchlist_remove`
- portfolio detail actions
  - `portfolio_watch`
  - `portfolio_activity_detail`
- search disambiguation
  - `disambiguation_select`

Design implication:

- the handheld can remain responsive even when the voice stack is idle or the LLM is not needed.

## 5. Trading capability inventory

Primary AVE trading and product tools are registered in:

- `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`

Registered AVE tools:

- `ave_list_signals`
- `ave_open_watchlist`
- `ave_get_trending`
- `ave_search_token`
- `ave_list_orders`
- `ave_cancel_order`
- `ave_token_detail`
- `ave_risk_check`
- `ave_buy_token`
- `ave_limit_order`
- `ave_sell_token`
- `ave_portfolio`
- `ave_set_trade_mode`
- `ave_confirm_trade`
- `ave_cancel_trade`
- `ave_back_to_feed`

Trading/product behaviors currently represented by code:

- real trading mode
- paper trading mode
- market buy flow
- market sell flow
- limit buy flow
- pending order list
- cancel order flow
- trending discovery
- search and disambiguation
- watchlist open and maintenance
- portfolio and portfolio activity detail
- risk checks before trade flows

### 5.1 Trade mode

Trade mode can be switched between:

- `real`
- `paper`

Surface entry points:

- `explorer`
- backend tool `ave_set_trade_mode`

### 5.2 Confirmation-before-execution model

Trade execution is not supposed to happen directly on first user intent.

Current model:

1. user expresses an intent to buy / sell / place limit order
2. backend stages a pending trade
3. GUI opens `confirm` or `limit_confirm`
4. user explicitly confirms or cancels
5. trade manager executes or discards the pending trade
6. `result` or deferred result presentation follows

Relevant code:

- `ave_buy_token`
- `ave_limit_order`
- `ave_sell_token`
- `ave_confirm_trade`
- `ave_cancel_trade`
- `server/main/xiaozhi-server/plugins_func/functions/ave_trade_mgr.py`

### 5.3 Pending trades and timeouts

Trade manager behavior in `ave_trade_mgr.py` includes:

- creation of pending trade IDs
- staged confirmation state
- cancellation
- timeout cleanup
- result payload generation
- special handling for submit-only acknowledgements
- reconciliation with later trade events when needed

Supported trade types in the manager:

- `market_buy`
- `market_sell`
- `limit_buy`
- `cancel_order`

### 5.4 Paper trading path

Trade manager explicitly contains a paper trading path.

Behavior:

- when current mode is `paper`, the manager calls the paper trade executor instead of the real proxy trade endpoint

This makes paper trading a first-class execution mode rather than just a UI mock.

### 5.5 Orders

Order capabilities currently include:

- list open limit orders
- cancel one or more limit orders

Important UI note:

- order listing is rendered through `feed` mode, not a dedicated order screen.

## 6. Portfolio and wallet capability inventory

### 6.1 In-product portfolio

Core tool:

- `ave_portfolio`

Current portfolio product surface includes:

- current holdings list
- chain switching
- per-token detail / activity aggregation
- sell from portfolio
- jump from portfolio into spotlight

### 6.2 Wallet / skill tools

Additional wallet-oriented tools are registered in:

- `server/main/xiaozhi-server/plugins_func/functions/ave_skill_tools.py`

Registered wallet tools:

- `ave_wallet_overview`
- `ave_wallet_tokens`
- `ave_wallet_history`
- `ave_wallet_pnl`

These are more assistant-style wallet inspection capabilities than core handheld browsing flows.

Current wallet capability coverage:

- wallet overview
- wallet token holdings
- wallet transaction history
- wallet PnL on a token

## 7. AI, voice, and assistant capability inventory

Core configuration lives in:

- `server/main/xiaozhi-server/config.yaml`
- optionally overridden by `server/main/xiaozhi-server/data/.config.yaml`

### 7.1 Selected runtime modules

Current selected modules in config:

- `VAD: SileroVAD`
- `ASR: Qwen3ASRFlashRealtime`
- `LLM: AliLLM`
- `VLLM: ChatGLMVLLM`
- `TTS: EdgeTTS`
- `Memory: nomem`
- `Intent: function_call`

### 7.2 Wake word support

Configured wake words include:

- `Hey Ava`
- `Hi Ava`
- `Hello Ava`
- `Ava`
- lowercase variants
- Chinese variants such as:
  - `你好Ava`
  - `嗨Ava`
  - `嘿Ava`
  - `艾娃`

### 7.3 Voice entry behavior

The main voice entry logic is in:

- `server/main/xiaozhi-server/core/handle/textHandler/listenMessageHandler.py`

Current behavior:

1. detect whether utterance is a wake word
2. if it is a wake word:
   - optionally greet
3. if it is not only a wake word:
   - first try deterministic AVE routing via `try_route_ave_command`
   - if not matched, fall back to normal chat via `startToChat`

Product implication:

- AVE already has a hybrid control model:
  - deterministic command router for fast known product actions
  - normal LLM conversational fallback for everything else

### 7.4 Deterministic AVE voice router

Main file:

- `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py`

Current deterministic routing coverage includes:

- open feed / trending
- open portfolio
- open watchlist
- open orders
- open signals
- open token detail
- deictic commands like "watch this" / "buy this"
- confirm / cancel / back
- symbol-based watch or buy
- guided market buy parsing
- guided limit buy parsing

### 7.5 Guided voice trade drafting

The AVE voice router now contains a draft-based trade parser with follow-up prompting.

Observed helper functions include:

- `_voice_trade_missing_field`
- `_build_voice_trade_prompt`
- `_build_voice_trade_draft`
- `_continue_voice_trade_draft`
- `_try_route_voice_trade_intent`

Current behavior:

- if the user gives a full market buy or limit buy request, it can route directly into the trade flow
- if required fields are missing, the router stores a draft and asks a follow-up question
- missing-field prompts cover at least:
  - token
  - amount
  - limit price
- amount interpretation is chain-aware instead of hard-coded to SOL

This is the current closest thing to multi-turn voice trade slot filling in the product.

### 7.6 LLM prompt-level AVE behavior

The system prompt in `config.yaml` explicitly teaches the assistant to map spoken intents to AVE tools.

Prompt-level covered areas include:

- trending feed
- token detail
- buy
- sell
- confirm
- cancel
- portfolio
- wallet overview
- wallet tokens
- wallet history
- wallet PnL
- limit orders
- list orders
- cancel order
- search
- platform feed requests
- AI / DePIN / GameFi feed requests
- kline interval requests
- sell ratio requests

### 7.7 Non-AVE assistant tools

General assistant tools enabled in the current `function_call` config include:

- `change_role`
- `get_weather`
- `get_news_from_newsnow`
- `play_music`

System/default assistant functions also present in the codebase include:

- `handle_exit_intent`
- `get_lunar`

This means the same voice assistant can both operate AVE trading flows and handle general assistant tasks.

## 8. Live data and realtime update capability

Realtime support is implemented primarily in:

- `server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`
- `server/main/xiaozhi-server/plugins_func/functions/ave_trade_mgr.py`

### 8.1 Feed live updates

The websocket manager supports:

- subscription to feed token prices
- capped feed subscription sets
- throttled / batched feed display pushes

Purpose:

- keep feed rows updated without requiring full page rebuilds

### 8.2 Spotlight live updates

Spotlight realtime support includes:

- spotlight token subscription state
- live price updates
- live chart patch generation
- interval-aware spotlight refresh behavior
- transition-safe handling while fresh REST data is loading

Spotlight chart behavior includes:

- rolling normalized chart points
- min / max labels
- interval-aware live update ownership

### 8.3 Trade event reconciliation

Trade websocket support includes:

- trade event subscription
- pending-trade matching
- submitted-trade matching
- fallback matching by trade attributes
- deferred result presentation when immediate execution acknowledgement is incomplete

This is important because some real trade submissions may return a submit acknowledgement before final execution evidence is available.

### 8.4 Display push model

Both trade manager and websocket manager can push display payloads back to the device using the display channel.

This supports:

- feed refresh patches
- spotlight refresh patches
- result screens
- notifications

## 9. Search, discovery, and browsing capability inventory

### 9.1 Discovery feeds

Supported discovery families from tools and prompt mapping:

- generic trending
- platform-specific discovery:
  - Pump hot
  - Pump new
  - 4.meme hot
  - 4.meme new
- topic discovery:
  - AI
  - DePIN
  - GameFi

### 9.2 Search

Search capability includes:

- voice-triggered search requests
- backend token search
- automatic disambiguation when multiple matches exist
- follow-through into spotlight after selection

### 9.3 Signals

Signals capability includes:

- backend signal listing
- browse-mode rendering
- chain cycling
- drill-down into spotlight

### 9.4 Watchlist

Watchlist capability includes:

- open watchlist screen
- browse watchlist entries
- drill-down into spotlight
- remove items
- cycle chain filter

## 10. Current screen-to-feature map

This is the practical surface map by screen.

### `feed`

- browse discovery lists
- refresh trending/platform/topic/search/orders list
- open spotlight
- cycle source
- open local explore panel

### `explorer`

- search entry
- orders entry
- trading mode switch
- source selection
- signals entry
- watchlist entry

### `browse`

- signals browser
- watchlist browser
- chain cycle
- open spotlight

### `disambiguation`

- search result disambiguation
- token selection

### `spotlight`

- token detail
- chart / interval switching
- previous / next token
- buy
- sell
- portfolio jump

### `confirm`

- market trade confirm / cancel

### `limit_confirm`

- limit order confirm / cancel

### `result`

- trade success / failure / timeout / cancel result

### `portfolio`

- holdings list
- chain cycle
- spotlight jump
- sell from holding
- per-token aggregated activity detail

### `notify`

- transient info / warning / error overlay

## 11. Important product constraints and implementation truths

These are easy to miss if someone only looks at the UI.

1. Orders are not a separate routed screen.
   - They are a `feed` mode.

2. Signals and watchlist are not separate routed screens.
   - They are both `browse` mode.

3. Portfolio detail is not a separate routed screen.
   - It is a subview inside `portfolio`.

4. `notify` does not replace the current screen.
   - It overlays the current screen.

5. The voice system is not pure free-chat.
   - It first attempts deterministic AVE routing, then falls back to normal LLM chat.

6. Trade execution is not intended to be immediate on first voice parse.
   - The intended flow is draft -> confirm screen -> user confirm -> execution.

7. The handheld has both device-native deterministic navigation and AI-driven tool invocation.
   - This is a hybrid product, not a chat-only shell.

## 12. Source file index

Frontend / GUI:

- `shared/ave_screens/ave_screen_manager.c`
- `shared/ave_screens/ave_screen_manager.h`
- `shared/ave_screens/screen_explorer.c`
- `shared/ave_screens/screen_feed.c`
- `shared/ave_screens/screen_browse.c`
- `shared/ave_screens/screen_disambiguation.c`
- `shared/ave_screens/screen_spotlight.c`
- `shared/ave_screens/screen_confirm.c`
- `shared/ave_screens/screen_limit_confirm.c`
- `shared/ave_screens/screen_result.c`
- `shared/ave_screens/screen_portfolio.c`
- `shared/ave_screens/screen_notify.c`

Voice / routing / interaction:

- `server/main/xiaozhi-server/config.yaml`
- `server/main/xiaozhi-server/core/handle/textHandler/listenMessageHandler.py`
- `server/main/xiaozhi-server/core/handle/textHandler/aveCommandRouter.py`
- `server/main/xiaozhi-server/core/handle/textHandler/keyActionHandler.py`

Backend tools and runtime:

- `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- `server/main/xiaozhi-server/plugins_func/functions/ave_skill_tools.py`
- `server/main/xiaozhi-server/plugins_func/functions/ave_trade_mgr.py`
- `server/main/xiaozhi-server/plugins_func/functions/ave_wss.py`

## 13. Bottom line

From the current code, AVE is not just a token list UI and not just a voice bot.

It is already a multi-surface trading product with:

- a routed handheld screen system
- list browsing + detail + trade confirmation flows
- real and paper trading modes
- signals, watchlist, orders, search, and portfolio surfaces
- wallet analysis skills
- wake-word voice entry
- deterministic voice navigation and trade parsing
- LLM fallback chat + function calling
- live websocket price, chart, and trade-result updates

That is the current complete product surface visible in code as of 2026-04-12.
