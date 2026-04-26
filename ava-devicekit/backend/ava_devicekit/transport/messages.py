from __future__ import annotations

import json
from typing import Any

from ava_devicekit.core.types import DeviceMessage


def parse_device_message(raw: str | bytes | dict[str, Any]) -> DeviceMessage:
    if isinstance(raw, bytes):
        raw = raw.decode()
    if isinstance(raw, str):
        return DeviceMessage.from_dict(json.loads(raw))
    return DeviceMessage.from_dict(raw)


def encode_device_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
