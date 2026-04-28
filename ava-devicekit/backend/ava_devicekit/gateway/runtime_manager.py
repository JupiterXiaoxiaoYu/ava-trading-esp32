from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ava_devicekit.apps.ava_box_skills import AvaBoxSkillConfig
from ava_devicekit.core.types import AppContext, ScreenPayload
from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.gateway.session import DeviceSession
from ava_devicekit.runtime.settings import RuntimeSettings
from ava_devicekit.storage.json_store import JsonStore

SessionBuilder = Callable[[str], DeviceSession]


@dataclass(slots=True)
class RuntimeEvent:
    ts: float
    device_id: str
    event: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ts": self.ts, "device_id": self.device_id, "event": self.event, "payload": self.payload}


class RuntimeManager:
    """Multi-device session manager for production gateways."""

    def __init__(
        self,
        session_builder: SessionBuilder | None = None,
        *,
        max_events: int = 1000,
        state_store_path: str | Path | None = None,
    ):
        self.session_builder = session_builder or (lambda device_id: create_device_session(mock=True))
        self.max_events = max_events
        self.state_store_path = str(state_store_path) if state_store_path else None
        self.sessions: dict[str, DeviceSession] = {}
        self.events: list[RuntimeEvent] = []
        self._restored_boot_payloads: dict[str, dict[str, Any]] = {}
        self._state_mtimes: dict[str, float] = {}

    @classmethod
    def for_app(
        cls,
        *,
        app_id: str = "ava_box",
        manifest_path: str | Path | None = None,
        adapter: str = "auto",
        mock: bool = False,
        skill_store_path: str | None = None,
        state_store_path: str | Path | None = None,
        skill_config: AvaBoxSkillConfig | None = None,
        adapter_options: dict[str, Any] | None = None,
    ) -> "RuntimeManager":
        def build(device_id: str) -> DeviceSession:
            store = _skill_store_path(skill_store_path, device_id)
            config = skill_config
            if config and store:
                config = AvaBoxSkillConfig(
                    store_path=store,
                    default_buy_sol=config.default_buy_sol,
                    default_slippage_bps=config.default_slippage_bps,
                    execution_mode=config.execution_mode,
                    execution_base_url=config.execution_base_url,
                    execution_api_key_env=config.execution_api_key_env,
                    execution_secret_key_env=config.execution_secret_key_env,
                    proxy_wallet_id_env=config.proxy_wallet_id_env,
                    proxy_default_gas=config.proxy_default_gas,
                    execution_provider_class=config.execution_provider_class,
                    execution_options=dict(config.execution_options or {}),
                )
            return create_device_session(
                app_id=app_id,
                manifest_path=manifest_path,
                adapter=adapter,
                mock=mock,
                skill_store_path=store,
                skill_config=config,
                adapter_options=adapter_options,
            )

        return cls(build, state_store_path=state_store_path)

    def get(self, device_id: str = "default") -> DeviceSession:
        device_id = normalize_device_id(device_id)
        if device_id not in self.sessions:
            session = self.session_builder(device_id)
            restored_payload = self._restore_session_state(device_id, session)
            self.sessions[device_id] = session
            if restored_payload:
                self._restored_boot_payloads[device_id] = restored_payload
            self.record(device_id, "session_created")
            if restored_payload:
                self.record(device_id, "session_restored", {"screen": restored_payload.get("screen")})
        return self.sessions[device_id]

    def boot(self, device_id: str = "default") -> dict[str, Any]:
        device_id = normalize_device_id(device_id)
        session = self.get(device_id)
        external_payload = self._refresh_external_state(device_id, session)
        restored_payload = self._restored_boot_payloads.pop(device_id, None) or external_payload
        payload = session.emit(_screen_from_payload(restored_payload, session.app.context)) if restored_payload else session.boot()
        self._persist_session_state(device_id, session)
        self.record(device_id, "boot", {"screen": payload.get("screen"), "restored": bool(restored_payload)})
        return payload

    def handle(self, device_id: str, message: dict[str, Any]) -> dict[str, Any]:
        device_id = normalize_device_id(device_id)
        session = self.get(device_id)
        self._refresh_external_state(device_id, session)
        payload = session.handle(message)
        self._persist_session_state(device_id, session)
        self.record(device_id, "message", {"message_type": message.get("type"), "screen": payload.get("screen")})
        return payload

    def state(self, device_id: str = "default") -> dict[str, Any]:
        device_id = normalize_device_id(device_id)
        session = self.get(device_id)
        self._refresh_external_state(device_id, session)
        return session.snapshot()

    def list_devices(self) -> list[dict[str, Any]]:
        return [{"device_id": device_id, **session.snapshot()} for device_id, session in sorted(self.sessions.items())]

    def outbox(self, device_id: str = "default") -> dict[str, Any]:
        device_id = normalize_device_id(device_id)
        session = self.get(device_id)
        self._refresh_external_state(device_id, session)
        items = session.outbox
        return {"items": items, "count": len(items), "device_id": normalize_device_id(device_id)}

    def persist(self, device_id: str = "default") -> None:
        device_id = normalize_device_id(device_id)
        self._persist_session_state(device_id, self.get(device_id))

    def record(self, device_id: str, event: str, payload: dict[str, Any] | None = None) -> None:
        self.events.append(RuntimeEvent(time.time(), normalize_device_id(device_id), event, payload or {}))
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events :]

    def event_log(self, *, device_id: str = "", limit: int = 100) -> dict[str, Any]:
        rows = self.events
        if device_id:
            device_id = normalize_device_id(device_id)
            rows = [row for row in rows if row.device_id == device_id]
        rows = rows[-max(1, limit) :]
        return {"items": [row.to_dict() for row in rows], "count": len(rows)}

    def _persist_session_state(self, device_id: str, session: DeviceSession) -> None:
        path = _device_store_path(self.state_store_path, device_id)
        if not path:
            return
        app = session.app
        last_screen = getattr(app, "last_screen", None)
        state = {
            "version": 1,
            "device_id": normalize_device_id(device_id),
            "updated_at": time.time(),
            "snapshot": session.snapshot(),
            "context": app.context.to_dict(),
            "last_screen": _last_screen_to_dict(last_screen),
            "spotlight_return": getattr(app, "spotlight_return", None),
        }
        target = Path(path)
        JsonStore(target).write(state)
        self._state_mtimes[normalize_device_id(device_id)] = _path_mtime(target)

    def _restore_session_state(self, device_id: str, session: DeviceSession) -> dict[str, Any] | None:
        path = _device_store_path(self.state_store_path, device_id)
        if not path:
            return None
        raw = JsonStore(path).read({})
        if not isinstance(raw, dict):
            return None
        self._state_mtimes[normalize_device_id(device_id)] = _path_mtime(Path(path))
        context = _context_from_stored_dict(raw.get("context"))
        if context:
            session.app.context = context
        restored_payload = raw.get("last_screen") if isinstance(raw.get("last_screen"), dict) else None
        if restored_payload and hasattr(session.app, "last_screen"):
            setattr(session.app, "last_screen", _screen_from_payload(restored_payload, session.app.context))
        spotlight_return = raw.get("spotlight_return")
        if hasattr(session.app, "spotlight_return") and (isinstance(spotlight_return, dict) or spotlight_return is None):
            setattr(session.app, "spotlight_return", spotlight_return)
        return restored_payload

    def _refresh_external_state(self, device_id: str, session: DeviceSession) -> dict[str, Any] | None:
        path = _device_store_path(self.state_store_path, device_id)
        if not path:
            return None
        target = Path(path)
        mtime = _path_mtime(target)
        if mtime <= 0 or mtime <= self._state_mtimes.get(normalize_device_id(device_id), 0):
            return None
        return self._restore_session_state(device_id, session)


