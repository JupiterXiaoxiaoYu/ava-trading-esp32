from __future__ import annotations

import base64

from ava_devicekit.core.types import AppContext, Selection
from ava_devicekit.providers.asr import QwenRealtimeASRProvider
from ava_devicekit.providers.pipeline import VoicePipeline
from ava_devicekit.streams import MockMarketStreamAdapter, StreamSubscription


def test_qwen_asr_realtime_builds_events_and_parses_transcript():
    provider = QwenRealtimeASRProvider()
    session = provider.session_update_event()
    assert session["session"]["input_audio_transcription"]["language"] == "zh"
    event = provider.audio_append_event(b"abc", event_id="e1")
    assert event["audio"] == base64.b64encode(b"abc").decode("ascii")
    parsed = provider.parse_transcript_event({"response": {"text": "你好 Ava"}})
    assert parsed and parsed.text == "你好 Ava"


def test_voice_pipeline_fallback_uses_selection_context():
    context = AppContext(
        app_id="ava_box",
        screen="spotlight",
        selected=Selection(symbol="SOL", token_id="So111-solana"),
    )
    result = VoicePipeline().reply("what is selected", context=context)
    assert "SOL" in result.text
    assert result.tts and result.tts.text == result.text


def test_mock_market_stream_snapshots_prices():
    stream = MockMarketStreamAdapter()
    stream.subscribe(StreamSubscription("price", ["So111-solana"]))
    stream.set_price("So111-solana", 123.456)
    events = stream.snapshot()
    assert events[0].token_id == "So111-solana"
    assert events[0].data["price_raw"] == 123.456
