from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava_devicekit.apps.base import HardwareApp
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, DeviceMessage, ScreenPayload
from ava_devicekit.screen import builders


@dataclass
class OnChainEventListenerApp(HardwareApp):
    manifest: HardwareAppManifest
    context: AppContext = field(init=False)
    events: list[dict[str, str]] = field(default_factory=lambda: [{"id": "evt_1", "source": "memo", "text": "Hello from Solana"}])

    def __post_init__(self) -> None:
        self.context = AppContext(app_id=self.manifest.app_id, chain=self.manifest.chain, screen="event_feed")

    def boot(self) -> ScreenPayload:
        self.context.screen = "event_feed"
        return ScreenPayload("event_feed", {"events": self.events, "subscription": "deployment-configured"}, self.context)

    def handle(self, message: DeviceMessage | dict[str, Any]) -> ScreenPayload | ActionDraft | ActionResult:
        msg = message if isinstance(message, DeviceMessage) else DeviceMessage.from_dict(message)
        if msg.context:
            self.context = msg.context
        action = msg.action or str(msg.payload.get("action") or msg.payload.get("semantic_action") or "")
        if action in {"event.subscribe", "event.ack", "event.speak"}:
            return self.boot()
        if action == "actuator.trigger":
            summary = {"event": self.events[0], "actuator": "deployment-configured", "requires_confirmation": True}
            return ActionDraft(action="actuator.trigger", chain="solana", summary=summary, screen=builders.confirm({"title": "Trigger actuator", "spend": "none", "get": "physical action"}, context=self.context), risk={"level": "medium", "reason": "physical output"}, requires_confirmation=True)
        if msg.type == "confirm":
            return ActionResult(ok=True, message="Actuator triggered", screen=builders.result("Event", "triggered", context=self.context))
        return builders.notify("Event Listener", action or msg.type, level="warn", context=self.context)
