from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ava_devicekit.adapters.base import ChainAdapter
from ava_devicekit.adapters.solana import SolanaAdapter
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, DeviceMessage, ScreenPayload, Selection
from ava_devicekit.screen import builders

DEFAULT_MANIFEST = Path(__file__).resolve().parents[3] / "apps" / "ava_box" / "manifest.json"


@dataclass
class AvaBoxApp:
    """Reference hardware app built on Ava DeviceKit."""

    manifest: HardwareAppManifest
    chain_adapter: ChainAdapter
    context: AppContext = field(init=False)
    last_screen: ScreenPayload | None = None
    last_draft: ActionDraft | None = None

    def __post_init__(self) -> None:
        self.context = AppContext(app_id=self.manifest.app_id, chain=self.manifest.chain, screen="boot")

    @classmethod
    def create(cls, manifest_path: str | Path = DEFAULT_MANIFEST, chain_adapter: ChainAdapter | None = None) -> "AvaBoxApp":
        manifest = HardwareAppManifest.load(manifest_path)
        return cls(manifest=manifest, chain_adapter=chain_adapter or SolanaAdapter())

    def boot(self) -> ScreenPayload:
        screen = self.chain_adapter.get_feed(topic="trending", context=self.context)
        return self._remember_screen(screen)

    def handle(self, message: DeviceMessage | dict[str, Any]) -> ScreenPayload | ActionResult | ActionDraft:
        msg = message if isinstance(message, DeviceMessage) else DeviceMessage.from_dict(message)
        if msg.type == "heartbeat":
            return builders.notify("Ava Box", "online", level="info", context=self.context)
        if msg.type == "screen_context":
            self._ingest_context(msg.payload)
            return builders.notify("Context", "updated", level="info", context=self.context)
        if msg.type == "confirm":
            return self._confirm(msg)
        if msg.type == "cancel":
            return self._cancel(msg)
        if msg.type == "listen_detect":
            return self._route_voice(msg.text or str(msg.payload.get("text") or ""))
        if msg.type == "key_action":
            return self._route_key(msg.action, msg.payload)
        return builders.notify("Unsupported", msg.type, level="warn", context=self.context)

    def _route_key(self, action: str, payload: dict[str, Any]) -> ScreenPayload | ActionDraft | ActionResult:
        action = str(action or "").strip().lower()
        if action in {"home", "feed", "refresh"}:
            return self._remember_screen(self.chain_adapter.get_feed(topic="trending", context=self.context))
        if action == "feed_source":
            topic = str(payload.get("topic") or payload.get("source") or "trending")
            platform = str(payload.get("platform") or "")
            return self._remember_screen(self.chain_adapter.get_feed(topic=topic, platform=platform, context=self.context))
        if action in {"watch", "detail", "open"}:
            token_id = str(payload.get("token_id") or self._selected_token_id())
            return self._remember_screen(self.chain_adapter.get_token_detail(token_id, context=self.context))
        if action in {"buy", "quick_buy"}:
            draft = self.chain_adapter.create_action_draft("trade.market_draft", {**payload, "token_id": payload.get("token_id") or self._selected_token_id(), "symbol": payload.get("symbol") or self._selected_symbol()}, context=self.context)
            self.last_draft = draft
            self._remember_screen(draft.screen)
            return draft
        if action in {"sell", "quick_sell"}:
            draft = self.chain_adapter.create_action_draft("trade.sell_draft", {**payload, "token_id": payload.get("token_id") or self._selected_token_id(), "symbol": payload.get("symbol") or self._selected_symbol()}, context=self.context)
            self.last_draft = draft
            self._remember_screen(draft.screen)
            return draft
        if action in {"limit", "limit_buy"}:
            draft = self.chain_adapter.create_action_draft("trade.limit_draft", {**payload, "token_id": payload.get("token_id") or self._selected_token_id(), "symbol": payload.get("symbol") or self._selected_symbol()}, context=self.context)
            self.last_draft = draft
            self._remember_screen(draft.screen)
            return draft
        if action == "portfolio":
            return self._remember_screen(self.chain_adapter.get_portfolio(context=self.context))
        if action == "search":
            return self._remember_screen(self.chain_adapter.search_tokens(str(payload.get("keyword") or payload.get("query") or ""), context=self.context))
        if action == "watchlist" and hasattr(self.chain_adapter, "get_watchlist"):
            return self._remember_screen(self.chain_adapter.get_watchlist(context=self.context))  # type: ignore[attr-defined]
        return builders.notify("Unknown action", action or "empty", level="warn", context=self.context)

    def _route_voice(self, text: str) -> ScreenPayload | ActionDraft | ActionResult:
        normalized = text.strip().lower()
        if not normalized:
            return builders.notify("Voice", "empty command", level="warn", context=self.context)
        if any(word in normalized for word in ("portfolio", "持仓", "组合")):
            return self._remember_screen(self.chain_adapter.get_portfolio(context=self.context))
        if any(word in normalized for word in ("watchlist", "观察", "收藏列表")):
            if hasattr(self.chain_adapter, "get_watchlist"):
                return self._remember_screen(self.chain_adapter.get_watchlist(context=self.context))  # type: ignore[attr-defined]
        if any(word in normalized for word in ("search", "find", "搜索", "查找")):
            keyword = normalized.replace("search", "").replace("find", "").replace("搜索", "").replace("查找", "").strip()
            return self._remember_screen(self.chain_adapter.search_tokens(keyword, context=self.context))
        if any(word in normalized for word in ("buy", "买", "购买")):
            draft = self.chain_adapter.create_action_draft("trade.market_draft", {"token_id": self._selected_token_id(), "symbol": self._selected_symbol()}, context=self.context)
            self.last_draft = draft
            self._remember_screen(draft.screen)
            return draft
        if any(word in normalized for word in ("sell", "卖")):
            draft = self.chain_adapter.create_action_draft("trade.sell_draft", {"token_id": self._selected_token_id(), "symbol": self._selected_symbol()}, context=self.context)
            self.last_draft = draft
            self._remember_screen(draft.screen)
            return draft
        if any(word in normalized for word in ("detail", "介绍", "详情")):
            return self._remember_screen(self.chain_adapter.get_token_detail(self._selected_token_id(), context=self.context))
        return builders.notify("Ava", "Command routed to model fallback", level="info", context=self.context)

    def _confirm(self, msg: DeviceMessage) -> ActionResult:
        request_id = str(msg.payload.get("request_id") or msg.payload.get("trade_id") or (self.last_draft.request_id if self.last_draft else ""))
        result = self.chain_adapter.confirm_action(request_id, context=self.context)
        if result.screen:
            self._remember_screen(result.screen)
        return result

    def _cancel(self, msg: DeviceMessage) -> ActionResult:
        request_id = str(msg.payload.get("request_id") or msg.payload.get("trade_id") or (self.last_draft.request_id if self.last_draft else ""))
        result = self.chain_adapter.cancel_action(request_id, context=self.context)
        if result.screen:
            self._remember_screen(result.screen)
        return result

    def _ingest_context(self, payload: dict[str, Any]) -> None:
        selected_data = payload.get("selected") if isinstance(payload.get("selected"), dict) else {}
        selected = None
        if selected_data:
            selected = Selection(
                token_id=str(selected_data.get("token_id") or ""),
                addr=str(selected_data.get("addr") or ""),
                chain=str(selected_data.get("chain") or self.manifest.chain),
                symbol=str(selected_data.get("symbol") or ""),
                cursor=_optional_int(selected_data.get("cursor")),
                source=str(selected_data.get("source") or ""),
            )
        self.context = AppContext(
            app_id=self.manifest.app_id,
            chain=str(payload.get("chain") or self.manifest.chain),
            screen=str(payload.get("screen") or self.context.screen),
            cursor=_optional_int(payload.get("cursor")),
            selected=selected or self.context.selected,
            visible_rows=payload.get("visible_rows") if isinstance(payload.get("visible_rows"), list) else self.context.visible_rows,
            state={**self.context.state, **{k: v for k, v in payload.items() if k not in {"selected", "visible_rows"}}},
        )

    def _remember_screen(self, screen: ScreenPayload) -> ScreenPayload:
        self.last_screen = screen
        self.context.screen = screen.screen
        rows = []
        if isinstance(screen.payload.get("tokens"), list):
            rows = screen.payload["tokens"]
        elif isinstance(screen.payload.get("items"), list):
            rows = screen.payload["items"]
        self.context.visible_rows = rows
        if rows:
            cursor = self.context.cursor or 0
            if 0 <= cursor < len(rows):
                row = rows[cursor]
                if isinstance(row, dict):
                    self.context.selected = Selection(
                        token_id=str(row.get("token_id") or ""),
                        addr=str(row.get("addr") or ""),
                        chain=str(row.get("chain") or self.manifest.chain),
                        symbol=str(row.get("symbol") or ""),
                        cursor=cursor,
                        source=str(row.get("source") or row.get("source_tag") or ""),
                    )
        elif screen.screen == "spotlight":
            self.context.selected = Selection(
                token_id=str(screen.payload.get("token_id") or ""),
                addr=str(screen.payload.get("addr") or ""),
                chain=str(screen.payload.get("chain") or self.manifest.chain),
                symbol=str(screen.payload.get("symbol") or ""),
                cursor=self.context.cursor,
                source=str(screen.payload.get("source") or screen.payload.get("source_tag") or ""),
            )
        return screen

    def _selected_token_id(self) -> str:
        return self.context.selected.token_id if self.context.selected else ""

    def _selected_symbol(self) -> str:
        return self.context.selected.symbol if self.context.selected else "TOKEN"


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
