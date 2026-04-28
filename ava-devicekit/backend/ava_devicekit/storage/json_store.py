from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Callable

try:  # Linux/WSL and other POSIX platforms.
    import fcntl
except ImportError:  # pragma: no cover - exercised on non-POSIX platforms only.
    fcntl = None  # type: ignore[assignment]


class JsonStore:
    _thread_locks: dict[Path, threading.RLock] = {}
    _thread_locks_guard = threading.Lock()

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read(self, default: Any):
        with self._locked(exclusive=False):
            return self._read_unlocked(default)

    def write(self, data: Any) -> None:
        with self._locked(exclusive=True):
            self._write_unlocked(data)

    def update(self, default: Any, mutator: Callable[[Any], Any]) -> Any:
        """Atomically read, mutate, and write state under one exclusive lock.

        The mutator may modify the loaded value in place and return None, or
        return a replacement value. The final persisted value is returned.
        """
        with self._locked(exclusive=True):
            data = self._read_unlocked(default)
            updated = mutator(data)
            if updated is not None:
                data = updated
            self._write_unlocked(data)
            return data

    def _read_unlocked(self, default: Any):
        if not self.path.exists():
            return default
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _write_unlocked(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        fd = -1
        tmp_path = ""
        try:
            fd, tmp_path = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                fd = -1
                tmp.write(payload)
                tmp.write("\n")
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_path, self.path)
            self._fsync_parent_dir()
        except Exception:
            if fd >= 0:
                os.close(fd)
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except FileNotFoundError:
                    pass
            raise

    @contextmanager
    def _locked(self, *, exclusive: bool):
        lock = self._thread_lock()
        with lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock_path = self.path.with_name(f"{self.path.name}.lock")
            with lock_path.open("a+b") as lock_file:
                if fcntl is not None:
                    operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                    fcntl.flock(lock_file.fileno(), operation)
                try:
                    yield
                finally:
                    if fcntl is not None:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _thread_lock(self) -> threading.RLock:
        key = self.path.resolve(strict=False)
        with self._thread_locks_guard:
            lock = self._thread_locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._thread_locks[key] = lock
            return lock

    def _fsync_parent_dir(self) -> None:
        if os.name == "nt":
            return
        try:
            dir_fd = os.open(self.path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
