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

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RuntimeSettings":
        data = data or {}
        server = data.get("server") if isinstance(data.get("server"), dict) else {}
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
