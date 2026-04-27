from __future__ import annotations

import base64

from ava_devicekit.core.types import AppContext, Selection
from ava_devicekit.providers.asr import AudioFrame, Pcm16PassthroughDecoder, QwenRealtimeASRProvider
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

from ava_devicekit.providers.registry import create_provider_bundle
from ava_devicekit.providers.tts.openai_compatible import OpenAICompatibleTTSConfig, OpenAICompatibleTTSProvider
from ava_devicekit.runtime.settings import RuntimeSettings
from ava_devicekit.streams.ave_data_wss import AveDataWSSAdapter


class _FakeASRTransport:
    def __init__(self):
        self.sent = []
        self.closed = False

    def send(self, payload: str) -> None:
        self.sent.append(payload)

    def recv(self, timeout=None):
        return '{"response":{"text":"hello ava"}}'

    def close(self) -> None:
        self.closed = True


def test_qwen_asr_session_streams_pcm_and_reads_transcript():
    provider = QwenRealtimeASRProvider()
    transport = _FakeASRTransport()
    session = provider.create_session(transport)
    session.start()
    session.append(b"abc")
    session.commit()
    result = session.receive_transcript(timeout=0.1)
    session.close()
    assert result and result.text == "hello ava"
    assert any('"type":"session.update"' in item for item in transport.sent)
    assert any('"type":"input_audio_buffer.append"' in item for item in transport.sent)
    assert transport.closed is True


def test_provider_registry_builds_configured_mock_pipeline():
    settings = RuntimeSettings.from_dict({"providers": {"llm": {"provider": "disabled"}, "tts": {"provider": "mock"}}})
    bundle = create_provider_bundle(settings)
    assert bundle.llm is None
    assert bundle.pipeline.reply("hello").tts is not None


def test_openai_compatible_tts_posts_audio(monkeypatch):
    monkeypatch.setenv("TEST_TTS_KEY", "secret")
    captured = {}

    class _Resp:
        headers = {"Content-Type": "audio/opus"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"audio"

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = req.data.decode()
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OpenAICompatibleTTSProvider(OpenAICompatibleTTSConfig(base_url="https://tts.example/v1", api_key_env="TEST_TTS_KEY", model="m", voice="v"))
    result = provider.synthesize("Ava")
    assert captured["url"] == "https://tts.example/v1/audio/speech"
    assert '"input": "Ava"' in captured["body"]
    assert result.audio == b"audio"


def test_ave_data_wss_builds_frames_and_parses_price_events():
    adapter = AveDataWSSAdapter()
    frame = adapter.subscribe_frame(StreamSubscription("price", ["So111-solana"]), request_id=7)
    assert '"method":"subscribe"' in frame
    assert 'So111-solana' in frame
    events = adapter.parse_message({"result": {"prices": [{"token_id": "So111-solana", "price": "100"}]}})
    assert events[0].channel == "price"
    assert events[0].data["price"] == "100"


def test_audio_decoder_boundary_accepts_pcm16_only():
    decoder = Pcm16PassthroughDecoder()
    assert decoder.decode_to_pcm16(AudioFrame(b"pcm", format="pcm16")) == b"pcm"
