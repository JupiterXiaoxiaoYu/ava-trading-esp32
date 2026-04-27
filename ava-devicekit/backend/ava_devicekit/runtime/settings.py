from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 8788
DEFAULT_WEBSOCKET_PORT = 8787
DEFAULT_FIRMWARE_BIN_DIR = "data/bin"
DEFAULT_TIMEZONE_OFFSET_HOURS = 8
DEFAULT_WEBSOCKET_PING_INTERVAL = 30
DEFAULT_WEBSOCKET_PING_TIMEOUT = 10


@dataclass(slots=True)
class RuntimeSettings:
    """Deployment-owned DeviceKit runtime settings.

    This keeps legacy-style OTA/WebSocket configuration as data, without
    importing the legacy config loader or manager API.
    """

    host: str = DEFAULT_HOST
    http_port: int = DEFAULT_HTTP_PORT
    websocket_port: int = DEFAULT_WEBSOCKET_PORT
    public_base_url: str = ""
    websocket_url: str = ""
    firmware_bin_dir: str = DEFAULT_FIRMWARE_BIN_DIR
    timezone_offset_hours: int = DEFAULT_TIMEZONE_OFFSET_HOURS
    websocket_ping_interval: int = DEFAULT_WEBSOCKET_PING_INTERVAL
    websocket_ping_timeout: int = DEFAULT_WEBSOCKET_PING_TIMEOUT
    asr_provider: str = "disabled"
    asr_base_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    asr_model: str = "qwen3-asr-flash-realtime"
    asr_api_key_env: str = "DASHSCOPE_API_KEY"
    asr_language: str = "zh"
    asr_sample_rate: int = 16000
    llm_provider: str = "disabled"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_api_key_env: str = "OPENAI_API_KEY"
    llm_timeout_sec: int = 30
    tts_provider: str = "mock"
    tts_base_url: str = "https://api.openai.com/v1"
    tts_model: str = "gpt-4o-mini-tts"
    tts_api_key_env: str = "OPENAI_API_KEY"
    tts_voice: str = "alloy"
    tts_format: str = "opus"
    tts_timeout_sec: int = 30

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RuntimeSettings":
        data = data or {}
        server = data.get("server") if isinstance(data.get("server"), dict) else {}
        providers = data.get("providers") if isinstance(data.get("providers"), dict) else {}
        asr = providers.get("asr") if isinstance(providers.get("asr"), dict) else {}
        llm = providers.get("llm") if isinstance(providers.get("llm"), dict) else {}
        tts = providers.get("tts") if isinstance(providers.get("tts"), dict) else {}
        return cls(
            host=str(data.get("host") or server.get("ip") or DEFAULT_HOST),
            http_port=int(data.get("http_port") or server.get("http_port") or DEFAULT_HTTP_PORT),
            websocket_port=int(data.get("websocket_port") or server.get("port") or DEFAULT_WEBSOCKET_PORT),
            public_base_url=str(data.get("public_base_url") or server.get("public_base_url") or ""),
            websocket_url=str(data.get("websocket_url") or server.get("websocket") or ""),
            firmware_bin_dir=str(data.get("firmware_bin_dir") or server.get("firmware_bin_dir") or DEFAULT_FIRMWARE_BIN_DIR),
            timezone_offset_hours=int(data.get("timezone_offset_hours") or server.get("timezone_offset") or DEFAULT_TIMEZONE_OFFSET_HOURS),
            websocket_ping_interval=int(data.get("websocket_ping_interval") or data.get("websocket_transport_ping_interval") or DEFAULT_WEBSOCKET_PING_INTERVAL),
            websocket_ping_timeout=int(data.get("websocket_ping_timeout") or data.get("websocket_transport_ping_timeout") or DEFAULT_WEBSOCKET_PING_TIMEOUT),
            asr_provider=str(data.get("asr_provider") or asr.get("provider") or "disabled"),
            asr_base_url=str(data.get("asr_base_url") or asr.get("base_url") or "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"),
            asr_model=str(data.get("asr_model") or asr.get("model") or "qwen3-asr-flash-realtime"),
            asr_api_key_env=str(data.get("asr_api_key_env") or asr.get("api_key_env") or "DASHSCOPE_API_KEY"),
            asr_language=str(data.get("asr_language") or asr.get("language") or "zh"),
            asr_sample_rate=int(data.get("asr_sample_rate") or asr.get("sample_rate") or 16000),
            llm_provider=str(data.get("llm_provider") or llm.get("provider") or "disabled"),
            llm_base_url=str(data.get("llm_base_url") or llm.get("base_url") or "https://api.openai.com/v1"),
            llm_model=str(data.get("llm_model") or llm.get("model") or "gpt-4o-mini"),
            llm_api_key_env=str(data.get("llm_api_key_env") or llm.get("api_key_env") or "OPENAI_API_KEY"),
            llm_timeout_sec=int(data.get("llm_timeout_sec") or llm.get("timeout_sec") or 30),
            tts_provider=str(data.get("tts_provider") or tts.get("provider") or "mock"),
            tts_base_url=str(data.get("tts_base_url") or tts.get("base_url") or "https://api.openai.com/v1"),
            tts_model=str(data.get("tts_model") or tts.get("model") or "gpt-4o-mini-tts"),
            tts_api_key_env=str(data.get("tts_api_key_env") or tts.get("api_key_env") or "OPENAI_API_KEY"),
            tts_voice=str(data.get("tts_voice") or tts.get("voice") or "alloy"),
            tts_format=str(data.get("tts_format") or tts.get("format") or "opus"),
            tts_timeout_sec=int(data.get("tts_timeout_sec") or tts.get("timeout_sec") or 30),
        )

    @classmethod
    def load(cls, path: str | Path | None = None) -> "RuntimeSettings":
        if path:
            return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        env_config = os.environ.get("AVA_DEVICEKIT_CONFIG_JSON")
        if env_config:
            return cls.from_dict(json.loads(env_config))
        return cls.from_dict({})

    def websocket_endpoint(self, host_hint: str = "127.0.0.1") -> str:
        if self.websocket_url and "你的" not in self.websocket_url:
            return self.websocket_url
        return f"ws://{host_hint}:{self.websocket_port}/ava/v1/"

    def ota_base_url(self, host_hint: str = "127.0.0.1") -> str:
        if self.public_base_url:
            return self.public_base_url.rstrip("/")
        return f"http://{host_hint}:{self.http_port}"

    def sanitized_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "http_port": self.http_port,
            "websocket_port": self.websocket_port,
            "public_base_url": self.public_base_url,
            "websocket_url": self.websocket_url,
            "firmware_bin_dir": self.firmware_bin_dir,
            "websocket_ping_interval": self.websocket_ping_interval,
            "websocket_ping_timeout": self.websocket_ping_timeout,
            "providers": {
                "asr": {"provider": self.asr_provider, "model": self.asr_model, "api_key_env": self.asr_api_key_env},
                "llm": {"provider": self.llm_provider, "model": self.llm_model, "base_url": self.llm_base_url, "api_key_env": self.llm_api_key_env},
                "tts": {"provider": self.tts_provider, "model": self.tts_model, "base_url": self.tts_base_url, "api_key_env": self.tts_api_key_env, "voice": self.tts_voice},
            },
        }
