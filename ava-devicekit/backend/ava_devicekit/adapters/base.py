from __future__ import annotations

from abc import ABC, abstractmethod

from ava_devicekit.core.types import AppContext, ScreenPayload


class ChainAdapter(ABC):
    """Basic blockchain data adapter used by hardware apps.

    Keep this interface chain-focused. App-specific skills such as trading,
    watchlists, portfolio composition, and voice command behavior belong in the
    app layer or helper adapters, not in the framework chain adapter.
    """

    chain: str

    @abstractmethod
    def get_feed(self, *, topic: str = "trending", platform: str = "", context: AppContext | None = None) -> ScreenPayload:
        raise NotImplementedError

    @abstractmethod
    def search_tokens(self, keyword: str, *, context: AppContext | None = None) -> ScreenPayload:
        raise NotImplementedError

    @abstractmethod
    def get_token_detail(self, token_id: str, *, interval: str = "60", context: AppContext | None = None) -> ScreenPayload:
        raise NotImplementedError
