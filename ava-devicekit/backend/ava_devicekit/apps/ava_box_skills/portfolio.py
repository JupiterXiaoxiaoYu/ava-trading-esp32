from __future__ import annotations

from typing import Any

from ava_devicekit.apps.ava_box_skills.config import SOLANA
from ava_devicekit.core.types import AppContext, ScreenPayload
from ava_devicekit.screen import builders
from ava_devicekit.storage.json_store import JsonStore


class PortfolioSkill:
    def __init__(self, store: JsonStore):
        self.store = store

    def open(self, *, context: AppContext | None = None) -> ScreenPayload:
        rows = [row for row in _state(self.store).get("paper_positions", []) if isinstance(row, dict)]
        if not rows:
            rows = [{"symbol": "EMPTY", "chain": SOLANA, "value": "$0", "pnl": "$0", "source": "paper"}]
        return builders.portfolio(rows, chain=SOLANA, context=context)


def _state(store: JsonStore) -> dict[str, Any]:
    return store.read({"watchlist": [], "paper_positions": []})
