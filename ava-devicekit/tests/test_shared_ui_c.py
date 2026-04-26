from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shared_ui_c_contract_compiles_and_runs(tmp_path):
    binary = tmp_path / "ava_devicekit_ui_test"
    cmd = [
        "gcc",
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        f"-I{ROOT / 'shared_ui' / 'include'}",
        str(ROOT / "shared_ui" / "src" / "ava_devicekit_ui.c"),
        str(ROOT / "shared_ui" / "tests" / "test_ava_devicekit_ui.c"),
        "-o",
        str(binary),
    ]
    subprocess.run(cmd, check=True)
    subprocess.run([str(binary)], check=True)
