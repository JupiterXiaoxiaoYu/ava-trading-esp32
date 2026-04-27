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


def test_firmware_runtime_contract_compiles_and_runs(tmp_path):
    binary = tmp_path / "ava_devicekit_runtime_test"
    cmd = [
        "gcc",
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        f"-I{ROOT / 'firmware' / 'include'}",
        str(ROOT / "firmware" / "src" / "ava_devicekit_runtime.c"),
        str(ROOT / "firmware" / "tests" / "test_ava_devicekit_runtime.c"),
        "-o",
        str(binary),
    ]
    subprocess.run(cmd, check=True)
    subprocess.run([str(binary)], check=True)


def test_scratch_arcade_port_contract_compiles_and_runs(tmp_path):
    binary = tmp_path / "ava_scratch_arcade_port_test"
    port_root = ROOT / "firmware" / "ports" / "scratch_arcade"
    cmd = [
        "gcc",
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        f"-I{ROOT / 'firmware' / 'include'}",
        f"-I{port_root / 'include'}",
        str(ROOT / "firmware" / "src" / "ava_devicekit_runtime.c"),
        str(port_root / "src" / "ava_scratch_arcade_port.c"),
        str(port_root / "tests" / "test_scratch_arcade_port.c"),
        "-o",
        str(binary),
    ]
    subprocess.run(cmd, check=True)
    subprocess.run([str(binary)], check=True)
