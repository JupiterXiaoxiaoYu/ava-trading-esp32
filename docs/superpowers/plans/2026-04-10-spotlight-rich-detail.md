# SPOTLIGHT Rich Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `SPOTLIGHT` to show richer token context on one screen, fix false honeypot labeling, and eliminate placeholder flicker during spotlight transitions.

**Architecture:** Keep the existing server-driven `spotlight` payload and LVGL `screen_spotlight.c` surface, but enrich the payload with formatted stats and normalized risk booleans before the screen renders. Preserve current key bindings and state machine; only the payload contract, spotlight layout, and regression coverage change.

**Tech Stack:** Python (`pytest`, async AVE server handlers), C/LVGL screen code, simulator mock harness, existing AVE REST helpers.

---

## File Map

- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `server/main/xiaozhi-server/test_p3_batch1.py`
- Modify: `server/main/xiaozhi-server/test_ave_api_matrix.py`
- Modify: `shared/ave_screens/screen_spotlight.c`
- Modify: `simulator/mock/verify_ave_json_payloads.c`
- Create: `simulator/mock/mock_scenes/15_spotlight_rich_detail.json`

---

### Task 1: Fix risk boolean normalization at the server boundary

**Files:**
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `server/main/xiaozhi-server/test_p3_batch1.py`
- Test: `server/main/xiaozhi-server/test_p3_batch1.py`

- [ ] **Step 1: Write the failing tests for `-1` and stringy booleans**

```python
def test_risk_flags_normalize_numeric_and_string_sentinels(self):
    flags = ave_tools._risk_flags(
        {"data": {"is_honeypot": -1, "has_mint_method": "1", "has_black_method": "false", "risk_score": 20}}
    )
    self.assertFalse(flags["is_honeypot"])
    self.assertTrue(flags["is_mintable"])
    self.assertFalse(flags["is_freezable"])
    self.assertEqual(flags["risk_level"], "MEDIUM")


def test_risk_flags_treat_missing_values_as_false(self):
    flags = ave_tools._risk_flags({"data": {"risk_score": 5}})
    self.assertFalse(flags["is_honeypot"])
    self.assertFalse(flags["is_mintable"])
    self.assertFalse(flags["is_freezable"])
    self.assertEqual(flags["risk_level"], "LOW")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_p3_batch1.py -k "risk_flags_normalize_numeric_and_string_sentinels or risk_flags_treat_missing_values_as_false" -q`
Expected: FAIL because `bool(-1)` currently evaluates to `True`.

- [ ] **Step 3: Write minimal implementation**

```python
def _ave_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value == 1
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "yes", "y"}


def _risk_level_from_response(risk_data: dict) -> str:
    data = risk_data.get("data", risk_data)
    if isinstance(data, list) and data:
        data = data[0]
    if _ave_bool(data.get("is_honeypot")):
        return "CRITICAL"
    score = data.get("risk_score", data.get("ave_risk_level"))
    if score is None:
        return "UNKNOWN"
    score = int(score)
    if score >= 80:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 20:
        return "MEDIUM"
    return "LOW"


def _risk_flags(risk_data: dict) -> dict:
    data = risk_data.get("data", risk_data)
    if isinstance(data, list) and data:
        data = data[0]
    return {
        "is_honeypot": _ave_bool(data.get("is_honeypot")),
        "is_mintable": _ave_bool(data.get("has_mint_method", data.get("is_mintable"))),
        "is_freezable": _ave_bool(data.get("has_black_method", data.get("is_freezable"))),
        "risk_level": _risk_level_from_response(risk_data),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_p3_batch1.py -k "risk_flags_normalize_numeric_and_string_sentinels or risk_flags_treat_missing_values_as_false" -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git -C /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32 add \
  server/main/xiaozhi-server/plugins_func/functions/ave_tools.py \
  server/main/xiaozhi-server/test_p3_batch1.py
git -C /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32 commit -m "fix: normalize ave risk booleans"
```

### Task 2: Enrich spotlight payload with volume, market cap, Top10, and contract short

**Files:**
- Modify: `server/main/xiaozhi-server/plugins_func/functions/ave_tools.py`
- Modify: `server/main/xiaozhi-server/test_p3_batch1.py`
- Modify: `server/main/xiaozhi-server/test_ave_api_matrix.py`
- Test: `server/main/xiaozhi-server/test_p3_batch1.py`
- Test: `server/main/xiaozhi-server/test_ave_api_matrix.py`

- [ ] **Step 1: Write the failing tests**

