from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, ScreenPayload


class ChainAdapter(ABC):
    """Blockchain/application data adapter used by hardware apps."""

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

    @abstractmethod
    def get_portfolio(self, *, wallet_id: str = "paper", context: AppContext | None = None) -> ScreenPayload:
        raise NotImplementedError

    @abstractmethod
    def create_action_draft(self, action: str, params: dict[str, Any], *, context: AppContext | None = None) -> ActionDraft:
        raise NotImplementedError

    @abstractmethod
    def confirm_action(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        raise NotImplementedError

    @abstractmethod
    def cancel_action(self, request_id: str, *, context: AppContext | None = None) -> ActionResult:
        raise NotImplementedError
