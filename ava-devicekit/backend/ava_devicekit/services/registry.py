from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DeveloperService:
    """Server-side service made available to apps without exposing secrets to devices."""

    service_id: str
    kind: str
    base_url: str = ""
    api_key_env: str = ""
    secret_key_env: str = ""
    wallet_id_env: str = ""
    capabilities: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeveloperService":
        return cls(
            service_id=str(data.get("id") or data.get("service_id") or data.get("name") or "").strip(),
            kind=str(data.get("kind") or data.get("type") or "api").strip(),
            base_url=str(data.get("base_url") or "").strip(),
            api_key_env=str(data.get("api_key_env") or "").strip(),
            secret_key_env=str(data.get("secret_key_env") or "").strip(),
            wallet_id_env=str(data.get("wallet_id_env") or data.get("proxy_wallet_id_env") or "").strip(),
            capabilities=[str(item) for item in data.get("capabilities", [])] if isinstance(data.get("capabilities"), list) else [],
            options=data.get("options") if isinstance(data.get("options"), dict) else {},
        )

    def health(self) -> dict[str, Any]:
        missing = [name for name in (self.api_key_env, self.secret_key_env, self.wallet_id_env) if name and not os.environ.get(name)]
        status = "missing_env" if missing else "configured"
        if not self.service_id:
            status = "invalid"
            missing.append("service_id")
        return {
            "id": self.service_id,
            "kind": self.kind,
            "base_url": self.base_url,
            "capabilities": list(self.capabilities),
            "status": status,
            "configured": status == "configured",
            "env": {
                "api_key_env": self.api_key_env,
                "secret_key_env": self.secret_key_env,
                "wallet_id_env": self.wallet_id_env,
                "missing": missing,
            },
            "options": _sanitize_options(self.options),
        }


def developer_service_report(services: list[dict[str, Any]] | list[DeveloperService] | None) -> dict[str, Any]:
    parsed = [item if isinstance(item, DeveloperService) else DeveloperService.from_dict(item) for item in (services or [])]
    items = [item.health() for item in parsed]
    return {"ok": all(item["configured"] for item in items), "items": items, "count": len(items)}


def find_developer_service(services: list[dict[str, Any]] | list[DeveloperService] | None, service_id: str) -> DeveloperService | None:
    needle = str(service_id or "").strip()
    for item in services or []:
        service = item if isinstance(item, DeveloperService) else DeveloperService.from_dict(item)
        if service.service_id == needle:
            return service
    return None


def _sanitize_options(options: dict[str, Any]) -> dict[str, Any]:
    blocked = ("key", "secret", "token", "password")
    return {k: ("<redacted>" if any(word in k.lower() for word in blocked) else v) for k, v in options.items()}
