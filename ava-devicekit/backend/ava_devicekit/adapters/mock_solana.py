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
                "chart_min": "$0.000010",
                "chart_max": "$0.000030",
                "chart_min_y": "1.00e-5",
                "chart_mid_y": "2.00e-5",
                "chart_max_y": "3.00e-5",
                "chart_t_start": "01/01 00:00",
                "chart_t_mid": "01/01 12:00",
                "chart_t_end": "now",
                "interval": interval,
                **_cursor_payload(context),
            },
            context=context,
        )


def _cursor_payload(context: AppContext | None) -> dict:
    if not context or not context.visible_rows:
        return {}
    cursor = context.cursor
    if cursor is None and context.selected:
        cursor = context.selected.cursor
    data = {"total": len(context.visible_rows)}
    if cursor is not None:
        data["cursor"] = cursor
    return data
