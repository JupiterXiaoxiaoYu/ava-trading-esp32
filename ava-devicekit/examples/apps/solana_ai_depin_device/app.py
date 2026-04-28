from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava_devicekit.apps.base import HardwareApp
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, DeviceMessage, ScreenPayload
from ava_devicekit.screen import builders


@dataclass
class SolanaAIDePINDeviceApp(HardwareApp):
    manifest: HardwareAppManifest
    context: AppContext = field(init=False)
    device_id: str = "unregistered"
    project: str = "default-solana"
    heartbeat_count: int = 0

    def __post_init__(self) -> None:
        self.context = AppContext(app_id=self.manifest.app_id, chain=self.manifest.chain, screen="boot")

    def boot(self) -> ScreenPayload:
        self.context.screen = "device_home"
        return self._home()

    def handle(self, message: DeviceMessage | dict[str, Any]) -> ScreenPayload | ActionDraft | ActionResult:
        msg = message if isinstance(message, DeviceMessage) else DeviceMessage.from_dict(message)
        if msg.context:
            self.context = msg.context
        action = msg.action or str(msg.payload.get("action") or "")
        if msg.type == "confirm":
            return ActionResult(ok=True, message="Confirmed", data={"status": "accepted", "device_id": self.device_id})
        if msg.type == "cancel":
            return ActionResult(ok=False, message="Cancelled", data={"status": "cancelled"})
        if action in {"home", "device.home"}:
            return self._home()
        if action == "device.heartbeat":
            self.heartbeat_count += 1
            return self._home(status="heartbeat sent")
        if action in {"device.register", "proof.submit"}:
            return self._draft(action, msg.payload)
        return builders.notify("Unsupported", action or msg.type, level="warn", context=self.context)

    def _home(self, *, status: str = "online") -> ScreenPayload:
        return ScreenPayload(
            "device_home",
            {
                "title": "Solana AI DePIN",
                "device_id": self.device_id,
                "project": self.project,
                "status": status,
                "heartbeat_count": self.heartbeat_count,
                "actions": ["device.heartbeat", "proof.submit"],
            },
            self.context,
        )

    def _draft(self, action: str, payload: dict[str, Any]) -> ActionDraft:
        proof_type = str(payload.get("proof_type") or ("registration" if action == "device.register" else "device_proof"))
        self.context.screen = "proof_detail"
        screen = ScreenPayload(
            "proof_detail",
            {"proof_type": proof_type, "summary": f"{proof_type} for {self.device_id}", "risk": "physical confirmation required"},
            self.context,
        )
        return ActionDraft(
            action=action,
            chain="solana",
            summary={
                "title": "Confirm Solana DePIN action",
                "description": f"{proof_type} for {self.device_id}",
                "chain": "solana",
                "device_id": self.device_id,
                "project": self.project,
                "proof_type": proof_type,
                "custody": "device identity only; no user asset key on ESP32",
            },
            screen=screen,
            risk={"level": "medium", "reason": "on-chain proof draft requires physical approval"},
            requires_confirmation=True,
        )
