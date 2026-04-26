from __future__ import annotations

from typing import Any

from ava_devicekit.apps.ava_box_skills.config import SOLANA
from ava_devicekit.core.types import AppContext, ScreenPayload
from ava_devicekit.screen import builders
from ava_devicekit.storage.json_store import JsonStore


class WatchlistSkill:
    def __init__(self, store: JsonStore):
        self.store = store

    def open(self, *, context: AppContext | None = None) -> ScreenPayload:
        rows = [row for row in _state(self.store).get("watchlist", []) if isinstance(row, dict)]
        return builders.feed(rows, chain=SOLANA, source_label="WATCHLIST", mode="watchlist", context=context)

    def add(self, token: dict[str, Any], *, context: AppContext | None = None) -> ScreenPayload:
        token_id = str(token.get("token_id") or token.get("addr") or "")
        if not token_id:
            return builders.notify("Watchlist", "No token selected", level="warn", context=context)
        row = token_identity(token)
        state = _state(self.store)
        state["watchlist"] = [item for item in state.get("watchlist", []) if item.get("token_id") != row["token_id"]]
        state["watchlist"].insert(0, row)
        state["watchlist"] = state["watchlist"][:100]
        self.store.write(state)
        return builders.notify("Watchlist", f"Added {row.get('symbol', 'token')}", context=context)


def token_identity(token: dict[str, Any]) -> dict[str, Any]:
    token_id = str(token.get("token_id") or token.get("addr") or "").strip()
    return {
        "symbol": str(token.get("symbol") or "?").strip() or "?",
        "chain": str(token.get("chain") or SOLANA),
        "addr": str(token.get("addr") or token_id.replace("-solana", "")),
        "token_id": token_id if token_id.endswith("-solana") else f"{token_id}-{SOLANA}" if token_id else "",
        "price": str(token.get("price") or ""),
        "change_24h": str(token.get("change_24h") or ""),
        "change_positive": bool(token.get("change_positive", True)),
        "source": str(token.get("source") or token.get("source_tag") or "watchlist"),
    }


def _state(store: JsonStore) -> dict[str, Any]:
    return store.read({"watchlist": [], "paper_positions": []})
