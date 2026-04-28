from __future__ import annotations

import base64
import asyncio
import sys
import types

from ava_devicekit.core.types import AppContext, Selection
from ava_devicekit.providers.asr.qwen_realtime import QwenRealtimeASRConfig
from ava_devicekit.providers.llm.base import LLMMessage, LLMResult
from ava_devicekit.providers.llm.openai_compatible import OpenAICompatibleLLMConfig, OpenAICompatibleLLMProvider
from ava_devicekit.providers.asr import AudioFrame, Pcm16PassthroughDecoder, QwenRealtimeASRProvider
from ava_devicekit.providers.pipeline import VoicePipeline
from ava_devicekit.streams import MockMarketStreamAdapter, StreamSubscription


def test_qwen_asr_realtime_builds_events_and_parses_transcript():
    provider = QwenRealtimeASRProvider(QwenRealtimeASRConfig(context="常用词：Ava"))
    session = provider.session_update_event()
    assert session["session"]["input_audio_transcription"]["language"] == "zh"
    assert session["session"]["input_audio_transcription"]["corpus"]["text"] == "常用词：Ava"
    assert provider.url() == "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime?model=qwen3-asr-flash-realtime"
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


def test_voice_pipeline_records_llm_and_tts_usage():
    events = []

    class _LLM:
        name = "demo_llm"

        def complete(self, messages, *, temperature=0.2):
            return LLMResult("answer", raw={"usage": {"total_tokens": 17}})

    def recorder(device_id, metric, amount, source, metadata):
        events.append((device_id, metric, amount, source, metadata))

    result = VoicePipeline(llm=_LLM(), usage_recorder=recorder).reply("hello", device_id="dev_001")

    assert result.text == "answer"
    assert ("dev_001", "llm_tokens", 17.0, "llm", {"provider": "demo_llm"}) in events
    assert any(item[1] == "tts_chars" and item[2] == len("answer") for item in events)


def test_mock_market_stream_snapshots_prices():
    stream = MockMarketStreamAdapter()
    stream.subscribe(StreamSubscription("price", ["So111-solana"]))
    stream.set_price("So111-solana", 123.456)
    events = stream.snapshot()
    assert events[0].token_id == "So111-solana"
    assert events[0].data["price_raw"] == 123.456

from ava_devicekit.providers.registry import create_provider_bundle
from ava_devicekit.providers.tts.alibl_stream import AliBLTTSConfig, AliBLTTSProvider
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


def test_alibl_tts_streams_audio_from_websocket(monkeypatch):
    monkeypatch.setenv("TEST_ALIBL_KEY", "secret")
    captured = {"sent": []}

    class _Conn:
        def __init__(self):
            self.messages = [
                '{"header":{"event":"task-started"}}',
                b"opus-audio",
                '{"header":{"event":"task-finished"}}',
            ]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def send(self, payload):
            captured["sent"].append(payload)

        async def recv(self):
            return self.messages.pop(0)

    def connect(url, additional_headers=None, **kwargs):
        captured["url"] = url
        captured["headers"] = additional_headers
        captured["kwargs"] = kwargs
        return _Conn()

    monkeypatch.setitem(sys.modules, "websockets", types.SimpleNamespace(connect=connect))
    provider = AliBLTTSProvider(
        AliBLTTSConfig(
            api_key_env="TEST_ALIBL_KEY",
            ws_url="wss://dashscope.example/ws",
            model="cosyvoice-v2",
            voice="longcheng_v2",
            response_format="opus",
        )
    )
    result = provider.synthesize("**Ava**")
    assert captured["url"] == "wss://dashscope.example/ws"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert any('"action":"run-task"' in item for item in captured["sent"])
    assert any('"voice":"longcheng_v2"' in item for item in captured["sent"])
    assert any('"text":"Ava"' in item for item in captured["sent"])
    assert result.audio == b"opus-audio"
    assert result.content_type == "audio/opus"


