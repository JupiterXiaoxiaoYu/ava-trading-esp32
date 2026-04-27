from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava_devicekit.apps.base import HardwareApp
from ava_devicekit.core.contracts import InputEvent
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, DeviceMessage, ScreenPayload
from ava_devicekit.screen import builders


@dataclass
class MyHardwareApp(HardwareApp):
    manifest: HardwareAppManifest
    context: AppContext = field(init=False)

    def __post_init__(self) -> None:
        self.context = AppContext(app_id=self.manifest.app_id, chain=self.manifest.chain, screen="boot")

    def boot(self) -> ScreenPayload:
        self.context.screen = "notify"
        return builders.notify(self.manifest.name, "ready", context=self.context)

    def handle(self, message: DeviceMessage | dict[str, Any]) -> ScreenPayload | ActionResult | ActionDraft:
        msg = message if isinstance(message, DeviceMessage) else DeviceMessage.from_dict(message)
        if msg.context:
            self.context = msg.context
        if msg.type == "input_event":
            event = InputEvent.from_dict({"payload": msg.payload, "context": msg.context.to_dict() if msg.context else None})
            if event and event.semantic_action:
                return self._route_action(event.semantic_action, event.to_dict())
            return builders.notify("Input", "event received", context=self.context)
        if msg.type == "key_action" and msg.action == "home":
            return self.boot()
        if msg.type == "key_action":
            return self._route_action(msg.action, msg.payload)
        return builders.notify("Unsupported", msg.action or msg.type, level="warn", context=self.context)

    def _route_action(self, action: str, payload: dict[str, Any]) -> ScreenPayload | ActionResult | ActionDraft:
        if action == "home":
            return self.boot()
        if action == "sensor.refresh":
            self.context.screen = "sensor_panel"
            return ScreenPayload(
                "sensor_panel",
                {"title": "Sensor Panel", "items": [{"id": "sensor-1", "label": "Example", "value": "online"}]},
                self.context,
            )
        return builders.notify("Unsupported", action, level="warn", context=self.context)
