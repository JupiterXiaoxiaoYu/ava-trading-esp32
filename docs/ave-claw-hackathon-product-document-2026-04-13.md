# Ava Box Product Document

## 1. Product Definition

`Ava Box` is a compact AI trading device for the on-chain ecosystem. It combines:

- a joystick-and-button hardware interface,
- a 320x240 screen-based trading UI,
- voice wake and voice command entry,
- deterministic page-aware routing,
- live token data and charts,
- paper trading and real trading,
- portfolio, watchlist, signals, and order management.

The product is designed to solve a specific problem: most crypto tools split monitoring, discovery, analysis, and execution across too many browser tabs and too much cognitive overhead. Ava Box compresses those flows into a dedicated handheld experience.

The product personality is `Ava`: a voice-first, embodied trading assistant. The platform layer behind it is `AVE Claw`, which provides the capability stack and Skills used by the box.

Because the runtime foundation is built on `ESP32`, this project is also effectively an intelligent hardware framework for `AVE Skills`. In practice, that means the AVE trading system is not limited to one handheld form factor: any ESP32-class device, including watches, robots, touch displays, and other embedded terminals, can be adapted into the same AVE-powered trading experience.

## 2. Why It Matters for This Hackathon

The hackathon describes `AVE Claw` as an AI-powered capability platform for the on-chain ecosystem, with Skill modules such as:

- asset monitoring,
- on-chain alerts,
- automated trading strategy execution.

`Ava Box` is the clearest productized expression of that platform. It already turns those capabilities into a usable end-user product:

- market discovery through multi-source token feeds,
- on-chain signal browsing,
- watchlist monitoring,
- portfolio tracking,
- AI-assisted search and trade entry,
- guarded market and limit execution,
- wallet analytics through backend Skills.

In short:

- `Ava Box` is the product,
- `AVE Claw` is the capability platform behind it,
- `AVE Skills` are the reusable abilities that power the box and can later power developer-built apps.

## 3. Hardware Profile

The current product profile used for Ava Box is:

| Item | Current profile |
|---|---|
| Chip | ESP32-S3 |
| Memory | 8MB Flash, 8MB PSRAM |
| Screen | 2.0-inch 320x240 landscape display |
| Connectivity | Wi-Fi, Bluetooth 5 |
| Battery | 800mAh |
| Left side | Joystick / D-pad navigation |
| Right side | Five programmable buttons |
| Audio | Microphone and speaker |
| IO | USB Type-C and expansion port |

What matters product-wise is not just the spec list, but the control model:

- the left hand handles continuous navigation,
- the right hand handles confirmation and action,
- voice acts as a parallel interaction channel,
- the screen remains the source of truth for high-risk actions.

This makes Ava Box feel more like a dedicated on-chain companion than a miniaturized dashboard.

## 4. Control Model

Current button mapping in `shared/ave_screens/ave_screen_manager.h`:

| Physical control | Logical key | Current meaning |
|---|---|---|
| Left on joystick | `AVE_KEY_LEFT` | Back, refresh, or previous token depending on page |
| Right on joystick | `AVE_KEY_RIGHT` | Enter, open detail, or next token depending on page |
| Up on joystick | `AVE_KEY_UP` | Move up / previous item / previous interval |
| Down on joystick | `AVE_KEY_DOWN` | Move down / next item / next interval |
| X | `AVE_KEY_X` | Quick sell or chain cycle depending on page |
| Y | `AVE_KEY_Y` | Global portfolio shortcut, except inside Portfolio where it cycles chain |
| A | `AVE_KEY_A` | Primary confirm / open / buy action |
| B | `AVE_KEY_B` | Back / cancel |
| FN | system / voice wake / PTT | Voice wake, push-to-talk, or system voice entry |

## 5. Current Product Surface

The current routed surfaces in code are:

- `feed`
- `explorer`
- `browse`
- `spotlight`
- `confirm`
- `limit_confirm`
- `result`
- `portfolio`
- `notify`
- `disambiguation`

Important implementation truths:

