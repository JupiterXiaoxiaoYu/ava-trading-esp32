from __future__ import annotations

import json

from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.gateway.legacy_firmware import LegacyFirmwareConnection


def test_legacy_firmware_hello_and_key_action_flow():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))
    hello = conn.handle_text(json.dumps({"type": "hello", "transport": "websocket", "audio_params": {"sample_rate": 16000}}))
    assert hello[0]["type"] == "hello"
    assert hello[0]["transport"] == "websocket"
    assert hello[1]["type"] == "display"
    assert hello[1]["screen"] == "feed"

    detail = conn.handle_text(json.dumps({"type": "key_action", "action": "watch"}))
    assert detail[0]["screen"] == "spotlight"
    assert detail[0]["data"]["chart_min_y"]
    assert detail[0]["data"]["chart_mid_y"]
    assert detail[0]["data"]["chart_max_y"]

    kline = conn.handle_text(json.dumps({"type": "key_action", "action": "kline_interval", "interval": "240"}))
    assert kline[0]["screen"] == "spotlight"
    assert kline[0]["data"]["interval"] == "240"
    assert kline[0]["data"]["chart_min_y"] != ""

    typo_compat = conn.handle_text(json.dumps({"type": "key_action", "action": "kline_internal", "interval": "1440"}))
    assert typo_compat[0]["screen"] == "spotlight"
    assert typo_compat[0]["data"]["interval"] == "1440"


def test_legacy_firmware_hello_reports_boot_config_error(monkeypatch):
    monkeypatch.delenv("AVE_API_KEY", raising=False)
    conn = LegacyFirmwareConnection(create_device_session())
    hello = conn.handle_text(json.dumps({"type": "hello", "transport": "websocket"}))
    assert hello[0]["type"] == "hello"
    assert hello[0]["devicekit"]["boot_screen"] == "notify"
    assert "AVE_API_KEY" in hello[0]["devicekit"]["boot_error"]
    assert hello[1]["type"] == "display"
    assert hello[1]["screen"] == "notify"


def test_legacy_firmware_listen_detect_preserves_selection_context():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))
    replies = conn.handle_text(
        json.dumps(
            {
                "type": "listen",
                "state": "detect",
                "text": "buy",
                "selection": {
                    "token_id": "So11111111111111111111111111111111111111112-solana",
                    "addr": "So11111111111111111111111111111111111111112",
                    "chain": "solana",
                    "symbol": "SOL",
                },
            }
        )
    )
    display = next(item for item in replies if item.get("type") == "display")
    assert display["screen"] == "confirm"
    assert display["action_draft"]["summary"]["symbol"] == "SOL"
    assert replies[-1]["type"] == "tts"
    assert replies[-1]["state"] == "stop"


def test_legacy_firmware_accepts_generic_listen_detect_frame():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))
    replies = conn.handle_text(
        json.dumps(
            {
                "type": "listen_detect",
                "text": "buy",
                "context": {
                    "screen": "spotlight",
                    "selected": {
                        "token_id": "So11111111111111111111111111111111111111112-solana",
                        "addr": "So11111111111111111111111111111111111111112",
                        "chain": "solana",
                        "symbol": "SOL",
                    },
                },
            }
        )
    )
    display = next(item for item in replies if item.get("type") == "display")
    assert display["screen"] == "confirm"
    assert display["action_draft"]["summary"]["symbol"] == "SOL"


def test_legacy_firmware_listen_detect_accepts_screen_selection_shape():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))
    replies = conn.handle_text(
        json.dumps(
            {
                "type": "listen",
                "state": "detect",
                "text": "buy",
                "selection": {
                    "screen": "feed",
                    "cursor": 2,
                    "token": {
                        "addr": "So11111111111111111111111111111111111111112",
                        "chain": "solana",
                        "symbol": "SOL",
                    },
                },
            }
        )
    )
    display = next(item for item in replies if item.get("type") == "display")
    assert display["screen"] == "confirm"
    assert display["action_draft"]["summary"]["symbol"] == "SOL"
    assert display["action_draft"]["summary"]["token_id"] == "So11111111111111111111111111111111111111112-solana"


def test_legacy_firmware_trade_action_confirm_routes_pending_draft():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))
    token = {
        "token_id": "So11111111111111111111111111111111111111112-solana",
        "addr": "So11111111111111111111111111111111111111112",
        "chain": "solana",
        "symbol": "SOL",
    }
    draft = conn.handle_text(json.dumps({"type": "key_action", "action": "buy", **token}))[0]
    request_id = draft["action_draft"]["request_id"]

    display = conn.handle_text(json.dumps({"type": "trade_action", "action": "confirm", "trade_id": request_id}))[0]
    assert display["screen"] == "result"
    assert display["data"]["title"] == "Action confirmed"
    assert display["action_result"]["ok"] is True


def test_legacy_firmware_trade_action_cancel_routes_pending_draft():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))
    draft = conn.handle_text(json.dumps({"type": "key_action", "action": "buy"}))[0]
    request_id = draft["action_draft"]["request_id"]

    display = conn.handle_text(json.dumps({"type": "trade_action", "action": "cancel", "trade_id": request_id}))[0]
    assert display["screen"] == "result"
    assert display["data"]["title"] == "Action cancelled"
    assert display["action_result"]["ok"] is True


