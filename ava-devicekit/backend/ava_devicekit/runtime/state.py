from __future__ import annotations

import time
from typing import Any

from ava_devicekit.runtime.errors import ERROR_RUNTIME_STATE_INVALID, RuntimeErrorInfo

RUNTIME_STATE_VERSION = 1


def migrate_runtime_state(raw: Any) -> tuple[dict[str, Any], list[RuntimeErrorInfo]]:
    """Normalize persisted runtime state into the current schema.

    Migration is intentionally conservative: unknown fields are preserved, while
    framework-owned keys get valid defaults so old state files do not crash a
    device session on boot.
    """

    errors: list[RuntimeErrorInfo] = []
    if not isinstance(raw, dict):
        return _empty_state(), [
            RuntimeErrorInfo(
                code=ERROR_RUNTIME_STATE_INVALID,
                message="runtime state must be a JSON object",
                component="runtime.state",
            )
        ]

    state = dict(raw)
    version = int(state.get("version") or 0)
    if version > RUNTIME_STATE_VERSION:
        errors.append(
            RuntimeErrorInfo(
                code=ERROR_RUNTIME_STATE_INVALID,
                message=f"runtime state version {version} is newer than supported {RUNTIME_STATE_VERSION}",
                component="runtime.state",
                details={"version": version, "supported": RUNTIME_STATE_VERSION},
            )
        )
    if not isinstance(state.get("snapshot"), dict):
        state["snapshot"] = {}
    if not isinstance(state.get("context"), dict):
        state["context"] = {}
    if not isinstance(state.get("last_screen"), dict):
        state["last_screen"] = None
    if "updated_at" not in state:
        state["updated_at"] = time.time()
    state["version"] = RUNTIME_STATE_VERSION
    return state, errors


def _empty_state() -> dict[str, Any]:
    return {"version": RUNTIME_STATE_VERSION, "updated_at": time.time(), "snapshot": {}, "context": {}, "last_screen": None}


__all__ = ["RUNTIME_STATE_VERSION", "migrate_runtime_state"]