```python
async def test_ave_token_detail_async_includes_rich_spotlight_fields(self):
    loop = asyncio.get_running_loop()
    conn = _FakeConn(loop)
    conn.ave_state = {"spotlight_request_seq": 3}
    sent = []

    def _fake_data_get(path, params=None):
        del params
        if path.startswith("/tokens/"):
            return {"data": {"token": {
                "symbol": "BONK",
                "current_price_usd": 1.23,
                "token_price_change_24h": 4.56,
                "holders": 1234,
                "main_pair_tvl": 98765,
                "token_tx_volume_usd_24h": 7654321,
                "market_cap": 123456789,
            }}}
        if path.startswith("/klines/token/"):
            return {"data": {"points": [{"close": 1.0, "time": 1710000000}, {"close": 2.0, "time": 1710003600}]}}
        if path.startswith("/contracts/"):
            return {"data": {"risk_score": 20}}
        if path.startswith("/tokens/holders/"):
            return {"data": {"top_10_holding_rate": 27.34}}
        raise AssertionError(path)

    async def _fake_send_display(_, screen, payload):
        sent.append((screen, dict(payload)))

    with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
         patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
        await ave_tools._ave_token_detail_async(conn, addr="token-123", chain="solana", symbol="BONK", interval="60", request_seq=3)

    payload = sent[-1][1]
    self.assertEqual(payload["volume_24h"], "$7.7M")
    self.assertEqual(payload["market_cap"], "$123.5M")
    self.assertEqual(payload["top10_concentration"], "27.3%")
    self.assertEqual(payload["contract_short"], "toke...-123")


async def test_ave_token_detail_async_falls_back_to_na_for_missing_rich_fields(self):
    loop = asyncio.get_running_loop()
    conn = _FakeConn(loop)
    conn.ave_state = {"spotlight_request_seq": 4}
    sent = []

    def _fake_data_get(path, params=None):
        del params
        if path.startswith("/tokens/"):
            return {"data": {"token": {"symbol": "BONK", "current_price_usd": 1.23, "token_price_change_24h": 0, "holders": 0, "main_pair_tvl": 0}}}
        if path.startswith("/klines/token/"):
            return {"data": {"points": [{"close": 1.23, "time": 1710000000}]}}
        if path.startswith("/contracts/"):
            return {"data": {"risk_score": 5}}
        if path.startswith("/tokens/holders/"):
            return {"data": {}}
        raise AssertionError(path)

    async def _fake_send_display(_, screen, payload):
        sent.append((screen, dict(payload)))

    with patch("plugins_func.functions.ave_tools._data_get", side_effect=_fake_data_get), \
         patch("plugins_func.functions.ave_tools._send_display", side_effect=_fake_send_display):
        await ave_tools._ave_token_detail_async(conn, addr="token-123", chain="solana", symbol="BONK", interval="60", request_seq=4)

    payload = sent[-1][1]
    self.assertEqual(payload["volume_24h"], "N/A")
    self.assertEqual(payload["market_cap"], "N/A")
    self.assertEqual(payload["top10_concentration"], "N/A")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_p3_batch1.py -k "includes_rich_spotlight_fields or falls_back_to_na_for_missing_rich_fields" -q`
Expected: FAIL because the payload currently omits the new fields.

- [ ] **Step 3: Write minimal implementation**

```python
def _fmt_percent(value) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def _contract_short(addr: str) -> str:
    text = str(addr or "").strip()
    if len(text) <= 10:
        return text or "N/A"
    return f"{text[:4]}...{text[-4:]}"


def _extract_top10_concentration(resp: dict) -> str:
    data = resp.get("data", resp)
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict):
        for key in ("top_10_holding_rate", "top10_holding_rate", "top10_concentration"):
            if data.get(key) not in (None, ""):
                return _fmt_percent(data.get(key))
        holders = data.get("holders") or data.get("items") or data.get("list")
        if isinstance(holders, list) and holders:
            total = 0.0
            for item in holders[:10]:
                share = item.get("holding_rate", item.get("rate", item.get("percentage")))
                try:
                    total += float(share or 0)
                except (TypeError, ValueError):
                    continue
            if total > 0:
                return _fmt_percent(total)
    return "N/A"
```