def test_legacy_firmware_generic_confirm_and_cancel_preserve_request_id():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))
    draft = conn.handle_text(json.dumps({"type": "key_action", "action": "buy"}))[0]
    request_id = draft["action_draft"]["request_id"]

    cancelled = conn.handle_text(json.dumps({"type": "cancel", "trade_id": request_id}))[0]
    assert cancelled["screen"] == "result"
    assert cancelled["action_result"]["ok"] is True

    draft = conn.handle_text(json.dumps({"type": "key_action", "action": "buy"}))[0]
    request_id = draft["action_draft"]["request_id"]
    confirmed = conn.handle_text(json.dumps({"type": "confirm", "request_id": request_id}))[0]
    assert confirmed["screen"] == "result"
    assert confirmed["action_result"]["ok"] is True


import asyncio

from ava_devicekit.providers.asr.base import ASRResult
from ava_devicekit.providers.tts.base import TTSResult


class _FakeASR:
    name = "fake-asr"

    async def transcribe_pcm16(self, audio: bytes, *, sample_rate: int = 16000, language: str = "zh") -> ASRResult:
        assert audio == b"buy"
        assert sample_rate == 16000
        return ASRResult("buy", language=language)


class _AudioTTS:
    name = "audio-tts"

    def synthesize(self, text: str, *, voice: str = "") -> TTSResult:
        return TTSResult(text=text, audio=b"voice", content_type="audio/opus")


def test_legacy_firmware_audio_stop_transcribes_and_routes():
    conn = LegacyFirmwareConnection(create_device_session(mock=True), asr_provider=_FakeASR())
    conn.handle_text(json.dumps({"type": "hello", "audio_params": {"format": "pcm16", "sample_rate": 16000}}))
    conn.handle_text(json.dumps({"type": "listen", "state": "start"}))
    conn.handle_binary(b"buy")
    replies = asyncio.run(conn.handle_raw(json.dumps({"type": "listen", "state": "stop"})))
    display = next(item for item in replies if item.get("type") == "display")
    assert display["screen"] == "confirm"
    assert replies[0]["type"] == "stt"
    assert replies[0]["text"] == "buy"


def test_legacy_firmware_tts_audio_frame_is_sent():
    from ava_devicekit.providers.pipeline import VoicePipeline

    conn = LegacyFirmwareConnection(create_device_session(mock=True), voice_pipeline=VoicePipeline(tts=_AudioTTS()))
    replies = conn.handle_text(json.dumps({"type": "listen", "state": "detect", "text": "portfolio"}))
    audio = next(item for item in replies if item.get("state") == "audio")
    assert audio["content_type"] == "audio/opus"
    assert audio["audio"]


def test_legacy_firmware_partial_transcript_frame():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))
    replies = conn.handle_text(json.dumps({"type": "listen", "state": "partial", "text": "buy sol"}))
    assert replies == [{"type": "stt", "state": "partial", "text": "buy sol", "session_id": conn.session_id}]


def test_legacy_firmware_accepts_goodbye_frame():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))
    replies = conn.handle_text(json.dumps({"type": "goodbye"}))
    assert replies == [{"type": "goodbye", "session_id": conn.session_id}]


def test_legacy_firmware_market_subscription_syncs_feed_and_s1_spotlight():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))

    conn.market_runtime = __import__("ava_devicekit.streams.runtime", fromlist=["MarketStreamRuntime"]).MarketStreamRuntime(
        __import__("ava_devicekit.streams.mock", fromlist=["MockMarketStreamAdapter"]).MockMarketStreamAdapter()
    )
    hello = conn.handle_text(json.dumps({"type": "hello"}))
    conn._sync_market_subscriptions(hello)
    assert any(sub.channel == "price" for sub in conn.market_runtime.subscriptions)

    spotlight = conn.handle_text(json.dumps({"type": "key_action", "action": "kline_interval", "interval": "s1"}))
    spotlight[0]["data"]["main_pair_id"] = "Pair111"
    conn._sync_market_subscriptions(spotlight)
    assert any(sub.channel == "kline" and sub.token_ids == ["Pair111"] and sub.interval == "s1" for sub in conn.market_runtime.subscriptions)


def test_legacy_firmware_accepts_screen_context_and_mcp_frames():
    conn = LegacyFirmwareConnection(create_device_session(mock=True))
    context_reply = conn.handle_text(
        json.dumps(
            {
                "type": "screen_context",
                "context": {
                    "screen": "spotlight",
                    "selected": {"token_id": "So111-solana", "addr": "So111", "chain": "solana", "symbol": "SOL"},
                },
            }
        )
    )
    assert context_reply[0]["screen"] == "notify"
    assert conn.session.snapshot()["context"]["selected"]["symbol"] == "SOL"

    mcp_reply = conn.handle_text(json.dumps({"type": "mcp", "payload": {"method": "noop"}}))
    assert mcp_reply[0]["screen"] == "notify"
    assert mcp_reply[0]["data"]["title"] == "MCP"
