"""
刷新模拟器 mock 数据 — 从真实 AVE API 拉取实时数据写入 mock_scenes/
用法：python3 refresh_mock_data.py
然后在模拟器里按 P 键查看最新数据
"""
import json, os, sys, time, urllib.request, urllib.parse, math

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "ava-devicekit", "backend"))
from ava_devicekit.formatting.numbers import format_compact_money, format_money, format_percent  # noqa: E402

API_KEY = os.environ.get("AVE_API_KEY",
    "5vHBOFMQZFnXcu3eQs5YvcQDPHAlkn1OlkhNdIhhEho3VF4bUG58jK6Sl0AGMNsP")
HEADERS = {"X-API-KEY": API_KEY}
DATA_BASE = "https://data.ave-api.xyz/v2"
SCENES_DIR = os.path.join(os.path.dirname(__file__), "mock/mock_scenes")


def get(path, params=None):
    url = DATA_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


def fmt_price(p):
    if p is None: return "$?"
    return format_money(p)


def fmt_change(c):
    if c is None: return "0.00%"
    return format_percent(c)


def fmt_vol(v):
    if v is None: return "$0"
    return format_compact_money(v)


def write(filename, data):
    path = os.path.join(SCENES_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ {filename}")


def make_display(screen, data):
    return {"type": "display", "screen": screen,
            "ts": int(time.time()), "data": data}


# ── 1. FEED: 热门代币 ───────────────────────────────────────────
print("Fetching trending...")
r = get("/tokens/trending", {"chain": "solana", "page_size": 12})
raw_tokens = r["data"]["tokens"]

tokens = []
for t in raw_tokens[:8]:
    addr = t.get("token", "")
    sym  = t.get("symbol", "?")
    price_raw = float(t.get("current_price_usd", 0) or 0)
    chg  = float(t.get("token_price_change_24h", 0) or 0)
    vol  = float(t.get("token_tx_volume_usd_24h", 0) or 0)
    mcap = float(t.get("market_cap", 0) or 0)
    chain = t.get("chain", "solana")
    tokens.append({
        "token_id": addr,
        "chain": chain,
        "symbol": sym,
        "price": fmt_price(price_raw),
        "price_raw": price_raw,
        "change_24h": fmt_change(chg),
        "change_positive": 1 if chg >= 0 else 0,
        "volume_24h": fmt_vol(vol),
        "market_cap": fmt_vol(mcap),
        "source": t.get("issue_platform", "trending"),
        "whale_count": 0,
        "risk_level": "SAFE" if not t.get("is_honeypot") else "CRITICAL",
    })

write("01_feed_bonk.json", make_display("feed", {
    "chain": "solana", "tokens": tokens
}))

# ── 2. SPOTLIGHT: 取第一个代币的详情+K线 ───────────────────────
if tokens:
    top = tokens[0]
    addr = top["token_id"]
    chain = top["chain"]
    print(f"Fetching spotlight for {top['symbol']} ({addr[:12]}...)...")

    try:
        # Token detail
        r2 = get(f"/tokens/{addr}-{chain}")
        td = r2.get("data", {})
        if isinstance(td, dict) and "token" in td:
            td = td["token"]

        # Risk
        r3 = get(f"/contracts/{addr}-{chain}")
        rd = r3.get("data", {})

        # Kline (last 24 hourly candles)
        chart_pts = []
        try:
            rk = get(f"/kline/token/{addr}-{chain}",
                     {"interval": "60", "limit": "24"})
            kdata = rk.get("data", [])
            if isinstance(kdata, list):
                closes = [float(k.get("close", k.get("c", 0)) or 0) for k in kdata]
                chart_pts = closes[-24:]
        except Exception:
            # fallback: flat line at current price
            chart_pts = [top["price_raw"]] * 24

        write("02_spotlight_bonk.json", make_display("spotlight", {
            "token_id": addr,
            "chain": chain,
            "symbol": top["symbol"],
            "pair": f"{top['symbol']}/SOL",
            "price": top["price"],
            "price_raw": top["price_raw"],
            "change_24h": top["change_24h"],
            "change_positive": top["change_positive"],
            "chart": chart_pts,
            "is_honeypot": bool(rd.get("is_honeypot")),
            "has_mint": bool(rd.get("has_mint_method")),
            "has_freeze": bool(rd.get("has_black_method")),
            "risk_level": "CRITICAL" if rd.get("is_honeypot") else
                          "HIGH" if (rd.get("ave_risk_level") or 0) >= 60 else
                          "MEDIUM" if (rd.get("ave_risk_level") or 0) >= 30 else "LOW",
            "holders": td.get("holders", 0),
            "liquidity": fmt_vol(td.get("main_pair_tvl", 0)),
        }))
    except Exception as e:
        print(f"  ⚠ spotlight failed: {e}")

# ── 3. CONFIRM: 买入确认 ───────────────────────────────────────
if tokens:
    t0 = tokens[0]
    write("03_confirm_buy.json", make_display("confirm", {
        "trade_id": "a1b2c3d4",
        "action": "BUY",
        "symbol": t0["symbol"],
        "amount_native": "0.1 SOL",
        "amount_usd": "≈ $15.00",
        "tp_pct": 25,
        "sl_pct": 15,
        "slippage_pct": 1.0,
        "timeout_sec": 10,
    }))

# ── 4. LIMIT CONFIRM ───────────────────────────────────────────
if tokens:
    t0 = tokens[0]
    pr = t0["price_raw"]
    target = pr * 0.85  # 目标价：当前价的85%
    write("04_limit_confirm.json", make_display("limit_confirm", {
        "trade_id": "e5f6g7h8",
        "symbol": t0["symbol"],
        "amount_native": "0.1 SOL",
        "limit_price": fmt_price(target),
        "limit_price_raw": target,
        "current_price": t0["price"],
        "current_price_raw": pr,
        "distance_pct": "-15.0%",
        "expire_hours": 24,
        "timeout_sec": 10,
    }))

# ── 5-6. RESULT (保持静态) ─────────────────────────────────────
sym = tokens[0]["symbol"] if tokens else "TOKEN"
write("05_result_success.json", make_display("result", {
    "success": True,
    "title": f"Bought {sym}!",
    "out_amount": "25000",
    "out_symbol": sym,
    "amount_usd": "$15.00",
    "tp_price": fmt_price(tokens[0]["price_raw"] * 1.25) if tokens else "$?",
    "sl_price": fmt_price(tokens[0]["price_raw"] * 0.85) if tokens else "$?",
    "tx_id": "3xK9mP...",
}))
write("06_result_fail.json", make_display("result", {
    "success": False,
    "title": "Failed",
    "error": "Slippage exceeded limit",
}))

# ── 7. PORTFOLIO (空) ─────────────────────────────────────────
write("07_portfolio.json", make_display("portfolio", {
    "holdings": [],
    "total_usd": "$0.00",
    "pnl": "--",
    "pnl_pct": "--",
}))

# ── 8-9. NOTIFY ───────────────────────────────────────────────
write("08_notify_tp.json", make_display("notify", {
    "level": "success",
    "title": f"Take Profit Hit!",
    "body": f"{sym} +25% TP triggered",
}))
write("09_notify_honeypot.json", make_display("notify", {
    "level": "error",
    "title": "Honeypot Blocked",
    "body": "Contract flagged as honeypot",
}))

print(f"\nDone! {len(tokens)} trending tokens loaded.")
print("Run simulator and press P to cycle through real data scenes.")
