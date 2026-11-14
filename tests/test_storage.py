"""Headless tests for TempBox file storage."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from tempbox.storage import (
    DEFAULT_RETENTION,
    RETENTION_OPTIONS,
    FileStore,
    FileRecord,
    StorageError,
)


class FileStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tempbox-test-")
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.data_dir = base / "data"
        self.source_dir = base / "sources"
        self.source_dir.mkdir()
        self.store = FileStore(self.data_dir)
        self.store.load()

    # -- helpers -------------------------------------------------------

    def _make_source(
        self,
        name: str,
        content: bytes = b"tempbox test content",
        directory: Path | None = None,
    ) -> Path:
        directory = directory or self.source_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_bytes(content)
        return path

    def _reload(self) -> FileStore:
        store = FileStore(self.data_dir)
        store.load()
        return store

    def _import_expired(
        self, name: str = "expired.txt", content: bytes = b"expired"
    ) -> FileRecord:
        source = self._make_source(name, content)
        record = self.store.import_files([source]).added[0]
        return self.store.set_expiry(
            record.id, datetime.now(timezone.utc) - timedelta(minutes=1)
        )

    # -- importing -----------------------------------------------------

    def test_import_moves_file_and_records_metadata(self) -> None:
        source = self._make_source("notes.txt", b"content-123")
        original_path = str(source.absolute())

        result = self.store.import_files([source])

        self.assertEqual(result.failed, [])
        self.assertEqual(len(result.added), 1)
        record = result.added[0]
        self.assertFalse(source.exists())
        stored = self.store.stored_path(record)
        self.assertTrue(stored.is_file())
        self.assertEqual(stored.read_bytes(), b"content-123")
        self.assertEqual(record.original_name, "notes.txt")
        self.assertEqual(record.original_path, original_path)
        self.assertEqual(record.size, len(b"content-123"))
        self.assertEqual(record.stored_relative_path, f"files/{record.id}/notes.txt")
        datetime.fromisoformat(record.added_at)
        self.assertIsNotNone(record.expires_at)
        self.assertIsNone(record.trash_error)
        expires_at = datetime.fromisoformat(record.expires_at)
        self.assertGreater(expires_at, datetime.now(timezone.utc) + timedelta(hours=23))
        self.assertLess(expires_at, datetime.now(timezone.utc) + timedelta(hours=25))

        payload = json.loads((self.data_dir / "records.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 2)
        self.assertEqual([item["id"] for item in payload["files"]], [record.id])
        self.assertEqual(payload["files"][0]["expires_at"], record.expires_at)
        self.assertFalse((self.data_dir / "records.json.tmp").exists())

    def test_import_multiple_files(self) -> None:
        first = self._make_source("one.txt", b"one")
        second = self._make_source("two.txt", b"two")

        result = self.store.import_files([first, second])

        self.assertEqual(len(result.added), 2)
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())
        contents = sorted(self.store.stored_path(record).read_bytes() for record in result.added)
        self.assertEqual(contents, [b"one", b"two"])

    def test_import_same_named_files_are_kept_apart(self) -> None:
        first = self._make_source("report.pdf", b"first", self.source_dir / "a")
        second = self._make_source("report.pdf", b"second", self.source_dir / "b")

        result = self.store.import_files([first, second])

        self.assertEqual(len(result.added), 2)
        self.assertNotEqual(result.added[0].id, result.added[1].id)
        contents = sorted(self.store.stored_path(record).read_bytes() for record in result.added)
        self.assertEqual(contents, [b"first", b"second"])
        self.assertEqual(len(self._reload().list_files()), 2)

    def test_import_reports_unsupported_sources_and_keeps_them(self) -> None:
        directory = self.source_dir / "a-folder"
        directory.mkdir()
        target = self._make_source("real.txt")
        symlink = self.source_dir / "link.txt"
        symlink.symlink_to(target)
        missing = self.source_dir / "missing.txt"

        result = self.store.import_files([directory, symlink, missing])

        self.assertEqual(result.added, [])
        self.assertEqual(len(result.failed), 3)
        self.assertTrue(directory.is_dir())
        self.assertTrue(symlink.is_symlink())
        self.assertTrue(target.is_file())
        self.assertEqual(self.store.list_files(), [])

    def test_import_partial_failure(self) -> None:
        good = self._make_source("good.txt")
        directory = self.source_dir / "bad"
        directory.mkdir()

        result = self.store.import_files([good, directory])

        self.assertEqual(len(result.added), 1)
        self.assertEqual(len(result.failed), 1)
        self.assertTrue(self.store.stored_path(result.added[0]).is_file())
        self.assertFalse(good.exists())

    def test_import_rejects_files_already_inside_tempbox(self) -> None:
        source = self._make_source("inside.txt")
        record = self.store.import_files([source]).added[0]
        stored = self.store.stored_path(record)

        result = self.store.import_files([stored])

        self.assertEqual(result.added, [])
        self.assertEqual(len(result.failed), 1)
        self.assertTrue(stored.is_file())
        self.assertEqual(len(self.store.list_files()), 1)

    def test_import_rolls_back_when_index_cannot_be_saved(self) -> None:
        source = self._make_source("rollback.txt", b"rollback data")

        with mock.patch.object(FileStore, "_save", side_effect=OSError("disk full")):
            result = self.store.import_files([source])

        self.assertEqual(result.added, [])
        self.assertEqual(len(result.failed), 1)
        self.assertTrue(source.is_file())
        self.assertEqual(source.read_bytes(), b"rollback data")
        self.assertEqual(self.store.list_files(), [])
        files_dir = self.data_dir / "files"
        self.assertEqual(list(files_dir.iterdir()) if files_dir.exists() else [], [])

    # -- persistence ---------------------------------------------------

    def test_records_survive_reload(self) -> None:
        source = self._make_source("keep.txt", b"keep me")
        record = self.store.import_files([source]).added[0]

        reloaded = self._reload()

        self.assertEqual(reloaded.list_files(), [record])
        self.assertTrue(reloaded.stored_path(reloaded.list_files()[0]).is_file())

    def test_damaged_index_is_backed_up_and_reported(self) -> None:
        self.data_dir.mkdir(parents=True)
        (self.data_dir / "records.json").write_text("{ not json", encoding="utf-8")

        store = FileStore(self.data_dir)
        problems = store.load()

        self.assertEqual(store.list_files(), [])
        self.assertEqual(len(problems), 1)
        self.assertIn("backed up", problems[0])
        backups = list(self.data_dir.glob("records.corrupt-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "{ not json")
        self.assertFalse((self.data_dir / "records.json").exists())

        # The app can keep saving after the damaged index was moved aside.
        source = self._make_source("after.txt")
        self.assertEqual(len(store.import_files([source]).added), 1)
        self.assertEqual(len(self._reload().list_files()), 1)

    def test_unexpected_index_structure_is_backed_up(self) -> None:
        self.data_dir.mkdir(parents=True)
        (self.data_dir / "records.json").write_text(
            json.dumps({"version": 99, "files": []}), encoding="utf-8"
        )

        store = FileStore(self.data_dir)

        self.assertEqual(len(store.load()), 1)
        self.assertEqual(len(list(self.data_dir.glob("records.corrupt-*.json"))), 1)
        self.assertEqual(store.list_files(), [])

    def test_missing_stored_file_is_reported_but_record_kept(self) -> None:
        source = self._make_source("missing.txt")
        record = self.store.import_files([source]).added[0]
        self.store.stored_path(record).unlink()

        reloaded = self._reload()

        problems = reloaded.load()
        self.assertEqual(len(reloaded.list_files()), 1)
        self.assertTrue(any("missing" in problem for problem in problems))
        payload = json.loads((self.data_dir / "records.json").read_text(encoding="utf-8"))
        self.assertEqual(len(payload["files"]), 1)

    def test_unknown_files_inside_store_are_not_deleted(self) -> None:
        orphan = self.data_dir / "files" / "orphan" / "stray.bin"
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b"stray")

        store = FileStore(self.data_dir)
        store.load()

        self.assertEqual(store.list_files(), [])
        self.assertTrue(orphan.is_file())

    # -- restoring -----------------------------------------------------

    def test_restore_returns_file_to_original_path(self) -> None:
        source = self._make_source("photo.jpg", b"jpeg-data")
        record = self.store.import_files([source]).added[0]
        stored_dir = self.store.stored_path(record).parent

        restored = self.store.restore(record.id, record.original_path)

        self.assertEqual(restored, Path(record.original_path))
        self.assertTrue(source.is_file())
        self.assertEqual(source.read_bytes(), b"jpeg-data")
        self.assertEqual(self.store.list_files(), [])
        self.assertFalse(stored_dir.exists())
        self.assertEqual(self._reload().list_files(), [])

    def test_restore_refuses_to_overwrite_existing_file(self) -> None:
        source = self._make_source("conflict.txt", b"tempbox copy")
        record = self.store.import_files([source]).added[0]
        source.write_bytes(b"existing file")

        with self.assertRaises(StorageError):
            self.store.restore(record.id, record.original_path)

        self.assertEqual(source.read_bytes(), b"existing file")
        self.assertTrue(self.store.stored_path(record).is_file())
        self.assertEqual(self.store.list_files(), [record])

    def test_restore_to_chosen_folder_when_original_is_gone(self) -> None:
        original_dir = self.source_dir / "nested"
        source = self._make_source("doc.txt", b"document", original_dir)
        record = self.store.import_files([source]).added[0]
        original_dir.rmdir()
        chosen_dir = self.source_dir / "chosen"
        chosen_dir.mkdir()
        target = chosen_dir / record.original_name

        restored = self.store.restore(record.id, target)

        self.assertEqual(restored, target)
        self.assertEqual(target.read_bytes(), b"document")
        self.assertEqual(self.store.list_files(), [])

    def test_restore_keeps_record_when_stored_file_is_gone(self) -> None:
        source = self._make_source("gone.txt")
        record = self.store.import_files([source]).added[0]
        self.store.stored_path(record).unlink()

        with self.assertRaises(StorageError):
            self.store.restore(record.id, record.original_path)

        self.assertEqual(self.store.list_files(), [record])

    def test_failed_restore_keeps_record_and_stored_file(self) -> None:
        source = self._make_source("readonly.txt", b"keep me safe")
        record = self.store.import_files([source]).added[0]
        target_dir = source.parent
        target_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            with self.assertRaises(StorageError):
                self.store.restore(record.id, record.original_path)
        finally:
            target_dir.chmod(stat.S_IRWXU)

        self.assertTrue(self.store.stored_path(record).is_file())
        self.assertEqual(self.store.list_files(), [record])
        self.assertFalse(source.exists())

    def test_restore_rolls_back_when_index_cannot_be_saved(self) -> None:
        source = self._make_source("rollback-restore.txt", b"data")
        record = self.store.import_files([source]).added[0]

        with mock.patch.object(FileStore, "_save", side_effect=OSError("disk full")):
            with self.assertRaises(StorageError):
                self.store.restore(record.id, record.original_path)

        self.assertTrue(self.store.stored_path(record).is_file())
        self.assertEqual(self.store.list_files(), [record])
        self.assertFalse(source.exists())

    # -- cross-device moves --------------------------------------------

    @mock.patch("tempbox.storage._is_same_device", return_value=False)
    def test_import_across_devices_copies_then_removes_source(self, _same_device: mock.Mock) -> None:
        source = self._make_source("cross.bin", b"cross-volume")

        result = self.store.import_files([source])

        self.assertEqual(len(result.added), 1)
        self.assertFalse(source.exists())
        self.assertEqual(self.store.stored_path(result.added[0]).read_bytes(), b"cross-volume")

    @mock.patch("tempbox.storage._is_same_device", return_value=False)
    def test_restore_across_devices_copies_then_removes_stored_file(
        self, _same_device: mock.Mock
    ) -> None:
        source = self._make_source("cross-restore.txt", b"data")
        record = self.store.import_files([source]).added[0]

        with mock.patch("tempbox.storage._is_same_device", return_value=False):
            self.store.restore(record.id, record.original_path)

        self.assertEqual(source.read_bytes(), b"data")
        self.assertEqual(self.store.list_files(), [])

    @mock.patch("tempbox.storage._is_same_device", return_value=False)
    @mock.patch("tempbox.storage.shutil.copy2", side_effect=OSError("disk full"))
    def test_failed_cross_device_copy_keeps_source(
        self, _copy2: mock.Mock, _same_device: mock.Mock
    ) -> None:
        source = self._make_source("copy-fail.bin", b"important")

        result = self.store.import_files([source])

        self.assertEqual(result.added, [])
        self.assertEqual(len(result.failed), 1)
        self.assertTrue(source.is_file())
        self.assertEqual(source.read_bytes(), b"important")
        self.assertEqual(self.store.list_files(), [])
        files_dir = self.data_dir / "files"
        self.assertEqual(list(files_dir.iterdir()) if files_dir.exists() else [], [])


    # -- Phase 2: retention -------------------------------------------

    def test_retention_presets_and_default(self) -> None:
        self.assertEqual(DEFAULT_RETENTION, timedelta(days=1))
        self.assertEqual(
            [duration for _label, duration in RETENTION_OPTIONS],
            [
                timedelta(hours=1),
                timedelta(days=1),
                timedelta(days=7),
                timedelta(days=30),
            ],
        )

    def test_set_expiry_saves_and_survives_reload(self) -> None:
        source = self._make_source("retain.txt")
        record = self.store.import_files([source]).added[0]
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        updated = self.store.set_expiry(record.id, expires_at)

        self.assertEqual(updated.added_at, record.added_at)
        self.assertEqual(
            datetime.fromisoformat(updated.expires_at), expires_at.replace(microsecond=0)
        )
        self.assertIsNone(updated.trash_error)
        reloaded = self._reload().get(record.id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.expires_at, updated.expires_at)

    def test_set_expiry_requires_time_zone(self) -> None:
        source = self._make_source("naive.txt")
        record = self.store.import_files([source]).added[0]

        with self.assertRaises(StorageError):
            self.store.set_expiry(record.id, datetime.now())

        self.assertEqual(self.store.get(record.id).expires_at, record.expires_at)

    def test_set_expiry_clears_cleanup_error(self) -> None:
        record = self._import_expired("retry.txt")
        with mock.patch("tempbox.storage.send2trash", side_effect=OSError("denied")):
            self.store.cleanup_expired()
        self.assertIsNotNone(self.store.get(record.id).trash_error)

        updated = self.store.set_expiry(
            record.id, datetime.now(timezone.utc) + timedelta(hours=2)
        )

        self.assertIsNone(updated.trash_error)
        self.assertIsNone(self._reload().get(record.id).trash_error)

    # -- Phase 2: clean-up --------------------------------------------

    def test_cleanup_skips_unexpired_and_records_without_expiry(self) -> None:
        source = self._make_source("later.txt")
        record = self.store.import_files([source]).added[0]
        self.store.set_expiry(record.id, datetime.now(timezone.utc) + timedelta(days=2))
        legacy_source = self._make_source("legacy.txt")
        legacy = self.store.import_files([legacy_source]).added[0]
        self.store.records[legacy.id] = replace(legacy, expires_at=None)

        with mock.patch("tempbox.storage.send2trash") as trash:
            result = self.store.cleanup_expired()

        trash.assert_not_called()
        self.assertEqual(result.trashed, [])
        self.assertEqual(len(self.store.list_files()), 2)

    def test_cleanup_moves_expired_file_to_trash(self) -> None:
        record = self._import_expired("old.txt", b"old data")
        stored = self.store.stored_path(record)

        with mock.patch(
            "tempbox.storage.send2trash", side_effect=lambda path: Path(path).unlink()
        ) as trash:
            result = self.store.cleanup_expired()

        self.assertEqual(len(result.trashed), 1)
        self.assertEqual(result.failed, [])
        trash.assert_called_once_with(str(stored))
        self.assertFalse(stored.exists())
        self.assertEqual(self.store.list_files(), [])
        self.assertEqual(self._reload().list_files(), [])

    def test_cleanup_failure_keeps_record_and_error(self) -> None:
        record = self._import_expired("stuck.txt")

        with mock.patch("tempbox.storage.send2trash", side_effect=OSError("permission denied")):
            result = self.store.cleanup_expired()

        self.assertEqual(result.trashed, [])
        self.assertEqual(len(result.failed), 1)
        kept = self.store.get(record.id)
        self.assertIsNotNone(kept)
        self.assertIn("permission denied", kept.trash_error)
        self.assertTrue(self.store.stored_path(kept).is_file())
        reloaded = self._reload().get(record.id)
        self.assertIn("permission denied", reloaded.trash_error)

    def test_cleanup_missing_file_is_kept_and_reported(self) -> None:
        record = self._import_expired("lost.txt")
        self.store.stored_path(record).unlink()

        with mock.patch("tempbox.storage.send2trash") as trash:
            result = self.store.cleanup_expired()

        trash.assert_not_called()
        self.assertEqual(len(result.missing), 1)
        self.assertEqual(result.trashed, [])
        kept = self.store.get(record.id)
        self.assertIsNotNone(kept)
        self.assertIn("missing", kept.trash_error)
        self.assertEqual(len(self.store.list_files()), 1)

    def test_cleanup_multiple_files_are_independent(self) -> None:
        first = self._import_expired("first.txt")
        second = self._import_expired("second.txt")

        def fake_trash(path: str) -> None:
            if path.endswith("first.txt"):
                raise OSError("first is stuck")
            Path(path).unlink()

        with mock.patch("tempbox.storage.send2trash", side_effect=fake_trash):
            result = self.store.cleanup_expired()

        self.assertEqual(len(result.trashed), 1)
        self.assertEqual(len(result.failed), 1)
        self.assertEqual(result.trashed[0].id, second.id)
        self.assertEqual(len(self.store.list_files()), 1)
        self.assertIsNotNone(self.store.get(first.id))
        self.assertIsNone(self.store.get(second.id))

        with mock.patch(
            "tempbox.storage.send2trash", side_effect=lambda path: Path(path).unlink()
        ):
            retried = self.store.cleanup_expired()

        self.assertEqual(len(retried.trashed), 1)
        self.assertEqual(self.store.list_files(), [])

    def test_cleanup_skips_file_outside_storage(self) -> None:
        record = self._import_expired("tampered.txt")
        stored = self.store.stored_path(record)
        outside = self.data_dir.parent / "outside.txt"
        stored.rename(outside)
        relative = os.path.relpath(outside, self.store.root)
        self.store.records[record.id] = replace(
            record, stored_relative_path=Path(relative).as_posix()
        )

        with mock.patch("tempbox.storage.send2trash") as trash:
            result = self.store.cleanup_expired()

        trash.assert_not_called()
        self.assertEqual(len(result.failed), 1)
        self.assertTrue(outside.is_file())
        self.assertEqual(len(self.store.list_files()), 1)

    def test_cleanup_skips_non_regular_file(self) -> None:
        record = self._import_expired("linked.txt")
        stored = self.store.stored_path(record)
        stored.unlink()
        target = self._make_source("target.txt")
        stored.symlink_to(target)

        with mock.patch("tempbox.storage.send2trash") as trash:
            result = self.store.cleanup_expired()

        trash.assert_not_called()
        self.assertEqual(len(result.failed), 1)
        self.assertTrue(stored.is_symlink())
        self.assertEqual(len(self.store.list_files()), 1)

    def test_cleanup_after_index_save_failure(self) -> None:
        record = self._import_expired("gone.txt")
        stored = self.store.stored_path(record)

        with mock.patch(
            "tempbox.storage.send2trash", side_effect=lambda path: Path(path).unlink()
        ) as trash, mock.patch.object(FileStore, "_save", side_effect=OSError("disk full")):
            result = self.store.cleanup_expired()

        self.assertEqual(len(result.trashed), 1)
        self.assertIsNotNone(result.save_error)
        self.assertFalse(stored.exists())
        self.assertEqual(trash.call_count, 1)

        reloaded = FileStore(self.data_dir)
        problems = reloaded.load()
        self.assertEqual(len(reloaded.list_files()), 1)
        self.assertTrue(any("missing" in problem for problem in problems))
        with mock.patch("tempbox.storage.send2trash") as trash_again:
            second = reloaded.cleanup_expired()
        trash_again.assert_not_called()
        self.assertEqual(len(second.missing), 1)
        self.assertEqual(len(reloaded.list_files()), 1)
    def test_cleanup_after_reload_removes_expired_files(self) -> None:
        self._import_expired("restart.txt")

        reloaded = self._reload()
        self.assertEqual(len(reloaded.list_files()), 1)
        with mock.patch(
            "tempbox.storage.send2trash", side_effect=lambda path: Path(path).unlink()
        ) as trash:
            result = reloaded.cleanup_expired()

        self.assertEqual(len(result.trashed), 1)
        trash.assert_called_once()
        self.assertEqual(reloaded.list_files(), [])


    def test_phase1_index_is_migrated_without_expiry(self) -> None:
        record_id = "phase1record"
        stored_dir = self.data_dir / "files" / record_id
        stored_dir.mkdir(parents=True)
        (stored_dir / "old.txt").write_bytes(b"old")
        phase1_index = {
            "version": 1,
            "files": [
                {
                    "id": record_id,
                    "original_name": "old.txt",
                    "original_path": "/Users/someone/Desktop/old.txt",
                    "stored_relative_path": f"files/{record_id}/old.txt",
                    "size": 3,
                    "added_at": "2024-01-01T10:00:00+08:00",
                }
            ],
        }
        (self.data_dir / "records.json").write_text(
            json.dumps(phase1_index), encoding="utf-8"
        )

        store = FileStore(self.data_dir)
        problems = store.load()

        self.assertEqual(problems, [])
        loaded = store.list_files()[0]
        self.assertIsNone(loaded.expires_at)
        self.assertIsNone(loaded.trash_error)
        with mock.patch("tempbox.storage.send2trash") as trash:
            result = store.cleanup_expired(
                now=datetime.now(timezone.utc) + timedelta(days=3650)
            )
        trash.assert_not_called()
        self.assertEqual(result.trashed, [])
        self.assertEqual(len(store.list_files()), 1)

        store.set_expiry(loaded.id, datetime.now(timezone.utc) + timedelta(days=1))
        payload = json.loads((self.data_dir / "records.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 2)
        self.assertEqual(payload["files"][0]["id"], record_id)


if __name__ == "__main__":
    unittest.main()
