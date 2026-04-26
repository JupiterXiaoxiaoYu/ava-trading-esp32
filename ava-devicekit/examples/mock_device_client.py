from __future__ import annotations

import argparse
import json
import urllib.request


def post(base_url: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a mock Ava Box device flow to a local DeviceKit gateway.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8788")
    args = parser.parse_args()
    flow = [
        post(args.base_url, "/device/boot"),
        post(args.base_url, "/device/message", {"type": "key_action", "action": "watch"}),
        post(args.base_url, "/device/message", {"type": "key_action", "action": "buy"}),
        post(args.base_url, "/device/message", {"type": "confirm"}),
    ]
    print(json.dumps(flow, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