def test_alibl_tts_can_run_inside_existing_event_loop(monkeypatch):
    monkeypatch.setenv("TEST_ALIBL_KEY", "secret")

    class _Conn:
        def __init__(self):
            self.messages = [
                '{"header":{"event":"task-started"}}',
                b"opus-audio",
                '{"header":{"event":"task-finished"}}',
            ]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def send(self, payload):
            pass

        async def recv(self):
            return self.messages.pop(0)

    monkeypatch.setitem(sys.modules, "websockets", types.SimpleNamespace(connect=lambda *a, **k: _Conn()))
    provider = AliBLTTSProvider(AliBLTTSConfig(api_key_env="TEST_ALIBL_KEY"))

    async def _call():
        return provider.synthesize("Ava")

    assert asyncio.run(_call()).audio == b"opus-audio"


def test_openai_compatible_llm_uses_runtime_options(monkeypatch):
    monkeypatch.setenv("TEST_LLM_KEY", "secret")
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    def fake_urlopen(req, timeout=0):
        captured["body"] = req.data.decode()
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OpenAICompatibleLLMProvider(
        OpenAICompatibleLLMConfig(
            base_url="https://llm.example/v1",
            api_key_env="TEST_LLM_KEY",
            model="qwen3-235b-a22b",
            temperature=0.7,
            max_tokens=500,
            top_p=1,
            frequency_penalty=0,
        )
    )
    result = provider.complete([LLMMessage("user", "hello")])
    assert result.text == "ok"
    assert '"temperature": 0.7' in captured["body"]
    assert '"max_tokens": 500' in captured["body"]
    assert '"top_p": 1' in captured["body"]
    assert '"frequency_penalty": 0' in captured["body"]
    assert "enable_thinking" not in captured["body"]


def test_dashscope_qwen3_non_streaming_llm_disables_thinking(monkeypatch):
    monkeypatch.setenv("TEST_LLM_KEY", "secret")
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    def fake_urlopen(req, timeout=0):
        captured["body"] = req.data.decode()
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OpenAICompatibleLLMProvider(
        OpenAICompatibleLLMConfig(
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            api_key_env="TEST_LLM_KEY",
            model="qwen3-235b-a22b",
        )
    )
    result = provider.complete([LLMMessage("user", "hello")])
    assert result.text == "ok"
    assert '"enable_thinking": false' in captured["body"]


def test_ave_data_wss_builds_frames_and_parses_price_events():
    adapter = AveDataWSSAdapter()
    frame = adapter.subscribe_frame(StreamSubscription("price", ["So111-solana"]), request_id=7)
    assert '"method":"subscribe"' in frame
    assert 'So111-solana' in frame
    kline_frame = adapter.subscribe_frame(StreamSubscription("kline", ["Pair111"], interval="s1", chain="solana"), request_id=8)
    assert '"params":["kline","Pair111","s1","solana"]' in kline_frame
    events = adapter.handle_message({"result": {"prices": [{"token_id": "So111-solana", "price": "100"}]}})
    assert events[0].channel == "price"
    assert events[0].data["price"] == "100"
    assert adapter.snapshot()[0].token_id == "So111-solana"


def test_ave_data_wss_parses_actual_kline_container():
    adapter = AveDataWSSAdapter()
    events = adapter.handle_message(
        {
            "result": {
                "id": "Pair111-solana",
                "interval": "s1",
                "kline": {"eth": {"close": "0.1234", "time": 1710000000}},
            }
        }
    )
    assert events[0].channel == "kline"
    assert events[0].token_id == "Pair111"
    assert events[0].data["pair"] == "Pair111"
    assert events[0].data["interval"] == "s1"


def test_audio_decoder_boundary_accepts_pcm16_only():
    decoder = Pcm16PassthroughDecoder()
    assert decoder.decode_to_pcm16(AudioFrame(b"pcm", format="pcm16")) == b"pcm"

from ava_devicekit.providers.asr.openai_compatible import OpenAICompatibleASRConfig, OpenAICompatibleASRProvider
from ava_devicekit.providers.tts.mock import MockTTSProvider


