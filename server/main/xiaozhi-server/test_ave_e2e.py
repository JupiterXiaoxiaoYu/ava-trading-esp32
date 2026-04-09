"""
AVE Xiaozhi 端对端测试脚本
用法：先在另一个终端启动服务端 python app.py，再运行此脚本

测试场景：
1. 查看热门代币 → 期望收到 display screen=feed
2. 查看持仓     → 期望收到 display screen=portfolio
"""
import asyncio
import json
import sys
import websockets

WS_URL = "ws://localhost:8000/xiaozhi/v1/?device-id=ave-xiaozhi-sim&client-id=sim-001"

HELLO_MSG = {
    "type": "hello",
    "version": 3,
    "transport": "websocket",
    "audio_params": {
        "format": "opus",
        "sample_rate": 16000,
        "channels": 1,
        "frame_duration": 60,
    },
}

async def inject_text(ws, text: str):
    """注入文字指令（绕过 ASR，直接触发 LLM）"""
    msg = {"type": "listen", "state": "detect", "text": text}
    await ws.send(json.dumps(msg))
    print(f"  → 发送: {text!r}")


async def inject_json(ws, payload: dict, label: str = "JSON"):
    """发送原始 JSON 消息（用于 key_action / trade_action）。"""
    await ws.send(json.dumps(payload))
    print(f"  → 发送{label}: {payload}")


async def wait_display(ws, timeout=30, label="", expect_screen=None):
    """等待收到 display 消息，打印结果。expect_screen 可指定只接受特定 screen。"""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
        except asyncio.TimeoutError:
            continue
        except websockets.ConnectionClosed:
            print("  连接关闭")
            return None

        # 跳过二进制音频帧
        if isinstance(raw, bytes):
            continue

        try:
            msg = json.loads(raw)
        except Exception:
            continue

        msg_type = msg.get("type", "")

        # 打印 TTS 文字（LLM 回复）
        if msg_type == "tts" and msg.get("state") == "sentence_start":
            print(f"  ← TTS: {msg.get('text', '')}")

        # 收到 display 消息
        if msg_type == "display":
            screen = msg.get("screen", "?")
            # 如果指定了期望的 screen，跳过不匹配的
            if expect_screen and screen != expect_screen:
                print(f"  (跳过 screen={screen}，等待 {expect_screen})")
                continue
            data   = msg.get("data", {})
            print(f"\n  ✅ [{label}] display screen={screen}")
            # 简要打印关键字段
            if screen == "feed":
                tokens = data.get("tokens", [])
                for t in tokens[:3]:
                    print(f"     {t.get('symbol','?')}  {t.get('price','?')}  {t.get('change_24h','?')}")
            elif screen == "spotlight":
                print(f"     symbol={data.get('symbol')}  price={data.get('price')}")
                print(f"     risk={data.get('risk_level')}  honeypot={data.get('is_honeypot')}")
            elif screen == "confirm":
                print(f"     trade_id={data.get('trade_id')}  action={data.get('action')}")
                print(f"     amount={data.get('amount_native')}  usd={data.get('amount_usd')}")
            elif screen == "portfolio":
                holdings = data.get("holdings", [])
                print(f"     total={data.get('total_usd')}  holdings={len(holdings)}")
            elif screen == "notify":
                print(f"     level={data.get('level')}  title={data.get('title')}")
                print(f"     body={data.get('body')}")
            return msg
    print(f"  ⏰ [{label}] 超时未收到 display")
    return None


def _display_has_keys(msg, screen: str, keys: list[str]) -> bool:
    if not msg or msg.get("screen") != screen:
        return False
    data = msg.get("data", {})
    missing = [key for key in keys if key not in data]
    if missing:
        print(f"  ❌ [{screen}] 缺少字段: {', '.join(missing)}")
        return False
    return True


def _display_has_nonempty(msg, screen: str, keys: list[str]) -> bool:
    if not _display_has_keys(msg, screen, keys):
        return False
    data = msg.get("data", {})
    missing = [key for key in keys if data.get(key) in (None, "", [])]
    if missing:
        print(f"  ❌ [{screen}] 字段为空: {', '.join(missing)}")
        return False
    return True


