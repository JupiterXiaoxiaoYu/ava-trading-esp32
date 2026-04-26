from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FirmwareCandidate:
    model: str
    version: str
    filename: str
    path: Path


def parse_version(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", str(version or ""))
    return tuple(int(part) for part in parts) if parts else (0,)


def is_higher_version(candidate: str, current: str) -> bool:
    left = parse_version(candidate)
    right = parse_version(current)
    width = max(len(left), len(right))
    for idx in range(width):
        a = left[idx] if idx < len(left) else 0
        b = right[idx] if idx < len(right) else 0
        if a > b:
            return True
        if a < b:
            return False
    return False


def scan_firmware(bin_dir: str | Path) -> dict[str, list[FirmwareCandidate]]:
    root = Path(bin_dir)
    root.mkdir(parents=True, exist_ok=True)
    result: dict[str, list[FirmwareCandidate]] = {}
    for path in root.glob("*.bin"):
        match = re.match(r"^(.+?)_([0-9][A-Za-z0-9._-]*)\.bin$", path.name)
        if not match:
            continue
        model, version = match.groups()
        result.setdefault(model, []).append(FirmwareCandidate(model, version, path.name, path))
    for candidates in result.values():
        candidates.sort(key=lambda item: parse_version(item.version), reverse=True)
    return result


def select_update(candidates: list[FirmwareCandidate], current_version: str) -> FirmwareCandidate | None:
    for candidate in candidates:
        if is_higher_version(candidate.version, current_version):
            return candidate
    return None
