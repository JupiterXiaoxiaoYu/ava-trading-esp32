from __future__ import annotations

from ava_devicekit.adapters.base import ChainAdapter
from ava_devicekit.core.types import AppContext, ScreenPayload
from ava_devicekit.screen import builders


class MockSolanaAdapter(ChainAdapter):
    """Offline Solana-shaped adapter for demos and tests."""

    chain = "solana"

    def __init__(self):
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
        return builders.feed([self.token], chain="solana", source_label=(platform or topic or "trending").upper(), context=context)

    def search_tokens(self, keyword: str, *, context: AppContext | None = None) -> ScreenPayload:
        return builders.feed([self.token], chain="solana", source_label="SEARCH", mode="search", context=context)

    def get_token_detail(self, token_id: str, *, interval: str = "60", context: AppContext | None = None) -> ScreenPayload:
        return builders.spotlight(
            {
                **self.token,
                "pair": "BONK / USDC",
                "risk_level": "LOW",
                "chart": [200, 350, 600],
                "interval": interval,
            },
            context=context,
        )
