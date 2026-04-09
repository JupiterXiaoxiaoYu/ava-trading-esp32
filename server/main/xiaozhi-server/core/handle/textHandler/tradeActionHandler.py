"""
Handle trade_action messages from the device:
  {"type": "trade_action", "action": "confirm"|"cancel", "trade_id": "..."}
"""
import json
import time
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class TradeActionHandler(TextMessageHandler):
    """处理设备发来的交易确认/取消消息"""

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.TRADE_ACTION

    async def handle(self, conn: "ConnectionHandler", msg_json: Dict[str, Any]) -> None:
        from plugins_func.functions.ave_trade_mgr import trade_mgr, _send_display
        from plugins_func.functions.ave_tools import (
            _build_result_payload,
            _ensure_ave_state,
            _get_pending_trade,
            _is_submit_only_ack,
            _clear_pending_trade,
            _push_submit_ack_transition,
        )

        action = msg_json.get("action", "")
        pending = _get_pending_trade(conn)
        pending_trade_id = pending.get("trade_id", "")
        trade_id = msg_json.get("trade_id", "")

        if not pending_trade_id:
            logger.bind(tag=TAG).warning("trade_action missing pending trade")
            return

        if trade_id and trade_id != pending_trade_id:
            logger.bind(tag=TAG).warning(
                f"trade_action trade_id mismatch pending={pending_trade_id} received={trade_id}"
            )
            return

        trade_id = pending_trade_id

        if action == "confirm":
            logger.bind(tag=TAG).info(f"Confirming trade {trade_id}")
            result = await trade_mgr.confirm(trade_id)
            if _is_submit_only_ack(result, pending=pending):
                await _push_submit_ack_transition(conn, result, pending=pending)
                return
            payload = _build_result_payload(result, pending=pending)
            await _send_display(conn, "result", payload)
            _clear_pending_trade(conn, trade_id)
            state = _ensure_ave_state(conn)
            state["screen"] = "result"

        elif action == "cancel":
            trade_mgr.cancel(trade_id)
            logger.bind(tag=TAG).info(f"Trade {trade_id} cancelled by user")
            _clear_pending_trade(conn, trade_id)
            state = _ensure_ave_state(conn)
            state["screen"] = "feed"
            await _send_display(conn, "feed", {"reason": "user_cancel"})

        else:
            logger.bind(tag=TAG).warning(f"Unknown trade action: {action}")
