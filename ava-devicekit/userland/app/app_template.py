from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava_devicekit.apps.base import HardwareApp
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
        if msg.type == "key_action" and msg.action == "home":
            return self.boot()
        return builders.notify("Unsupported", msg.action or msg.type, level="warn", context=self.context)
