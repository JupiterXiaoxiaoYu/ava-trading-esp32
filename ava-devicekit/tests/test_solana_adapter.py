from __future__ import annotations

from typing import Any

from ava_devicekit.adapters.solana import SolanaAdapter


class _FakeSolanaClient:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.paths.append(path)
        if path.startswith("/tokens/top100/"):
            return {"data": {"list": [{"balance_ratio": 0.25}, {"balance_ratio": "12.5%"}]}}
        if path.startswith("/tokens/"):
            return {
                "data": {
                    "token": {
                        "addr": "Token111",
                        "chain": "solana",
                        "symbol": "TOK",
                        "current_price_usd": "0.1",
                        "holders": 10,
                    }
                }
            }
        if path.startswith("/contracts/"):
            return {"data": {}}
        if path.startswith("/klines/token/"):
            return {"data": {"points": [{"close": 0.1}, {"close": 0.11}]}}
        raise AssertionError(path)


def test_solana_adapter_fetches_and_formats_top100_concentration():
    adapter = SolanaAdapter()
    client = _FakeSolanaClient()
    adapter.client = client

    detail = adapter.get_token_detail("Token111-solana")

    assert "/tokens/top100/Token111-solana" in client.paths
    assert detail.payload["top100_concentration"] == "37.5%"