- `Orders` is not a separate routed screen; it is a mode inside `Feed`.
- `Signals` and `Watchlist` are not separate screen files; they are modes inside `Browse`.
- `Portfolio detail` is not a separate screen id; it is a detail subview inside `Portfolio`.
- `Notify` is an overlay, not a full-screen replacement.

## 6. Master Page / Feature / Button Table

The table below is the current code-aligned product map.

| Page / mode | What it is for | Main user-visible functions | Buttons |
|---|---|---|---|
| `Feed` - standard home | Main market discovery surface | Browse token list; open token detail; refresh current source; cycle standard sources; jump to Explorer | `UP/DOWN`: move selection<br>`RIGHT` or `A`: open `Spotlight` for selected token<br>`LEFT`: refresh current source<br>`X`: cycle source across `TRENDING / GAINER / LOSER / NEW / MEME / AI / DEPIN / GAMEFI`<br>`B`: open `Explorer`<br>`Y`: open `Portfolio` globally<br>`FN`: voice wake / PTT |
| `Feed` - search / special source | Search-result feed or non-standard source list | Browse results; open token detail; return to standard feed source | `UP/DOWN`: move selection<br>`RIGHT` or `A`: open `Spotlight`<br>`LEFT`: disabled, shows notify<br>`X`: disabled, shows notify<br>`B`: restore remembered standard feed source<br>`Y`: open `Portfolio` globally<br>`FN`: voice wake / PTT |
| `Feed` - orders mode | Open limit-order list rendered inside Feed | View pending orders only; exit back to standard feed | `UP/DOWN`: move selection<br>`RIGHT`, `A`, `LEFT`, `X`: disabled in code<br>`B`: send back and exit orders mode<br>`Y`: open `Portfolio` globally<br>`FN`: voice wake / PTT |
| `Explorer` - menu | Top-level navigation hub | Access Search guide, Orders, Trading Mode, Sources, Signals, Watchlist | `UP/DOWN`: move menu selection<br>`RIGHT` or `A`: activate selected item<br>`LEFT` or `B`: return to cached `Feed`<br>`Y`: open `Portfolio` globally<br>`FN`: voice wake / PTT |
| `Explorer` - search guide | Voice-first search helper | Shows the user to say a token name; no direct search keyboard entry on device | `LEFT` or `B`: back to Explorer menu<br>`Y`: open `Portfolio` globally<br>`FN`: voice wake / PTT for token search |
| `Explorer` - sources | Source and platform picker | Load topic feeds and platform feeds | `UP/DOWN`: move source selection<br>`RIGHT` or `A`: load source into `Feed`<br>`LEFT` or `B`: back to Explorer menu<br>`Y`: open `Portfolio` globally<br>`FN`: voice wake / PTT |
| `Explorer` - trading mode | Execution mode switcher | Switch between `real` and `paper` trading | `UP/DOWN`: choose mode<br>`RIGHT` or `A`: apply `real` or `paper`<br>`LEFT` or `B`: back to Explorer menu<br>`Y`: open `Portfolio` globally<br>`FN`: voice wake / PTT |
| `Browse` - signals | Public signal browser | Browse signal list; open token detail; cycle signal chain | `UP/DOWN`: move selection<br>`RIGHT` or `A`: open selected token in `Spotlight`<br>`X`: cycle signal chain, currently `solana <-> bsc` in server handler<br>`LEFT` or `B`: return to `Explorer`<br>`Y`: open `Portfolio` globally<br>`FN`: voice wake / PTT |
| `Browse` - watchlist | Saved-token browser | Browse watchlist; open token detail; cycle watchlist chain | `UP/DOWN`: move selection<br>`RIGHT` or `A`: open selected token in `Spotlight`<br>`X`: cycle watchlist chain through `all / solana / base / eth / bsc` in server handler<br>`LEFT` or `B`: return to `Explorer`<br>`Y`: open `Portfolio` globally<br>`FN`: voice wake / PTT |
| `Disambiguation` | Ambiguous search-result resolver | Choose the exact token when search returns multiple matches | `UP/DOWN`: move cursor<br>`RIGHT` or `A`: select current candidate and open token detail<br>`LEFT` or `B`: back<br>`X`: locked, shows notify<br>`Y`: open `Portfolio` globally<br>`FN`: voice wake / PTT |
| `Spotlight` | Token detail and action page | Show token detail, chart, price context, contract, interval switch, buy, sell, previous/next token | `LEFT`: previous token in current feed context<br>`RIGHT`: next token in current feed context<br>`UP`: next chart interval<br>`DOWN`: previous chart interval<br>`A`: stage market buy and open `Confirm`<br>`X`: stage quick sell and open `Confirm`<br>`B`: back with server-driven restore plus local fallback timer<br>`Y`: open `Portfolio` globally<br>`FN`: voice wake / PTT |
| `Confirm` | Market trade confirmation gate | Review staged market trade; explicitly confirm or cancel | `A`: confirm staged trade, then wait for server ack<br>`B`: cancel staged trade<br>`Y`: global handler cancels staged trade then opens `Portfolio` unless ack is already pending<br>`LEFT/RIGHT/UP/DOWN/X`: no page action in current code<br>`FN`: voice wake / PTT |
| `Limit Confirm` | Limit-order confirmation gate | Review staged limit order; explicitly confirm or cancel | `A`: confirm staged limit order<br>`B`: cancel staged limit order<br>`Y`: global handler cancels staged trade then opens `Portfolio` unless ack is already pending<br>`LEFT/RIGHT/UP/DOWN/X`: no page action in current code<br>`FN`: voice wake / PTT |
| `Result` | Trade outcome page | Show success, failure, timeout, cancellation, or deferred/reconciled result | `Any key`: request back immediately<br>`Y`: same global shortcut rules still apply if intercepted before page dispatch, otherwise result page exits on key<br>`FN`: voice wake / PTT |
| `Portfolio` - holdings list | Holdings overview | View positions, switch chain, open Spotlight, open token activity detail, sell holding | `UP/DOWN`: move holding selection<br>`RIGHT`: open selected token in `Spotlight`<br>`A`: open token activity detail subview<br>`X`: sell selected holding<br>`B`: back with server-driven restore plus local fallback timer<br>`Y`: cycle portfolio chain through `solana / base / eth / bsc` in server handler<br>`FN`: voice wake / PTT |
| `Portfolio` - activity detail | Per-token trade aggregation | Show Buy Avg, Buy Tot, Sell Avg, Sell Tot, P&L, Open, First Buy, Last Buy, First Sell, Last Sell | `RIGHT`: jump from detail view to `Spotlight` for this token<br>`B`: back to portfolio list via server-driven restore plus local fallback timer<br>`Y`: no local detail action; portfolio remains current screen<br>`FN`: voice wake / PTT |
| `Notify` overlay | Non-blocking message layer | Show info / warning / error / trade state notices without replacing current screen | `Any key`: dismiss overlay first; key does not continue into underlying screen on the same press |

