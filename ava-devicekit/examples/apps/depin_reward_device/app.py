from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava_devicekit.apps.base import HardwareApp
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, DeviceMessage, ScreenPayload
from ava_devicekit.screen import builders


@dataclass
class DePINRewardDeviceApp(HardwareApp):
    manifest: HardwareAppManifest
    context: AppContext = field(init=False)
    device_id: str = "dev_reward_001"
    telemetry_count: int = 0
    reward: str = "0.00 SOL"

    def __post_init__(self) -> None:
        self.context = AppContext(app_id=self.manifest.app_id, chain=self.manifest.chain, screen="reward_home")

    def boot(self) -> ScreenPayload:
        self.context.screen = "reward_home"
        return self._home("online")

    def handle(self, message: DeviceMessage | dict[str, Any]) -> ScreenPayload | ActionDraft | ActionResult:
        msg = message if isinstance(message, DeviceMessage) else DeviceMessage.from_dict(message)
        if msg.context:
            self.context = msg.context
        action = msg.action or str(msg.payload.get("action") or msg.payload.get("semantic_action") or "")
        if msg.type == "confirm":
            return ActionResult(ok=True, message="Reward action approved", screen=builders.result("Reward", "approved", context=self.context), data={"device_id": self.device_id})
        if msg.type == "cancel":
            return ActionResult(ok=False, message="Reward action cancelled", screen=builders.result("Reward", "cancelled", ok=False, context=self.context))
        if action == "telemetry.submit":
            self.telemetry_count += 1
            return self._home("telemetry signed")
        if action == "reward.check":
            self.reward = "0.03 SOL"
            return self._home("oracle eligible")
        if action in {"reward.claim", "device.identity"}:
            return self._draft(action)
        return builders.notify("DePIN Reward", action or msg.type, level="warn", context=self.context)

    def _home(self, status: str) -> ScreenPayload:
        return ScreenPayload("reward_home", {"device_id": self.device_id, "status": status, "telemetry_count": self.telemetry_count, "reward": self.reward, "services": ["device_ingest", "oracle", "reward_distributor"]}, self.context)

    def _draft(self, action: str) -> ActionDraft:
        self.context.screen = "proof_detail"
        summary = {"device_id": self.device_id, "action": action, "reward": self.reward, "oracle": "deployment-configured", "custody": "device identity only"}
        screen = ScreenPayload("proof_detail", {"proof_type": action, "summary": summary, "risk": "requires physical approval"}, self.context)
        return ActionDraft(action=action, chain="solana", summary=summary, screen=screen, risk={"level": "medium", "reason": "oracle/reward proof"}, requires_confirmation=True)
