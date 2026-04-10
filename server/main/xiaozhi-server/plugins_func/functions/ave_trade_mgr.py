"""
AVE pending trade state machine.

Usage:
    from plugins_func.functions.ave_trade_mgr import trade_mgr
    tid = trade_mgr.create("market_buy", params, conn)
    await trade_mgr.confirm(tid)
    trade_mgr.cancel(tid)
"""
import asyncio
import base64
import datetime
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

TRADE_BASE = "https://bot-api.ave.ai"
TRADE_CONFIRM_TIMEOUT_SEC = 15
NATIVE_SOL = "So11111111111111111111111111111111111111112"
USDC_SOL = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOLANA_NATIVE_TOKEN_ALIAS = "sol"
SOLANA_STABLE_TOKEN_ALIAS = "usdt"
DEFAULT_SOLANA_GAS_LAMPORTS = "1000000"
DEFAULT_SOLANA_AUTO_GAS = "average"
_SUCCESS_STATUS_CODES = {0, 1, 200}
SWAP_RECONCILE_POLL_ATTEMPTS = 3
SWAP_RECONCILE_POLL_DELAY_SEC = 0.35
_SWAP_TERMINAL_STATUSES = {"confirmed", "error", "failed", "cancelled", "canceled", "auto_cancelled"}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get_api_key():
    key = os.environ.get("AVE_API_KEY", "")
    if not key:
        raise EnvironmentError("AVE_API_KEY not set")
    return key


def _get_secret_key():
    key = os.environ.get("AVE_SECRET_KEY", "")
    if not key:
        raise EnvironmentError("AVE_SECRET_KEY not set")
    return key


def _proxy_headers(method: str, path: str, body=None):
    secret = _get_secret_key()
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    msg = ts + method.upper().strip() + path.strip()
    if body:
        msg += json.dumps(body, sort_keys=True, separators=(",", ":"))
    sig = base64.b64encode(
        hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "AVE-ACCESS-KEY": _get_api_key(),
        "AVE-ACCESS-TIMESTAMP": ts,
        "AVE-ACCESS-SIGN": sig,
        "Content-Type": "application/json",
    }


def _trade_post(path: str, payload: dict) -> dict:
    url = TRADE_BASE + path
    headers = _proxy_headers("POST", path, payload)
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Trade API {e.code}: {body}")


def _trade_get(path: str, params: dict = None) -> dict:
    url = TRADE_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = _proxy_headers("GET", path)
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Trade API {e.code}: {body}")


def _normalize_quote_token_address(chain: str, token_address) -> str:
    token = str(token_address or "")
    if str(chain or "").lower() != "solana":
        return token

    lowered = token.lower()
    if lowered in {NATIVE_SOL.lower(), SOLANA_NATIVE_TOKEN_ALIAS}:
        return SOLANA_NATIVE_TOKEN_ALIAS
    if lowered in {USDC_SOL.lower(), "usdc", "usdt"}:
        return SOLANA_STABLE_TOKEN_ALIAS
    return token


def _stringify_payload_value(value):
    if value in (None, ""):
        return None
    return str(value)


