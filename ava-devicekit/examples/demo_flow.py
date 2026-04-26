from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ava_devicekit.adapters.base import ChainAdapter
from ava_devicekit.apps.ava_box import AvaBoxApp
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, ScreenPayload
from ava_devicekit.gateway.session import DeviceSession
from ava_devicekit.screen import builders

ROOT = Path(__file__).resolve().parents[1]


class MockSolanaAdapter(ChainAdapter):
    chain = "solana"

    def __init__(self):
        self.pending = {}
        self.token = {
            "symbol": "BONK",
            "chain": "solana",
            "addr": "DezXAZ8z7PnrnRJjz3hwKQ9kGJ6Y4X8QH1pPB263w9S",
            "token_id": "DezXAZ8z7PnrnRJjz3hwKQ9kGJ6Y4X8QH1pPB263w9S-solana",
            "price": "$0.000020",
            "change_24h": "+3.12%",
            "change_positive": True,
            "source": "mock",
        }

    def get_feed(self, *, topic: str = "trending", platform: str = "", context: AppContext | None = None) -> ScreenPayload:
        return builders.feed([self.token], chain="solana", source_label="TRENDING", context=context)

    def search_tokens(self, keyword: str, *, context: AppContext | None = None) -> ScreenPayload:
        return builders.feed([self.token], chain="solana", source_label="SEARCH", mode="search", context=context)

    def get_token_detail(self, token_id: str, *, interval: str = "60", context: AppContext | None = None) -> ScreenPayload:
        return builders.spotlight({**self.token, "pair": "BONK / USDC", "risk_level": "LOW", "chart": [200, 350, 600]}, context=context)

    def get_portfolio(self, *, wallet_id: str = "paper", context: AppContext | None = None) -> ScreenPayload:
        return builders.portfolio([{**self.token, "value": "$12.30", "pnl": "+$1.20"}], context=context)

    def create_action_draft(self, action: str, params: dict[str, Any], *, context: AppContext | None = None) -> ActionDraft:
        request_id = "mock_draft_1"
        screen = builders.confirm({"trade_id": request_id, "action": "BUY", "symbol": "BONK", "amount_native": "0.1 SOL", "timeout_sec": 30}, context=context)
        draft = ActionDraft(action=action, chain="solana", summary={"symbol": "BONK", "amount": "0.1 SOL"}, screen=screen, request_id=request_id)
        self.pending[request_id] = draft
        return draft

    def confirm_action(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        return ActionResult(True, "confirmed", screen=builders.result("Confirmed", request_id, context=context))

    def cancel_action(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        return ActionResult(True, "cancelled", screen=builders.result("Cancelled", request_id, context=context))


def main() -> None:
    manifest = HardwareAppManifest.load(ROOT / "apps" / "ava_box" / "manifest.json")
    session = DeviceSession(AvaBoxApp(manifest=manifest, chain_adapter=MockSolanaAdapter()))
    flow = [
        session.boot(),
        session.handle({"type": "key_action", "action": "watch"}),
        session.handle({"type": "key_action", "action": "buy"}),
        session.handle({"type": "confirm"}),
    ]
    print(json.dumps(flow, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
