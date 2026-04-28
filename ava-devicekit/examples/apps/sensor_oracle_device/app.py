from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava_devicekit.apps.base import HardwareApp
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, DeviceMessage, ScreenPayload
from ava_devicekit.screen import builders


@dataclass
class SensorOracleDeviceApp(HardwareApp):
    manifest: HardwareAppManifest
    context: AppContext = field(init=False)
    device_id: str = "sensor_001"
    reading: dict[str, Any] = field(default_factory=lambda: {"temperature": 25.5, "humidity": 60.0})

    def __post_init__(self) -> None:
        self.context = AppContext(app_id=self.manifest.app_id, chain=self.manifest.chain, screen="sensor_panel")

    def boot(self) -> ScreenPayload:
        return self._panel("wss")

    def handle(self, message: DeviceMessage | dict[str, Any]) -> ScreenPayload | ActionDraft | ActionResult:
        msg = message if isinstance(message, DeviceMessage) else DeviceMessage.from_dict(message)
        if msg.context:
            self.context = msg.context
        action = msg.action or str(msg.payload.get("action") or msg.payload.get("semantic_action") or "")
        if action in {"sensor.read", "sensor.submit", "oracle.verify"}:
            return self._panel("wss_or_http_fallback")
        if action == "data.anchor":
            return self._anchor_draft()
        if msg.type == "confirm":
            return ActionResult(ok=True, message="Anchor approved", screen=builders.result("Data Anchor", "approved", context=self.context))
        return builders.notify("Sensor Oracle", action or msg.type, level="warn", context=self.context)

    def _panel(self, transport: str) -> ScreenPayload:
        self.context.screen = "sensor_panel"
        return ScreenPayload("sensor_panel", {"device_id": self.device_id, "readings": self.reading, "transport": transport, "services": ["device_ingest", "oracle", "data_anchor"]}, self.context)

    def _anchor_draft(self) -> ActionDraft:
        summary = {"device_id": self.device_id, "readings": self.reading, "service": "data_anchor", "batch": "latest"}
        return ActionDraft(action="data.anchor", chain="solana", summary=summary, screen=builders.confirm({"title": "Anchor sensor batch", "spend": "network fee", "get": "verifiable data proof"}, context=self.context), risk={"level": "medium", "reason": "publishes device data"}, requires_confirmation=True)
