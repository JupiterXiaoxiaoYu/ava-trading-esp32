from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

SOLANA = "solana"
DEFAULT_STORE = "data/ava_box_app_state.json"


@dataclass(slots=True)
class AvaBoxSkillConfig:
    store_path: str = DEFAULT_STORE
    default_buy_sol: Decimal = Decimal("0.1")
    default_slippage_bps: int = 100
    execution_mode: str = "paper"
    execution_base_url: str = "https://bot-api.ave.ai"
    execution_api_key_env: str = "AVE_API_KEY"
