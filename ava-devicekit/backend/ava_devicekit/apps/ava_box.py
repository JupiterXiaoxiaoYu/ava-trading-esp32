from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ava_devicekit.adapters.base import ChainAdapter
from ava_devicekit.adapters.solana import SolanaAdapter
from ava_devicekit.apps.ava_box_skills import AvaBoxSkillService
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.core.contracts import InputEvent
from ava_devicekit.core.types import ActionDraft, ActionResult, AppContext, DeviceMessage, ScreenPayload, Selection
from ava_devicekit.formatting.numbers import format_money, format_percent, parse_number
from ava_devicekit.screen import builders
from ava_devicekit.streams.base import MarketStreamEvent

DEFAULT_MANIFEST = Path(__file__).resolve().parents[3] / "apps" / "ava_box" / "manifest.json"


@dataclass
class AvaBoxApp:
    """Reference hardware app built on Ava DeviceKit."""

    manifest: HardwareAppManifest
    chain_adapter: ChainAdapter
    skills: AvaBoxSkillService = field(default_factory=AvaBoxSkillService)
    context: AppContext = field(init=False)
    last_screen: ScreenPayload | None = None
    last_draft: ActionDraft | None = None

    def __post_init__(self) -> None:
        self.context = AppContext(app_id=self.manifest.app_id, chain=self.manifest.chain, screen="boot")

    @classmethod
    def create(
        cls,
        manifest_path: str | Path = DEFAULT_MANIFEST,
        chain_adapter: ChainAdapter | None = None,
        skills: AvaBoxSkillService | None = None,
    ) -> "AvaBoxApp":
        manifest = HardwareAppManifest.load(manifest_path)
        return cls(
            manifest=manifest,
            chain_adapter=chain_adapter or SolanaAdapter(),
            skills=skills or AvaBoxSkillService(),
        )

    def boot(self) -> ScreenPayload:
        screen = self.chain_adapter.get_feed(topic="trending", context=self.context)
        return self._remember_screen(screen)

    def handle(self, message: DeviceMessage | dict[str, Any]) -> ScreenPayload | ActionResult | ActionDraft:
        msg = message if isinstance(message, DeviceMessage) else DeviceMessage.from_dict(message)
        if msg.context:
            self._ingest_context(msg.context.to_dict())
        if msg.type == "heartbeat":
            return builders.notify("Ava Box", "online", level="info", context=self.context)
        if msg.type == "screen_context":
            self._ingest_context(msg.payload)
            return builders.notify("Context", "updated", level="info", context=self.context)
        if msg.type == "input_event":
            payload = dict(msg.payload)
            if msg.action and "semantic_action" not in payload:
                payload["semantic_action"] = msg.action
            return self._route_input_event(payload, msg.context)
        if msg.type == "confirm":
            return self._confirm(msg)
        if msg.type == "cancel":
            return self._cancel(msg)
        if msg.type == "signed_tx":
            return self._submit_signed(msg)
        if msg.type == "listen_detect":
            return self._route_voice(msg.text or str(msg.payload.get("text") or ""))
        if msg.type == "key_action":
            return self._route_key(msg.action, msg.payload)
        return builders.notify("Unsupported", msg.type, level="warn", context=self.context)

    def _route_input_event(self, payload: dict[str, Any], context: AppContext | None = None) -> ScreenPayload | ActionDraft | ActionResult:
        event = InputEvent.from_dict({"payload": payload, "context": context.to_dict() if context else None})
        if event and event.context:
            self._ingest_context(event.context.to_dict())
        action = event.semantic_action if event else ""
        if action == "mcp":
            return builders.notify("MCP", "Payload received", level="info", context=self.context)
        if action:
            return self._route_key(action, {**payload, "input_source": event.source if event else "", "input_kind": event.kind if event else ""})
        return builders.notify("Input", "Event received", level="info", context=self.context)

    def _route_key(self, action: str, payload: dict[str, Any]) -> ScreenPayload | ActionDraft | ActionResult:
        action = str(action or "").strip().lower()
        trade_mode = str(self.context.state.get("trade_mode") or "").lower()
        trade_mode_payload = {"execution_mode": trade_mode} if trade_mode else {}
        if action in {"home", "feed", "refresh", "feed_home", "back"}:
            return self._remember_screen(self.chain_adapter.get_feed(topic="trending", context=self.context))
        if action == "confirm":
            return self._confirm(DeviceMessage(type="confirm", context=self.context))
        if action in {"cancel", "cancel_trade"}:
            return self._cancel(DeviceMessage(type="cancel", context=self.context))
        if action == "explorer_sync":
            return self._remember_screen(ScreenPayload("explorer", {"trade_mode": self.context.state.get("trade_mode", "real")}, self.context))
        if action == "trade_mode_set":
            mode = str(payload.get("mode") or "real").lower()
            mode = "paper" if mode == "paper" else "real"
            self.context.state["trade_mode"] = mode
            return self._remember_screen(ScreenPayload("explorer", {"trade_mode": mode}, self.context))
        if action == "feed_source":
            topic = str(payload.get("topic") or payload.get("source") or "trending")
            platform = str(payload.get("platform") or "")
            return self._remember_screen(self.chain_adapter.get_feed(topic=topic, platform=platform, context=self.context))
        if action == "feed_platform":
            platform = str(payload.get("platform") or "")
            return self._remember_screen(self.chain_adapter.get_feed(platform=platform, context=self.context))
        if action in {"signals", "signals_chain_cycle"}:
            feed = self.chain_adapter.get_feed(topic="gainer", context=self.context)
            return self._remember_screen(_as_browse(feed, mode="signals", source_label="SIGNALS"))
        if action == "watchlist_chain_cycle":
            feed = self.skills.get_watchlist(context=self.context)
            return self._remember_screen(_as_browse(feed, mode="watchlist", source_label="WATCHLIST"))
        if action in {"watch", "detail", "open", "disambiguation_select", "portfolio_watch", "portfolio_activity_detail"}:
            token_id = str(payload.get("token_id") or self._selected_token_id())
            return self._remember_screen(self.chain_adapter.get_token_detail(token_id, context=self.context))
        if action in {"kline_interval", "kline_internal"}:
            token_id = str(payload.get("token_id") or self._selected_token_id())
            interval = str(payload.get("interval") or self.context.state.get("interval") or "60")
            return self._remember_screen(self.chain_adapter.get_token_detail(token_id, interval=interval, context=self.context))
        if action in {"feed_prev", "feed_next"}:
            return self._route_feed_nav(action)
        if action in {"buy", "quick_buy"}:
            draft = self.skills.create_action_draft("trade.market_draft", {**payload, **trade_mode_payload, "token_id": payload.get("token_id") or self._selected_token_id(), "symbol": payload.get("symbol") or self._selected_symbol()}, context=self.context)
            self.last_draft = draft
            self._remember_screen(draft.screen)
            return draft
        if action in {"sell", "quick_sell"}:
            draft = self.skills.create_action_draft("trade.sell_draft", {**payload, **trade_mode_payload, "token_id": payload.get("token_id") or self._selected_token_id(), "symbol": payload.get("symbol") or self._selected_symbol()}, context=self.context)
            self.last_draft = draft
            self._remember_screen(draft.screen)
            return draft
        if action == "portfolio_sell":
            token_id = str(payload.get("token_id") or payload.get("addr") or self._selected_token_id())
            draft = self.skills.create_action_draft("trade.sell_draft", {**payload, **trade_mode_payload, "token_id": token_id, "symbol": payload.get("symbol") or self._selected_symbol(), "amount_native": payload.get("balance_raw") or payload.get("amount_native") or ""}, context=self.context)
            self.last_draft = draft
            self._remember_screen(draft.screen)
            return draft
        if action in {"limit", "limit_buy"}:
            draft = self.skills.create_action_draft("trade.limit_draft", {**payload, **trade_mode_payload, "token_id": payload.get("token_id") or self._selected_token_id(), "symbol": payload.get("symbol") or self._selected_symbol()}, context=self.context)
            self.last_draft = draft
            self._remember_screen(draft.screen)
            return draft
        if action == "portfolio":
            return self._remember_screen(self.skills.get_portfolio(context=self.context))
        if action in {"orders", "paper_orders"}:
            return self._remember_screen(self.skills.get_orders(context=self.context))
        if action == "search":
            return self._remember_screen(self.chain_adapter.search_tokens(str(payload.get("keyword") or payload.get("query") or ""), context=self.context))
        if action == "watchlist":
            return self._remember_screen(self.skills.get_watchlist(context=self.context))
        if action in {"watchlist_add", "add_watchlist", "favorite"}:
            selected = self.context.selected.to_dict() if self.context.selected else {}
            return self.skills.add_watchlist({**selected, **payload}, context=self.context)
        if action in {"watchlist_remove", "remove_watchlist", "unfavorite"}:
            selected = self.context.selected.to_dict() if self.context.selected else {}
            return self.skills.remove_watchlist({**selected, **payload}, context=self.context)
        if action == "portfolio_chain_cycle":
            return builders.notify("Portfolio", "Only Solana portfolio is enabled in this build", level="info", context=self.context)
        return builders.notify("Unknown action", action or "empty", level="warn", context=self.context)

    def _route_feed_nav(self, action: str) -> ScreenPayload:
        rows = self.context.visible_rows or []
        if not rows:
            return builders.notify("Navigation", "No feed context", level="warn", context=self.context)
        cursor = self.context.cursor
        if cursor is None and self.context.selected:
            cursor = self.context.selected.cursor
        cursor = cursor if cursor is not None else 0
        next_cursor = cursor + (1 if action == "feed_next" else -1)
        if next_cursor < 0 or next_cursor >= len(rows):
            return builders.notify("Navigation", "Feed boundary", level="info", context=self.context)
        row = rows[next_cursor] if isinstance(rows[next_cursor], dict) else {}
        token_id = str(row.get("token_id") or row.get("addr") or "")
        self.context.cursor = next_cursor
        if self.context.selected:
            self.context.selected.cursor = next_cursor
        return self._remember_screen(self.chain_adapter.get_token_detail(token_id, context=self.context))

    def _route_voice(self, text: str) -> ScreenPayload | ActionDraft | ActionResult:
        normalized = text.strip().lower()
        if not normalized:
            return builders.notify("Voice", "empty command", level="warn", context=self.context)
        if any(word in normalized for word in ("portfolio", "持仓", "组合")):
            return self._remember_screen(self.skills.get_portfolio(context=self.context))
        if any(word in normalized for word in ("orders", "订单")):
            return self._remember_screen(self.skills.get_orders(context=self.context))
        if any(word in normalized for word in ("watchlist", "观察", "收藏列表")):
            return self._remember_screen(self.skills.get_watchlist(context=self.context))
        if any(word in normalized for word in ("取消收藏", "移除收藏", "remove watch", "unfavorite")):
            selected = self.context.selected.to_dict() if self.context.selected else {}
            return self.skills.remove_watchlist(selected, context=self.context)
        if any(word in normalized for word in ("收藏", "加入收藏", "加自选", "favorite", "add watch")):
            selected = self.context.selected.to_dict() if self.context.selected else {}
            return self.skills.add_watchlist(selected, context=self.context)
        if any(word in normalized for word in ("search", "find", "搜索", "查找")):
            keyword = normalized.replace("search", "").replace("find", "").replace("搜索", "").replace("查找", "").strip()
            return self._remember_screen(self.chain_adapter.search_tokens(keyword, context=self.context))
        if any(word in normalized for word in ("buy", "买", "购买")):
            draft = self.skills.create_action_draft("trade.market_draft", {"token_id": self._selected_token_id(), "symbol": self._selected_symbol()}, context=self.context)
            self.last_draft = draft
            self._remember_screen(draft.screen)
            return draft
        if any(word in normalized for word in ("sell", "卖")):
            draft = self.skills.create_action_draft("trade.sell_draft", {"token_id": self._selected_token_id(), "symbol": self._selected_symbol()}, context=self.context)
            self.last_draft = draft
            self._remember_screen(draft.screen)
            return draft
        if any(word in normalized for word in ("detail", "详情", "打开详情", "进入详情")):
            return self._remember_screen(self.chain_adapter.get_token_detail(self._selected_token_id(), context=self.context))
        return builders.notify("Ava", "Command routed to model fallback", level="info", context=self.context)

    def _confirm(self, msg: DeviceMessage) -> ActionResult:
        request_id = str(msg.payload.get("request_id") or msg.payload.get("trade_id") or (self.last_draft.request_id if self.last_draft else ""))
        result = self.skills.confirm_action(request_id, context=self.context)
        if result.screen:
            self._remember_screen(result.screen)
        return result

    def _cancel(self, msg: DeviceMessage) -> ActionResult:
        request_id = str(msg.payload.get("request_id") or msg.payload.get("trade_id") or (self.last_draft.request_id if self.last_draft else ""))
        result = self.skills.cancel_action(request_id, context=self.context)
        if result.screen:
            self._remember_screen(result.screen)
        return result

    def _submit_signed(self, msg: DeviceMessage) -> ActionResult:
        request_id = str(msg.payload.get("request_id") or msg.payload.get("trade_id") or (self.last_draft.request_id if self.last_draft else ""))
        result = self.skills.submit_signed_action(request_id, str(msg.payload.get("signed_tx") or ""), context=self.context)
        if result.screen:
            self._remember_screen(result.screen)
        return result

    def _ingest_context(self, payload: dict[str, Any]) -> None:
        selected_data = payload.get("selected") if isinstance(payload.get("selected"), dict) else payload.get("token") if isinstance(payload.get("token"), dict) else {}
        incoming_state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
        selected = Selection.from_dict(selected_data)
        if selected and selected.cursor is None:
            selected.cursor = _optional_int(payload.get("cursor"))
        self.context = AppContext(
            app_id=self.manifest.app_id,
            chain=str(payload.get("chain") or self.manifest.chain),
            screen=str(payload.get("screen") or self.context.screen),
            cursor=_optional_int(payload.get("cursor")),
            selected=selected or self.context.selected,
            visible_rows=payload.get("visible_rows") if isinstance(payload.get("visible_rows"), list) else self.context.visible_rows,
            state={
                **self.context.state,
                **incoming_state,
                **{k: v for k, v in payload.items() if k not in {"selected", "token", "visible_rows", "state"}},
            },
        )

    def _remember_screen(self, screen: ScreenPayload) -> ScreenPayload:
        self.last_screen = screen
        self.context.screen = screen.screen
        rows = []
        if isinstance(screen.payload.get("tokens"), list):
            rows = screen.payload["tokens"]
        elif isinstance(screen.payload.get("holdings"), list):
            rows = screen.payload["holdings"]
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
            if screen.payload.get("cursor") is not None:
                self.context.cursor = _optional_int(screen.payload.get("cursor"))
            if screen.payload.get("interval") is not None:
                self.context.state["interval"] = str(screen.payload.get("interval") or "")
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

    def apply_market_events(self, events: list[MarketStreamEvent]) -> ScreenPayload | None:
        """Apply live market updates to the current screen payload.

        Live streams are app-level behavior: the framework provides stream
        contracts, while Ava Box decides how price/kline data modifies feed and
        spotlight screens.
        """

        if not self.last_screen:
            return None
        changed = False
        payload = dict(self.last_screen.payload)
        if self.last_screen.screen == "feed":
            rows = [dict(row) for row in payload.get("tokens", []) if isinstance(row, dict)]
            changed = _apply_events_to_rows(rows, events)
            if changed:
                payload["tokens"] = rows
        elif self.last_screen.screen == "spotlight":
            token_id = str(payload.get("token_id") or "")
            pair_id = str(payload.get("main_pair_id") or "")
            for event in events:
                if event.channel == "price" and _event_matches_token(event.token_id, token_id, payload):
                    _apply_price(payload, event.data)
                    changed = True
                if event.channel == "kline" and _event_matches_kline(event.token_id, pair_id, token_id):
                    incoming_interval = str(event.data.get("interval") or "")
                    selected_interval = str(payload.get("interval") or self.context.state.get("interval") or "60")
                    if _normalized_interval(selected_interval) != "s1":
                        continue
                    if incoming_interval and _normalized_interval(incoming_interval) != _normalized_interval(selected_interval):
                        continue
                    close = _optional_float(event.data.get("close", event.data.get("c")))
                    if close > 0:
                        key = f"_live_kline:{token_id}:s1"
                        points = [row for row in self.context.state.get(key, []) if isinstance(row, dict)]
                        points.append({"close": close, "time": _optional_int(event.data.get("time", event.data.get("t"))) or 0})
                        points = points[-48:]
                        self.context.state[key] = points
                        payload.update(_chart_payload(points))
                        payload["interval"] = selected_interval
                        changed = True
        if not changed:
            return None
        payload["live"] = True
        return self._remember_screen(ScreenPayload(self.last_screen.screen, payload, context=self.context))


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _apply_events_to_rows(rows: list[dict[str, Any]], events: list[MarketStreamEvent]) -> bool:
    by_token = {event.token_id: event for event in events if event.channel == "price"}
    changed = False
    for row in rows:
        event = by_token.get(str(row.get("token_id") or ""))
        if event:
            _apply_price(row, event.data)
            changed = True
    return changed


