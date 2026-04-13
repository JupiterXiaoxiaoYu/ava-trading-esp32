import asyncio
import json
import queue
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.connection import ConnectionHandler
from core.handle.helloHandle import handleHelloMessage
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType


class _FakeLogger:
    def bind(self, **kwargs):
        return self

    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


class _FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(message)


class _StreamAsr:
    def __init__(self):
        self.interface_type = InterfaceType.STREAM
        self.stop_request_calls = 0

    async def _send_stop_request(self):
        self.stop_request_calls += 1


class _ManualSelectionAsr(ASRProviderBase):
    def __init__(self):
        super().__init__()
        self.interface_type = InterfaceType.STREAM
        self.output_dir = "/tmp"

    async def speech_to_text(self, opus_data, session_id, audio_format="opus", artifacts=None):
        return "帮我分析这个", None


class VoiceProtocolTests(unittest.IsolatedAsyncioTestCase):
    def _build_connection(self):
        conn = ConnectionHandler.__new__(ConnectionHandler)
        conn.logger = _FakeLogger()
        conn.is_exiting = False
        conn.bind_completed_event = asyncio.Event()
        conn.bind_completed_event.set()
        conn.need_bind = False
        conn.vad = object()
        conn.asr = object()
        conn.conn_from_mqtt_gateway = False
        conn.asr_audio_queue = queue.Queue()
        conn.headers = {}
        conn.websocket_protocol_version = 1
        conn.websocket = _FakeWebSocket()

        conn.client_audio_buffer = bytearray()
        conn.client_have_voice = False
        conn.client_voice_stop = False
        conn.client_voice_window = []
        conn.last_is_voice = False
        conn.client_listen_mode = "auto"
        conn.pending_listen_payload = None
        conn.asr_audio = []

        conn.welcome_msg = {
            "type": "hello",
            "transport": "websocket",
            "audio_params": {
                "format": "opus",
                "sample_rate": 24000,
                "channels": 1,
                "frame_duration": 60,
            },
        }
        conn.features = None
        return conn

    @staticmethod
    def _build_v2_packet(payload: bytes, timestamp: int, packet_type: int = 0) -> bytes:
        return (
            (2).to_bytes(2, "big")
            + packet_type.to_bytes(2, "big")
            + (0).to_bytes(4, "big")
            + timestamp.to_bytes(4, "big")
            + len(payload).to_bytes(4, "big")
            + payload
        )

    @staticmethod
    def _build_v3_packet(payload: bytes, packet_type: int = 0) -> bytes:
        return bytes([packet_type, 0]) + len(payload).to_bytes(2, "big") + payload

    async def test_hello_version_prefer_message_body_over_protocol_version_header(self):
        conn = self._build_connection()
        conn.headers = {"Protocol-Version": "2"}

        conn._record_websocket_protocol_version_from_headers()
        self.assertEqual(conn.websocket_protocol_version, 2)

        await handleHelloMessage(conn, {"type": "hello", "version": 3})

        self.assertEqual(conn.websocket_protocol_version, 3)
        self.assertEqual(len(conn.websocket.sent), 1)

    async def test_route_message_v1_audio_raw_passthrough(self):
        conn = self._build_connection()
        conn.websocket_protocol_version = 1

        raw = b"raw-opus-frame"
        await conn._route_message(raw)

        self.assertEqual(conn.asr_audio_queue.get_nowait(), raw)

    async def test_route_message_v2_audio_unpacked_and_ordered_with_timestamp(self):
        conn = self._build_connection()
        conn.websocket_protocol_version = 2

        calls = []

        def _capture(audio_data, timestamp):
            calls.append((audio_data, timestamp))

        conn._process_websocket_audio = _capture

        payload = b"opus-v2"
        ts = 123456
        await conn._route_message(self._build_v2_packet(payload, ts))

        self.assertEqual(calls, [(payload, ts)])
        self.assertTrue(conn.asr_audio_queue.empty())

    async def test_route_message_v3_audio_unpacked_payload_only(self):
        conn = self._build_connection()
        conn.websocket_protocol_version = 3

        payload = b"opus-v3"
        await conn._route_message(self._build_v3_packet(payload))

        self.assertEqual(conn.asr_audio_queue.get_nowait(), payload)

    async def test_route_message_v2_json_packet_is_consumed_but_not_routed_as_audio(self):
        conn = self._build_connection()
        conn.websocket_protocol_version = 2
        conn._process_websocket_audio = MagicMock()

        payload = b'{"type":"listen","state":"start"}'
        await conn._route_message(self._build_v2_packet(payload, 123456, packet_type=1))

        conn._process_websocket_audio.assert_not_called()
        self.assertTrue(conn.asr_audio_queue.empty())

    async def test_route_message_v3_json_packet_is_consumed_but_not_routed_as_audio(self):
        conn = self._build_connection()
        conn.websocket_protocol_version = 3

        payload = b'{"type":"listen","state":"start"}'
        await conn._route_message(self._build_v3_packet(payload, packet_type=1))

        self.assertTrue(conn.asr_audio_queue.empty())

    def test_protocol_doc_marks_binary_json_packet_type_as_unsupported_server_path(self):
        doc_path = (
            Path(__file__).resolve().parents[3] / "firmware" / "docs" / "websocket.md"
        )
        doc_text = doc_path.read_text(encoding="utf-8")

        self.assertIn("服务器当前仅处理 type=0", doc_text)
        self.assertIn("type=1", doc_text)
        self.assertIn("JSON 文本帧", doc_text)

    def test_selection_docs_require_missing_chain_to_fail_closed(self):
        repo_root = Path(__file__).resolve().parents[3]
        firmware_doc = (repo_root / "firmware" / "docs" / "websocket.md").read_text(
            encoding="utf-8"
        )
        simulator_doc = (repo_root / "docs" / "simulator-ui-guide.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("selection.token.chain", simulator_doc)
        self.assertIn("默认为 `solana`", simulator_doc)
        self.assertIn("selection.token.chain", firmware_doc)
        self.assertIn("默认为 `solana`", firmware_doc)
        self.assertIn("fail-closed", firmware_doc)

    def test_simulator_doc_covers_feed_explore_without_rebinding_fn(self):
        repo_root = Path(__file__).resolve().parents[3]
        simulator_doc = (repo_root / "docs" / "simulator-ui-guide.md").read_text(
            encoding="utf-8"
        )
        explore_section = simulator_doc.split("### FEED Explore（标准首页本地浮层）", 1)[1].split(
            "### 模拟器可直接触发", 1
        )[0]

        self.assertIn(
            "| `B` | 标准：打开 Explore 面板；SEARCH/特殊来源：恢复记住的标准来源并刷新；ORDERS：退出 orders |",
            simulator_doc,
        )
        self.assertIn("Explore 只在标准 FEED 首页可用", explore_section)
        self.assertIn("面板条目固定为 `Search / Orders / Sources`。", explore_section)
        self.assertIn(
            "`UP/DOWN` 移动条目；`A/RIGHT` 激活；`B/LEFT` 本地关闭；`Y` 仍按全局规则进入 `PORTFOLIO`；`X` 没有新增语义。",
            explore_section,
        )
        self.assertIn(
            "`Search` 只展示引导文案 `FN 说币名`，`F1/FN` 继续使用既有手动 `listen start/stop` 语义。",
            explore_section,
        )

    async def test_manual_listen_start_stop_still_works(self):
        conn = self._build_connection()
        stream_asr = _StreamAsr()
        conn.asr = stream_asr

        reset_calls = {"count": 0}

        def _reset_audio_states():
            reset_calls["count"] += 1

        conn.reset_audio_states = _reset_audio_states

        await conn._route_message(
            json.dumps({"type": "listen", "state": "start", "mode": "manual"})
        )
        await conn._route_message(
            json.dumps({"type": "listen", "state": "stop", "mode": "manual"})
        )
        await asyncio.sleep(0)

        self.assertEqual(conn.client_listen_mode, "manual")
        self.assertEqual(reset_calls["count"], 1)
        self.assertTrue(conn.client_voice_stop)
        self.assertEqual(stream_asr.stop_request_calls, 1)

    async def test_asr_voice_stop_forwards_pending_manual_selection_payload(self):
        conn = self._build_connection()
        conn.session_id = "selection-test"
        conn.audio_format = "pcm"
        conn.voiceprint_provider = None
        conn.pending_listen_payload = {
            "type": "listen",
            "state": "start",
            "mode": "manual",
            "selection": {
                "screen": "feed",
                "cursor": 1,
                "token": {"addr": "token-1", "chain": "base", "symbol": "AVA"},
            },
        }

        asr = _ManualSelectionAsr()

        with (
            patch(
                "core.providers.asr.base.enqueue_asr_report",
                MagicMock(),
            ),
            patch(
                "core.providers.asr.base.startToChat",
                AsyncMock(),
            ) as start_chat,
        ):
            await asr.handle_voice_stop(conn, [b"\x00\x00" * 320])

        start_chat.assert_awaited_once_with(
            conn,
            "帮我分析这个",
            message_payload={
                "type": "listen",
                "state": "start",
                "mode": "manual",
                "selection": {
                    "screen": "feed",
                    "cursor": 1,
                    "token": {
                        "addr": "token-1",
                        "chain": "base",
                        "symbol": "AVA",
                    },
                },
            },
        )
        self.assertIsNone(conn.pending_listen_payload)


if __name__ == "__main__":
    unittest.main()