def test_registry_selects_openai_compatible_asr_and_custom_tts():
    settings = RuntimeSettings.from_dict(
        {
            "providers": {
                "asr": {"provider": "openai-compatible", "base_url": "https://asr.example/v1", "model": "whisper-x", "api_key_env": "ASR_KEY", "language": "en"},
                "tts": {"provider": "custom", "class": "ava_devicekit.providers.tts.mock.MockTTSProvider"},
            }
        }
    )
    bundle = create_provider_bundle(settings)
    assert isinstance(bundle.asr, OpenAICompatibleASRProvider)
    assert bundle.asr.config.model == "whisper-x"
    assert isinstance(bundle.tts, MockTTSProvider)


def test_registry_selects_alibl_tts():
    settings = RuntimeSettings.from_dict(
        {
            "providers": {
                "tts": {
                    "provider": "alibl",
                    "base_url": "wss://dashscope.example/ws",
                    "model": "cosyvoice-v2",
                    "voice": "longcheng_v2",
                    "format": "opus",
                    "api_key_env": "TEST_ALIBL_KEY",
                }
            }
        }
    )
    bundle = create_provider_bundle(settings)
    assert isinstance(bundle.tts, AliBLTTSProvider)
    assert bundle.tts.config.voice == "longcheng_v2"


def test_openai_compatible_asr_posts_wav_transcription(monkeypatch):
    monkeypatch.setenv("TEST_ASR_KEY", "secret")
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"text":"hello"}'

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = req.data
        captured["content_type"] = req.headers["Content-type"]
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OpenAICompatibleASRProvider(OpenAICompatibleASRConfig(base_url="https://asr.example/v1", api_key_env="TEST_ASR_KEY", model="whisper-x"))
    result = provider._transcribe_pcm16_blocking(b"\x00\x00\x01\x00", 16000, "en")
    assert captured["url"] == "https://asr.example/v1/audio/transcriptions"
    assert b"audio.wav" in captured["body"]
    assert b"RIFF" in captured["body"]
    assert "multipart/form-data" in captured["content_type"]
    assert result.text == "hello"

from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.streams.base import MarketStreamEvent
from ava_devicekit.streams.runtime import MarketStreamRuntime


def test_market_stream_runtime_updates_current_feed_screen():
    session = create_device_session(mock=True)
    session.boot()
    selected = session.app.context.selected
    assert selected and selected.token_id
    runtime = MarketStreamRuntime(MockMarketStreamAdapter())
    emitted = runtime.apply_events(session, [MarketStreamEvent("price", selected.token_id, {"price": "999", "change_24h": "1.5"})])
    assert emitted
    assert emitted[0]["data"]["tokens"][0]["price"] == "$999"
    assert emitted[0]["data"]["tokens"][0]["change_24h"] == "+1.5%"


def test_market_stream_runtime_updates_live_s1_spotlight_chart():
    session = create_device_session(mock=True)
    session.handle({"type": "key_action", "action": "watch"})
    app = session.app
    app.last_screen.payload["interval"] = "s1"
    app.last_screen.payload["main_pair_id"] = "Pair111"
    runtime = MarketStreamRuntime(MockMarketStreamAdapter())
    emitted = runtime.apply_events(
        session,
        [
            MarketStreamEvent("kline", "Pair111", {"close": "0.1", "time": 1710000000, "interval": "s1"}),
            MarketStreamEvent("kline", "Pair111", {"close": "0.2", "time": 1710000001, "interval": "s1"}),
        ],
    )
    assert emitted
    data = emitted[-1]["data"]
    assert data["live"] is True
    assert data["interval"] == "s1"
    assert data["chart_t_end"] == "now"
    assert data["chart"] == [0, 1000]


