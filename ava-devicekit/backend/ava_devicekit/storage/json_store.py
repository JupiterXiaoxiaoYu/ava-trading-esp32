from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read(self, default: Any):
        if not self.path.exists():
            return default
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def write(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
