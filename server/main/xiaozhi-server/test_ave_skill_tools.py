import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.providers.tools.server_plugins.plugin_executor import ServerPluginExecutor
from plugins_func.loadplugins import auto_import_modules
from plugins_func.register import Action


class _FakeConn:
    def __init__(self):
        self.config = {
            "selected_module": {"Intent": "function_call"},
            "Intent": {
                "function_call": {
                    "functions": [
                        "ave_wallet_overview",
                        "ave_wallet_tokens",
                        "ave_wallet_history",
                        "ave_wallet_pnl",
                    ]
                }
            },
            "plugins": {},
        }


class AveSkillToolRegistryTests(unittest.TestCase):
    def test_server_plugin_executor_exposes_ave_wallet_skill_tools(self):
        auto_import_modules("plugins_func.functions")
        executor = ServerPluginExecutor(_FakeConn())

        tools = executor.get_tools()

        self.assertIn("ave_wallet_overview", tools)
        self.assertIn("ave_wallet_tokens", tools)
        self.assertIn("ave_wallet_history", tools)
        self.assertIn("ave_wallet_pnl", tools)


class AveSkillToolBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.mod = importlib.import_module("plugins_func.functions.ave_skill_tools")
        self.conn = SimpleNamespace(ave_state={})

    def test_wallet_overview_uses_proxy_wallet_address_when_wallet_omitted(self):
        wallet_payload = {
            "data": [
                {
                    "assetsId": "wallet-1",
                    "addressList": [
                        {
                            "chain": "solana",
                            "address": "SoWallet1111111111111111111111111111111111"
                        }
                    ],
                }
            ]
        }
        overview_payload = {
            "data": {
                "total_value_usd": "1234.56",
                "win_rate": "61.2",
                "trade_count": 23,
            }
        }

        with patch.object(self.mod, "_trade_get", return_value=wallet_payload) as mock_trade_get, \
             patch.object(self.mod, "_data_get", return_value=overview_payload) as mock_data_get, \
             patch.object(self.mod.os.environ, "get", side_effect=lambda key, default=None: "wallet-1" if key == "AVE_PROXY_WALLET_ID" else default):
            resp = self.mod.ave_wallet_overview(self.conn)

        self.assertEqual(resp.action, Action.RESPONSE)
        self.assertIn("solana", resp.response)
        self.assertIn("$1,235", resp.response)
        self.assertIn("61.2%", resp.response)
        mock_trade_get.assert_called_once()
        mock_data_get.assert_called_once_with(
            "/address/walletinfo",
            {
                "wallet_address": "SoWallet1111111111111111111111111111111111",
                "chain": "solana",
            },
        )

    def test_wallet_tokens_summarizes_top_holdings(self):
        token_payload = {
            "data": {
                "list": [
                    {"symbol": "BONK", "value_usd": "321.12"},
                    {"symbol": "SOL", "value_usd": "210.00"},
                    {"symbol": "JUP", "value_usd": "98.77"},
                ]
            }
        }

        with patch.object(self.mod, "_resolve_wallet_target", return_value=("WalletAddr", "solana")):
            with patch.object(self.mod, "_data_get", return_value=token_payload) as mock_data_get:
                resp = self.mod.ave_wallet_tokens(self.conn, wallet_address="WalletAddr", chain="solana")

        self.assertEqual(resp.action, Action.RESPONSE)
        self.assertIn("BONK", resp.response)
        self.assertIn("SOL", resp.response)
        self.assertIn("3 个", resp.response)
        mock_data_get.assert_called_once()

    def test_wallet_history_summarizes_recent_transactions(self):
        tx_payload = {
            "data": {
                "list": [
                    {"side": "buy", "symbol": "BONK", "amount_usd": "50.5"},
                    {"side": "sell", "symbol": "WIF", "amount_usd": "22"},
                ]
            }
        }

        with patch.object(self.mod, "_resolve_wallet_target", return_value=("WalletAddr", "solana")):
            with patch.object(self.mod, "_data_get", return_value=tx_payload) as mock_data_get:
                resp = self.mod.ave_wallet_history(self.conn, wallet_address="WalletAddr", chain="solana")

        self.assertEqual(resp.action, Action.RESPONSE)
        self.assertIn("BONK", resp.response)
        self.assertIn("WIF", resp.response)
        self.assertIn("最近", resp.response)
        mock_data_get.assert_called_once()

    def test_wallet_pnl_uses_current_token_when_token_omitted(self):
        self.conn.ave_state = {
            "current_token": {
                "addr": "TokenAddr111",
                "chain": "solana",
                "symbol": "BONK",
            }
        }
        pnl_payload = {
            "data": {
                "total_pnl_usd": "88.6",
                "pnl_percent": "25.4",
            }
        }

        with patch.object(self.mod, "_resolve_wallet_target", return_value=("WalletAddr", "solana")):
            with patch.object(self.mod, "_data_get", return_value=pnl_payload) as mock_data_get:
                resp = self.mod.ave_wallet_pnl(self.conn, wallet_address="WalletAddr")

        self.assertEqual(resp.action, Action.RESPONSE)
        self.assertIn("BONK", resp.response)
        self.assertIn("$88.6", resp.response)
        self.assertIn("25.4%", resp.response)
        mock_data_get.assert_called_once_with(
            "/address/pnl",
            {
                "wallet_address": "WalletAddr",
                "chain": "solana",
                "token_address": "TokenAddr111",
            },
        )