```python
holders_task = asyncio.to_thread(_data_get, f"/tokens/holders/{addr}-{chain}")
...
if is_live_second:
    token_resp, risk_resp, holders_resp = await asyncio.gather(token_task, risk_task, holders_task)
    kline_resp = {"data": {"points": []}}
else:
    token_resp, kline_resp, risk_resp, holders_resp = await asyncio.gather(token_task, kline_task, risk_task, holders_task)
...
spotlight_data = {
    **identity,
    "addr": addr,
    "interval": str(interval or "60"),
    "pair": f"{token.get('symbol', symbol or '???')} / USDC",
    "price": _fmt_price(token.get("current_price_usd", token.get("price"))),
    "price_raw": price_now,
    "change_24h": _fmt_change(token.get("token_price_change_24h", token.get("price_change_24h"))),
    "change_positive": float(token.get("token_price_change_24h", token.get("price_change_24h", 0)) or 0) >= 0,
    "holders": f"{int(token['holders']):,}" if token.get("holders") else "N/A",
    "liquidity": _fmt_volume(token.get("main_pair_tvl", token.get("tvl"))),
    "volume_24h": _fmt_volume(token.get("token_tx_volume_usd_24h", token.get("volume_24h"))),
    "market_cap": _fmt_volume(token.get("market_cap", token.get("fdv"))),
    "top10_concentration": _extract_top10_concentration(holders_resp),
    "contract_short": _contract_short(addr),
    ...
}
```

- [ ] **Step 4: Pin the public display contract in `test_ave_api_matrix.py`**

```python
self.assertEqual(sent[0][0], "spotlight")
self.assertIn("volume_24h", sent[0][1])
self.assertIn("market_cap", sent[0][1])
self.assertIn("top10_concentration", sent[0][1])
self.assertIn("contract_short", sent[0][1])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_p3_batch1.py test_ave_api_matrix.py -k "spotlight or risk_flags" -q`
Expected: PASS with the new payload fields and no regressions in spotlight sequencing.

- [ ] **Step 6: Commit**

```bash
git -C /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32 add \
  server/main/xiaozhi-server/plugins_func/functions/ave_tools.py \
  server/main/xiaozhi-server/test_p3_batch1.py \
  server/main/xiaozhi-server/test_ave_api_matrix.py
git -C /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32 commit -m "feat: enrich spotlight payload"
```

### Task 3: Re-layout `screen_spotlight.c` to the approved four-line footer

**Files:**
- Modify: `shared/ave_screens/screen_spotlight.c`
- Modify: `simulator/mock/verify_ave_json_payloads.c`
- Create: `simulator/mock/mock_scenes/15_spotlight_rich_detail.json`
- Test: `simulator/mock/verify_ave_json_payloads.c`

- [ ] **Step 1: Add the mock scene**

```json
{
  "screen": "spotlight",
  "symbol": "BONK",
  "price": "$1.2300",
  "change_24h": "+4.56%",
  "change_positive": true,
  "risk_level": "LOW",
  "is_honeypot": false,
  "is_mintable": false,
  "is_freezable": false,
  "holders": "1,234",
  "liquidity": "$98.8K",
  "volume_24h": "$7.7M",
  "market_cap": "$123.5M",
  "top10_concentration": "27.3%",
  "contract_short": "0x22...C599",
  "chart": [120, 240, 360, 520, 680, 740, 810, 900],
  "chart_min_y": "$1.00",
  "chart_max_y": "$2.00",
  "chart_t_start": "09:00",
  "chart_t_mid": "12:00",
  "chart_t_end": "now"
}
```

- [ ] **Step 2: Add the failing C harness assertion**

```c
screen_spotlight_show(json);
assert(strstr(s_lbl_stats_row2->text, "Vol24h:") != NULL);
assert(strstr(s_lbl_stats_row2->text, "Mcap:") != NULL);
assert(strstr(s_lbl_stats_row3->text, "Top10:") != NULL);
assert(strstr(s_lbl_stats_row4->text, "CA:") != NULL);
```

- [ ] **Step 3: Write minimal layout implementation**

```c
static lv_obj_t *s_lbl_stats_row1 = NULL;
static lv_obj_t *s_lbl_stats_row2 = NULL;
static lv_obj_t *s_lbl_stats_row3 = NULL;
static lv_obj_t *s_lbl_stats_row4 = NULL;
```

```c
s_lbl_stats_row1 = lv_label_create(s_screen);
lv_obj_set_pos(s_lbl_stats_row1, 4, 150);
lv_obj_set_style_text_color(s_lbl_stats_row1, COLOR_GRAY, 0);
lv_obj_set_style_text_font(s_lbl_stats_row1, &lv_font_montserrat_12, 0);

s_lbl_stats_row2 = lv_label_create(s_screen);
lv_obj_set_pos(s_lbl_stats_row2, 4, 166);
lv_obj_set_style_text_color(s_lbl_stats_row2, COLOR_GRAY, 0);
lv_obj_set_style_text_font(s_lbl_stats_row2, &lv_font_montserrat_12, 0);

s_lbl_stats_row3 = lv_label_create(s_screen);
lv_obj_set_pos(s_lbl_stats_row3, 4, 182);
lv_obj_set_style_text_color(s_lbl_stats_row3, COLOR_GRAY, 0);
lv_obj_set_style_text_font(s_lbl_stats_row3, &lv_font_montserrat_12, 0);

s_lbl_stats_row4 = lv_label_create(s_screen);
lv_obj_set_pos(s_lbl_stats_row4, 4, 198);
lv_obj_set_style_text_color(s_lbl_stats_row4, COLOR_GRAY, 0);
lv_obj_set_style_text_font(s_lbl_stats_row4, &lv_font_montserrat_12, 0);
```