def _normalize_proxy_trade_payload(trade_type: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload

    normalized = dict(payload)
    if "inToken" in normalized and "inTokenAddress" not in normalized:
        normalized["inTokenAddress"] = normalized.pop("inToken")
    if "outToken" in normalized and "outTokenAddress" not in normalized:
        normalized["outTokenAddress"] = normalized.pop("outToken")

    chain = str(normalized.get("chain", "") or "").lower()
    if chain:
        normalized["chain"] = chain

    if chain == "solana":
        if "inTokenAddress" in normalized:
            normalized["inTokenAddress"] = _normalize_quote_token_address(chain, normalized["inTokenAddress"])
        if "outTokenAddress" in normalized:
            normalized["outTokenAddress"] = _normalize_quote_token_address(chain, normalized["outTokenAddress"])
        if trade_type in {"market_buy", "market_sell"}:
            normalized.setdefault("gas", DEFAULT_SOLANA_GAS_LAMPORTS)
            normalized.setdefault("autoGas", DEFAULT_SOLANA_AUTO_GAS)
        elif trade_type == "limit_buy":
            normalized.setdefault("gas", DEFAULT_SOLANA_GAS_LAMPORTS)
            # Solana limit endpoint rejects autoGas values used by swap endpoint.
            normalized.pop("autoGas", None)

    for key in (
        "assetsId",
        "inTokenAddress",
        "outTokenAddress",
        "inAmount",
        "swapType",
        "slippage",
        "limitPrice",
        "expireTime",
        "gas",
        "extraGas",
        "autoGas",
    ):
        if key in normalized:
            string_value = _stringify_payload_value(normalized.get(key))
            if string_value is None:
                normalized.pop(key, None)
            else:
                normalized[key] = string_value

    if "ids" in normalized and isinstance(normalized["ids"], list):
        normalized["ids"] = [str(item) for item in normalized["ids"] if item not in (None, "")]

    if "autoSellConfig" in normalized and isinstance(normalized["autoSellConfig"], list):
        cleaned_rules = []
        for rule in normalized["autoSellConfig"]:
            if not isinstance(rule, dict):
                continue
            cleaned_rule = dict(rule)
            for key in ("priceChange", "sellRatio", "type"):
                if key in cleaned_rule:
                    string_value = _stringify_payload_value(cleaned_rule.get(key))
                    if string_value is None:
                        cleaned_rule.pop(key, None)
                    else:
                        cleaned_rule[key] = string_value
            cleaned_rules.append(cleaned_rule)
        normalized["autoSellConfig"] = cleaned_rules

    return normalized


def _normalize_trade_status(status):
    if isinstance(status, bool):
        return None
    if isinstance(status, int):
        return status
    if isinstance(status, str):
        text = status.strip()
        if not text:
            return None
        if text.lstrip("-").isdigit():
            return int(text)
    return None


def _result_data_dict(result: dict) -> dict:
    data = result.get("data") if isinstance(result, dict) else {}
    return data if isinstance(data, dict) else {}


def _extract_swap_order_id(result: dict) -> str:
    data = _result_data_dict(result)
    for key in ("id", "orderId", "order_id", "swapOrderId", "swap_order_id"):
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _has_execution_evidence(data: dict) -> bool:
    for key in ("txId", "tx_id", "txHash", "tx_hash"):
        value = data.get(key)
        if value not in (None, ""):
            return True
    return False


def _is_submit_only_swap_ack(result: dict, trade_type: str) -> bool:
    if trade_type not in {"market_buy", "market_sell"}:
        return False
    if not isinstance(result, dict) or result.get("error") not in (None, ""):
        return False
    if _normalize_trade_status(result.get("status")) not in _SUCCESS_STATUS_CODES:
        return False
    return not _has_execution_evidence(_result_data_dict(result))


def _trade_chain(trade: dict) -> str:
    params = trade.get("params", {}) if isinstance(trade, dict) else {}
    return str(params.get("chain", "") or "").strip().lower()


def _extract_swap_order_rows(resp: dict) -> list:
    data = resp.get("data", resp) if isinstance(resp, dict) else resp
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("list", "orders", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        return [data]
    return []


def _find_swap_order(resp: dict, order_id: str) -> dict:
    order_id = str(order_id or "")
    for row in _extract_swap_order_rows(resp):
        if not isinstance(row, dict):
            continue
        if str(row.get("id", "")) == order_id:
            return row
    return {}


def _normalize_swap_status(status) -> str:
    if status in (None, ""):
        return ""
    return str(status).strip().lower()


def _is_terminal_swap_status(status) -> bool:
    return _normalize_swap_status(status) in _SWAP_TERMINAL_STATUSES


def _build_swap_reconcile_result(
    trade_type: str,
    submit_result: dict,
    order: dict,
    *,
    chain: str,
    order_id: str,
) -> dict:
    status = _normalize_swap_status(order.get("status"))
    wrapped = {
        "trade_type": trade_type,
        "status": status or submit_result.get("status"),
        "msg": submit_result.get("msg", ""),
        "swap_order_id": order_id,
        "chain": chain,
        "data": {
            "id": order_id,
            "chain": chain,
            "swapType": order.get("swapType", order.get("swap_type", "")),
            "inTokenSymbol": order.get("inTokenSymbol", order.get("in_token_symbol", "")),
            "outTokenSymbol": order.get("outTokenSymbol", order.get("out_token_symbol", "")),
            "outAmount": order.get("outAmount", order.get("out_amount", "")),
            "outAmountUsd": order.get("outAmountUsd", order.get("amountUsd", order.get("amount_usd", ""))),
            "txHash": order.get("txHash", order.get("tx_hash", "")),
        },
    }
    if status in {"error", "failed"}:
        wrapped["error"] = (
            order.get("errorMessage")
            or order.get("errorMsg")
            or submit_result.get("error")
            or submit_result.get("msg")
            or "Trade failed"
        )
        wrapped["errorMessage"] = wrapped["error"]
    return wrapped


# ---------------------------------------------------------------------------
# Trade manager
# ---------------------------------------------------------------------------

class _TradeMgr:
    def __init__(self):
        self._pending: dict = {}  # trade_id → {type, params, conn, ts}

    def create(self, trade_type: str, params: dict, conn) -> str:
        tid = str(uuid.uuid4())[:8]
        self._pending[tid] = {
            "type": trade_type,   # "market_buy" | "market_sell" | "limit_buy"
            "params": params,
            "conn": conn,
            "ts": time.time(),
        }
        asyncio.create_task(self._timeout(tid, TRADE_CONFIRM_TIMEOUT_SEC))
        logger.bind(tag=TAG).info(f"Created pending trade {tid} type={trade_type}")
        return tid

    async def _timeout(self, tid: str, secs: int):
        await asyncio.sleep(secs)
        if tid in self._pending:
            trade = self._pending[tid]
            conn = trade["conn"]
            del self._pending[tid]
            try:
                from plugins_func.functions.ave_tools import (
                    _build_trade_state_result_payload,
                    _clear_pending_trade,
                    _get_pending_trade,
                    _present_trade_result_or_defer,
                )
                pending = _get_pending_trade(conn) or {
                    "trade_id": tid,
                    "trade_type": trade.get("type", ""),
                    "symbol": "",
                }
                payload = _build_trade_state_result_payload("confirm_timeout", pending=pending)
                await _present_trade_result_or_defer(
                    conn,
                    payload,
                    current_trade_id=tid,
                )
                _clear_pending_trade(conn, tid)
                return
            except Exception:
                payload = {
                    "success": False,
                    "title": "Trade Cancelled",
                    "error": "Confirmation timed out. Nothing was executed.",
                    "subtitle": "Confirmation timed out. Nothing was executed.",
                    "explain_state": "confirm_timeout",
                }
                logger.bind(tag=TAG).debug(f"Timeout cleanup skipped for trade {tid}", exc_info=True)
            logger.bind(tag=TAG).info(f"Trade {tid} timed out, showing cancellation result")
            await _send_display(conn, "result", payload)

    async def confirm(self, tid: str) -> dict:
        trade = self._pending.pop(tid, None)
        if trade is None:
            return {"error": "expired_or_not_found"}
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._execute_sync, trade
            )
            trade_type = str(trade.get("type", "") or "")
            if _is_submit_only_swap_ack(result, trade_type):
                order_id = _extract_swap_order_id(result)
                chain = _trade_chain(trade)
                if order_id:
                    result["swap_order_id"] = order_id
                if chain:
                    result["chain"] = chain
                if order_id and chain:
                    reconciled = await self.reconcile_swap_order(
                        {
                            "trade_type": trade_type,
                            "swap_order_id": order_id,
                            "chain": chain,
                        },
                        submit_result=result,
                        attempts=SWAP_RECONCILE_POLL_ATTEMPTS,
                        delay=SWAP_RECONCILE_POLL_DELAY_SEC,
                    )
                    if _is_terminal_swap_status(reconciled.get("status")):
                        return reconciled
            return result
        except Exception as e:
            logger.bind(tag=TAG).error(f"Trade {tid} execution failed: {e}")
            return {"error": str(e), "trade_type": trade["type"]}

    def cancel(self, tid: str):
        trade = self._pending.pop(tid, None)
        if trade:
            try:
                from plugins_func.functions.ave_tools import _clear_pending_trade, _ensure_ave_state
                conn = trade.get("conn")
                if conn is not None:
                    _clear_pending_trade(conn, tid)
                    _ensure_ave_state(conn)["screen"] = "feed"
            except Exception:
                logger.bind(tag=TAG).debug(f"Cancel cleanup skipped for trade {tid}", exc_info=True)
        logger.bind(tag=TAG).info(f"Trade {tid} cancelled")

    def _execute_sync(self, trade: dict) -> dict:
        t = trade["type"]
        p = _normalize_proxy_trade_payload(t, trade["params"])

        if t == "market_buy":
            result = _trade_post("/v1/thirdParty/tx/sendSwapOrder", p)
        elif t == "market_sell":
            result = _trade_post("/v1/thirdParty/tx/sendSwapOrder", p)
        elif t == "limit_buy":
            result = _trade_post("/v1/thirdParty/tx/sendLimitOrder", p)
        elif t == "cancel_order":
            result = _trade_post("/v1/thirdParty/tx/cancelLimitOrder", p)
        else:
            raise ValueError(f"Unknown trade type: {t}")

        if not isinstance(result, dict):
            raise RuntimeError(f"Trade rejected: malformed response type={type(result).__name__}")

        if "status" not in result:
            raise RuntimeError("Trade rejected: status=missing msg=missing status in trade response")

        raw_status = result.get("status")
        status = _normalize_trade_status(raw_status)
        if status not in _SUCCESS_STATUS_CODES:
            msg = (
                result.get("msg")
                or result.get("message")
                or result.get("errorMessage")
                or result.get("errorMsg")
                or ""
            )
            raise RuntimeError(f"Trade rejected: status={raw_status} msg={msg}")

        wrapped = dict(result)
        wrapped["trade_type"] = t
        return wrapped

    def _get_swap_order_sync(self, chain: str, order_id: str) -> dict:
        return _trade_get("/v1/thirdParty/tx/getSwapOrder", {
            "chain": chain,
            "ids": order_id,
        })

    async def reconcile_swap_order(
        self,
        submitted_trade: dict,
        *,
        submit_result: dict = None,
        attempts: int = 1,
        delay: float = 0.0,
    ) -> dict:
        order_id = str(
            submitted_trade.get("swap_order_id")
            or submitted_trade.get("id")
            or submitted_trade.get("order_id")
            or ""
        )
        chain = str(submitted_trade.get("chain", "") or "").strip().lower()
        trade_type = str(submitted_trade.get("trade_type", "") or "")
        submit_result = dict(submit_result or {})

        if not (order_id and chain and trade_type):
            return {}

        latest = {}
        for attempt in range(max(1, int(attempts or 1))):
            try:
                resp = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._get_swap_order_sync,
                    chain,
                    order_id,
                )
            except Exception as exc:
                logger.bind(tag=TAG).warning(
                    f"Swap order reconcile failed order_id={order_id} chain={chain}: {exc}"
                )
                return latest

            order = _find_swap_order(resp, order_id)
            if order:
                latest = _build_swap_reconcile_result(
                    trade_type,
                    submit_result,
                    order,
                    chain=chain,
                    order_id=order_id,
                )
                if _is_terminal_swap_status(latest.get("status")):
                    return latest

            if attempt + 1 < max(1, int(attempts or 1)) and delay > 0:
                await asyncio.sleep(delay)

        return latest


trade_mgr = _TradeMgr()


# ---------------------------------------------------------------------------
# Display helper (used by both trade_mgr and ave_tools)
# ---------------------------------------------------------------------------

async def _send_display(conn, screen: str, data: dict):
    """Push a display message to the connected device."""
    msg = json.dumps({
        "type": "display",
        "screen": screen,
        "ts": int(time.time()),
        "data": data,
    })
    try:
        await conn.websocket.send(msg)
    except Exception as e:
        logger.bind(tag=TAG).warning(f"Failed to send display({screen}): {e}")
