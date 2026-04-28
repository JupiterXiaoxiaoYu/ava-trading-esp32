from __future__ import annotations

import json
from pathlib import Path

from ava_devicekit.core.contracts import ScreenContract, validate_screen_payload
from ava_devicekit.core.manifest import HardwareAppManifest

ROOT = Path(__file__).resolve().parents[2]


def test_reference_app_manifests_load_and_declare_contracts():
    manifests = sorted((ROOT / "examples" / "apps").glob("*/manifest.json"))
    assert manifests
    for path in manifests:
        raw = json.loads(path.read_text(encoding="utf-8"))
        manifest = HardwareAppManifest.from_dict(raw)
        assert manifest.app_id
        assert manifest.name
        assert manifest.screens
        contracts = [ScreenContract.from_dict(item) for item in raw.get("screen_contracts", [])]
        assert any(contract and contract.screen_id for contract in contracts)


def test_solana_depin_reference_templates_are_packaged():
    app_ids = {
        json.loads(path.read_text(encoding="utf-8")).get("app_id")
        for path in sorted((ROOT / "examples" / "apps").glob("*/manifest.json"))
    }
    assert {
        "payment_terminal",
        "depin_reward_device",
        "sensor_oracle_device",
        "onchain_event_listener",
        "hardware_signer_approval",
    } <= app_ids


def test_screen_payload_validator_accepts_reference_screen_ids():
    for path in sorted((ROOT / "examples" / "apps").glob("*/manifest.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        screens = raw.get("screens") or []
        first_screen = screens[0]
        result = validate_screen_payload({"type": "display", "screen": first_screen, "data": {}}, screens=screens)
        assert result.ok, f"{path}: {result.errors}"
