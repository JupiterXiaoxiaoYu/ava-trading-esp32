from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_loads():
    from ava_devicekit.core.manifest import HardwareAppManifest

    manifest = HardwareAppManifest.load(ROOT / "apps" / "ava_box" / "manifest.json")
    assert manifest.app_id == "ava_box"
    assert manifest.chain == "solana"
    assert "trade.market_draft" in manifest.actions


def test_demo_flow_contracts():
    import importlib.util

    spec = importlib.util.spec_from_file_location("demo_flow", ROOT / "examples" / "demo_flow.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    manifest = module.HardwareAppManifest.load(ROOT / "apps" / "ava_box" / "manifest.json")
    session = module.DeviceSession(module.AvaBoxApp(manifest=manifest, chain_adapter=module.MockSolanaAdapter()))
    feed = session.boot()
    assert feed["screen"] == "feed"
    detail = session.handle({"type": "key_action", "action": "watch"})
    assert detail["screen"] == "spotlight"
    draft = session.handle({"type": "key_action", "action": "buy"})
    assert draft["screen"] == "confirm"
    assert draft["action_draft"]["requires_confirmation"] is True
    result = session.handle({"type": "confirm"})
    assert result["screen"] == "result"


def test_clean_framework_has_no_legacy_imports():
    forbidden = ("plugins_func", "core.connection", "config.logger", "register_function")
    for path in (ROOT / "backend" / "ava_devicekit").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(name.startswith(forbidden) or name in forbidden for name in names), (path, names)


def test_json_files_parse():
    for path in list((ROOT / "schemas").glob("*.json")) + [ROOT / "apps" / "ava_box" / "manifest.json"]:
        json.loads(path.read_text(encoding="utf-8"))
