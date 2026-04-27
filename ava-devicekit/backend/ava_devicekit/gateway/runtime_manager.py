from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ava_devicekit.apps.ava_box_skills import AvaBoxSkillConfig
from ava_devicekit.gateway.factory import create_device_session
from ava_devicekit.gateway.session import DeviceSession

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

    def __init__(self, session_builder: SessionBuilder | None = None, *, max_events: int = 1000):
        self.session_builder = session_builder or (lambda device_id: create_device_session(mock=True))
        self.max_events = max_events
        self.sessions: dict[str, DeviceSession] = {}
        self.events: list[RuntimeEvent] = []

    @classmethod
    def for_app(
        cls,
        *,
        app_id: str = "ava_box",
        manifest_path: str | Path | None = None,
        adapter: str = "auto",
        mock: bool = False,
        skill_store_path: str | None = None,
        skill_config: AvaBoxSkillConfig | None = None,
    ) -> "RuntimeManager":
        def build(device_id: str) -> DeviceSession:
            store = _device_store_path(skill_store_path, device_id)
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
                )
            return create_device_session(
                app_id=app_id,
                manifest_path=manifest_path,
                adapter=adapter,
                mock=mock,
                skill_store_path=store,
                skill_config=config,
            )

        return cls(build)

    def get(self, device_id: str = "default") -> DeviceSession:
        device_id = normalize_device_id(device_id)
        if device_id not in self.sessions:
            self.sessions[device_id] = self.session_builder(device_id)
            self.record(device_id, "session_created")
        return self.sessions[device_id]

    def boot(self, device_id: str = "default") -> dict[str, Any]:
        payload = self.get(device_id).boot()
        self.record(device_id, "boot", {"screen": payload.get("screen")})
        return payload

    def handle(self, device_id: str, message: dict[str, Any]) -> dict[str, Any]:
        payload = self.get(device_id).handle(message)
        self.record(device_id, "message", {"message_type": message.get("type"), "screen": payload.get("screen")})
        return payload

    def state(self, device_id: str = "default") -> dict[str, Any]:
        return self.get(device_id).snapshot()

    def list_devices(self) -> list[dict[str, Any]]:
        return [{"device_id": device_id, **session.snapshot()} for device_id, session in sorted(self.sessions.items())]

    def outbox(self, device_id: str = "default") -> dict[str, Any]:
        items = self.get(device_id).outbox
        return {"items": items, "count": len(items), "device_id": normalize_device_id(device_id)}

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


def normalize_device_id(device_id: str | None) -> str:
    text = str(device_id or "default").strip()
    return text or "default"


def _device_store_path(base: str | None, device_id: str) -> str | None:
    if not base:
        return None
    path = Path(base)
    if path.suffix:
        return str(path.with_name(f"{path.stem}.{normalize_device_id(device_id)}{path.suffix}"))
    return str(path / f"{normalize_device_id(device_id)}.json")
