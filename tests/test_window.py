"""Offscreen GUI tests for the TempBox main window.

These run with Qt's "offscreen" platform plugin so they do not open windows on
the developer's desktop. Menu bar interaction itself is verified manually.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QItemSelectionModel, QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QApplication

from tempbox.storage import RETENTION_OPTIONS, FileStore
from tempbox.app import _toggle_window
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

    def _select_rows(self, *rows: int) -> None:
        model = self.window.table.selectionModel()
        model.clearSelection()
        for row in rows:
            index = self.window.table.model().index(row, 0)
            model.select(
                index,
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows,
            )

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
        self.assertTrue(self.window.count_label.text().startswith("1 file"))
        self.assertIn("5 B", self.window.count_label.text())
        self.assertIs(self.window.content.currentWidget(), self.window.table)
        self.assertIn("Imported 1 file", self.window.status_label.text())

    def test_drop_multiple_files(self) -> None:
        first = self._make_source("one.txt")
        second = self._make_source("two.txt")

        self._drop(first, second)

        self.assertEqual(self.window.table.rowCount(), 2)
        self.assertTrue(self.window.count_label.text().startswith("2 files"))
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


    # -- Phase 3: stats, search, sort, batch, settings -----------------

    def test_header_shows_count_and_total_size(self) -> None:
        self._drop(
            self._make_source("a.bin", b"x" * 1024),
            self._make_source("b.bin", b"y" * 1024),
        )

        text = self.window.count_label.text()

        self.assertIn("2 files", text)
        self.assertIn("2.0 KB", text)

    def test_search_filters_files(self) -> None:
        self._drop(
            self._make_source("alpha.txt"),
            self._make_source("beta.txt"),
            self._make_source("alphabet.txt"),
        )

        self.window.search_edit.setText("alpha")
        self.assertEqual(self.window.table.rowCount(), 2)

        self.window.search_edit.setText("ALPHA")
        self.assertEqual(self.window.table.rowCount(), 2)

        self.window.search_edit.setText("zzz")
        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertEqual(self.window.empty_label.text(), "No files match your search.")

        self.window.search_edit.clear()
        self.assertEqual(self.window.table.rowCount(), 3)

    def test_sort_changes_row_order(self) -> None:
        self._drop(
            self._make_source("beta.txt", b"22"),
            self._make_source("alpha.txt", b"1"),
            self._make_source("gamma.txt", b"333"),
        )

        self.window.sort_combo.setCurrentIndex(self.window.sort_combo.findData("name"))
        names = [self.window.table.item(row, 0).text() for row in range(3)]
        self.assertEqual(names, ["alpha.txt", "beta.txt", "gamma.txt"])

        self.window.sort_combo.setCurrentIndex(self.window.sort_combo.findData("size"))
        names = [self.window.table.item(row, 0).text() for row in range(3)]
        self.assertEqual(names, ["gamma.txt", "beta.txt", "alpha.txt"])

    def test_sort_by_expiry_puts_no_expiry_last(self) -> None:
        self._drop(
            self._make_source("later.txt"),
            self._make_source("soon.txt"),
            self._make_source("never.txt"),
        )
        records = {record.original_name: record for record in self.store.list_files()}
        self.store.set_expiry(
            records["soon.txt"].id, datetime.now(timezone.utc) + timedelta(hours=1)
        )
        self.store.set_expiry(
            records["later.txt"].id, datetime.now(timezone.utc) + timedelta(days=3)
        )
        self.store.records[records["never.txt"].id] = replace(
            records["never.txt"], expires_at=None
        )

        self.window.sort_combo.setCurrentIndex(self.window.sort_combo.findData("expires"))
        names = [self.window.table.item(row, 0).text() for row in range(3)]

        self.assertEqual(names, ["soon.txt", "later.txt", "never.txt"])

    def test_batch_expiry_updates_selected_files(self) -> None:
        self._drop(
            self._make_source("one.txt"),
            self._make_source("two.txt"),
            self._make_source("three.txt"),
        )
        self._select_rows(0, 1)
        selected_ids = {record.id for record in self.window._selected_records()}
        self.assertEqual(len(selected_ids), 2)

        started = datetime.now(timezone.utc)
        self.window._set_retention(timedelta(days=7))

        for record in self.store.list_files():
            expires_at = datetime.fromisoformat(record.expires_at)
            if record.id in selected_ids:
                self.assertGreaterEqual(
                    expires_at, started + timedelta(days=7) - timedelta(seconds=2)
                )
            else:
                self.assertGreater(
                    expires_at, datetime.now(timezone.utc) + timedelta(hours=23)
                )
        self.assertEqual(len(self.window._selected_records()), 2)
        self.assertIn("2 files", self.window.status_label.text())

    def test_batch_restore_restores_selected_files(self) -> None:
        first = self._make_source("r1.txt", b"one")
        second = self._make_source("r2.txt", b"two")
        self._drop(first, second)
        self._select_rows(0, 1)

        self.window._restore_selected()

        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())
        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertEqual(self.store.list_files(), [])
        self.assertIn("Restored 2 files", self.window.status_label.text())

    def test_batch_restore_reports_partial_failure(self) -> None:
        first = self._make_source("keep.txt", b"one")
        second = self._make_source("lost.txt", b"two")
        self._drop(first, second)
        lost = next(
            record for record in self.store.list_files() if record.original_name == "lost.txt"
        )
        self.store.stored_path(lost).unlink()
        self.window._refresh()
        self._select_rows(0, 1)

        with mock.patch("tempbox.window.QMessageBox.warning") as warning:
            self.window._restore_selected()

        warning.assert_called_once()
        self.assertTrue(first.is_file())
        self.assertFalse(second.exists())
        self.assertEqual(len(self.store.list_files()), 1)
        status = self.window.status_label.text()
        self.assertIn("Restored 1 file", status)
        self.assertIn("1 file failed", status)

    def test_context_menu_contains_file_actions(self) -> None:
        self._drop(self._make_source("menu.txt"))
        self.window.table.selectRow(0)

        menu = self.window._build_context_menu()
        self.addCleanup(menu.deleteLater)
        texts = [action.text() for action in menu.actions()]

        self.assertIn("Open", texts)
        self.assertIn("Show in Finder", texts)
        self.assertIn("Restore", texts)
        self.assertIn("Change Expiration", texts)

    def test_default_retention_setting_persists_and_only_affects_new_files(self) -> None:
        old = self._import_record("old.txt")

        self.window.set_default_retention(timedelta(hours=1))

        self.assertEqual(self.store.get(old.id).expires_at, old.expires_at)
        settings_path = self.store.root / "settings.json"
        self.assertTrue(settings_path.is_file())

        self._drop(self._make_source("new.txt"))
        new = next(
            record for record in self.store.list_files() if record.original_name == "new.txt"
        )
        expires_at = datetime.fromisoformat(new.expires_at)
        self.assertGreaterEqual(
            expires_at, datetime.now(timezone.utc) + timedelta(minutes=59)
        )
        self.assertLessEqual(
            expires_at, datetime.now(timezone.utc) + timedelta(hours=1, minutes=1)
        )

        from tempbox.settings import AppSettings

        self.assertEqual(
            AppSettings.load(self.store.root).default_retention, timedelta(hours=1)
        )

    def test_settings_dialog_shows_current_default(self) -> None:
        from tempbox.window import SettingsDialog

        self.window.set_default_retention(timedelta(days=7))
        with mock.patch("tempbox.window.autostart.is_enabled", return_value=False):
            dialog = SettingsDialog(self.window)
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(dialog.retention_combo.currentText(), "7 days")
        self.assertFalse(dialog.autostart_checkbox.isChecked())

    def test_application_deactivate_hides_window(self) -> None:
        self.window.show()
        QApplication.processEvents()
        self.assertTrue(self.window.isVisible())

        self.window._on_application_state_changed(Qt.ApplicationState.ApplicationInactive)

        self.assertFalse(self.window.isVisible())

    def test_tray_click_after_auto_hide_stays_hidden(self) -> None:
        self.window.show()
        QApplication.processEvents()
        # Clicking the menu bar icon can deactivate the app just before the tray
        # activation is delivered; the toggle must still hide (not re-show).
        self.window._on_application_state_changed(Qt.ApplicationState.ApplicationInactive)
        self.assertFalse(self.window.isVisible())

        with mock.patch("tempbox.app.activate_application"), mock.patch(
            "tempbox.app._position_window"
        ):
            _toggle_window(self.window, None)
        self.assertFalse(self.window.isVisible())

        with mock.patch("tempbox.app.activate_application"), mock.patch(
            "tempbox.app._position_window"
        ):
            _toggle_window(self.window, None)
        self.assertTrue(self.window.isVisible())

    def test_stale_auto_hide_marker_allows_reopen(self) -> None:
        self.window.show()
        QApplication.processEvents()
        self.window.hide()
        self.window._auto_hidden_at = time.monotonic() - 2.0

        with mock.patch("tempbox.app.activate_application"), mock.patch(
            "tempbox.app._position_window"
        ):
            _toggle_window(self.window, None)

        self.assertTrue(self.window.isVisible())


if __name__ == "__main__":
    unittest.main()