## 7. Current User-Facing Features

From the current code, Ava Box already includes these product-level features.

### 8.1 Discovery and browsing

- trending feed
- topic feeds: `trending`, `gainer`, `loser`, `new`, `meme`, `ai`, `depin`, `gamefi`
- platform feeds: `pump_in_hot`, `pump_in_new`, `fourmeme_in_hot`, `fourmeme_in_new`
- token search
- multi-result disambiguation
- signals browsing
- watchlist browsing

### 8.2 Analysis

- token detail in `Spotlight`
- kline interval switching
- contract and token identity display
- previous / next token navigation inside the current list context
- risk-check path in backend tools

### 8.3 Trading

- paper trading mode
- real trading mode
- market buy
- market sell
- quick sell
- limit buy
- order list
- cancel order
- guarded confirm flow before execution

### 8.4 Portfolio and wallet understanding

- holdings list
- chain-specific portfolio view
- per-token trade aggregation in portfolio detail
- backend wallet overview
- backend wallet token list
- backend wallet history
- backend wallet PnL

### 8.5 Realtime behavior

- live feed price updates
- live spotlight price updates
- live kline updates
- trade-result reconciliation through websocket events

## 8. Voice and AI in Ava Box

The AI model is not the UI controller by itself. Ava Box uses a hybrid model:

1. deterministic routing for known product actions,
2. LLM fallback for open-ended conversation and tool calling.

