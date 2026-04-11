import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plugins_func.functions.ave_watchlist_store import (
    WatchlistStoreCorruptError,
    WatchlistStoreError,
    add_watchlist_entry,
    list_watchlist_entries,
    remove_watchlist_entry,
    watchlist_contains,
)


class WatchlistStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.tmp.name) / "watchlists.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_dedupes_by_addr_and_chain(self):
        add_watchlist_entry(
            self.store_path,
            "wallet-1",
            {"addr": "So111", "chain": "solana", "symbol": "BONK", "added_at": "2026-04-11T10:00:00Z"},
        )
        add_watchlist_entry(
            self.store_path,
            "wallet-1",
            {"addr": "So111", "chain": "solana", "symbol": "BONK", "added_at": "2026-04-11T10:01:00Z"},
        )

        rows = list_watchlist_entries(self.store_path, "wallet-1")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "BONK")
        self.assertEqual(rows[0]["added_at"], "2026-04-11T10:01:00Z")
        self.assertEqual(rows[0]["chain"], "solana")
        self.assertTrue(watchlist_contains(self.store_path, "wallet-1", "So111", "solana"))
        self.assertTrue(watchlist_contains(self.store_path, "wallet-1", "So111", "SOLANA"))

    def test_non_dict_json_raises_and_preserves_corrupt_file(self):
        self.store_path.write_text("[]", encoding="utf-8")
        with self.assertRaises(WatchlistStoreCorruptError):
            list_watchlist_entries(self.store_path, "wallet-1")
        corrupt_files = list(Path(self.tmp.name).glob("watchlists.json.corrupt.*"))
        self.assertTrue(corrupt_files)

    def test_invalid_namespace_shape_fails_closed(self):
        self.store_path.write_text(json.dumps({"wallet-1": "oops"}), encoding="utf-8")
        with self.assertRaises(WatchlistStoreCorruptError):
            list_watchlist_entries(self.store_path, "wallet-1")
        corrupt_files = list(Path(self.tmp.name).glob("watchlists.json.corrupt.*"))
        self.assertTrue(corrupt_files)

    def test_invalid_row_shape_fails_closed(self):
        self.store_path.write_text(
            json.dumps({"wallet-1": [{"addr": "So111"}, "oops"]}), encoding="utf-8"
        )
        with self.assertRaises(WatchlistStoreCorruptError):
            list_watchlist_entries(self.store_path, "wallet-1")
        corrupt_files = list(Path(self.tmp.name).glob("watchlists.json.corrupt.*"))
        self.assertTrue(corrupt_files)

    def test_read_os_error_reports_and_keeps_original(self):
        self.store_path.write_text(
            json.dumps({"wallet-1": [{"addr": "So111", "chain": "solana", "symbol": "BONK"}]}),
            encoding="utf-8",
        )
        corrupt_before = list(Path(self.tmp.name).glob("watchlists.json.corrupt.*"))
        with patch("pathlib.Path.open", side_effect=OSError("boom")):
            with self.assertRaises(WatchlistStoreError):
                list_watchlist_entries(self.store_path, "wallet-1")
        self.assertTrue(self.store_path.exists())
        corrupt_after = list(Path(self.tmp.name).glob("watchlists.json.corrupt.*"))
        self.assertEqual(corrupt_before, corrupt_after)

    def test_save_failure_wraps_error(self):
        with patch(
            "plugins_func.functions.ave_watchlist_store.tempfile.NamedTemporaryFile",
            side_effect=OSError("no disk"),
        ):
            with self.assertRaises(WatchlistStoreError):
                add_watchlist_entry(
                    self.store_path,
                    "wallet-1",
                    {"addr": "So111", "chain": "solana", "symbol": "BONK"},
                )
        tmp_glob = list(Path(self.tmp.name).glob("watchlists.json.tmp.*"))
        self.assertFalse(tmp_glob)

    def test_mkdir_failure_wrapped(self):
        with patch("pathlib.Path.mkdir", side_effect=OSError("mkdir fail")):
            with self.assertRaises(WatchlistStoreError):
                add_watchlist_entry(
                    self.store_path,
                    "wallet-1",
                    {"addr": "So111", "chain": "solana", "symbol": "BONK"},
                )
        tmp_files = list(Path(self.tmp.name).glob("watchlists.json.tmp.*"))
        self.assertFalse(tmp_files)

    def test_dump_failure_cleanup(self):
        with patch(
            "plugins_func.functions.ave_watchlist_store.json.dump",
            side_effect=OSError("dump fail"),
        ):
            with self.assertRaises(WatchlistStoreError):
                add_watchlist_entry(
                    self.store_path,
                    "wallet-1",
                    {"addr": "So111", "chain": "solana", "symbol": "BONK"},
                )
        tmp_files = list(Path(self.tmp.name).glob("watchlists.json.tmp.*"))
        self.assertFalse(tmp_files)

    def test_remove_only_affects_matching_namespace(self):
        add_watchlist_entry(self.store_path, "wallet-1", {"addr": "So111", "chain": "solana", "symbol": "BONK"})
        add_watchlist_entry(self.store_path, "wallet-2", {"addr": "So111", "chain": "solana", "symbol": "BONK"})

        removed = remove_watchlist_entry(self.store_path, "wallet-1", "So111", "solana")

        self.assertTrue(removed)
        self.assertEqual(list_watchlist_entries(self.store_path, "wallet-1"), [])
        self.assertEqual(len(list_watchlist_entries(self.store_path, "wallet-2")), 1)


if __name__ == "__main__":
    unittest.main()
