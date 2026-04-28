from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava_devicekit.apps.base import HardwareApp
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.core.types import ActionDraft, AppContext, DeviceMessage, ScreenPayload
from ava_devicekit.screen import builders


@dataclass
class PaymentTerminalApp(HardwareApp):
    manifest: HardwareAppManifest
    context: AppContext = field(init=False)

    def __post_init__(self) -> None:
        self.context = AppContext(app_id=self.manifest.app_id, chain=self.manifest.chain, screen="payment_home")

    def boot(self) -> ScreenPayload:
        self.context.screen = "payment_home"
        self.context.selected = None
        return ScreenPayload("payment_home", {"merchant": "Demo Store", "amount": "0.10", "asset": "USDC"}, self.context)

    def handle(self, message: DeviceMessage | dict[str, Any]) -> ScreenPayload | ActionDraft:
        msg = message if isinstance(message, DeviceMessage) else DeviceMessage.from_dict(message)
        if msg.context:
            self.context = msg.context
        action = msg.action or str(msg.payload.get("semantic_action") or "")
        if action in {"payment.draft", "pay", "buy"}:
            return ActionDraft(
                action="payment.send",
                summary={"merchant": "Demo Store", "spend": "0.10 USDC", "network": "solana"},
                requires_confirmation=True,
                payload={"recipient": "demo", "amount": "0.10", "asset": "USDC"},
            )
        return builders.notify("Payment Terminal", f"unsupported: {action or msg.type}", level="warn", context=self.context)
