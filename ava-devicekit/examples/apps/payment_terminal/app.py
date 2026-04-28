from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ava_devicekit.apps.base import HardwareApp
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, DeviceMessage, ScreenPayload
from ava_devicekit.screen import builders


@dataclass
class PaymentTerminalApp(HardwareApp):
    manifest: HardwareAppManifest
    context: AppContext = field(init=False)
    pending_request_id: str = "pay_demo_001"

    def __post_init__(self) -> None:
        self.context = AppContext(app_id=self.manifest.app_id, chain=self.manifest.chain, screen="payment_home")

    def boot(self) -> ScreenPayload:
        self.context.screen = "payment_home"
        self.context.selected = None
        return ScreenPayload(
            "payment_home",
            {
                "merchant": "Demo Store",
                "amount": "0.10",
                "asset": "USDC",
                "network": "solana",
                "payment_method": "solana_pay_transaction_request",
                "actions": ["payment.draft", "payment.qr"],
            },
            self.context,
        )

    def handle(self, message: DeviceMessage | dict[str, Any]) -> ScreenPayload | ActionDraft | ActionResult:
        msg = message if isinstance(message, DeviceMessage) else DeviceMessage.from_dict(message)
        if msg.context:
            self.context = msg.context
        action = msg.action or str(msg.payload.get("semantic_action") or msg.payload.get("action") or "")
        if msg.type == "confirm":
            return ActionResult(ok=True, message="Payment approved", screen=builders.result("Payment", "approved", context=self.context), data={"request_id": self.pending_request_id})
        if msg.type == "cancel":
            return ActionResult(ok=False, message="Payment cancelled", screen=builders.result("Payment", "cancelled", ok=False, context=self.context), data={"request_id": self.pending_request_id})
        if action in {"payment.draft", "payment.qr", "pay", "buy"}:
            return self._payment_draft()
        if action in {"home", "payment.home"}:
            return self.boot()
        return builders.notify("Payment Terminal", f"unsupported: {action or msg.type}", level="warn", context=self.context)

    def _payment_draft(self) -> ActionDraft:
        self.context.screen = "confirm"
        summary = {
            "title": "Confirm Solana Pay request",
            "merchant": "Demo Store",
            "spend": "0.10 USDC",
            "network": "solana",
            "recipient": "demo_merchant_wallet",
            "request_id": self.pending_request_id,
            "wallet_mode": "external_wallet_or_backend_draft",
        }
        screen = builders.confirm({"title": "Pay Demo Store", "spend": "0.10 USDC", "get": "receipt", "risk": "payment request"}, context=self.context)
        return ActionDraft(
            action="payment.solana_pay_request",
            chain="solana",
            summary=summary,
            screen=screen,
            risk={"level": "medium", "reason": "payment requires wallet/backend confirmation"},
            requires_confirmation=True,
            request_id=self.pending_request_id,
        )
