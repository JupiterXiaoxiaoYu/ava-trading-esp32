from __future__ import annotations

from typing import Any, Protocol

from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, DeviceMessage, ScreenPayload


class HardwareApp(Protocol):
    """Minimal runtime contract implemented by DeviceKit hardware apps."""

    manifest: HardwareAppManifest
    context: AppContext

    def boot(self) -> ScreenPayload:
        raise NotImplementedError

    def handle(self, message: DeviceMessage | dict[str, Any]) -> ScreenPayload | ActionResult | ActionDraft:
        raise NotImplementedError
