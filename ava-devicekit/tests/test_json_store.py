from __future__ import annotations

import os
from multiprocessing import Process, Queue
from pathlib import Path

import pytest

from ava_devicekit.storage import json_store
from ava_devicekit.storage.json_store import JsonStore


def _increment_store(path: Path, iterations: int, errors: Queue) -> None:
    store = JsonStore(path)
    try:
        for _ in range(iterations):
            def mutate(state):
                state["count"] = state.get("count", 0) + 1

            store.update({"count": 0}, mutate)
    except Exception as exc:  # pragma: no cover - reported to parent process.
        errors.put(repr(exc))


def test_write_is_atomic_and_cleans_temp_file_on_replace_failure(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    store = JsonStore(path)
    store.write({"version": 1})

    def fail_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(json_store.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        store.write({"version": 2})

    assert JsonStore(path).read({}) == {"version": 1}
    assert not list(tmp_path.glob("*.tmp"))


def test_update_serializes_read_modify_write_across_processes(tmp_path):
    path = tmp_path / "counter.json"
    workers = 4
    iterations = 30
    errors: Queue = Queue()
    processes = [Process(target=_increment_store, args=(path, iterations, errors)) for _ in range(workers)]

    for process in processes:
        process.start()
    for process in processes:
        process.join(10)

    assert errors.empty()
    assert all(process.exitcode == 0 for process in processes)
    assert JsonStore(path).read({}) == {"count": workers * iterations}
    assert os.path.exists(f"{path}.lock")
