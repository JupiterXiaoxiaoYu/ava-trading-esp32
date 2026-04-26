"""Text-first AVE skill tools for the server-side agent path.

These tools intentionally do not push new display screens. They expose
wallet/address analysis abilities from the AVE Cloud Data REST API through the
existing server plugin tool system, so the LLM can answer questions like
"看我的钱包概览" or "这个钱包最近做了什么" using direct tool calls.
"""

import os
from typing import TYPE_CHECKING, Iterable

from plugins_func.functions.ave_tools import (
    _data_get,
    _fmt_price,
    _normalize_chain_name,
    _normalize_portfolio_wallets,
)
from plugins_func.functions.ave_trade_mgr import _trade_get
from plugins_func.register import Action, ActionResponse, ToolType, register_function

if TYPE_CHECKING:
    from core.connection import ConnectionHandler


_SUPPORTED_CHAIN_HINTS = ("solana",)


def _short_addr(value: str) -> str:
    text = str(value or "").strip()
    if len(text) <= 12:
        return text
    return f"{text[:6]}...{text[-4:]}"


def _pick_first(mapping: dict, *keys, default=None):
    if not isinstance(mapping, dict):
        return default
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return default


def _pick_list(data) -> list:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("list", "items", "records", "rows", "result"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    nested_data = data.get("data")
    if isinstance(nested_data, list):
        return nested_data
    if isinstance(nested_data, dict):
        for key in ("list", "items", "records", "rows", "result"):
            value = nested_data.get(key)
            if isinstance(value, list):
                return value
    return []


def _pct_text(value) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    return text if text.endswith("%") else f"{text}%"


def _chain_from_state(conn: "ConnectionHandler") -> str:
    return "solana"


def _current_token(conn: "ConnectionHandler") -> dict:
    state = getattr(conn, "ave_state", {})
    if not isinstance(state, dict):
        return {}
    token = state.get("current_token")
    return token if isinstance(token, dict) else {}


def _load_proxy_wallets(conn: "ConnectionHandler") -> list:
    state = getattr(conn, "ave_state", {})
    if isinstance(state, dict):
        cached = state.get("portfolio_wallets")
        if isinstance(cached, list) and cached:
            return cached

    assets_id = os.environ.get("AVE_PROXY_WALLET_ID", "").strip()
    if not assets_id:
        return []

    response = _trade_get(
        "/v1/thirdParty/user/getUserByAssetsId",
        {"assetsIds": assets_id},
    )
    wallets = _normalize_portfolio_wallets(response.get("data", []))
    if isinstance(state, dict):
        state["portfolio_wallets"] = wallets
    return wallets


def _resolve_wallet_target(
    conn: "ConnectionHandler",
    wallet_address: str = "",
    chain: str = "",
) -> tuple[str, str]:
    preferred_chain = "solana"

    if wallet_address:
        return str(wallet_address).strip(), preferred_chain

    wallets = _load_proxy_wallets(conn)
    if not wallets:
        raise ValueError("未提供 Solana 钱包地址，且未配置可解析的 AVE_PROXY_WALLET_ID。")

    for wallet in wallets:
        for address_info in wallet.get("addresses", []):
            chain_name = _normalize_chain_name(address_info.get("chain"))
            address = str(address_info.get("address", "") or "").strip()
            if chain_name == preferred_chain and address:
                return address, preferred_chain

    raise ValueError("代理钱包已配置，但没有可用的 Solana 地址。")


def _metric_parts(parts: Iterable[str]) -> str:
    values = [part for part in parts if part]
    return "；".join(values)


def _success_response(text: str, result: str = "") -> ActionResponse:
    return ActionResponse(action=Action.RESPONSE, result=result or text, response=text)


def _error_response(text: str) -> ActionResponse:
    return ActionResponse(action=Action.RESPONSE, result=text, response=text)


def _wallet_overview_summary(chain: str, wallet_address: str, payload: dict) -> str:
    data = payload.get("data", payload)
    total_value = _pick_first(
        data,
        "total_value_usd",
        "totalValueUsd",
        "total_usd",
        "portfolio_value_usd",
    )
    win_rate = _pick_first(data, "win_rate", "winRate", "total_win_rate")
    trade_count = _pick_first(data, "trade_count", "tradeCount", "tx_count", "total_tx_count")
    pnl_usd = _pick_first(data, "total_pnl_usd", "totalPnlUsd", "realized_pnl_usd", "pnl_usd")

    summary = _metric_parts(
        (
            f"总资产 {_fmt_price(total_value)}" if total_value not in (None, "") else "",
            f"胜率 {_pct_text(win_rate)}" if win_rate not in (None, "") else "",
            f"交易 {trade_count} 笔" if trade_count not in (None, "") else "",
            f"PnL {_fmt_price(pnl_usd)}" if pnl_usd not in (None, "") else "",
        )
    )
    if not summary:
        field_count = len(data) if isinstance(data, dict) else 0
        summary = f"已返回 {field_count} 个统计字段"
    return f"钱包概览（{chain}，{_short_addr(wallet_address)}）：{summary}。"


def _wallet_tokens_summary(chain: str, wallet_address: str, payload: dict) -> str:
    rows = _pick_list(payload.get("data", payload))
    if not rows:
        return f"钱包持仓（{chain}，{_short_addr(wallet_address)}）为空。"

    preview = []
    for row in rows[:5]:
        symbol = _pick_first(row, "symbol", "token_symbol", "name", default="TOKEN")
        value_usd = _pick_first(row, "value_usd", "valueUsd", "amount_usd", "total_value_usd")
        if value_usd not in (None, ""):
            preview.append(f"{symbol} {_fmt_price(value_usd)}")
        else:
            balance = _pick_first(row, "balance", "amount", "balance_formatted", default="?")
            preview.append(f"{symbol} {balance}")
    return (
        f"钱包持仓（{chain}，{_short_addr(wallet_address)}）共 {len(rows)} 个："
        + "，".join(preview)
        + "。"
    )


def _history_action_label(row: dict) -> str:
    action = str(_pick_first(row, "side", "type", "action", "trade_type", default="交易")).strip().lower()
    mapping = {
        "buy": "买入",
        "sell": "卖出",
        "swap": "兑换",
        "transfer": "转账",
    }
    return mapping.get(action, action or "交易")


def _wallet_history_summary(chain: str, wallet_address: str, payload: dict) -> str:
    rows = _pick_list(payload.get("data", payload))
    if not rows:
        return f"钱包历史（{chain}，{_short_addr(wallet_address)}）暂无记录。"

    preview = []
    for row in rows[:3]:
        symbol = _pick_first(row, "symbol", "token_symbol", "base_symbol", "name", default="TOKEN")
        action = _history_action_label(row)
        amount_usd = _pick_first(row, "amount_usd", "amountUsd", "value_usd", "trade_value_usd")
        amount_text = _fmt_price(amount_usd) if amount_usd not in (None, "") else "金额未知"
        preview.append(f"{action} {symbol} {amount_text}")
    return (
        f"钱包最近 {len(rows)} 笔（{chain}，{_short_addr(wallet_address)}）："
        + "；".join(preview)
        + "。"
    )


def _wallet_pnl_summary(chain: str, wallet_address: str, token_symbol: str, payload: dict) -> str:
    data = payload.get("data", payload)
    pnl_usd = _pick_first(data, "total_pnl_usd", "totalPnlUsd", "pnl_usd", "profit_usd")
    pnl_pct = _pick_first(data, "pnl_percent", "pnlPercent", "profit_percent", "roi")
    win_rate = _pick_first(data, "win_rate", "winRate")

    summary = _metric_parts(
        (
            f"PnL {_fmt_price(pnl_usd)}" if pnl_usd not in (None, "") else "",
            f"{_pct_text(pnl_pct)}" if pnl_pct not in (None, "") else "",
            f"胜率 {_pct_text(win_rate)}" if win_rate not in (None, "") else "",
        )
    )
    if not summary:
        summary = "接口返回了结果，但没有可直接展示的盈亏字段"
    return f"钱包在 {token_symbol}（{chain}）上的表现：{summary}。"


ave_wallet_overview_desc = {
    "type": "function",
    "function": {
        "name": "ave_wallet_overview",
        "description": "查看钱包/地址概览统计。适合用户说“看我的钱包概览”“这个地址怎么样”“这个钱包胜率如何”。wallet_address 可省略；省略时优先解析当前代理钱包地址。",
        "parameters": {
            "type": "object",
            "properties": {
                "wallet_address": {
                    "type": "string",
                    "description": "目标钱包地址；不填时优先使用当前代理钱包地址。",
                },
                "chain": {
                    "type": "string",
                    "description": "链名，本分支固定为 solana。",
                },
            },
            "required": [],
        },
    },
}


@register_function("ave_wallet_overview", ave_wallet_overview_desc, ToolType.SYSTEM_CTL)
def ave_wallet_overview(
    conn: "ConnectionHandler",
    wallet_address: str = "",
    chain: str = "",
):
    try:
        resolved_wallet, resolved_chain = _resolve_wallet_target(conn, wallet_address, chain)
        payload = _data_get(
            "/address/walletinfo",
            {
                "wallet_address": resolved_wallet,
                "chain": resolved_chain,
            },
        )
        text = _wallet_overview_summary(resolved_chain, resolved_wallet, payload)
        return _success_response(text, result="wallet_overview")
    except ValueError as exc:
        return _error_response(str(exc))
    except Exception as exc:
        return ActionResponse(action=Action.ERROR, response=str(exc))


ave_wallet_tokens_desc = {
    "type": "function",
    "function": {
        "name": "ave_wallet_tokens",
        "description": "查看钱包/地址持仓列表。适合用户说“看钱包持仓”“这个地址有哪些币”“我的钱包里都有什么”。wallet_address 可省略；省略时优先解析当前代理钱包地址。",
        "parameters": {
            "type": "object",
            "properties": {
                "wallet_address": {
                    "type": "string",
                    "description": "目标钱包地址；不填时优先使用当前代理钱包地址。",
                },
                "chain": {
                    "type": "string",
                    "description": "链名，本分支固定为 solana。",
                },
            },
            "required": [],
        },
    },
}


@register_function("ave_wallet_tokens", ave_wallet_tokens_desc, ToolType.SYSTEM_CTL)
def ave_wallet_tokens(
    conn: "ConnectionHandler",
    wallet_address: str = "",
    chain: str = "",
):
    try:
        resolved_wallet, resolved_chain = _resolve_wallet_target(conn, wallet_address, chain)
        payload = _data_get(
            "/address/walletinfo/tokens",
            {
                "wallet_address": resolved_wallet,
                "chain": resolved_chain,
            },
        )
        text = _wallet_tokens_summary(resolved_chain, resolved_wallet, payload)
        return _success_response(text, result="wallet_tokens")
    except ValueError as exc:
        return _error_response(str(exc))
    except Exception as exc:
        return ActionResponse(action=Action.ERROR, response=str(exc))


ave_wallet_history_desc = {
    "type": "function",
    "function": {
        "name": "ave_wallet_history",
        "description": "查看钱包/地址最近交易历史。适合用户说“看这个钱包最近交易”“我的钱包最近做了什么”“这个地址最近买卖了什么”。wallet_address 可省略；省略时优先解析当前代理钱包地址。",
        "parameters": {
            "type": "object",
            "properties": {
                "wallet_address": {
                    "type": "string",
                    "description": "目标钱包地址；不填时优先使用当前代理钱包地址。",
                },
                "chain": {
                    "type": "string",
                    "description": "链名，本分支固定为 solana。",
                },
                "token_address": {
                    "type": "string",
                    "description": "可选；只看某个 token 的历史。",
                },
            },
            "required": [],
        },
    },
}


@register_function("ave_wallet_history", ave_wallet_history_desc, ToolType.SYSTEM_CTL)
def ave_wallet_history(
    conn: "ConnectionHandler",
    wallet_address: str = "",
    chain: str = "",
    token_address: str = "",
):
    try:
        resolved_wallet, resolved_chain = _resolve_wallet_target(conn, wallet_address, chain)
        params = {
            "wallet_address": resolved_wallet,
            "chain": resolved_chain,
        }
        if token_address:
            params["token_address"] = token_address
        payload = _data_get("/address/tx", params)
        text = _wallet_history_summary(resolved_chain, resolved_wallet, payload)
        return _success_response(text, result="wallet_history")
    except ValueError as exc:
        return _error_response(str(exc))
    except Exception as exc:
        return ActionResponse(action=Action.ERROR, response=str(exc))


ave_wallet_pnl_desc = {
    "type": "function",
    "function": {
        "name": "ave_wallet_pnl",
        "description": "查看钱包在某个 token 上的盈亏。适合用户说“这个钱包在这只币上赚了吗”“看我的钱包在 BONK 上的 PnL”。token_address 可省略；若当前 AVE 页面已选中 token，则优先使用当前 token。",
        "parameters": {
            "type": "object",
            "properties": {
                "wallet_address": {
                    "type": "string",
                    "description": "目标钱包地址；不填时优先使用当前代理钱包地址。",
                },
                "chain": {
                    "type": "string",
                    "description": "链名，本分支固定为 solana。",
                },
                "token_address": {
                    "type": "string",
                    "description": "目标 token 合约地址；不填时优先使用当前 AVE token。",
                },
                "token_symbol": {
                    "type": "string",
                    "description": "可选；仅用于结果文案展示。",
                },
            },
            "required": [],
        },
    },
}


@register_function("ave_wallet_pnl", ave_wallet_pnl_desc, ToolType.SYSTEM_CTL)
def ave_wallet_pnl(
    conn: "ConnectionHandler",
    wallet_address: str = "",
    chain: str = "",
    token_address: str = "",
    token_symbol: str = "",
):
    try:
        current = _current_token(conn)
        resolved_wallet, resolved_chain = _resolve_wallet_target(
            conn,
            wallet_address,
            chain or _normalize_chain_name(current.get("chain")),
        )
        resolved_token = str(token_address or current.get("addr") or "").strip()
        resolved_symbol = str(token_symbol or current.get("symbol") or "该 token").strip()
        if not resolved_token:
            return _error_response("请补充 token 地址，或先打开目标代币详情页。")

        payload = _data_get(
            "/address/pnl",
            {
                "wallet_address": resolved_wallet,
                "chain": resolved_chain,
                "token_address": resolved_token,
            },
        )
        text = _wallet_pnl_summary(resolved_chain, resolved_wallet, resolved_symbol, payload)
        return _success_response(text, result="wallet_pnl")
    except ValueError as exc:
        return _error_response(str(exc))
    except Exception as exc:
        return ActionResponse(action=Action.ERROR, response=str(exc))