def _apply_price(target: dict[str, Any], data: dict[str, Any]) -> None:
    price = data.get("price") or data.get("current_price_usd") or data.get("price_usd")
    change = data.get("change_24h") or data.get("token_price_change_24h") or data.get("price_change_24h")
    if price not in (None, ""):
        target["price_raw"] = _optional_float(price)
        target["price"] = format_money(price)
    if change not in (None, ""):
        value = _optional_float(change)
        target["change_24h"] = format_percent(value)
        target["change_positive"] = value >= 0


def _event_matches_token(event_token_id: str, token_id: str, payload: dict[str, Any]) -> bool:
    event_id = str(event_token_id or "")
    if not event_id:
        return False
    addr = str(payload.get("addr") or "")
    chain = str(payload.get("chain") or "solana")
    candidates = {token_id, addr, f"{addr}-{chain}"}
    return event_id in candidates


def _event_matches_kline(event_token_id: str, pair_id: str, token_id: str) -> bool:
    event_id = str(event_token_id or "")
    if not event_id:
        return False
    return event_id in {pair_id, token_id} or (pair_id and event_id.startswith(pair_id + "-"))


def _normalized_interval(interval: str) -> str:
    value = str(interval or "").strip().lower()
    return value[1:] if value.startswith("k") else value


