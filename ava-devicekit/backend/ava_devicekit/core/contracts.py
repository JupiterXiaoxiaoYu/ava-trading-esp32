from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ava_devicekit.core.types import Selection

JsonDict = dict[str, Any]


@dataclass(slots=True)
class ContextSnapshot:
    """Device-provided UI context for deterministic routing and AI grounding."""

    screen: str
    cursor: int | None = None
    selected: Selection | None = None
    visible_rows: list[JsonDict] = field(default_factory=list)
    focused_component: str = ""
    page_data: JsonDict = field(default_factory=dict)
    state: JsonDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> "ContextSnapshot | None":
        if not isinstance(data, dict):
            return None
        selected = Selection.from_dict(data.get("selected") if isinstance(data.get("selected"), dict) else data.get("token"))
        if selected and selected.cursor is None:
            selected.cursor = _optional_int(data.get("cursor"))
        return cls(
            screen=str(data.get("screen") or ""),
            cursor=_optional_int(data.get("cursor")),
            selected=selected,
            visible_rows=data.get("visible_rows") if isinstance(data.get("visible_rows"), list) else [],
            focused_component=str(data.get("focused_component") or data.get("focus") or ""),
            page_data=data.get("page_data") if isinstance(data.get("page_data"), dict) else {},
            state=data.get("state") if isinstance(data.get("state"), dict) else {
                k: v
                for k, v in data.items()
                if k not in {"screen", "cursor", "selected", "token", "visible_rows", "focused_component", "focus", "page_data"}
            },
        )

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        if self.selected:
            data["selected"] = self.selected.to_dict()
        return _drop_empty(data)


@dataclass(slots=True)
class InputEvent:
    """Hardware-agnostic input event emitted by a board port or UI runtime."""

    source: str
    kind: str
    code: str = ""
    value: int | float | str | None = None
    x: int | None = None
    y: int | None = None
    semantic_action: str = ""
    context: ContextSnapshot | None = None
    metadata: JsonDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> "InputEvent | None":
        if not isinstance(data, dict):
            return None
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
        context_data = data.get("context") if isinstance(data.get("context"), dict) else payload.get("context") if isinstance(payload.get("context"), dict) else None
        reserved = {"type", "payload", "context", "source", "kind", "code", "value", "x", "y", "semantic_action", "action"}
        return cls(
            source=str(payload.get("source") or ""),
            kind=str(payload.get("kind") or payload.get("event") or ""),
            code=str(payload.get("code") or payload.get("key") or ""),
            value=payload.get("value"),
            x=_optional_int(payload.get("x")),
            y=_optional_int(payload.get("y")),
            semantic_action=str(payload.get("semantic_action") or payload.get("action") or ""),
            context=ContextSnapshot.from_dict(context_data),
            metadata={k: v for k, v in payload.items() if k not in reserved},
        )

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        if self.context:
            data["context"] = self.context.to_dict()
        return _drop_empty(data)


@dataclass(slots=True)
class ScreenContract:
    """Developer-declared page contract used by apps, devices, and tests."""

    screen_id: str
    payload_schema: JsonDict = field(default_factory=dict)
    context_schema: JsonDict = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> "ScreenContract | None":
        if not isinstance(data, dict):
            return None
        return cls(
            screen_id=str(data.get("screen_id") or data.get("id") or data.get("screen") or ""),
            payload_schema=data.get("payload_schema") if isinstance(data.get("payload_schema"), dict) else {},
            context_schema=data.get("context_schema") if isinstance(data.get("context_schema"), dict) else {},
            actions=[str(item) for item in data.get("actions", [])] if isinstance(data.get("actions"), list) else [],
            description=str(data.get("description") or ""),
        )

    def to_dict(self) -> JsonDict:
        return _drop_empty(asdict(self))


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _drop_empty(data: JsonDict) -> JsonDict:
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}
