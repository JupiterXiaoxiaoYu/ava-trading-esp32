from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from ava_devicekit.streams.base import MarketStreamEvent, StreamSubscription

DATA_WSS_URL = "wss://wss.ave-api.xyz"


@dataclass(slots=True)
class AveDataWSSConfig:
    url: str = DATA_WSS_URL
    api_key_env: str = "AVE_API_KEY"


@dataclass
class AveDataWSSAdapter:
    """Ava Box reference live market stream adapter for AVE data WSS.

    This is app/reference infrastructure, not a framework core dependency. Tests
    validate frame construction and parser behavior without opening the socket.
    """

    config: AveDataWSSConfig = field(default_factory=AveDataWSSConfig)
    subscriptions: list[StreamSubscription] = field(default_factory=list)
    cached_events: list[MarketStreamEvent] = field(default_factory=list)
    name: str = "ave-data-wss"

    def subscribe(self, subscription: StreamSubscription) -> None:
        self.subscriptions.append(subscription)

    def snapshot(self) -> list[MarketStreamEvent]:
        events = list(self.cached_events)
        self.cached_events.clear()
        return events

    def headers(self) -> dict[str, str]:
        api_key = os.environ.get(self.config.api_key_env, "")
        return {"X-API-KEY": api_key} if api_key else {}

    def subscribe_frame(self, subscription: StreamSubscription, *, request_id: int = 1) -> str:
        if subscription.channel == "kline":
            params: list[Any] = ["kline", *subscription.token_ids, subscription.interval]
        else:
            params = [subscription.channel, subscription.token_ids]
        return json.dumps({"jsonrpc": "2.0", "method": "subscribe", "params": params, "id": request_id}, separators=(",", ":"))

    def parse_message(self, message: str | dict[str, Any]) -> list[MarketStreamEvent]:
        data = json.loads(message) if isinstance(message, str) else message
        return parse_ave_wss_message(data)

    def handle_message(self, message: str | dict[str, Any]) -> list[MarketStreamEvent]:
        events = self.parse_message(message)
        self.cached_events.extend(events)
        self.cached_events = self.cached_events[-500:]
        return events

    async def run_forever(
        self,
        on_events: Callable[[list[MarketStreamEvent]], Awaitable[None] | None],
        *,
        reconnect_delay_sec: float = 3.0,
    ) -> None:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - optional dependency boundary
            raise RuntimeError("Install websockets or ava-devicekit[websocket] to use AVE live WSS") from exc

        request_id = 1
        while True:
            try:
                async with websockets.connect(self.config.url, additional_headers=self.headers() or None) as ws:
                    for sub in self.subscriptions:
                        await ws.send(self.subscribe_frame(sub, request_id=request_id))
                        request_id += 1
                    async for raw in ws:
                        events = self.handle_message(raw)
                        if events:
                            result = on_events(events)
                            if hasattr(result, "__await__"):
                                await result  # type: ignore[misc]
            except Exception:
                await _sleep(reconnect_delay_sec)


def parse_ave_wss_message(data: dict[str, Any]) -> list[MarketStreamEvent]:
    payload = data.get("result", data.get("params", data)) if isinstance(data, dict) else {}
    if isinstance(payload, dict) and "result" in payload and isinstance(payload["result"], dict):
        payload = payload["result"]
    events: list[MarketStreamEvent] = []
    if isinstance(payload, dict):
        prices = payload.get("prices") or payload.get("price") or []
        if isinstance(prices, dict):
            prices = [prices]
        for row in prices if isinstance(prices, list) else []:
            if not isinstance(row, dict):
                continue
            token_id = str(row.get("token_id") or row.get("id") or row.get("addr") or row.get("address") or "")
            if token_id:
                events.append(MarketStreamEvent("price", token_id, dict(row)))
        klines = payload.get("klines") or payload.get("kline") or []
        if isinstance(klines, dict):
            klines = [klines]
        for row in klines if isinstance(klines, list) else []:
            if not isinstance(row, dict):
                continue
            token_id = str(row.get("token_id") or row.get("pair") or row.get("id") or "")
            if token_id:
                events.append(MarketStreamEvent("kline", token_id, dict(row)))
    if not events and isinstance(data, dict) and str(data.get("type") or data.get("channel")) in {"price", "kline"}:
        token_id = str(data.get("token_id") or data.get("id") or data.get("addr") or "")
        if token_id:
            events.append(MarketStreamEvent(str(data.get("type") or data.get("channel")), token_id, dict(data)))
    return events


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(max(0.1, seconds))
