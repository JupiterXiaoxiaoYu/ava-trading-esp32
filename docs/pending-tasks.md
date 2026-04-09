# AVE Xiaozhi - pending tasks (reconciled)

> Last verified: 2026-04-10
>
> This file keeps only:
> - genuinely unfinished work
> - implemented work that still lacks final E2E/manual proof
>
> Decision log: the previously removed `P2-9` stays removed and must not return.

---

## Verification evidence used in this round

1) Final batch Python regression suite:

```bash
python3 -m pytest -q \
  server/main/xiaozhi-server/test_ave_router.py \
  server/main/xiaozhi-server/test_surface_input_sync.py \
  server/main/xiaozhi-server/test_p3_trade_flows.py \
  server/main/xiaozhi-server/test_p3_orders.py \
  server/main/xiaozhi-server/test_portfolio_surface.py \
  server/main/xiaozhi-server/test_p3_batch1.py \
  server/main/xiaozhi-server/test_ave_skill_tools.py
```

2) Simulator screenshot gate:

```bash
cd /home/jupiter/ave-xiaozhi/simulator
./mock/run_screenshot_test.sh
```

- This gate now includes a dedicated `disambiguation` scene/baseline in addition to the FEED/EXPLORE/ORDERS/SPOTLIGHT/CONFIRM/RESULT/PORTFOLIO captures.

3) Renderer/state-machine fallback probe (rerun because batch 1 changed screen routing):

```bash
cd /home/jupiter/ave-xiaozhi/simulator
cc -std=c99 -Wall -Wextra \
  -I/home/jupiter/ave-xiaozhi/simulator \
  -I/home/jupiter/ave-xiaozhi/shared/ave_screens \
  mock/verify_p3_5_minimal.c \
  /home/jupiter/ave-xiaozhi/shared/ave_screens/ave_screen_manager.c \
  /home/jupiter/ave-xiaozhi/shared/ave_screens/screen_disambiguation.c \
  -o /tmp/verify_p3_5_minimal && /tmp/verify_p3_5_minimal
```

4) Live/contract highlights already locked by the reconciled batch:
- Data REST works for `trending`, `platform`, `ranks`, `search`, `token detail`, `contracts`, `price`, `klines`
- Solana quote works on `POST /v1/thirdParty/chainWallet/getAmountOut`
- Solana buy quote must use `inTokenAddress="sol"`
- `/tokens/platform` uses `tag=` rather than `platform=`
- `/tokens/price` uses `{"token_ids": ["addr-chain"]}`
- Data WSS price subscribe works with JSON-RPC and `X-API-KEY` header
- Trade WSS JSON-RPC subscribe no longer errors immediately, but no real order event sample was captured in this round

---

## P0 - still open / still risky

| ID | Status | Type | Real remaining problem | Relevant code | What still needs proof |
|---|---|---|---|---|---|
| (none) | - | - | No open P0 items remain from this reconciliation pass. | - | Continue routine regression + live smoke in future rounds. |

---

## Done and verified enough to remove from pending

- FEED refresh / source switching / topic routing are implemented and regression-covered
- Platform feed requests use `tag=` and the code now keeps enough feed context for back-navigation restoration
- Buy / sell / limit payload normalization has been updated to the current live-compatible shape (`inTokenAddress` / `outTokenAddress`, string fields, Solana gas defaults)
- `P0-6` is now closed with doc + live-probe fixture coverage:
  - status hardening rejects missing/malformed status as success
  - RESULT normalization safely handles `data` as dict/list/None/malformed
  - REST submit ack without execution evidence no longer claims terminal `Bought!`/`Sold!`
  - Solana `limit_buy` no longer injects invalid `autoGas` default
  - WSS `orderType=limit` now maps to limit semantics without risky pending-state auto-clear
- Orders flow is implemented: `ave_list_orders`, `ave_cancel_order`, FEED orders mode, and related tests
- Portfolio schema handling no longer fabricates holdings when `getUserByAssetsId` only returns wallet metadata
- Data WSS and Trade WSS have been migrated to JSON-RPC subscribe frames and have regression coverage
- Kline handling now tolerates live `limit + 1` behavior by trimming client-side
- Portfolio selection / detail / sell actions preserve `addr`, `chain`, and `balance_raw`
- Server-side back-navigation state now has regression coverage for `portfolio_watch`, `portfolio_sell`, and feed/platform return context
- Batch 1 state hardening is now implemented and verified enough to remove from pending:
  - `DISAMBIGUATION` routing and trusted-selection guardrails
  - `search_session` restore for `FEED_SEARCH -> SPOTLIGHT/DISAMBIGUATION -> back`
  - confirm timeout / ack-timeout / deferred-result explanation states
  - wallet/order explanation fields (`wallet_source_label`, `pnl_reason`, order-state subtitle copy)
- Simulator visual verification now also covers `DISAMBIGUATION` with dedicated standard + overflow-hint screenshot baselines, so the last Task 6 visual-proof concern is closed
- `P3-5` is now closed by two layers of evidence:
  - real WebSocket E2E: `PORTFOLIO -> SPOTLIGHT -> back -> PORTFOLIO`, and `RESULT -> back -> PORTFOLIO`
  - simulator fallback probe: `simulator/mock/verify_p3_5_minimal.c` verifies SPOTLIGHT / RESULT fallback preference returns to `PORTFOLIO`

---

## P2 - still open / still risky

| ID | Status | Type | Real remaining problem | Relevant code | What still needs proof |
|---|---|---|---|---|---|
| (none) | - | - | No open P2 items remain from this reconciliation pass. | - | Keep running the screenshot gate when UI contracts or baselines change. |

---

## Intentionally not doing

| Item | Why it stays out of scope |
|---|---|
| FEED + A quick-buy shortcut | Too easy to mis-trigger; unsafe without SPOTLIGHT context |
| Key-based FEED mode switch into orders | Low-frequency, adds state complexity; voice entry to orders mode is enough |
| Real-time whale alerts (`tx` / `multi_tx` / `liq`) | Needs Pro plus extra filtering and UX work |
| Top holders list | Too heavy for the device UI relative to its value |
| EVM approve management | Signature / security flow is out of scope |
| Multi-wallet switching | Security-sensitive and out of scope |
| History endpoint integration | `GET /v1/thirdParty/tx/history` is not in the official docs used here |
| Pure key-driven limit-order entry from SPOTLIGHT | Requires numeric target-price input that the device keys cannot collect cleanly |
