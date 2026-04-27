from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

JsonDict = dict[str, Any]


@dataclass(slots=True)
class Selection:
    token_id: str = ""
    addr: str = ""
    chain: str = "solana"
    symbol: str = ""
    cursor: int | None = None
    source: str = ""

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> "Selection | None":
        if not isinstance(data, dict):
            return None
        return cls(
            token_id=str(data.get("token_id") or ""),
            addr=str(data.get("addr") or ""),
            chain=str(data.get("chain") or "solana"),
            symbol=str(data.get("symbol") or ""),
            cursor=_optional_int(data.get("cursor")),
            source=str(data.get("source") or ""),
        )

    def to_dict(self) -> JsonDict:
        return _drop_empty(asdict(self))


@dataclass(slots=True)
class AppContext:
    app_id: str
    chain: str = "solana"
    screen: str = ""
    cursor: int | None = None
    selected: Selection | None = None
    visible_rows: list[JsonDict] = field(default_factory=list)
    state: JsonDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: JsonDict | None, *, default_app_id: str = "ava_box", default_chain: str = "solana") -> "AppContext | None":
        if not isinstance(data, dict):
            return None
        return cls(
            app_id=str(data.get("app_id") or default_app_id),
            chain=str(data.get("chain") or default_chain),
            screen=str(data.get("screen") or ""),
            cursor=_optional_int(data.get("cursor")),
            selected=Selection.from_dict(data.get("selected")),
            visible_rows=data.get("visible_rows") if isinstance(data.get("visible_rows"), list) else [],
            state={k: v for k, v in data.items() if k not in {"app_id", "chain", "screen", "cursor", "selected", "visible_rows"}},
        )

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        if self.selected:
            data["selected"] = self.selected.to_dict()
        return _drop_empty(data)


@dataclass(slots=True)
class DeviceMessage:
    type: Literal["key_action", "listen_detect", "screen_context", "confirm", "cancel", "signed_tx", "heartbeat"]
    app_id: str = "ava_box"
    action: str = ""
    text: str = ""
    payload: JsonDict = field(default_factory=dict)
    context: AppContext | None = None

    @classmethod
    def from_dict(cls, data: JsonDict) -> "DeviceMessage":
        msg_type = str(data.get("type") or "heartbeat")
        if msg_type not in {"key_action", "listen_detect", "screen_context", "confirm", "cancel", "signed_tx", "heartbeat"}:
            msg_type = "heartbeat"
        app_id = str(data.get("app_id") or data.get("app") or "ava_box")
        payload = dict(data.get("payload")) if isinstance(data.get("payload"), dict) else {}
        payload.update({k: v for k, v in data.items() if k not in {"type", "app_id", "app", "action", "text", "context", "payload"}})
        return cls(
            type=msg_type,  # type: ignore[arg-type]
            app_id=app_id,
            action=str(data.get("action") or ""),
            text=str(data.get("text") or ""),
            payload=payload,
            context=AppContext.from_dict(data.get("context"), default_app_id=app_id),
        )

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        if self.context:
            data["context"] = self.context.to_dict()
        return _drop_empty(data)


@dataclass(slots=True)
class ScreenPayload:
    screen: str
    payload: JsonDict
    context: AppContext | None = None

    def to_dict(self) -> JsonDict:
        data = {"type": "display", "screen": self.screen, "data": self.payload}
        if self.context:
            data["context"] = self.context.to_dict()
        return data


@dataclass(slots=True)
class ActionDraft:
    action: str
    chain: str
    summary: JsonDict
    screen: ScreenPayload
    risk: JsonDict = field(default_factory=lambda: {"level": "info", "reason": ""})
    requires_confirmation: bool = True
    request_id: str = ""

    def to_dict(self) -> JsonDict:
        return {
            "action": self.action,
            "chain": self.chain,
            "summary": self.summary,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
            "request_id": self.request_id,
            "screen": self.screen.to_dict(),
        }


@dataclass(slots=True)
class ActionResult:
    ok: bool
    message: str
    screen: ScreenPayload | None = None
    data: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        data = {"ok": self.ok, "message": self.message, "data": self.data}
        if self.screen:
            data["screen"] = self.screen.to_dict()
        return data


def _drop_empty(data: JsonDict) -> JsonDict:
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
