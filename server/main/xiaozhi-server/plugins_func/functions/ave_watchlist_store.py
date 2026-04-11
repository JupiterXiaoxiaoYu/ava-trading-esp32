import json
import tempfile
import time
import threading
from pathlib import Path


class WatchlistStoreError(RuntimeError):
    """Raised for any watchlist store persistence failures."""


class WatchlistStoreCorruptError(WatchlistStoreError):
    """Raised when the persisted store contains invalid JSON."""


_store_lock = threading.Lock()


def _load_store(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        _preserve_corrupt_file(path)
        raise WatchlistStoreCorruptError(
            f"watchlist store corrupted at {path}"
        ) from exc
    except OSError as exc:
        raise WatchlistStoreError("failed to read watchlist store") from exc
    if not isinstance(data, dict):
        _preserve_corrupt_file(path)
        raise WatchlistStoreCorruptError(
            f"watchlist store should be a dict at {path}"
        )
    return _validate_store(data, path)


def _save_store(path: Path, data: dict[str, list[dict]]) -> None:
    tmp_path = None
    try:
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=parent,
            delete=False,
            prefix=f"{path.name}.tmp.",
        ) as tmp:
            tmp_path = Path(tmp.name)
            json.dump(data, tmp, ensure_ascii=False, indent=2, sort_keys=True)
            tmp.flush()
        tmp_path.replace(path)
    except OSError as exc:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise WatchlistStoreError("failed to write watchlist store") from exc


def _preserve_corrupt_file(path: Path) -> None:
    if not path.exists():
        return
    timestamp = int(time.time() * 1000)
    corrupt_name = f"{path.name}.corrupt.{timestamp}"
    corrupt_path = path.with_name(corrupt_name)
    try:
        path.replace(corrupt_path)
    except OSError:
        pass


def _validate_store(data: dict, path: Path) -> dict[str, list[dict]]:
    validated: dict[str, list[dict]] = {}
    for namespace, value in data.items():
        if not isinstance(namespace, str) or not isinstance(value, list):
            _preserve_corrupt_file(path)
            raise WatchlistStoreCorruptError(
                f"watchlist namespace must map to a list of rows at {path}"
            )
        normalized_rows: list[dict] = []
        for row in value:
            if not isinstance(row, dict):
                _preserve_corrupt_file(path)
                raise WatchlistStoreCorruptError(
                    f"watchlist row entries must be dicts at {path}"
                )
            normalized_rows.append(row)
        validated[namespace] = normalized_rows
    return validated


def _normalize_entry(entry: dict) -> dict:
    addr = str(entry.get("addr") or "").strip()
    chain = str(entry.get("chain") or "").strip().lower()
    symbol = str(entry.get("symbol") or "?").strip() or "?"
    added_at = str(entry.get("added_at") or "").strip()
    return {
        "addr": addr,
        "chain": chain,
        "symbol": symbol,
        "added_at": added_at,
    }


def _entries_for_namespace(store: dict[str, list[dict]], namespace: str) -> list[dict]:
    rows = store.get(namespace, [])
    return [row for row in rows if isinstance(row, dict)]


def _query_key(addr: str, chain: str) -> tuple[str, str]:
    return str(addr or "").strip(), str(chain or "").strip().lower()


def list_watchlist_entries(path: Path, namespace: str) -> list[dict]:
    store = _load_store(path)
    return _entries_for_namespace(store, namespace)


def add_watchlist_entry(path: Path, namespace: str, entry: dict) -> list[dict]:
    normalized = _normalize_entry(entry)
    key_addr, key_chain = _query_key(normalized.get("addr"), normalized.get("chain"))
    with _store_lock:
        store = _load_store(path)
        rows = _entries_for_namespace(store, namespace)
        rows = [row for row in rows if _query_key(row.get("addr"), row.get("chain")) != (key_addr, key_chain)]
        rows.insert(0, normalized)
        store[namespace] = rows
        _save_store(path, store)
    return rows


def remove_watchlist_entry(path: Path, namespace: str, addr: str, chain: str) -> bool:
    with _store_lock:
        store = _load_store(path)
        rows = _entries_for_namespace(store, namespace)
        target = _query_key(addr, chain)
        kept = [row for row in rows if _query_key(row.get("addr"), row.get("chain")) != target]
        changed = len(kept) != len(rows)
        if changed:
            store[namespace] = kept
            _save_store(path, store)
    return changed


def watchlist_contains(path: Path, namespace: str, addr: str, chain: str) -> bool:
    target = _query_key(addr, chain)
    return any(
        _query_key(row.get("addr"), row.get("chain")) == target
        for row in list_watchlist_entries(path, namespace)
    )