def normalize_device_id(device_id: str | None) -> str:
    text = str(device_id or "default").strip()
    return text or "default"


def _device_store_path(base: str | Path | None, device_id: str) -> str | None:
    if not base:
        return None
    path = Path(base)
    if path.suffix:
        return str(path.with_name(f"{path.stem}.{normalize_device_id(device_id)}{path.suffix}"))
    return str(path / f"{normalize_device_id(device_id)}.json")


def _skill_store_path(base: str | Path | None, device_id: str) -> str | None:
    if not base:
        return None
    path = Path(base)
    if path.suffix:
        return str(path)
    return str(path / f"{normalize_device_id(device_id)}.json")


def _last_screen_to_dict(screen: Any) -> dict[str, Any] | None:
    if not isinstance(screen, ScreenPayload):
        return None
    return screen.to_dict()


def _screen_from_payload(payload: dict[str, Any], context: AppContext | None = None) -> ScreenPayload:
    return ScreenPayload(str(payload.get("screen") or ""), dict(payload.get("data") or {}), context)


def _context_from_stored_dict(data: Any) -> AppContext | None:
    if not isinstance(data, dict):
        return None
    flattened = dict(data)
    state = flattened.pop("state", None)
    if isinstance(state, dict):
        flattened.update(state)
    return AppContext.from_dict(flattened)


def _path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def runtime_manager_for_settings(
    settings: RuntimeSettings,
    *,
    app_id: str = "ava_box",
    manifest_path: str | Path | None = None,
    adapter: str = "auto",
    mock: bool = False,
    skill_store_path: str | None = None,
) -> RuntimeManager:
    adapter_name = settings.chain_adapter if adapter.strip().lower() in {"", "auto"} and settings.chain_adapter else adapter
    return RuntimeManager.for_app(
        app_id=app_id,
        manifest_path=manifest_path,
        adapter=adapter_name,
        mock=mock,
        skill_store_path=skill_store_path,
        state_store_path=settings.runtime_state_dir,
        adapter_options={**settings.chain_adapter_options, **({"class": settings.chain_adapter_class} if settings.chain_adapter_class else {})},
        skill_config=settings.ava_box_skill_config(store_path=skill_store_path),
    )
