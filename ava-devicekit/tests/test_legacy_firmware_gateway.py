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
