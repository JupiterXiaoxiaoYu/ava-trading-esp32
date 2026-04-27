from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ava_devicekit.apps.base import HardwareApp
from ava_devicekit.core.types import ActionDraft, ActionResult, DeviceMessage, ScreenPayload

Outbound = Callable[[dict[str, Any]], None]


@dataclass
class DeviceSession:
    app: HardwareApp
    send: Outbound | None = None
    outbox: list[dict[str, Any]] = field(default_factory=list)

    def boot(self) -> dict[str, Any]:
        return self._emit(self.app.boot())

    def handle_json(self, raw: str) -> dict[str, Any]:
        return self.handle(DeviceMessage.from_dict(json.loads(raw)))

    def handle(self, message: DeviceMessage | dict[str, Any]) -> dict[str, Any]:
        result = self.app.handle(message)
        return self._emit(result)

    def emit(self, result: ScreenPayload | ActionDraft | ActionResult) -> dict[str, Any]:
        return self._emit(result)

    def snapshot(self) -> dict[str, Any]:
        return {
            "app_id": self.app.manifest.app_id,
            "app_name": self.app.manifest.name,
            "chain": self.app.manifest.chain,
            "screen": self.app.context.screen,
            "context": self.app.context.to_dict(),
            "outbox_count": len(self.outbox),
        }

    def _emit(self, result: ScreenPayload | ActionDraft | ActionResult) -> dict[str, Any]:
        if isinstance(result, ScreenPayload):
            payload = result.to_dict()
        elif isinstance(result, ActionDraft):
            payload = result.screen.to_dict()
            payload["action_draft"] = result.to_dict()
        elif isinstance(result, ActionResult):
            payload = result.screen.to_dict() if result.screen else result.to_dict()
            payload["action_result"] = result.to_dict()
        else:
            payload = {"type": "error", "message": "unsupported result"}
        self.outbox.append(payload)
        if self.send:
            self.send(payload)
        return payload
