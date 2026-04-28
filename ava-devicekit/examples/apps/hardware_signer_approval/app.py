from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava_devicekit.apps.base import HardwareApp
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, DeviceMessage, ScreenPayload
from ava_devicekit.screen import builders


@dataclass
class HardwareSignerApprovalApp(HardwareApp):
    manifest: HardwareAppManifest
    context: AppContext = field(init=False)
    pubkey: str = "deployment_device_pubkey"
    request_id: str = "sig_req_001"

    def __post_init__(self) -> None:
        self.context = AppContext(app_id=self.manifest.app_id, chain=self.manifest.chain, screen="signer_home")

    def boot(self) -> ScreenPayload:
        self.context.screen = "signer_home"
        return ScreenPayload("signer_home", {"pubkey": self.pubkey, "status": "ready", "secure_element": "optional"}, self.context)

    def handle(self, message: DeviceMessage | dict[str, Any]) -> ScreenPayload | ActionDraft | ActionResult:
        msg = message if isinstance(message, DeviceMessage) else DeviceMessage.from_dict(message)
        if msg.context:
            self.context = msg.context
        action = msg.action or str(msg.payload.get("action") or msg.payload.get("semantic_action") or "")
        if action == "signer.get_pubkey":
            return self.boot()
        if action in {"signer.review_message", "signer.approve"}:
            summary = {"request_id": self.request_id, "pubkey": self.pubkey, "message": "base64 message hash", "policy": "physical confirmation required"}
            screen = ScreenPayload("sign_request", {"summary": summary, "request_id": self.request_id}, self.context)
            return ActionDraft(action="signer.approve", chain="solana", summary=summary, screen=screen, risk={"level": "high", "reason": "signature approval"}, requires_confirmation=True, request_id=self.request_id)
        if msg.type == "confirm":
            return ActionResult(ok=True, message="Signature approved", screen=builders.result("Signer", "approved", context=self.context), data={"request_id": self.request_id, "signature": "device_signature_placeholder"})
        if msg.type == "cancel":
            return ActionResult(ok=False, message="Signature rejected", screen=builders.result("Signer", "rejected", ok=False, context=self.context), data={"request_id": self.request_id})
        return builders.notify("Signer", action or msg.type, level="warn", context=self.context)
