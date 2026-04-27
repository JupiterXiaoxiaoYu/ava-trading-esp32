from __future__ import annotations

from ava_devicekit.adapters.base import ChainAdapter
from ava_devicekit.core.types import AppContext, ScreenPayload
from ava_devicekit.screen import builders


class MyChainAdapter(ChainAdapter):
    chain = "my_chain"

    def get_feed(self, *, topic: str = "trending", platform: str = "", context: AppContext | None = None) -> ScreenPayload:
        rows = []
        return builders.feed(rows, chain=self.chain, source_label=topic.upper(), context=context)

    def search_tokens(self, keyword: str, *, context: AppContext | None = None) -> ScreenPayload:
        rows = []
        return builders.feed(rows, chain=self.chain, source_label="SEARCH", mode="search", context=context)

    def get_token_detail(self, token_id: str, *, interval: str = "60", context: AppContext | None = None) -> ScreenPayload:
        payload = {"token_id": token_id, "chain": self.chain, "symbol": "TOKEN", "interval": interval}
        return builders.spotlight(payload, context=context)
