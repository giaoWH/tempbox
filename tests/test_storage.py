"""Headless tests for TempBox file storage."""

from __future__ import annotations

import json
import stat
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tempbox.storage import FileStore, StorageError


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

        payload = json.loads((self.data_dir / "records.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)
        self.assertEqual([item["id"] for item in payload["files"]], [record.id])
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


if __name__ == "__main__":
    unittest.main()
