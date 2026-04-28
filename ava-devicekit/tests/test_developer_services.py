from __future__ import annotations

from ava_devicekit.services.registry import DeveloperService, developer_service_report


def test_developer_service_reports_configured_env(monkeypatch):
    monkeypatch.setenv("WALLET_KEY", "secret")
    service = DeveloperService.from_dict(
        {
            "id": "proxy_wallet",
            "kind": "custodial_wallet",
            "base_url": "https://wallet.example.com",
            "api_key_env": "WALLET_KEY",
            "capabilities": ["trade.market"],
            "options": {"api_secret": "hidden", "timeout": 5},
        }
    )

    health = service.health()

    assert health["status"] == "configured"
    assert health["options"]["api_secret"] == "<redacted>"
    assert health["options"]["timeout"] == 5


def test_developer_service_report_flags_missing_env(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)

    report = developer_service_report([{"id": "data", "kind": "market_data", "api_key_env": "MISSING_KEY"}])

    assert report["ok"] is False
    assert report["items"][0]["status"] == "missing_env"
    assert report["items"][0]["env"]["missing"] == ["MISSING_KEY"]
