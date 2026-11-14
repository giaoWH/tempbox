"""Tests for the recently-cleaned file history."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tempbox.history import MAX_ENTRIES, CleanupEntry, CleanupHistory
from tempbox.storage import FileRecord


def make_record(index: int = 0, name: str | None = None) -> FileRecord:
    return FileRecord(
        id=f"id-{index}",
        original_name=name or f"file-{index}.txt",
        original_path=f"/Users/example/Desktop/file-{index}.txt",
        stored_relative_path=f"files/id-{index}/file-{index}.txt",
        size=100 + index,
        added_at="2026-11-14T10:00:00+00:00",
        expires_at="2026-11-15T10:00:00+00:00",
    )


class CleanupHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tempbox-history-test-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_missing_history_is_empty(self) -> None:
        history = CleanupHistory(self.root)
        history.load()
        self.assertEqual(history.entries, [])

    def test_add_persists_metadata_and_loads_back(self) -> None:
        history = CleanupHistory(self.root)
        trashed_at = datetime(2026, 11, 15, 9, 30, tzinfo=timezone.utc)

        count = history.add([make_record(1, "report.pdf")], trashed_at=trashed_at)

        self.assertEqual(count, 1)
        self.assertTrue(history.path.is_file())
        reloaded = CleanupHistory(self.root)
        reloaded.load()
        self.assertEqual(len(reloaded.entries), 1)
        entry = reloaded.entries[0]
        self.assertEqual(entry.original_name, "report.pdf")
        self.assertEqual(entry.original_path, "/Users/example/Desktop/file-1.txt")
        self.assertEqual(entry.size, 101)
        self.assertEqual(entry.added_at, "2026-11-14T10:00:00+00:00")
        self.assertEqual(entry.expires_at, "2026-11-15T10:00:00+00:00")
        self.assertEqual(entry.trashed_at, "2026-11-15T09:30:00+00:00")

    def test_newest_entries_come_first_and_are_capped(self) -> None:
        history = CleanupHistory(self.root)
        for index in range(MAX_ENTRIES + 10):
            history.add([make_record(index)])

        self.assertEqual(len(history.entries), MAX_ENTRIES)
        self.assertEqual(history.entries[0].original_name, f"file-{MAX_ENTRIES + 9}.txt")
        self.assertEqual(
            history.entries[-1].original_name, f"file-10.txt"
        )

    def test_clear_empties_history_without_touching_files(self) -> None:
        history = CleanupHistory(self.root)
        history.add([make_record(1)])
        stored_file = self.root / "files" / "id-1" / "file-1.txt"
        stored_file.parent.mkdir(parents=True)
        stored_file.write_text("still here", encoding="utf-8")

        history.clear()

        self.assertEqual(history.entries, [])
        self.assertEqual(CleanupHistory(self.root).entries, [])
        self.assertTrue(stored_file.is_file())
        self.assertEqual(stored_file.read_text(encoding="utf-8"), "still here")

    def test_corrupt_history_is_backed_up(self) -> None:
        path = self.root / "history.json"
        path.write_text("{bad json", encoding="utf-8")

        history = CleanupHistory(self.root)
        history.load()

        self.assertEqual(history.entries, [])
        backups = list(self.root.glob("history.corrupt-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "{bad json")

    def test_invalid_entries_are_skipped(self) -> None:
        path = self.root / "history.json"
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "files": [
                        {"original_name": "bad"},
                        CleanupEntry(
                            original_name="ok.txt",
                            original_path="/tmp/ok.txt",
                            size=1,
                            added_at="2026-11-14T10:00:00+00:00",
                            expires_at=None,
                            trashed_at="2026-11-15T10:00:00+00:00",
                        ).to_dict(),
                    ],
                }
            ),
            encoding="utf-8",
        )

        history = CleanupHistory(self.root)
        history.load()

        self.assertEqual(len(history.entries), 1)
        self.assertEqual(history.entries[0].original_name, "ok.txt")


if __name__ == "__main__":
    unittest.main()
