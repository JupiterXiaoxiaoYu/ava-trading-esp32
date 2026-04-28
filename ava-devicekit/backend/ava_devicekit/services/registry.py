from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

SERVICE_KIND_CATALOG: dict[str, dict[str, Any]] = {
    "api": {"description": "Generic backend API service.", "default_capabilities": ["api.invoke"]},
    "custom": {"description": "Custom app-specific backend service.", "default_capabilities": ["custom.invoke"]},
    "custodial_wallet": {"description": "Proxy/custodial wallet service for balances, trades, and order status.", "default_capabilities": ["wallet.balance", "trade.market", "trade.limit", "order.status"]},
    "market_data_api": {"description": "Market-data service for feeds, search, token detail, prices, and klines.", "default_capabilities": ["token.feed", "token.search", "token.detail", "price.stream"]},
    "payment_api": {"description": "Payment provider service for invoices, payment requests, and settlement status.", "default_capabilities": ["payment.request", "payment.status"]},
    "order_router": {"description": "Order routing service for market/limit orders and status refresh.", "default_capabilities": ["order.create", "order.cancel", "order.status"]},
    "solana_rpc": {"description": "Solana RPC or RPC aggregator endpoint.", "default_capabilities": ["rpc.get_latest_blockhash", "rpc.send_transaction", "rpc.account_subscribe"]},
    "solana_pay": {"description": "Solana Pay transaction request, QR, wallet handoff, and confirmation service.", "default_capabilities": ["solana_pay.request", "solana_pay.qr", "payment.status"]},
    "oracle": {"description": "Oracle service for verifying device telemetry, proof batches, and eligibility.", "default_capabilities": ["oracle.verify", "oracle.sign_eligibility"]},
    "reward_distributor": {"description": "Reward distributor service for DePIN reward claim drafts and status.", "default_capabilities": ["reward.check", "reward.claim_draft", "reward.status"]},
    "data_anchor": {"description": "Data anchoring service for batched telemetry, proofs, blobs, and verification.", "default_capabilities": ["data_anchor.upload", "data_anchor.fetch", "data_anchor.verify"]},
    "gasless_tx": {"description": "Gasless transaction or fee-payer service.", "default_capabilities": ["tx.sponsor", "tx.submit", "tx.status"]},
    "device_ingest": {"description": "Realtime device ingest service for WSS telemetry, HTTP fallback, and fanout.", "default_capabilities": ["device_ingest.wss", "device_ingest.http_fallback", "device_ingest.heartbeat"]},
}

SERVICE_KIND_ALIASES = {
    "market_data": "market_data_api",
    "wallet": "custodial_wallet",
    "proxy_wallet": "custodial_wallet",
    "payment": "payment_api",
    "orders": "order_router",
    "rpc": "solana_rpc",
    "solana-pay": "solana_pay",
    "reward": "reward_distributor",
    "ingest": "device_ingest",
}


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
        kind = normalize_service_kind(str(data.get("kind") or data.get("type") or "api").strip())
        return cls(
            service_id=str(data.get("id") or data.get("service_id") or data.get("name") or "").strip(),
            kind=kind,
            base_url=str(data.get("base_url") or "").strip(),
            api_key_env=str(data.get("api_key_env") or "").strip(),
            secret_key_env=str(data.get("secret_key_env") or "").strip(),
            wallet_id_env=str(data.get("wallet_id_env") or data.get("proxy_wallet_id_env") or "").strip(),
            capabilities=[str(item) for item in data.get("capabilities", [])] if isinstance(data.get("capabilities"), list) else [],
            options=data.get("options") if isinstance(data.get("options"), dict) else {},
        )

    def health(self) -> dict[str, Any]:
        spec = SERVICE_KIND_CATALOG.get(self.kind)
        missing = [name for name in (self.api_key_env, self.secret_key_env, self.wallet_id_env) if name and not os.environ.get(name)]
        status = "missing_env" if missing else "configured"
        if not self.service_id:
            status = "invalid"
            missing.append("service_id")
        if not spec:
            status = "invalid"
            missing.append("known_kind")
        capabilities = list(self.capabilities or ((spec or {}).get("default_capabilities") or []))
        return {
            "id": self.service_id,
            "kind": self.kind,
            "description": str((spec or {}).get("description") or ""),
            "base_url": self.base_url,
            "capabilities": capabilities,
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
    return {"ok": all(item["configured"] for item in items), "items": items, "count": len(items), "kind_catalog": service_kind_catalog()}


def find_developer_service(services: list[dict[str, Any]] | list[DeveloperService] | None, service_id: str) -> DeveloperService | None:
    needle = str(service_id or "").strip()
    for item in services or []:
        service = item if isinstance(item, DeveloperService) else DeveloperService.from_dict(item)
        if service.service_id == needle:
            return service
    return None


def normalize_service_kind(kind: str) -> str:
    normalized = str(kind or "api").strip().lower().replace("-", "_")
    return SERVICE_KIND_ALIASES.get(normalized, normalized)


def service_kind_catalog() -> list[dict[str, Any]]:
    return [
        {"kind": kind, "description": str(spec.get("description") or ""), "default_capabilities": list(spec.get("default_capabilities") or [])}
        for kind, spec in sorted(SERVICE_KIND_CATALOG.items())
    ]


def _sanitize_options(options: dict[str, Any]) -> dict[str, Any]:
    blocked = ("key", "secret", "token", "password")
    return {k: ("<redacted>" if any(word in k.lower() for word in blocked) else v) for k, v in options.items()}