This is important because it keeps the product fast and safe.

### 9.1 Current wake words

Configured wake words in `server/main/xiaozhi-server/config.yaml` include:

- `Hey Ava`
- `Hi Ava`
- `Hello Ava`
- `Ava`
- lowercase variants
- phonetic variants such as `Eva` and `Ai Wa`
- Chinese variants such as `你好Ava`, `嗨Ava`, `嘿Ava`, `艾娃`

### 9.2 What voice already does

From current router and config, voice already supports:

- open trending feed
- open portfolio
- open orders
- open signals
- open watchlist
- token search
- token detail
- deictic commands such as "watch this" and "buy this" when trusted selection exists
- market buy drafting
- limit buy drafting
- follow-up prompts when trade parameters are missing
- confirm / cancel / back flows

### 9.3 Why this matters

This means Ava Box is not just "voice on top of a screen." It is a screen-native device where voice is integrated into the product logic:

- voice can route into navigation,
- voice can route into trading drafts,
- but execution still stays guarded by confirm screens.

## 9. How AVE Claw and AVE Skills Are Used

For this document, `Ava Box` is the product. `AVE Claw` and `AVE Skills` are the capability backend that the product uses.

### 10.1 AVE Claw as the product backend

The box uses AVE backend capabilities for:

- token feeds,
- token detail,
- kline data,
- contract/risk data,
- live updates,
- order and trade execution,
- portfolio and wallet information.

### 10.2 AVE Skills inside the assistant layer

The server currently exposes AVE-related callable tools such as:

- `ave_get_trending`
- `ave_token_detail`
- `ave_risk_check`
- `ave_buy_token`
- `ave_limit_order`
- `ave_list_orders`
- `ave_cancel_order`
- `ave_sell_token`
- `ave_portfolio`
- `ave_confirm_trade`
- `ave_cancel_trade`
- `ave_back_to_feed`
- `ave_search_token`
- `ave_wallet_overview`
- `ave_wallet_tokens`
- `ave_wallet_history`
- `ave_wallet_pnl`

In practice, this means:

- Ava Box uses AVE Skills as its action and intelligence layer,
- the handheld UI is the product surface,
- the Skill layer can later be reused for other apps and developers.

## 10. Current Architecture in One Paragraph

The current codebase implements Ava Box as a shared screen system in `shared/ave_screens/`, a server-side routing and action layer in `server/main/xiaozhi-server/core/handle/textHandler/`, a set of AVE market/trade/wallet tools in `server/main/xiaozhi-server/plugins_func/functions/`, a desktop simulator in `simulator/`, and an ESP32 firmware target in `firmware/`.

That is why the project is stronger than a demo-only mockup:

- the UI exists,
- the routing exists,
- the trading logic exists,
- the realtime logic exists,
- the voice logic exists,
- the device runtime exists.

At a platform level, this also means Ava Box is the first product form of a broader ESP32-native AVE hardware framework. The same capability stack can be carried into different ESP32 devices, including wearable screens, robots, touch displays, and other embedded hardware surfaces, without changing the core AVE trading backend.

## 11. What Makes Ava Box Different

Three things make the product stand out.

### 12.1 Dedicated device, not browser dependency

Ava Box is built around a handheld control loop. That gives it a different interaction rhythm from web trading tools.

### 12.2 AI is embedded into product logic

The assistant is not decorative. It can search, route, ask follow-up questions, and prepare trade actions.

### 12.3 Guarded execution

The product never relies on "the model understood me, so execute immediately." It uses selection-aware routing plus explicit confirm surfaces.

That combination is especially important for DeFi and on-chain products.

## 12. Bottom Line

`Ava Box` is the product that this hackathon entry should lead with.

It is already a real, coherent on-chain handheld:

- feed,
- search,
- signals,
- watchlist,
- spotlight,
- portfolio,
- orders,
- paper mode,
- real mode,
- market buy,
- limit buy,
- voice routing,
- guarded confirmation.

`AVE Claw` and `AVE Skills` are what make that product extensible.  
But for judges, the clearest story is this:

`Ava Box` is a handheld AI trading terminal for the on-chain world, already implemented as a device-native product rather than a concept.
