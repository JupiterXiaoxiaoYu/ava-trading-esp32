from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

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


@dataclass(slots=True)
class ValidationResult:
    """Lightweight validation result that keeps framework code dependency-free."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def valid(cls, warnings: list[str] | None = None) -> "ValidationResult":
        return cls(ok=True, warnings=list(warnings or []))

    @classmethod
    def invalid(cls, errors: list[str], warnings: list[str] | None = None) -> "ValidationResult":
        return cls(ok=False, errors=errors, warnings=list(warnings or []))

    def raise_for_errors(self) -> None:
        if not self.ok:
            raise ValueError("; ".join(self.errors))


@dataclass(slots=True)
class ScreenPayloadValidator:
    """Reusable validator bound to a screen set and optional contracts."""

    contracts: list[ScreenContract] = field(default_factory=list)
    screens: list[str] = field(default_factory=list)

    def validate(self, data: Any) -> ValidationResult:
        return validate_screen_payload(data, contracts=self.contracts, screens=self.screens)

    def ensure(self, data: Any) -> JsonDict:
        return ensure_screen_payload(data, contracts=self.contracts, screens=self.screens)


@dataclass(slots=True)
class InputCapability:
    """One hardware input source exposed by a board port."""

    source: str
    kinds: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    semantic_actions: list[str] = field(default_factory=list)
    description: str = ""
    metadata: JsonDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> "InputCapability | None":
        if not isinstance(data, dict):
            return None
        reserved = {"source", "id", "kind", "kinds", "codes", "semantic_actions", "actions", "description"}
        return cls(
            source=str(data.get("source") or data.get("id") or ""),
            kinds=_string_list(data.get("kinds") if "kinds" in data else data.get("kind")),
            codes=_string_list(data.get("codes")),
            semantic_actions=_string_list(data.get("semantic_actions") if "semantic_actions" in data else data.get("actions")),
            description=str(data.get("description") or ""),
            metadata={k: v for k, v in data.items() if k not in reserved},
        )

    def to_dict(self) -> JsonDict:
        data = asdict(self)
        metadata = data.pop("metadata", {})
        data.update(metadata)
        return _drop_empty(data)


@dataclass(slots=True)
class InputMap:
    """Board-level capability map from physical controls to semantic actions."""

    capabilities: list[InputCapability] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    required_actions: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> "InputMap":
        if not isinstance(data, dict):
            return cls()
        raw_capabilities = data.get("capabilities", data.get("inputs", []))
        capabilities: list[InputCapability] = []
        if isinstance(raw_capabilities, dict):
            for source, config in raw_capabilities.items():
                item = dict(config) if isinstance(config, dict) else {}
                item.setdefault("source", source)
                capability = InputCapability.from_dict(item)
                if capability:
                    capabilities.append(capability)
        elif isinstance(raw_capabilities, list):
            for item in raw_capabilities:
                capability = InputCapability.from_dict(item if isinstance(item, dict) else {"source": item})
                if capability:
                    capabilities.append(capability)
        reserved = {"capabilities", "inputs", "aliases", "required_actions", "actions"}
        return cls(
            capabilities=capabilities,
            aliases={str(k): str(v) for k, v in data.get("aliases", {}).items()} if isinstance(data.get("aliases"), dict) else {},
            required_actions=_string_list(data.get("required_actions") if "required_actions" in data else data.get("actions")),
            metadata={k: v for k, v in data.items() if k not in reserved},
        )

    def validate(self) -> ValidationResult:
        errors: list[str] = []
        seen: set[str] = set()
        actions: set[str] = set()
        for index, capability in enumerate(self.capabilities):
            path = f"capabilities[{index}]"
            if not capability.source:
                errors.append(f"{path}.source is required")
            if capability.source in seen:
                errors.append(f"{path}.source duplicates {capability.source!r}")
            seen.add(capability.source)
            actions.update(capability.semantic_actions)
            if not capability.kinds and not capability.codes and not capability.semantic_actions:
                errors.append(f"{path} must declare at least one kind, code, or semantic action")
        for alias, action in self.aliases.items():
            if not alias or not action:
                errors.append("aliases must map non-empty input names to non-empty actions")
            actions.add(action)
        missing = [action for action in self.required_actions if action not in actions]
        errors.extend(f"required action {action!r} is not mapped" for action in missing)
        return ValidationResult.invalid(errors) if errors else ValidationResult.valid()

    def to_dict(self) -> JsonDict:
        data: JsonDict = {
            "capabilities": [item.to_dict() for item in self.capabilities],
            "aliases": self.aliases,
            "required_actions": self.required_actions,
        }
        data.update(self.metadata)
        return _drop_empty(data)


@dataclass(slots=True)
class BoardProfile:
    """Portable hardware contract for board ports and third-party apps."""

    board_id: str
    name: str = ""
    display: JsonDict = field(default_factory=dict)
    input_map: InputMap = field(default_factory=InputMap)
    outputs: list[str] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> "BoardProfile | None":
        if not isinstance(data, dict):
            return None
        reserved = {"board_id", "id", "name", "display", "input_map", "inputs", "outputs"}
        input_data = data.get("input_map") if isinstance(data.get("input_map"), dict) else {"inputs": data.get("inputs", [])}
        return cls(
            board_id=str(data.get("board_id") or data.get("id") or ""),
            name=str(data.get("name") or ""),
            display=dict(data.get("display")) if isinstance(data.get("display"), dict) else {},
            input_map=InputMap.from_dict(input_data),
            outputs=_string_list(data.get("outputs")),
            metadata={k: v for k, v in data.items() if k not in reserved},
        )

    def validate(self) -> ValidationResult:
        errors: list[str] = []
        if not self.board_id:
            errors.append("board_id is required")
        width = _optional_int(self.display.get("width"))
        height = _optional_int(self.display.get("height"))
        if self.display and (width is None or width <= 0 or height is None or height <= 0):
            errors.append("display.width and display.height must be positive integers")
        input_result = self.input_map.validate()
        errors.extend(f"input_map.{error}" for error in input_result.errors)
        return ValidationResult.invalid(errors, input_result.warnings) if errors else ValidationResult.valid(input_result.warnings)

    def to_dict(self) -> JsonDict:
        data: JsonDict = {
            "board_id": self.board_id,
            "name": self.name,
            "display": self.display,
            "input_map": self.input_map.to_dict(),
            "outputs": self.outputs,
        }
        data.update(self.metadata)
        return _drop_empty(data)


@dataclass(slots=True)
class SelectionContext:
    """Generic page selection context sent by devices; not tied to Ava Box tokens."""

    screen: str
    cursor: int | None = None
    selected: JsonDict | None = None
    visible_rows: list[JsonDict] = field(default_factory=list)
    focused_component: str = ""
    page_data: JsonDict = field(default_factory=dict)
    state: JsonDict = field(default_factory=dict)
    app_id: str = ""

    @classmethod
    def from_dict(cls, data: JsonDict | None) -> "SelectionContext | None":
        if not isinstance(data, dict):
            return None
        selected = (
            data.get("selected")
            if isinstance(data.get("selected"), dict)
            else data.get("token")
            if isinstance(data.get("token"), dict)
            else None
        )
        reserved = {"app_id", "screen", "cursor", "selected", "token", "visible_rows", "focused_component", "focus", "page_data", "state"}
        return cls(
            app_id=str(data.get("app_id") or ""),
            screen=str(data.get("screen") or ""),
            cursor=_optional_int(data.get("cursor")),
            selected=dict(selected) if selected else None,
            visible_rows=(
                [dict(item) for item in data.get("visible_rows", []) if isinstance(item, dict)]
                if isinstance(data.get("visible_rows"), list)
                else []
            ),
            focused_component=str(data.get("focused_component") or data.get("focus") or ""),
            page_data=dict(data.get("page_data")) if isinstance(data.get("page_data"), dict) else {},
            state=dict(data.get("state")) if isinstance(data.get("state"), dict) else {k: v for k, v in data.items() if k not in reserved},
        )

    def validate(self) -> ValidationResult:
        errors: list[str] = []
        if not self.screen:
            errors.append("screen is required")
        if self.cursor is not None and self.cursor < 0:
            errors.append("cursor must be a non-negative integer")
        if self.selected is not None and not isinstance(self.selected, dict):
            errors.append("selected must be an object when provided")
        if not isinstance(self.visible_rows, list) or any(not isinstance(item, dict) for item in self.visible_rows):
            errors.append("visible_rows must be a list of objects")
        if self.cursor is not None and self.visible_rows and self.cursor >= len(self.visible_rows):
            errors.append("cursor must point at a visible_rows entry when visible_rows is provided")
        return ValidationResult.invalid(errors) if errors else ValidationResult.valid()

    def to_dict(self) -> JsonDict:
        return _drop_empty(asdict(self))


def validate_selection_context(data: SelectionContext | JsonDict | None) -> ValidationResult:
    raw_errors: list[str] = []
    if isinstance(data, dict):
        if "cursor" in data and data.get("cursor") is not None and _optional_int(data.get("cursor")) is None:
            raw_errors.append("cursor must be an integer when provided")
        visible_rows = data.get("visible_rows")
        if visible_rows is not None and (
            not isinstance(visible_rows, list) or any(not isinstance(item, dict) for item in visible_rows)
        ):
            raw_errors.append("visible_rows must be a list of objects")
        selected = data.get("selected", data.get("token"))
        if selected is not None and not isinstance(selected, dict):
            raw_errors.append("selected must be an object when provided")
    context = data if isinstance(data, SelectionContext) else SelectionContext.from_dict(data)
    if context is None:
        return ValidationResult.invalid(["context must be an object"])
    result = context.validate()
    errors = raw_errors + result.errors
    return ValidationResult.invalid(errors, result.warnings) if errors else result


def validate_input_map(data: InputMap | JsonDict | None) -> ValidationResult:
    input_map = data if isinstance(data, InputMap) else InputMap.from_dict(data)
    return input_map.validate()


def validate_board_profile(data: BoardProfile | JsonDict | None) -> ValidationResult:
    profile = data if isinstance(data, BoardProfile) else BoardProfile.from_dict(data)
    if profile is None:
        return ValidationResult.invalid(["board profile must be an object"])
    return profile.validate()


def validate_screen_payload(
    data: Any,
    *,
    contracts: Iterable[ScreenContract | JsonDict] | Mapping[str, ScreenContract | JsonDict] | None = None,
    screens: Iterable[str] | None = None,
) -> ValidationResult:
    """Validate a display payload without importing jsonschema."""

    payload = _screen_payload_dict(data)
    if payload is None:
        return ValidationResult.invalid(["screen payload must be a ScreenPayload or object"])
    errors: list[str] = []
    warnings: list[str] = []
    if payload.get("type", "display") != "display":
        errors.append("type must be 'display'")
    screen = str(payload.get("screen") or "")
    if not screen:
        errors.append("screen is required")
    screen_data = payload.get("data", payload.get("payload"))
    if not isinstance(screen_data, dict):
        errors.append("data must be an object")
    allowed_screens = set(str(item) for item in screens or [])
    contract_map = _contract_map(contracts)
    allowed_screens.update(contract_map)
    if allowed_screens and screen and screen not in allowed_screens:
        errors.append(f"screen {screen!r} is not declared")
    context = payload.get("context")
    if context is not None:
        context_result = validate_selection_context(context if isinstance(context, dict) else None)
        errors.extend(f"context.{error}" for error in context_result.errors)
    contract = contract_map.get(screen)
    if contract and isinstance(screen_data, dict):
        errors.extend(_validate_schema(screen_data, contract.payload_schema, "data"))
        if isinstance(context, dict):
            errors.extend(_validate_schema(context, contract.context_schema, "context"))
    return ValidationResult.invalid(errors, warnings) if errors else ValidationResult.valid(warnings)


def ensure_screen_payload(data: Any, **kwargs: Any) -> JsonDict:
    result = validate_screen_payload(data, **kwargs)
    result.raise_for_errors()
    payload = _screen_payload_dict(data)
    assert payload is not None
    return payload


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _drop_empty(data: JsonDict) -> JsonDict:
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value != "" else []


def _screen_payload_dict(data: Any) -> JsonDict | None:
    if hasattr(data, "to_dict") and callable(data.to_dict):
        converted = data.to_dict()
        return converted if isinstance(converted, dict) else None
    return data if isinstance(data, dict) else None


def _contract_map(
    contracts: Iterable[ScreenContract | JsonDict] | Mapping[str, ScreenContract | JsonDict] | None,
) -> dict[str, ScreenContract]:
    if contracts is None:
        return {}
    values = contracts.values() if isinstance(contracts, Mapping) else contracts
    mapped: dict[str, ScreenContract] = {}
    for item in values:
        contract = item if isinstance(item, ScreenContract) else ScreenContract.from_dict(item if isinstance(item, dict) else None)
        if contract and contract.screen_id:
            mapped[contract.screen_id] = contract
    return mapped


def _validate_schema(value: Any, schema: JsonDict, path: str) -> list[str]:
    if not schema:
        return []
    errors: list[str] = []
    expected = schema.get("type")
    if expected and not _matches_schema_type(value, expected):
        errors.append(f"{path} must be {_type_label(expected)}")
        return errors
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path} must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path} must be one of {schema['enum']!r}")
    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required if isinstance(required, list) else []:
            if key not in value:
                errors.append(f"{path}.{key} is required")
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, dict):
                errors.extend(_validate_schema(value[key], child_schema, f"{path}.{key}"))
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            errors.extend(f"{path}.{key} is not allowed" for key in extra)
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            errors.extend(_validate_schema(item, schema["items"], f"{path}[{index}]"))
    return errors


def _matches_schema_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_matches_schema_type(value, item) for item in expected)
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(str(expected), True)


def _type_label(expected: Any) -> str:
    return " or ".join(expected) if isinstance(expected, list) else str(expected)
