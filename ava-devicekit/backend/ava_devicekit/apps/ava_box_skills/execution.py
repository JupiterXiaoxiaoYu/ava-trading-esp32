from __future__ import annotations

import json
import os
import urllib.request
import base64
import datetime
import hashlib
import hmac
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
    secret_key_env: str = "AVE_SECRET_KEY"
    proxy_wallet_id_env: str = "AVE_PROXY_WALLET_ID"
    proxy_default_gas: str = "1000000"
    timeout_sec: int = 20


class AveSolanaTradeProvider:
    """Ava Box app-level provider for AVE self-custody transaction construction.

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


class AveProxyWalletTradeProvider:
    """Ava Box app-level provider for AVE server-managed proxy/custodial wallets."""

    name = "ave-proxy-wallet-trade"

    def __init__(self, config: AveSolanaTradeConfig | None = None):
        self.config = config or AveSolanaTradeConfig()

    def execute(self, summary: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        payload = build_proxy_wallet_order_payload(summary, params, self.config)
        is_limit = payload.pop("_is_limit")
        path = "/v1/thirdParty/tx/sendLimitOrder" if is_limit else "/v1/thirdParty/tx/sendSwapOrder"
        response = self._post(path, payload)
        return {"status": "order_submitted", "provider": self.name, "request": payload, "response": response}

    def list_wallets(self, assets_ids: str = "") -> dict[str, Any]:
        params = {"assetsIds": assets_ids} if assets_ids else None
        return self._get("/v1/thirdParty/user/getUserByAssetsId", params)

    def get_swap_orders(self, chain: str, ids: str) -> dict[str, Any]:
        return self._get("/v1/thirdParty/tx/getSwapOrder", {"chain": chain, "ids": ids})

    def get_limit_orders(self, chain: str, assets_id: str, *, status: str = "", token: str = "", page_size: int = 20, page_no: int = 0) -> dict[str, Any]:
        params: dict[str, Any] = {"chain": chain, "assetsId": assets_id, "pageSize": page_size, "pageNo": page_no}
        if status:
            params["status"] = status
        if token:
            params["token"] = token
        return self._get("/v1/thirdParty/tx/getLimitOrder", params)

    def cancel_limit_order(self, chain: str, ids: list[str]) -> dict[str, Any]:
        return self._post("/v1/thirdParty/tx/cancelLimitOrder", {"chain": chain, "ids": ids})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self.config.base_url.rstrip("/") + path
        if params:
            import urllib.parse

            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=self._headers("GET", path), method="GET")
        with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        req = urllib.request.Request(
            self.config.base_url.rstrip("/") + path,
            data=data,
            headers=self._headers("POST", path, payload),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _headers(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, str]:
        api_key = os.environ.get(self.config.api_key_env, "")
        secret = os.environ.get(self.config.secret_key_env, "")
        if not api_key:
            raise RuntimeError(f"missing API key env: {self.config.api_key_env}")
        if not secret:
            raise RuntimeError(f"missing secret key env: {self.config.secret_key_env}")
        timestamp, signature = _trade_sign(secret, method, path, body)
        return {
            "AVE-ACCESS-KEY": api_key,
            "AVE-ACCESS-TIMESTAMP": timestamp,
            "AVE-ACCESS-SIGN": signature,
            "Content-Type": "application/json",
        }


def build_proxy_wallet_order_payload(summary: dict[str, Any], params: dict[str, Any], config: AveSolanaTradeConfig | None = None) -> dict[str, Any]:
    config = config or AveSolanaTradeConfig()
    action = str(summary.get("action") or params.get("action") or "trade.market_draft")
    side = "sell" if "sell" in action else "buy"
    is_limit = "limit" in action
    token_id = str(summary.get("token_id") or params.get("token_id") or "")
    token_addr = _token_addr(token_id)
    amount = _native_amount(params.get("amount_sol") or params.get("amount_native") or summary.get("amount") or "")
    payload: dict[str, Any] = {
        "_is_limit": is_limit,
        "chain": str(params.get("chain") or "solana"),
        "assetsId": str(params.get("assets_id") or params.get("assetsId") or os.environ.get(config.proxy_wallet_id_env, "")),
        "inTokenAddress": str(params.get("in_token") or ("sol" if side == "buy" else token_addr)),
        "outTokenAddress": str(params.get("out_token") or (token_addr if side == "buy" else "sol")),
        "inAmount": str(params.get("in_amount") or amount),
        "swapType": side,
        "slippage": int(params.get("slippage_bps") or params.get("slippage") or 1000),
        "useMev": bool(params.get("use_mev", params.get("useMev", True))),
    }
    if payload["chain"] == "solana":
        payload["gas"] = str(params.get("gas") or config.proxy_default_gas)
    if params.get("auto_slippage") or params.get("autoSlippage"):
        payload["autoSlippage"] = True
    if params.get("auto_gas") or params.get("autoGas"):
        payload["autoGas"] = params.get("auto_gas") or params.get("autoGas")
    if is_limit:
        payload["limitPrice"] = str(summary.get("limit_price") or params.get("limit_price") or "")
        if params.get("expire_time") or params.get("expireTime"):
            payload["expireTime"] = params.get("expire_time") or params.get("expireTime")
    if not payload["assetsId"]:
        raise RuntimeError(f"missing proxy wallet id env: {config.proxy_wallet_id_env}")
    if not token_addr:
        raise RuntimeError("missing token address for proxy wallet order")
    return payload


def _trade_sign(secret: str, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[str, str]:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    message = timestamp + method.upper().strip() + path.strip()
    if body:
        message += json.dumps(body, sort_keys=True, separators=(",", ":"))
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return timestamp, base64.b64encode(digest).decode("ascii")


def _token_addr(token_id: str) -> str:
    token = str(token_id or "").strip()
    if token.endswith("-solana"):
        return token[:-7]
    return token


def _native_amount(value: Any) -> str:
    text = str(value or "").strip().lower().replace("sol", "").strip()
    if not text:
        return ""
    try:
        # Proxy-wallet Solana examples use lamports.
        return str(int(float(text) * 1_000_000_000))
    except ValueError:
        return str(value)
