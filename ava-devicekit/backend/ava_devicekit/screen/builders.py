from __future__ import annotations

from ava_devicekit.core.types import AppContext, ScreenPayload


def feed(tokens: list[dict], *, chain: str = "solana", source_label: str = "TRENDING", mode: str = "standard", context: AppContext | None = None) -> ScreenPayload:
    return ScreenPayload("feed", {"tokens": tokens, "chain": chain, "source_label": source_label, "mode": mode}, context)


def spotlight(payload: dict, *, context: AppContext | None = None) -> ScreenPayload:
    return ScreenPayload("spotlight", payload, context)


def portfolio(
    rows: list[dict],
    *,
    chain: str = "solana",
    total_usd: str = "$0",
    pnl: str = "$0",
    pnl_pct: str = "0.00%",
    mode_label: str = "Portfolio",
    chain_label: str = "SOL",
    pnl_reason: str = "Paper positions",
    context: AppContext | None = None,
) -> ScreenPayload:
    return ScreenPayload(
        "portfolio",
        {
            "holdings": rows,
            "chain": chain,
            "total_usd": total_usd,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "mode_label": mode_label,
            "chain_label": chain_label,
            "pnl_reason": pnl_reason,
        },
        context,
    )


def confirm(payload: dict, *, context: AppContext | None = None, limit: bool = False) -> ScreenPayload:
    return ScreenPayload("limit_confirm" if limit else "confirm", payload, context)


def result(title: str, body: str, *, ok: bool = True, context: AppContext | None = None) -> ScreenPayload:
    return ScreenPayload("result", {"ok": ok, "title": title, "body": body}, context)


def notify(title: str, body: str, *, level: str = "info", context: AppContext | None = None) -> ScreenPayload:
    return ScreenPayload("notify", {"level": level, "title": title, "body": body}, context)