```c
char volume_24h[20] = {0}, market_cap[20] = {0}, top10[20] = {0}, contract_short[32] = {0};
_str(json_data, "volume_24h", volume_24h, sizeof(volume_24h));
_str(json_data, "market_cap", market_cap, sizeof(market_cap));
_str(json_data, "top10_concentration", top10, sizeof(top10));
_str(json_data, "contract_short", contract_short, sizeof(contract_short));

lv_label_set_text_fmt(s_lbl_stats_row1, "Risk:%s | Mint:%s | Freeze:%s", ...);
lv_label_set_text_fmt(s_lbl_stats_row2, "Vol24h:%s | Liq:%s | Mcap:%s", volume_24h[0] ? volume_24h : "N/A", liq[0] ? liq : "N/A", market_cap[0] ? market_cap : "N/A");
lv_label_set_text_fmt(s_lbl_stats_row3, "Holders:%s | Top10:%s", holders[0] ? holders : "N/A", top10[0] ? top10 : "N/A");
lv_label_set_text_fmt(s_lbl_stats_row4, "CA:%s", contract_short[0] ? contract_short : "N/A");
```

- [ ] **Step 4: Run the C harness and verify it passes**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/simulator/mock && cc -std=c99 -Ijson_verify_include -I../../shared/ave_screens verify_ave_json_payloads.c ../../shared/ave_screens/ave_json_utils.c -o /tmp/verify_ave_json_payloads && /tmp/verify_ave_json_payloads`
Expected: exit code `0` with spotlight rich-detail assertions passing.

- [ ] **Step 5: Build the simulator target**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/simulator && cmake --build build --target simulator`
Expected: build succeeds without introducing new font or link errors.

- [ ] **Step 6: Commit**

```bash
git -C /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32 add \
  shared/ave_screens/screen_spotlight.c \
  simulator/mock/verify_ave_json_payloads.c \
  simulator/mock/mock_scenes/15_spotlight_rich_detail.json
git -C /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32 commit -m "feat: redesign spotlight footer layout"
```

### Task 4: Verify end-to-end spotlight behavior against the running stack

**Files:**
- Modify: none required unless regressions are found
- Test: existing server and simulator commands

- [ ] **Step 1: Run the complete spotlight-focused Python regression slice**

Run: `cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server && python3 -m pytest test_p3_batch1.py test_ave_api_matrix.py test_trade_contract_fixes.py -k "spotlight or honeypot or risk_flags" -q`
Expected: PASS.

- [ ] **Step 2: Restart the server with the project env and keep one live process**

```bash
cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/server/main/xiaozhi-server
pkill -f "python3 app.py" || true
set -a && [ -f .env ] && . ./.env >/dev/null 2>&1 || true && set +a
python3 app.py
```

- [ ] **Step 3: Restart the simulator for manual validation**

```bash
cd /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32/simulator
pkill -f "/simulator/build/.*/simulator" || true
./build/simulator
```

- [ ] **Step 4: Manual QA checklist**

```text
1. Open a token from FEED and confirm footer shows Risk/Mint/Freeze + Vol24h/Liq/Mcap + Holders/Top10 + CA.
2. Switch UP/DOWN intervals and confirm the old payload stays stable until the new one lands.
3. Use LEFT/RIGHT watch-next and confirm there is no blank/rollback flicker.
4. Open a token whose contract API returns is_honeypot = -1 and confirm it is not labeled HONEYPOT.
```

- [ ] **Step 5: Commit only if verification required follow-up fixes**

```bash
git -C /mnt/c/Users/72988/Desktop/AVE/ava-trading-esp32 status --short
```

---

## Self-Review

- Spec coverage: includes the approved one-screen layout, risk normalization, richer fields, no new buttons, and anti-flicker verification.
- Placeholder scan: no unresolved markers remain in the plan.
- Type consistency: new server payload fields are consistently named `volume_24h`, `market_cap`, `top10_concentration`, and `contract_short` across all tasks.
