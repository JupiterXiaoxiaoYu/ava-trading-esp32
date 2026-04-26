"""Small backend boundary for Ava DeviceKit hardware app contracts.

This module is intentionally independent from the larger assistant runtime. It
normalizes app/action payloads that can be consumed by ESP32 devices, the desktop
simulator, and reference apps such as Ava Box.
"""
from __future__ import annotations

import time
from typing import Any

DEFAULT_APP_ID = "ava_box_solana"
DEFAULT_CHAIN = "solana"
DEFAULT_CONFIRM_BUTTON = "A"
DEFAULT_CANCEL_BUTTON = "B"


def normalize_chain(value: Any, default: str = DEFAULT_CHAIN, *, solana_only: bool = True) -> str:
    """Normalize a chain label for hardware app payloads."""
    if solana_only:
        return DEFAULT_CHAIN
    chain = str(value or "").strip().lower()
    return chain or default


def build_screen_context(
    state: dict | None,
    *,
    app_id: str = DEFAULT_APP_ID,
    chain: str = DEFAULT_CHAIN,
) -> dict:
    """Build a compact screen/cursor context for model routing and logs."""
    state = state if isinstance(state, dict) else {}
    selected = state.get("current_token") if isinstance(state.get("current_token"), dict) else None
    return {
        "app_id": app_id,
        "chain": normalize_chain(chain),
        "screen": str(state.get("screen") or ""),
        "cursor": state.get("feed_cursor"),
        "selected": selected,
        "mode": str(state.get("feed_mode") or state.get("feed_source") or ""),
    }


def build_action_payload(
    *,
    action: str,
    chain: str = DEFAULT_CHAIN,
    summary: dict | None = None,
    app_id: str = DEFAULT_APP_ID,
    request_id: str = "",
    risk: dict | None = None,
    confirm_required: bool = True,
    timeout_sec: int = 0,
    screen: str = "",
    screen_payload: dict | None = None,
) -> dict:
    """Create a DeviceKit action envelope around an app-specific screen payload."""
    payload = {
        "app_id": app_id,
        "action": action,
        "chain": normalize_chain(chain),
        "request_id": request_id or f"dk_{int(time.time() * 1000)}",
        "summary": dict(summary or {}),
        "risk": dict(risk or {"level": "info", "reason": ""}),
        "confirm": {
            "required": bool(confirm_required),
            "confirm_button": DEFAULT_CONFIRM_BUTTON,
            "cancel_button": DEFAULT_CANCEL_BUTTON,
            "timeout_sec": int(timeout_sec or 0),
        },
    }
    if screen:
        payload["screen"] = {
            "name": screen,
            "payload": dict(screen_payload or {}),
        }
    return payload


def build_trade_confirmation_payload(
    *,
    trade_id: str,
    action: str,
    symbol: str,
    chain: str = DEFAULT_CHAIN,
    amount_native: str = "",
    amount_usd: str = "",
    timeout_sec: int = 0,
    identity: dict | None = None,
    mode_label: str = "",
    extra: dict | None = None,
) -> dict:
    """Build the stable screen payload used by Ava Box confirmation screens."""
    payload = dict(identity or {})
    payload.update({
        "trade_id": trade_id,
        "action": action,
        "symbol": symbol or "TOKEN",
        "chain": normalize_chain(chain),
        "amount_native": amount_native or "",
        "amount_usd": amount_usd or "",
        "timeout_sec": int(timeout_sec or 0),
    })
    if mode_label:
        payload["mode_label"] = mode_label
    if extra:
        payload.update({k: v for k, v in extra.items() if v is not None})
    return payload
