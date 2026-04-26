from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class HardwareAppManifest:
    app_id: str
    name: str
    chain: str
    device: dict[str, Any]
    screens: list[str]
    actions: list[str]
    adapters: dict[str, Any]
    safety: dict[str, Any]
    models: dict[str, Any]
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HardwareAppManifest":
        missing = [key for key in ("app_id", "name", "chain", "device", "screens", "actions", "safety") if key not in data]
        if missing:
            raise ValueError(f"manifest missing required keys: {', '.join(missing)}")
        return cls(
            app_id=str(data["app_id"]),
            name=str(data["name"]),
            chain=str(data["chain"]),
            device=dict(data["device"]),
            screens=list(data["screens"]),
            actions=list(data["actions"]),
            adapters=dict(data.get("adapters") or {}),
            safety=dict(data["safety"]),
            models=dict(data.get("models") or {}),
            description=str(data.get("description") or ""),
        )

    @classmethod
    def load(cls, path: str | Path) -> "HardwareAppManifest":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "name": self.name,
            "description": self.description,
            "chain": self.chain,
            "device": self.device,
            "screens": self.screens,
            "actions": self.actions,
            "adapters": self.adapters,
            "models": self.models,
            "safety": self.safety,
        }