def _chart_payload(points: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [_optional_float(row.get("close", row.get("c"))) for row in points]
    closes = [value for value in closes if value > 0]
    if not closes:
        return {}
    lo, hi = min(closes), max(closes)
    if hi <= lo:
        chart = [500 for _ in closes]
    else:
        chart = [int((value - lo) / (hi - lo) * 1000) for value in closes]
    times = [_optional_int(row.get("time", row.get("t"))) or 0 for row in points]
    times = [value for value in times if value > 0]
    return {
        "chart": chart,
        "chart_min": _fmt_price(lo),
        "chart_max": _fmt_price(hi),
        "chart_min_y": _fmt_y_label(lo),
        "chart_mid_y": _fmt_y_label((lo + hi) / 2.0),
        "chart_max_y": _fmt_y_label(hi),
        "chart_t_start": _fmt_chart_time(times[0]) if times else "",
        "chart_t_mid": _fmt_chart_time(times[len(times) // 2]) if times else "",
        "chart_t_end": "now",
    }


def _optional_float(value: Any) -> float:
    return parse_number(value)


def _fmt_price(price: Any) -> str:
    return format_money(price)


def _fmt_y_label(price: Any) -> str:
    value = _optional_float(price)
    if value <= 0:
        return "--"
    return format_money(value)


def _fmt_chart_time(ts: int) -> str:
    if not ts:
        return ""
    from datetime import datetime

    try:
        return datetime.fromtimestamp(ts).strftime("%m/%d %H:%M")
    except Exception:
        return ""


def _as_browse(screen: ScreenPayload, *, mode: str, source_label: str) -> ScreenPayload:
    payload = dict(screen.payload)
    rows = payload.get("tokens")
    if not isinstance(rows, list):
        rows = payload.get("items") if isinstance(payload.get("items"), list) else []
    return ScreenPayload(
        "browse",
        {
            "tokens": rows,
            "chain": payload.get("chain") or "solana",
            "mode": mode,
            "source_label": source_label,
            "cursor": payload.get("cursor", 0),
        },
        screen.context,
    )
