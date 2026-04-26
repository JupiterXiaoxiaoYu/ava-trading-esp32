from __future__ import annotations

import json

from ava_devicekit.gateway.factory import create_device_session


def main() -> None:
    session = create_device_session(mock=True)
    flow = [
        session.boot(),
        session.handle({"type": "key_action", "action": "watch"}),
        session.handle({"type": "key_action", "action": "buy"}),
        session.handle({"type": "confirm"}),
    ]
    print(json.dumps(flow, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