def test_market_stream_runtime_fills_paper_limit_orders(tmp_path):
    session = create_device_session(mock=True, skill_store_path=str(tmp_path / "skills.json"))
    feed = session.boot()
    token = feed["data"]["tokens"][0]
    draft = session.handle({"type": "key_action", "action": "limit", "limit_price": "0.00001", **token})
    result = session.handle({"type": "confirm", "trade_id": draft["action_draft"]["request_id"]})
    assert result["data"]["success"] is True

    orders = session.handle({"type": "key_action", "action": "orders"})
    assert orders["data"]["tokens"][0]["change_24h"] == "paper_open"

    runtime = MarketStreamRuntime(MockMarketStreamAdapter())
    emitted = runtime.apply_events(session, [MarketStreamEvent("price", token["token_id"], {"price": "0.000009"})])
    assert emitted
    assert emitted[0]["data"]["tokens"][0]["symbol"] == "ORDERS"
    assert emitted[0]["data"]["order_refresh"]["targets"] == ["orders", "history", "portfolio"]

    history = session.handle({"type": "key_action", "action": "order_history"})
    assert history["data"]["tokens"][0]["symbol"] == token["symbol"]
    assert history["data"]["tokens"][0]["change_24h"] == "paper_filled"


def test_market_stream_runtime_fills_paper_limit_history_without_navigation(tmp_path):
    session = create_device_session(mock=True, skill_store_path=str(tmp_path / "skills.json"))
    feed = session.boot()
    token = feed["data"]["tokens"][0]
    draft = session.handle({"type": "key_action", "action": "limit", "limit_price": "0.00001", **token})
    result = session.handle({"type": "confirm", "trade_id": draft["action_draft"]["request_id"]})
    assert result["data"]["success"] is True

    history = session.handle({"type": "key_action", "action": "order_history"})
    assert history["data"]["tokens"][0]["symbol"] == "HISTORY"

    runtime = MarketStreamRuntime(MockMarketStreamAdapter())
    emitted = runtime.apply_events(session, [MarketStreamEvent("price", token["token_id"], {"price": "0.000009"})])
    assert emitted
    assert emitted[0]["data"]["source_label"] == "PAPER HISTORY"
    assert emitted[0]["data"]["tokens"][0]["symbol"] == token["symbol"]
    assert emitted[0]["data"]["tokens"][0]["change_24h"] == "paper_filled"
    assert emitted[0]["data"]["order_refresh"]["reason"] == "paper_limit_filled"


def test_market_stream_runtime_fills_paper_limit_portfolio_without_navigation(tmp_path):
    session = create_device_session(mock=True, skill_store_path=str(tmp_path / "skills.json"))
    feed = session.boot()
    token = feed["data"]["tokens"][0]
    draft = session.handle({"type": "key_action", "action": "limit", "limit_price": "0.00001", **token})
    result = session.handle({"type": "confirm", "trade_id": draft["action_draft"]["request_id"]})
    assert result["data"]["success"] is True

    portfolio = session.handle({"type": "key_action", "action": "portfolio"})
    assert all(row["symbol"] != token["symbol"] for row in portfolio["data"]["holdings"])

    runtime = MarketStreamRuntime(MockMarketStreamAdapter())
    emitted = runtime.apply_events(session, [MarketStreamEvent("price", token["token_id"], {"price": "0.000009"})])
    assert emitted
    assert emitted[0]["screen"] == "portfolio"
    assert any(row["symbol"] == token["symbol"] for row in emitted[0]["data"]["holdings"])
    assert emitted[0]["data"]["order_refresh"]["targets"] == ["orders", "history", "portfolio"]


def test_market_stream_runtime_emits_order_refresh_hook_when_screen_is_not_refreshable(tmp_path):
    session = create_device_session(mock=True, skill_store_path=str(tmp_path / "skills.json"))
    feed = session.boot()
    token = feed["data"]["tokens"][0]
    draft = session.handle({"type": "key_action", "action": "limit", "limit_price": "0.00001", **token})
    result = session.handle({"type": "confirm", "trade_id": draft["action_draft"]["request_id"]})
    assert result["screen"] == "result"

    runtime = MarketStreamRuntime(MockMarketStreamAdapter())
    emitted = runtime.apply_events(session, [MarketStreamEvent("price", token["token_id"], {"price": "0.000009"})])
    assert emitted
    assert emitted[0]["screen"] == "result"
    assert emitted[0]["data"]["order_refresh"]["reason"] == "paper_limit_filled"
    assert emitted[0]["data"]["order_refresh"]["symbols"] == [token["symbol"]]
