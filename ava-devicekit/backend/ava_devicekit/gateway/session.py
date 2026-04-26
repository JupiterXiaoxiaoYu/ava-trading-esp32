from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ava_devicekit.apps.ava_box import AvaBoxApp
from ava_devicekit.core.types import ActionDraft, ActionResult, DeviceMessage, ScreenPayload

Outbound = Callable[[dict[str, Any]], None]


@dataclass
class DeviceSession:
    app: AvaBoxApp
    send: Outbound | None = None
    outbox: list[dict[str, Any]] = field(default_factory=list)

    def boot(self) -> dict[str, Any]:
        return self._emit(self.app.boot())

    def handle_json(self, raw: str) -> dict[str, Any]:
        return self.handle(DeviceMessage.from_dict(json.loads(raw)))

    def handle(self, message: DeviceMessage | dict[str, Any]) -> dict[str, Any]:
        result = self.app.handle(message)
        return self._emit(result)

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
