"""Offscreen GUI tests for the TempBox main window.

These run with Qt's "offscreen" platform plugin so they do not open windows on
the developer's desktop. Menu bar interaction itself is verified manually.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QApplication

from tempbox.storage import RETENTION_OPTIONS, FileStore
from tempbox.window import ExpiryDialog, MainWindow


class MainWindowTest(unittest.TestCase):
    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tempbox-window-test-")
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.data_dir = base / "data"
        self.source_dir = base / "sources"
        self.source_dir.mkdir()
        self.store = FileStore(self.data_dir)
        self.store.load()
        self.window = MainWindow(self.store)

    # -- helpers -------------------------------------------------------

    def _make_source(self, name: str, content: bytes = b"window test content") -> Path:
        path = self.source_dir / name
        path.write_bytes(content)
        return path

    def _mime_for(self, *paths: Path) -> QMimeData:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        return mime

    def _drop(self, *paths: Path) -> QDropEvent:
        mime = self._mime_for(*paths)  # keep alive while the event is processed
        event = QDropEvent(
            QPointF(10, 10),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.window.dropEvent(event)
        return event

    def _import_record(self, name: str):
        self._drop(self._make_source(name))
        return self.store.list_files()[0]

    # -- empty state ---------------------------------------------------

    def test_empty_state(self) -> None:
        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertEqual(self.window.count_label.text(), "0 files")
        self.assertIs(self.window.content.currentWidget(), self.window.empty_label)
        self.assertFalse(self.window.open_button.isEnabled())
        self.assertFalse(self.window.restore_button.isEnabled())
        self.assertFalse(self.window.retention_button.isEnabled())

    # -- drag and drop -------------------------------------------------

    def test_drag_enter_accepts_file_urls_and_highlights(self) -> None:
        source = self._make_source("drag.txt")
        mime = self._mime_for(source)  # keep alive while the event is processed
        event = QDragEnterEvent(
            QPointF(10, 10),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.window.dragEnterEvent(event)

        self.assertTrue(event.isAccepted())
        self.assertTrue(self.window.drop_zone.property("dragging"))
        self.window.dragLeaveEvent(QDragLeaveEvent())
        self.assertFalse(self.window.drop_zone.property("dragging"))

    def test_drag_enter_ignores_plain_text(self) -> None:
        mime = QMimeData()
        mime.setText("not a file")
        event = QDragEnterEvent(
            QPointF(10, 10),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.window.dragEnterEvent(event)

        self.assertFalse(event.isAccepted())
        self.assertFalse(self.window.drop_zone.property("dragging"))

    def test_drop_single_file_updates_window(self) -> None:
        source = self._make_source("notes.txt", b"hello")

        event = self._drop(source)

        self.assertTrue(event.isAccepted())
        self.assertFalse(source.exists())
        self.assertEqual(len(self.store.list_files()), 1)
        self.assertEqual(self.window.table.rowCount(), 1)
        self.assertEqual(self.window.table.item(0, 0).text(), "notes.txt")
        self.assertEqual(self.window.count_label.text(), "1 file")
        self.assertIs(self.window.content.currentWidget(), self.window.table)
        self.assertIn("Imported 1 file", self.window.status_label.text())

    def test_drop_multiple_files(self) -> None:
        first = self._make_source("one.txt")
        second = self._make_source("two.txt")

        self._drop(first, second)

        self.assertEqual(self.window.table.rowCount(), 2)
        self.assertEqual(self.window.count_label.text(), "2 files")
        names = {self.window.table.item(row, 0).text() for row in range(2)}
        self.assertEqual(names, {"one.txt", "two.txt"})
        self.assertIn("Imported 2 files", self.window.status_label.text())

    def test_drop_folder_reports_failure(self) -> None:
        folder = self.source_dir / "a-folder"
        folder.mkdir()

        self._drop(folder)

        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertIs(self.window.content.currentWidget(), self.window.empty_label)
        status = self.window.status_label.text()
        self.assertIn("Skipped", status)
        self.assertIn("regular files", status)
        self.assertTrue(folder.is_dir())

    # -- selection and restore -----------------------------------------

    def test_selection_enables_actions(self) -> None:
        source = self._make_source("select.txt")
        self._drop(source)

        self.assertFalse(self.window.open_button.isEnabled())
        self.window.table.selectRow(0)

        self.assertTrue(self.window.open_button.isEnabled())
        self.assertTrue(self.window.reveal_button.isEnabled())
        self.assertTrue(self.window.restore_button.isEnabled())
        self.assertTrue(self.window.retention_button.isEnabled())

    def test_restore_updates_window_and_file(self) -> None:
        source = self._make_source("restore.txt", b"restore me")
        self._drop(source)
        record = self.store.list_files()[0]
        target = Path(record.original_path)

        self.window._restore_to(record, target)

        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(), b"restore me")
        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertEqual(self.window.count_label.text(), "0 files")
        self.assertIs(self.window.content.currentWidget(), self.window.empty_label)
        self.assertIn("Restored", self.window.status_label.text())
        self.assertEqual(self.store.list_files(), [])


    # -- Phase 2: retention and expiry --------------------------------

    def test_import_defaults_to_one_day(self) -> None:
        record = self._import_record("default.txt")

        self.assertIsNotNone(record.expires_at)
        expires_at = datetime.fromisoformat(record.expires_at)
        self.assertGreater(expires_at, datetime.now(timezone.utc) + timedelta(hours=23))
        self.assertNotEqual(self.window.table.item(0, 3).text(), "—")
        self.assertIn("day", self.window.table.item(0, 4).text())
    def test_preset_durations_update_expiry(self) -> None:
        record = self._import_record("presets.txt")
        self.window.table.selectRow(0)
        for _label, duration in RETENTION_OPTIONS:
            started = datetime.now(timezone.utc)
            self.window._set_retention(duration)
            updated = self.store.get(record.id)
            expires_at = datetime.fromisoformat(updated.expires_at)
            self.assertGreaterEqual(
                expires_at, started + duration - timedelta(seconds=2)
            )
            self.assertLessEqual(
                expires_at,
                datetime.now(timezone.utc) + duration + timedelta(seconds=2),
            )


    def test_remaining_display_formats(self) -> None:
        record = self._import_record("format.txt")
        cases = (
            (timedelta(days=3), "3 days left"),
            (timedelta(hours=12), "12 hours left"),
            (timedelta(minutes=35), "35 minutes left"),
        )
        for delta, expected in cases:
            self.store.set_expiry(record.id, datetime.now(timezone.utc) + delta)
            self.window._refresh()
            self.assertEqual(self.window.table.item(0, 4).text(), expected)
        self.store.set_expiry(record.id, datetime.now(timezone.utc) - timedelta(minutes=1))
        self.window._refresh()
        self.assertEqual(self.window.table.item(0, 4).text(), "Expired")

    def test_retention_updates_expiry_and_row(self) -> None:
        self._drop(self._make_source("retention.txt"))
        self.window.table.selectRow(0)
        started = datetime.now(timezone.utc)

        self.window._set_retention(timedelta(days=7))

        record = self.store.list_files()[0]
        expires_at = datetime.fromisoformat(record.expires_at)
        self.assertGreaterEqual(
            expires_at, started + timedelta(days=7) - timedelta(seconds=2)
        )
        self.assertLessEqual(
            expires_at, datetime.now(timezone.utc) + timedelta(days=7) + timedelta(seconds=2)
        )
        self.assertIn("days left", self.window.table.item(0, 4).text())
        self.assertIn("expires", self.window.status_label.text())

    def test_historical_record_shows_no_expiry(self) -> None:
        record = self._import_record("legacy.txt")
        self.store.records[record.id] = replace(record, expires_at=None)

        self.window._refresh()

        self.assertEqual(self.window.table.item(0, 4).text(), "No expiry")
        self.assertEqual(self.window.table.item(0, 3).text(), "—")

    def test_cleanup_removes_expired_file_from_list(self) -> None:
        record = self._import_record("expired.txt")
        self.store.set_expiry(record.id, datetime.now(timezone.utc) - timedelta(minutes=1))

        with mock.patch(
            "tempbox.storage.send2trash", side_effect=lambda path: Path(path).unlink()
        ):
            self.window._run_cleanup()

        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertEqual(self.store.list_files(), [])
        self.assertIn("Trash", self.window.status_label.text())

    def test_startup_cleanup_runs_on_window_creation(self) -> None:
        record = self._import_record("startup.txt")
        self.store.set_expiry(record.id, datetime.now(timezone.utc) - timedelta(minutes=1))

        with mock.patch(
            "tempbox.storage.send2trash", side_effect=lambda path: Path(path).unlink()
        ):
            window = MainWindow(self.store)
        self.addCleanup(window.deleteLater)

        self.assertEqual(window.table.rowCount(), 0)
        self.assertEqual(self.store.list_files(), [])
        self.assertIn("Trash", window.status_label.text())

    def test_cleanup_timer_is_configured(self) -> None:
        self.assertTrue(self.window._cleanup_timer.isActive())
        self.assertEqual(self.window._cleanup_timer.interval(), 30_000)

    def test_custom_expiry_dialog_returns_utc_future_time(self) -> None:
        dialog = ExpiryDialog(None, self.window)
        self.addCleanup(dialog.deleteLater)

        expiry = dialog.selected_expiry()

        self.assertIsNotNone(expiry.tzinfo)
        self.assertEqual(expiry.utcoffset(), timedelta(0))
        self.assertGreater(expiry, datetime.now(timezone.utc) + timedelta(hours=23))


if __name__ == "__main__":
    unittest.main()