async def run_tests():
    print(f"连接 {WS_URL} ...")
    try:
        async with websockets.connect(WS_URL, ping_interval=None) as ws:
            # 握手
            await ws.send(json.dumps(HELLO_MSG))
            # 等待 welcome
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            welcome = json.loads(raw)
            print(f"握手成功: session_id={welcome.get('session_id','?')}\n")

            # ── 测试1：查看热门代币 ─────────────────────────────────
            print("=== 测试1: 查看热门代币 ===")
            await inject_text(ws, "帮我看看当前热门代币")
            msg1 = await wait_display(ws, timeout=30, label="trending", expect_screen="feed")
            if _display_has_nonempty(msg1, "feed", ["tokens"]):
                print("  → 测试1 PASS\n")
            else:
                print("  → 测试1 FAIL\n")

            await asyncio.sleep(2)

            # ── 测试2：查看持仓 ────────────────────────────────────
            print("=== 测试2: 查看我的持仓 ===")
            await inject_text(ws, "看看我的持仓")
            msg2 = await wait_display(ws, timeout=30, label="portfolio", expect_screen="portfolio")
            if _display_has_keys(msg2, "portfolio", ["holdings", "total_usd"]):
                print("  → 测试2 PASS\n")
            else:
                print("  → 测试2 FAIL\n")

            # 从 feed 中挑一个 token 作为后续导航与交易路径的测试对象
            token_addr = "So11111111111111111111111111111111111111112"
            token_chain = "solana"
            token_symbol = "SOL"
            if msg1:
                tokens = msg1.get("data", {}).get("tokens", [])
                if tokens:
                    t0 = tokens[0]
                    token_symbol = t0.get("symbol", token_symbol)
                    token_chain = t0.get("chain", token_chain)
                    token_id = t0.get("token_id", "")
                    if token_id:
                        if "-" in token_id:
                            token_addr, ch = token_id.rsplit("-", 1)
                            if ch:
                                token_chain = ch
                        else:
                            token_addr = token_id
            print(f"  → 用于后续测试 token: {token_symbol} {token_addr} {token_chain}\n")

            # ── 测试3：PORTFOLIO -> SPOTLIGHT -> back 应返回 PORTFOLIO ─────────
            print("=== 测试3: PORTFOLIO -> SPOTLIGHT -> back ===")
            await inject_json(ws, {"type": "key_action", "action": "portfolio"}, "key_action")
            msg3a = await wait_display(ws, timeout=20, label="portfolio-entry", expect_screen="portfolio")
            await inject_json(ws, {
                "type": "key_action",
                "action": "portfolio_watch",
                "token_id": token_addr,
                "chain": token_chain,
            }, "key_action")
            msg3b = await wait_display(ws, timeout=40, label="spotlight-from-portfolio", expect_screen="spotlight")
            await inject_json(ws, {"type": "key_action", "action": "back"}, "key_action")
            msg3c = await wait_display(ws, timeout=30, label="back-to-portfolio", expect_screen="portfolio")
            if (
                _display_has_keys(msg3a, "portfolio", ["holdings", "total_usd"])
                and _display_has_nonempty(msg3b, "spotlight", ["symbol", "price"])
                and _display_has_keys(msg3c, "portfolio", ["holdings", "total_usd"])
            ):
                print("  → 测试3 PASS\n")
            else:
                print("  → 测试3 FAIL\n")

            # ── 测试4：RESULT 返回（按键）应回 PORTFOLIO ───────────────────────
            print("=== 测试4: RESULT back -> PORTFOLIO ===")
            await inject_json(ws, {"type": "key_action", "action": "portfolio"}, "key_action")
            msg4a = await wait_display(ws, timeout=20, label="portfolio-before-sell", expect_screen="portfolio")
            if not msg4a:
                # 允许重试一次，避免实时推送噪声导致短暂错过 portfolio 帧
                await inject_json(ws, {"type": "key_action", "action": "portfolio"}, "key_action")
                msg4a = await wait_display(ws, timeout=20, label="portfolio-before-sell-retry", expect_screen="portfolio")
            await inject_json(ws, {
                "type": "key_action",
                "action": "portfolio_sell",
                "addr": token_addr,
                "chain": token_chain,
                "symbol": token_symbol,
                # 传 0，避免真实卖出；这里仅验证导航链路。
                "balance_raw": "0",
            }, "key_action")
            msg4b = await wait_display(ws, timeout=30, label="confirm", expect_screen="confirm")

            trade_id = ""
            if _display_has_nonempty(msg4b, "confirm", ["trade_id", "action"]):
                trade_id = msg4b.get("data", {}).get("trade_id", "")
            if not trade_id:
                print("  → 测试4 FAIL（未拿到 trade_id）\n")
            else:
                await inject_json(ws, {
                    "type": "trade_action",
                    "action": "confirm",
                    "trade_id": trade_id,
                }, "trade_action")
                msg4c = await wait_display(ws, timeout=60, label="result", expect_screen="result")
                await inject_json(ws, {"type": "key_action", "action": "back"}, "key_action")
                msg4d = await wait_display(ws, timeout=30, label="result-back-portfolio", expect_screen="portfolio")
                if (
                    _display_has_nonempty(msg4b, "confirm", ["trade_id", "action"])
                    and _display_has_keys(msg4c, "result", ["title", "action", "success"])
                    and _display_has_keys(msg4d, "portfolio", ["holdings", "total_usd"])
                ):
                    print("  → 测试4 PASS\n")
                else:
                    print("  → 测试4 FAIL\n")

            await asyncio.sleep(1)
            print("=== 所有测试完成 ===")

    except ConnectionRefusedError:
        print("连接失败 — 请先启动服务端：python app.py")
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_tests())
