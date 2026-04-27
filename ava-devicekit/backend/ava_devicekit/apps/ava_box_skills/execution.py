from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class TradeExecutionProvider(Protocol):
    name: str

    def execute(self, summary: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


@dataclass(slots=True)
class AveSolanaTradeConfig:
    base_url: str = "https://bot-api.ave.ai"
    api_key_env: str = "AVE_API_KEY"
    timeout_sec: int = 20


class AveSolanaTradeProvider:
    """Ava Box app-level provider for AVE Solana transaction construction.

    It creates transaction payloads for an external wallet/signing flow. The
    ESP32 remains a physical confirmation surface and does not custody user
    wallet keys.
    """

    name = "ave-solana-trade"

    def __init__(self, config: AveSolanaTradeConfig | None = None):
        self.config = config or AveSolanaTradeConfig()

    def execute(self, summary: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        payload = build_create_solana_tx_payload(summary, params)
        response = self.create_solana_tx(payload)
        return {"status": "transaction_created", "provider": self.name, "request": payload, "response": response}

    def create_solana_tx(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/thirdParty/chainWallet/createSolanaTx", payload)

    def send_signed_solana_tx(self, request_id: str, signed_tx: str) -> dict[str, Any]:
        return self._post("/v1/thirdParty/chainWallet/sendSignedSolanaTx", {"request_id": request_id, "signed_tx": signed_tx})

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        api_key = os.environ.get(self.config.api_key_env, "")
        if not api_key:
            raise RuntimeError(f"missing API key env: {self.config.api_key_env}")
        req = urllib.request.Request(
            self.config.base_url.rstrip("/") + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-API-KEY": api_key, "AVE-ACCESS-KEY": api_key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))


def build_create_solana_tx_payload(summary: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    action = str(summary.get("action") or params.get("action") or "trade.market_draft")
    side = "sell" if "sell" in action else "buy"
    tx_type = "limit" if "limit" in action else "market"
    return {
        "chain": "solana",
        "side": side,
        "type": tx_type,
        "token_id": str(summary.get("token_id") or params.get("token_id") or ""),
        "symbol": str(summary.get("symbol") or params.get("symbol") or ""),
        "amount_native": str(params.get("amount_sol") or params.get("amount_native") or ""),
        "limit_price": str(summary.get("limit_price") or params.get("limit_price") or ""),
        "slippage_bps": int(params.get("slippage_bps") or params.get("slippage") or 100),
        "client_request_id": str(params.get("request_id") or ""),
        "wallet": str(params.get("wallet") or params.get("owner") or ""),
    }
