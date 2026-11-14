"""Offscreen GUI tests for the TempBox floating panel.

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

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from tempbox.app import _toggle_window
from tempbox.history import CleanupHistory
from tempbox.settings import AppSettings
from tempbox.storage import RETENTION_OPTIONS, FileStore
from tempbox.dialogs import ExpiryDialog, HistoryDialog, SettingsDialog
from tempbox.window import MainWindow


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
        return next(
            record for record in self.store.list_files() if record.original_name == name
        )

    def _row(self, name: str):
        for row in self.window.rows:
            if row.record.original_name == name:
                return row
        raise AssertionError(f"row not found: {name}")

    def _row_names(self) -> list[str]:
        return [row.record.original_name for row in self.window.rows]

    def _select(self, *names: str) -> None:
        self.window.set_selection_mode(True)
        for name in names:
            self.window._on_row_checked(self._row(name), True)

    # -- empty state / window shape -----------------------------------

    def test_empty_state(self) -> None:
        self.assertEqual(self.window.rows, [])
        self.assertEqual(self.window.stats_label.text(), "0 files")
        self.assertIs(self.window.list_stack.currentWidget(), self.window.empty_state)
        self.assertEqual(self.window.empty_state.title_text, "No files yet")
        self.assertEqual(
            self.window.width(), MainWindow.PANEL_WIDTH + MainWindow.SHADOW_MARGIN * 2
        )

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
        self.assertTrue(self.window.drop_zone.is_active())
        self.window.dragLeaveEvent(QDragLeaveEvent())
        self.assertFalse(self.window.drop_zone.is_active())

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
        self.assertFalse(self.window.drop_zone.is_active())

    def test_drop_single_file_updates_panel(self) -> None:
        source = self._make_source("notes.txt", b"hello")

        event = self._drop(source)

        self.assertTrue(event.isAccepted())
        self.assertFalse(source.exists())
        self.assertEqual(len(self.store.list_files()), 1)
        self.assertEqual(len(self.window.rows), 1)
        self.assertEqual(self.window.rows[0].record.original_name, "notes.txt")
        self.assertTrue(self.window.stats_label.text().startswith("1 file"))
        self.assertIn("5 B", self.window.stats_label.text())
        self.assertIs(self.window.list_stack.currentWidget(), self.window.scroll)
        self.assertIn("Imported 1 file", self.window.footer_status.text())

    def test_drop_multiple_files(self) -> None:
        first = self._make_source("one.txt")
        second = self._make_source("two.txt")

        self._drop(first, second)

        self.assertEqual(len(self.window.rows), 2)
        self.assertTrue(self.window.stats_label.text().startswith("2 files"))
        self.assertEqual(set(self._row_names()), {"one.txt", "two.txt"})
        self.assertIn("Imported 2 files", self.window.footer_status.text())

    def test_drop_folder_reports_failure(self) -> None:
        folder = self.source_dir / "a-folder"
        folder.mkdir()

        self._drop(folder)

        self.assertEqual(self.window.rows, [])
        self.assertIs(self.window.list_stack.currentWidget(), self.window.empty_state)
        status = self.window.footer_status.text()
        self.assertIn("Skipped", status)
        self.assertIn("regular files", status)
        self.assertTrue(folder.is_dir())

    # -- row menu / restore --------------------------------------------

    def test_row_menu_contains_file_actions(self) -> None:
        self._import_record("menu.txt")
        menu = self.window._build_row_menu(self.store.list_files()[0])
        self.addCleanup(menu.deleteLater)

        texts = [action.text() for action in menu.actions()]

        self.assertIn("Open", texts)
        self.assertIn("Show in Finder", texts)
        self.assertIn("Restore", texts)
        self.assertIn("Change Expiration", texts)

    def test_row_menu_restore_action_restores_file(self) -> None:
        source = self._make_source("menu-restore.txt", b"restore via menu")
        self._drop(source)
        record = self.store.list_files()[0]
        menu = self.window._build_row_menu(record)
        self.addCleanup(menu.deleteLater)

        restore_action = next(action for action in menu.actions() if action.text() == "Restore")
        restore_action.trigger()

        self.assertTrue(source.is_file())
        self.assertEqual(source.read_bytes(), b"restore via menu")
        self.assertEqual(self.window.rows, [])

    def test_row_menu_expiration_action_updates_expiry(self) -> None:
        record = self._import_record("menu-expiry.txt")
        menu = self.window._build_row_menu(record)
        self.addCleanup(menu.deleteLater)
        expiration = next(
            action for action in menu.actions() if action.text() == "Change Expiration"
        )
        submenu = expiration.menu()
        seven_days = next(
            action for action in submenu.actions() if action.text() == "7 days"
        )

        started = datetime.now(timezone.utc)
        seven_days.trigger()

        updated = self.store.get(record.id)
        expires_at = datetime.fromisoformat(updated.expires_at)
        self.assertGreaterEqual(
            expires_at, started + timedelta(days=7) - timedelta(seconds=2)
        )
        self.assertLessEqual(
            expires_at,
            datetime.now(timezone.utc) + timedelta(days=7) + timedelta(seconds=2),
        )

    def test_restore_updates_panel_and_file(self) -> None:
        source = self._make_source("restore.txt", b"restore me")
        self._drop(source)
        record = self.store.list_files()[0]
        target = Path(record.original_path)

        self.window._restore_to(record, target)

        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(), b"restore me")
        self.assertEqual(self.window.rows, [])
        self.assertEqual(self.window.stats_label.text(), "0 files")
        self.assertIs(self.window.list_stack.currentWidget(), self.window.empty_state)
        self.assertIn("Restored", self.window.footer_status.text())
        self.assertEqual(self.store.list_files(), [])

    # -- retention / expiry display ------------------------------------

    def test_import_defaults_to_one_day(self) -> None:
        record = self._import_record("default.txt")

        self.assertIsNotNone(record.expires_at)
        expires_at = datetime.fromisoformat(record.expires_at)
        self.assertGreater(expires_at, datetime.now(timezone.utc) + timedelta(hours=23))
        row = self._row("default.txt")
        self.assertIn("day", row.remaining_text)
        self.assertIn("Added", row.toolTip())
        self.assertIn("Expires", row.toolTip())

    def test_preset_durations_update_expiry(self) -> None:
        record = self._import_record("presets.txt")
        for _label, duration in RETENTION_OPTIONS:
            started = datetime.now(timezone.utc)
            self.window._set_retention(duration, [record])
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
            (timedelta(days=3), "3 days"),
            (timedelta(hours=12), "12 hours"),
            (timedelta(minutes=35), "35 min"),
        )
        for delta, expected in cases:
            self.store.set_expiry(record.id, datetime.now(timezone.utc) + delta)
            self.window._refresh()
            self.assertEqual(self._row("format.txt").remaining_text, expected)
        self.store.set_expiry(
            record.id, datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        self.window._refresh()
        self.assertEqual(self._row("format.txt").remaining_text, "Expired")

    def test_retention_updates_expiry_and_row(self) -> None:
        self._import_record("retention.txt")
        started = datetime.now(timezone.utc)

        self.window._set_retention(timedelta(days=7), self.store.list_files())

        record = self.store.list_files()[0]
        expires_at = datetime.fromisoformat(record.expires_at)
        self.assertGreaterEqual(
            expires_at, started + timedelta(days=7) - timedelta(seconds=2)
        )
        self.assertLessEqual(
            expires_at,
            datetime.now(timezone.utc) + timedelta(days=7) + timedelta(seconds=2),
        )
        self.assertIn("days", self._row("retention.txt").remaining_text)
        self.assertIn("expires", self.window.footer_status.text())

    def test_historical_record_shows_no_expiration(self) -> None:
        record = self._import_record("legacy.txt")
        self.store.records[record.id] = replace(record, expires_at=None)

        self.window._refresh()

        self.assertEqual(self._row("legacy.txt").remaining_text, "No expiration")

    def test_cleanup_removes_expired_file_from_list(self) -> None:
        record = self._import_record("expired.txt")
        self.store.set_expiry(
            record.id, datetime.now(timezone.utc) - timedelta(minutes=1)
        )

        with mock.patch(
            "tempbox.storage.send2trash", side_effect=lambda path: Path(path).unlink()
        ):
            self.window._run_cleanup()

        self.assertEqual(self.window.rows, [])
        self.assertEqual(self.store.list_files(), [])
        self.assertIn("Trash", self.window.footer_status.text())

    def test_startup_cleanup_runs_on_window_creation(self) -> None:
        record = self._import_record("startup.txt")
        self.store.set_expiry(
            record.id, datetime.now(timezone.utc) - timedelta(minutes=1)
        )

        with mock.patch(
            "tempbox.storage.send2trash", side_effect=lambda path: Path(path).unlink()
        ):
            window = MainWindow(self.store)
        self.addCleanup(window.deleteLater)

        self.assertEqual(window.rows, [])
        self.assertEqual(self.store.list_files(), [])
        self.assertIn("Trash", window.footer_status.text())

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

    # -- stats / search / sort -----------------------------------------

    def test_header_shows_count_and_total_size(self) -> None:
        self._drop(
            self._make_source("a.bin", b"x" * 1024),
            self._make_source("b.bin", b"y" * 1024),
        )

        text = self.window.stats_label.text()

        self.assertIn("2 files", text)
        self.assertIn("2.0 KB", text)

    def test_search_filters_files(self) -> None:
        self._drop(
            self._make_source("alpha.txt"),
            self._make_source("beta.txt"),
            self._make_source("alphabet.txt"),
        )

        self.window.search_edit.setText("alpha")
        self.assertEqual(len(self.window.rows), 2)

        self.window.search_edit.setText("ALPHA")
        self.assertEqual(len(self.window.rows), 2)

        self.window.search_edit.setText("zzz")
        self.assertEqual(self.window.rows, [])
        self.assertEqual(
            self.window.empty_state.title_text, "No files match your search."
        )

        self.window.search_edit.clear()
        self.assertEqual(len(self.window.rows), 3)

    def test_sort_changes_row_order(self) -> None:
        self._drop(
            self._make_source("beta.txt", b"22"),
            self._make_source("alpha.txt", b"1"),
            self._make_source("gamma.txt", b"333"),
        )

        self.window._set_sort("name")
        self.assertEqual(self._row_names(), ["alpha.txt", "beta.txt", "gamma.txt"])

        self.window._set_sort("size")
        self.assertEqual(self._row_names(), ["gamma.txt", "beta.txt", "alpha.txt"])

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

        self.window._set_sort("expires")

        self.assertEqual(self._row_names(), ["soon.txt", "later.txt", "never.txt"])

    # -- selection / batch ---------------------------------------------

    def test_selection_mode_toggles_checkboxes_and_footer(self) -> None:
        self._import_record("select.txt")

        self.window.set_selection_mode(True)
        self.assertEqual(self.window.select_button.text(), "Done")
        self.assertEqual(self.window.footer_stack.currentIndex(), 1)
        self.assertTrue(self.window.rows[0]._selection_mode)

        self.window._on_row_checked(self.window.rows[0], True)
        self.assertEqual(self.window.batch_count.text(), "1 selected")
        self.assertTrue(self.window.rows[0]._checked)

        self.window.set_selection_mode(False)
        self.assertEqual(self.window.select_button.text(), "Select")
        self.assertEqual(self.window.footer_stack.currentIndex(), 0)
        self.assertEqual(self.window._checked_records(), [])

    def test_batch_expiry_updates_selected_files(self) -> None:
        self._drop(
            self._make_source("one.txt"),
            self._make_source("two.txt"),
            self._make_source("three.txt"),
        )
        self._select("one.txt", "two.txt")
        selected_ids = {record.id for record in self.window._checked_records()}
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
        self.assertEqual(len(self.window._checked_records()), 2)
        self.assertIn("2 files", self.window.footer_status.text())

    def test_batch_restore_restores_selected_files(self) -> None:
        first = self._make_source("r1.txt", b"one")
        second = self._make_source("r2.txt", b"two")
        self._drop(first, second)
        self._select("r1.txt", "r2.txt")

        self.window._restore_checked()

        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())
        self.assertEqual(self.window.rows, [])
        self.assertEqual(self.store.list_files(), [])
        self.assertIn("Restored 2 files", self.window.footer_status.text())

    def test_batch_restore_reports_partial_failure(self) -> None:
        first = self._make_source("keep.txt", b"one")
        second = self._make_source("lost.txt", b"two")
        self._drop(first, second)
        lost = next(
            record for record in self.store.list_files() if record.original_name == "lost.txt"
        )
        self.store.stored_path(lost).unlink()
        self.window._refresh()
        self._select("keep.txt", "lost.txt")

        with mock.patch("tempbox.window.QMessageBox.warning") as warning:
            self.window._restore_checked()

        warning.assert_called_once()
        self.assertTrue(first.is_file())
        self.assertFalse(second.exists())
        self.assertEqual(len(self.store.list_files()), 1)
        status = self.window.footer_status.text()
        self.assertIn("Restored 1 file", status)
        self.assertIn("1 file failed", status)

    # -- settings ------------------------------------------------------

    def test_default_retention_setting_persists_and_only_affects_new_files(self) -> None:
        old = self._import_record("old.txt")

        self.window.set_default_retention(timedelta(hours=1))

        self.assertEqual(self.store.get(old.id).expires_at, old.expires_at)
        self.assertEqual(self.window.footer_hint.text(), "Default \u00b7 1 hour")
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
        self.window.set_default_retention(timedelta(days=7))
        with mock.patch("tempbox.dialogs.autostart.is_enabled", return_value=False):
            dialog = SettingsDialog(self.window)
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(dialog.retention_combo.currentText(), "7 days")
        self.assertFalse(dialog.autostart_checkbox.isChecked())

    # -- Phase 4: pause / reminders / history / external sync ----------

    def test_pause_prevents_cleanup_and_persists(self) -> None:
        record = self._import_record("paused.txt")
        self.store.set_expiry(
            record.id, datetime.now(timezone.utc) - timedelta(minutes=1)
        )

        self.assertTrue(self.window.set_auto_cleanup_paused(True))

        self.assertFalse(self.window.pause_label.isHidden())
        self.assertTrue(AppSettings.load(self.store.root).pause_auto_cleanup)
        with mock.patch("tempbox.storage.send2trash") as trash:
            self.window._on_cleanup_tick()
        trash.assert_not_called()
        self.assertEqual(len(self.store.list_files()), 1)
        self.assertIn("paused", self.window.footer_status.text())

    def test_resume_with_overdue_files_requires_confirmation(self) -> None:
        record = self._import_record("resume.txt")
        self.store.set_expiry(
            record.id, datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        self.window.set_auto_cleanup_paused(True)

        with mock.patch(
            "tempbox.window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ) as question:
            self.assertFalse(self.window.set_auto_cleanup_paused(False))

        question.assert_called_once()
        self.assertTrue(self.window._auto_cleanup_paused)
        self.assertTrue(AppSettings.load(self.store.root).pause_auto_cleanup)
        self.assertEqual(len(self.store.list_files()), 1)

    def test_resume_with_confirmation_cleans_overdue_files_and_writes_history(self) -> None:
        record = self._import_record("resume-yes.txt")
        self.store.set_expiry(
            record.id, datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        self.window.set_auto_cleanup_paused(True)

        with mock.patch(
            "tempbox.window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), mock.patch(
            "tempbox.storage.send2trash", side_effect=lambda path: Path(path).unlink()
        ):
            self.assertTrue(self.window.set_auto_cleanup_paused(False))

        self.assertFalse(self.window._auto_cleanup_paused)
        self.assertEqual(self.store.list_files(), [])
        history = CleanupHistory(self.store.root)
        history.load()
        self.assertEqual(len(history.entries), 1)

    def test_pause_state_is_respected_after_restart(self) -> None:
        record = self._import_record("restart-paused.txt")
        self.store.set_expiry(
            record.id, datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        self.window.set_auto_cleanup_paused(True)

        with mock.patch("tempbox.storage.send2trash") as trash:
            restarted = MainWindow(self.store)
        self.addCleanup(restarted.deleteLater)

        trash.assert_not_called()
        self.assertEqual(len(self.store.list_files()), 1)
        self.assertTrue(restarted._auto_cleanup_paused)
        self.assertFalse(restarted.pause_label.isHidden())

    def test_expiry_reminder_fires_once_per_expiry_cycle(self) -> None:
        notifier = mock.Mock()
        self.window.set_notifier(notifier)
        record = self._import_record("soon.txt")
        self.store.set_expiry(
            record.id, datetime.now(timezone.utc) + timedelta(minutes=5)
        )

        self.window.check_expiry_reminders()
        self.assertEqual(notifier.call_count, 1)
        title, message = notifier.call_args.args
        self.assertEqual(title, "TempBox")
        self.assertIn("soon.txt", message)
        self.assertIn("expire", message)

        self.window.check_expiry_reminders()
        self.assertEqual(notifier.call_count, 1)

        self.store.set_expiry(
            record.id, datetime.now(timezone.utc) + timedelta(minutes=6)
        )
        self.window.check_expiry_reminders()
        self.assertEqual(notifier.call_count, 2)

    def test_expiry_reminder_can_be_disabled(self) -> None:
        notifier = mock.Mock()
        self.window.set_notifier(notifier)
        record = self._import_record("quiet.txt")
        self.store.set_expiry(
            record.id, datetime.now(timezone.utc) + timedelta(minutes=5)
        )
        self.window.settings.remind_before_expiry = False

        self.window.check_expiry_reminders()

        notifier.assert_not_called()

    def test_multiple_expiring_files_are_merged_into_one_notification(self) -> None:
        notifier = mock.Mock()
        self.window.set_notifier(notifier)
        first = self._import_record("first.txt")
        second = self._import_record("second.txt")
        soon = datetime.now(timezone.utc) + timedelta(minutes=5)
        self.store.set_expiry(first.id, soon)
        self.store.set_expiry(second.id, soon)

        self.window.check_expiry_reminders()

        self.assertEqual(notifier.call_count, 1)
        self.assertIn("2 files", notifier.call_args.args[1])

    def test_notification_failure_does_not_break_cleanup(self) -> None:
        notifier = mock.Mock(side_effect=RuntimeError("notifications unavailable"))
        self.window.set_notifier(notifier)
        record = self._import_record("notify-fail.txt")
        self.store.set_expiry(
            record.id, datetime.now(timezone.utc) + timedelta(minutes=5)
        )
        self.window.check_expiry_reminders()  # must not raise

        expired = self._import_record("cleanup-after-notify.txt")
        self.store.set_expiry(
            expired.id, datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        with mock.patch(
            "tempbox.storage.send2trash", side_effect=lambda path: Path(path).unlink()
        ):
            self.window._run_cleanup()
        self.assertEqual(len(self.store.list_files()), 1)

    def test_cleanup_records_history_only_for_successful_moves(self) -> None:
        success = self._import_record("history-ok.txt")
        self.store.set_expiry(
            success.id, datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        with mock.patch(
            "tempbox.storage.send2trash", side_effect=lambda path: Path(path).unlink()
        ):
            self.window._run_cleanup()

        history = CleanupHistory(self.store.root)
        history.load()
        self.assertEqual(len(history.entries), 1)
        self.assertEqual(history.entries[0].original_name, "history-ok.txt")

        failure = self._import_record("history-failed.txt")
        self.store.set_expiry(
            failure.id, datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        with mock.patch(
            "tempbox.storage.send2trash", side_effect=OSError("Trash unavailable")
        ):
            self.window._run_cleanup()

        history.load()
        self.assertEqual(len(history.entries), 1)
        failed_record = next(
            record
            for record in self.store.list_files()
            if record.original_name == "history-failed.txt"
        )
        self.assertIsNotNone(failed_record.trash_error)

    def test_history_dialog_lists_and_clears_entries(self) -> None:
        record = self._import_record("dialog-history.txt")
        self.store.set_expiry(
            record.id, datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        with mock.patch(
            "tempbox.storage.send2trash", side_effect=lambda path: Path(path).unlink()
        ):
            self.window._run_cleanup()

        dialog = HistoryDialog(self.window)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.entry_list.count(), 1)
        self.assertIn("dialog-history.txt", dialog.entry_list.item(0).text())

        with mock.patch(
            "tempbox.dialogs.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            dialog._clear_history()

        self.assertEqual(dialog.entry_list.count(), 0)
        history = CleanupHistory(self.store.root)
        history.load()
        self.assertEqual(history.entries, [])

    def test_syncs_files_imported_by_external_helper(self) -> None:
        external = FileStore(self.store.root)
        external.load()
        source = self._make_source("from-finder.txt")
        result = external.import_files([source])
        self.assertEqual(len(result.added), 1)

        self.window._sync_external_changes()

        self.assertIn("from-finder.txt", self._row_names())
        self.assertIn("1 file", self.window.stats_label.text())

    def test_settings_dialog_exposes_phase4_controls(self) -> None:
        with mock.patch(
            "tempbox.dialogs.autostart.is_enabled", return_value=False
        ), mock.patch(
            "tempbox.dialogs.quick_action.is_installed", return_value=False
        ):
            dialog = SettingsDialog(self.window)
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(dialog.version_label.text(), "TempBox v0.5.0")
        self.assertFalse(dialog.pause_checkbox.isChecked())
        self.assertTrue(dialog.reminder_checkbox.isChecked())
        self.assertIn("Install", dialog.quick_action_button.text())

        with mock.patch("tempbox.dialogs.QMessageBox.information") as information:
            dialog._on_check_updates()
        information.assert_called_once()
        message = information.call_args.args[2]
        self.assertIn("not enabled", message)
        self.assertNotIn("up to date", message.lower())

    def test_settings_reminder_toggle_persists(self) -> None:
        with mock.patch(
            "tempbox.dialogs.autostart.is_enabled", return_value=False
        ), mock.patch(
            "tempbox.dialogs.quick_action.is_installed", return_value=False
        ):
            dialog = SettingsDialog(self.window)
        self.addCleanup(dialog.deleteLater)

        dialog.reminder_checkbox.setChecked(False)

        self.assertFalse(self.window.settings.remind_before_expiry)
        self.assertFalse(AppSettings.load(self.store.root).remind_before_expiry)

    def test_settings_pause_toggle_controls_cleanup_state(self) -> None:
        with mock.patch(
            "tempbox.dialogs.autostart.is_enabled", return_value=False
        ), mock.patch(
            "tempbox.dialogs.quick_action.is_installed", return_value=False
        ):
            dialog = SettingsDialog(self.window)
        self.addCleanup(dialog.deleteLater)

        dialog.pause_checkbox.setChecked(True)
        self.assertTrue(self.window._auto_cleanup_paused)
        self.assertTrue(AppSettings.load(self.store.root).pause_auto_cleanup)
        self.assertFalse(self.window.pause_label.isHidden())

        dialog.pause_checkbox.setChecked(False)
        self.assertFalse(self.window._auto_cleanup_paused)
        self.assertFalse(AppSettings.load(self.store.root).pause_auto_cleanup)
        self.assertTrue(self.window.pause_label.isHidden())

    def test_quick_action_install_button_rewires_service(self) -> None:
        with mock.patch(
            "tempbox.dialogs.autostart.is_enabled", return_value=False
        ), mock.patch(
            "tempbox.dialogs.quick_action.is_installed", return_value=False
        ):
            dialog = SettingsDialog(self.window)
        self.addCleanup(dialog.deleteLater)

        with mock.patch(
            "tempbox.dialogs.quick_action.is_installed", side_effect=[False, True]
        ), mock.patch("tempbox.dialogs.quick_action.install") as install:
            dialog._on_quick_action_clicked()

        install.assert_called_once()
        self.assertIn("Remove", dialog.quick_action_button.text())

    # -- window behaviour ----------------------------------------------

    def test_height_follows_rows_and_caps_for_long_lists(self) -> None:
        paths = [self._make_source(f"f{index}.txt") for index in range(8)]
        self._drop(*paths)

        expected_height = MainWindow.MAX_VISIBLE_ROWS * 56 + 8
        self.assertEqual(self.window.list_stack.height(), expected_height)
        self.assertEqual(len(self.window.rows), 8)

    def test_small_list_is_compact(self) -> None:
        self._import_record("one.txt")
        self._import_record("two.txt")

        self.assertEqual(self.window.list_stack.height(), 2 * 56 + 8)

    def test_long_file_name_does_not_change_window_width(self) -> None:
        long_name = "A very long temporary file name " * 6 + ".pdf"
        self._drop(self._make_source(long_name))

        self.assertEqual(
            self.window.width(), MainWindow.PANEL_WIDTH + MainWindow.SHADOW_MARGIN * 2
        )
        self.assertEqual(self.window.rows[0].record.original_name, long_name)

    def test_quit_button_emits_quit_request(self) -> None:
        requests: list[bool] = []
        self.window.quit_requested.connect(lambda: requests.append(True))

        self.window.quit_button.click()

        self.assertEqual(requests, [True])

    def test_application_deactivate_hides_window(self) -> None:
        self.window.show()
        QApplication.processEvents()
        self.assertTrue(self.window.isVisible())

        self.window._on_application_state_changed(Qt.ApplicationState.ApplicationInactive)

        self.assertFalse(self.window.isVisible())

    def test_modal_widget_prevents_auto_hide(self) -> None:
        self.window.show()
        QApplication.processEvents()
        self.assertTrue(self.window.isVisible())

        with mock.patch(
            "tempbox.window.QApplication.activeModalWidget", return_value=object()
        ):
            self.window._on_application_state_changed(
                Qt.ApplicationState.ApplicationInactive
            )
        self.assertTrue(self.window.isVisible())

        self.window._on_application_state_changed(Qt.ApplicationState.ApplicationInactive)
        self.assertFalse(self.window.isVisible())

    def test_tray_click_after_auto_hide_stays_hidden(self) -> None:
        self.window.show()
        QApplication.processEvents()
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
