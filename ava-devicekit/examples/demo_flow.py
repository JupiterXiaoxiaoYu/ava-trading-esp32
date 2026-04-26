from __future__ import annotations

import json
from pathlib import Path

from ava_devicekit.adapters.mock_solana import MockSolanaAdapter
from ava_devicekit.apps.ava_box import AvaBoxApp
from ava_devicekit.core.manifest import HardwareAppManifest
from ava_devicekit.gateway.session import DeviceSession

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    manifest = HardwareAppManifest.load(ROOT / "apps" / "ava_box" / "manifest.json")
    session = DeviceSession(AvaBoxApp(manifest=manifest, chain_adapter=MockSolanaAdapter()))
    flow = [
        session.boot(),
        session.handle({"type": "key_action", "action": "watch"}),
        session.handle({"type": "key_action", "action": "buy"}),
        session.handle({"type": "confirm"}),
    ]
    print(json.dumps(flow, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
