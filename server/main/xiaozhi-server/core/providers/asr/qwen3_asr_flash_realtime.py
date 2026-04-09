import asyncio
import base64
import json
import os
import uuid
from typing import List, TYPE_CHECKING

import opuslib_next
import websockets

from config.logger import setup_logging
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType

if TYPE_CHECKING:
    from core.connection import ConnectionHandler


TAG = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__()
        self.interface_type = InterfaceType.STREAM
        self.config = config
        self.text = ""
        self.decoder = opuslib_next.Decoder(16000, 1)
        self.asr_ws = None
        self.forward_task = None
        self.is_processing = False
        self.server_ready = False
        self.stop_sent = False

        self.api_key = config.get("api_key")
        if not self.api_key:
            raise ValueError("Qwen3ASRFlashRealtime 需要配置 api_key")

        self.model_name = config.get("model_name", "qwen3-asr-flash-realtime")
        self.sample_rate = int(config.get("sample_rate", 16000))
        self.audio_format = config.get("format", "pcm")
        self.language = config.get("language")
        self.threshold = float(config.get("threshold", 0.2))
        self.silence_duration_ms = int(config.get("silence_duration_ms", 800))
        self.ws_url = config.get(
            "ws_url",
            f"wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime?model={self.model_name}",
        )

        self.output_dir = config.get("output_dir", "./audio_output")
        self.delete_audio_file = delete_audio_file
        os.makedirs(self.output_dir, exist_ok=True)

    async def open_audio_channels(self, conn):
        await super().open_audio_channels(conn)

    def _build_session_update_event(self, manual_mode: bool) -> dict:
        session = {
            "modalities": ["text"],
            "input_audio_format": self.audio_format,
            "sample_rate": self.sample_rate,
            "input_audio_transcription": {},
        }
        if self.language:
            session["input_audio_transcription"]["language"] = self.language

        if manual_mode:
            session["turn_detection"] = None
        else:
            session["turn_detection"] = {
                "type": "server_vad",
                "threshold": self.threshold,
                "silence_duration_ms": self.silence_duration_ms,
            }

        return {
            "event_id": f"event_{uuid.uuid4().hex}",
            "type": "session.update",
            "session": session,
        }

    def _process_server_event(self, event: dict) -> dict:
        event_type = event.get("type", "")
        result = {
            "server_ready": False,
            "final_transcript": None,
            "interim_text": None,
            "error": None,
        }

        if event_type == "session.updated":
            result["server_ready"] = True
        elif event_type == "conversation.item.input_audio_transcription.text":
            result["interim_text"] = event.get("text") or event.get("stash")
        elif event_type == "conversation.item.input_audio_transcription.completed":
            result["final_transcript"] = event.get("transcript", "")
        elif event_type == "error":
            error_info = event.get("error", {})
            result["error"] = error_info.get("message") or json.dumps(
                error_info or event, ensure_ascii=False
            )
        elif event_type.endswith(".failed"):
            result["error"] = json.dumps(event, ensure_ascii=False)

        return result

    async def receive_audio(self, conn, audio, audio_have_voice):
        await super().receive_audio(conn, audio, audio_have_voice)

        if audio_have_voice and not self.is_processing and not self.asr_ws:
            try:
                await self._start_recognition(conn)
            except Exception as e:
                logger.bind(tag=TAG).error(f"开始识别失败: {str(e)}")
                await self._cleanup()
                return

        if self.asr_ws and self.is_processing and self.server_ready:
            try:
                pcm_frame = audio
                if conn.audio_format != "pcm":
                    pcm_frame = self.decoder.decode(audio, 960)
                await self._send_pcm_frame(pcm_frame)
            except Exception as e:
                logger.bind(tag=TAG).warning(f"发送音频失败: {str(e)}")
                await self._cleanup()

    async def _start_recognition(self, conn: "ConnectionHandler"):
        manual_mode = conn.client_listen_mode == "manual"
        self.is_processing = True
        self.server_ready = False
        self.stop_sent = False
        self.text = ""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        logger.bind(tag=TAG).debug(f"正在连接Qwen实时ASR服务: {self.ws_url}")

        self.asr_ws = await websockets.connect(
            self.ws_url,
            additional_headers=headers,
            max_size=1000000000,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=5,
        )

        self.forward_task = asyncio.create_task(self._forward_results(conn))
        await self.asr_ws.send(
            json.dumps(
                self._build_session_update_event(manual_mode=manual_mode),
                ensure_ascii=False,
            )
        )

    async def _send_pcm_frame(self, pcm_frame: bytes):
        if not self.asr_ws or not pcm_frame:
            return
        payload = {
            "event_id": f"event_{uuid.uuid4().hex}",
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm_frame).decode("utf-8"),
        }
        await self.asr_ws.send(json.dumps(payload, ensure_ascii=False))

    async def _forward_results(self, conn: "ConnectionHandler"):
        try:
            while not conn.stop_event.is_set():
                audio_data = conn.asr_audio
                try:
                    response = await asyncio.wait_for(self.asr_ws.recv(), timeout=1.0)
                    event = json.loads(response)
                    parsed = self._process_server_event(event)
                    event_type = event.get("type", "")

                    if event_type == "session.created":
                        logger.bind(tag=TAG).debug("Qwen实时ASR会话已创建")
                        continue

                    if parsed["server_ready"]:
                        self.server_ready = True
                        logger.bind(tag=TAG).debug("Qwen实时ASR已准备，开始发送缓存音频")
                        if conn.asr_audio:
                            for cached_audio in conn.asr_audio[-10:]:
                                pcm_frame = cached_audio
                                if conn.audio_format != "pcm":
                                    pcm_frame = self.decoder.decode(cached_audio, 960)
                                await self._send_pcm_frame(pcm_frame)
                        continue

                    interim_text = parsed["interim_text"]
                    if interim_text:
                        logger.bind(tag=TAG).debug(f"实时转写中: {interim_text}")

                    if parsed["error"]:
                        logger.bind(tag=TAG).error(
                            f"Qwen实时ASR返回错误: {parsed['error']}"
                        )
                        break

                    final_transcript = parsed["final_transcript"]
                    if final_transcript is not None:
                        logger.bind(tag=TAG).info(f"识别到文本: {final_transcript}")

                        if conn.client_listen_mode == "manual":
                            if final_transcript:
                                self.text += final_transcript

                            if conn.client_voice_stop:
                                await self.handle_voice_stop(conn, audio_data)
                                break
                        else:
                            self.text = final_transcript
                            await self.handle_voice_stop(conn, audio_data)
                            break

                except asyncio.TimeoutError:
                    continue
                except websockets.ConnectionClosed:
                    logger.bind(tag=TAG).info("Qwen实时ASR连接已关闭")
                    self.is_processing = False
                    break
                except Exception as e:
                    logger.bind(tag=TAG).error(f"处理Qwen实时ASR结果失败: {str(e)}")
                    break
        except Exception as e:
            logger.bind(tag=TAG).error(f"Qwen实时ASR转发失败: {str(e)}")
        finally:
            await self._cleanup()
            conn.reset_audio_states()

    async def _send_stop_request(self):
        if self.asr_ws and not self.stop_sent:
            try:
                self.is_processing = False
                self.stop_sent = True
                await self.asr_ws.send(
                    json.dumps(
                        {
                            "event_id": f"event_{uuid.uuid4().hex}",
                            "type": "input_audio_buffer.commit",
                        },
                        ensure_ascii=False,
                    )
                )
                logger.bind(tag=TAG).debug("已发送Qwen实时ASR commit 事件")
            except Exception as e:
                logger.bind(tag=TAG).error(f"发送Qwen实时ASR停止请求失败: {e}")

    async def _cleanup(self):
        self.is_processing = False
        self.server_ready = False
        self.stop_sent = False

        if self.asr_ws:
            try:
                await asyncio.wait_for(self.asr_ws.close(), timeout=2.0)
            except Exception as e:
                logger.bind(tag=TAG).debug(f"关闭Qwen实时ASR连接失败: {e}")
            finally:
                self.asr_ws = None

        self.forward_task = None

    async def close(self):
        await self._cleanup()

    async def speech_to_text(self, opus_data, session_id, audio_format="opus", artifacts=None):
        result = self.text
        self.text = ""
        return result, None
