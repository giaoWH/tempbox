"""Main window: drop area, file list, retention, search, settings and actions."""

from __future__ import annotations

import math
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import (
    QDateTime,
    QFileInfo,
    QItemSelectionModel,
    QMimeData,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QIcon,
    QKeySequence,
    QPalette,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import autostart
from .settings import AppSettings
from .storage import (
    CleanupResult,
    DEFAULT_RETENTION,
    FileRecord,
    FileStore,
    ImportResult,
    RETENTION_OPTIONS,
    StorageError,
)

COLUMNS = ("Name", "Size", "Added", "Expires", "Remaining")
SORT_OPTIONS = (
    ("Added (newest first)", "added"),
    ("Name (A\u2013Z)", "name"),
    ("Size (largest first)", "size"),
    ("Expires (soonest first)", "expires"),
)
CLEANUP_INTERVAL_MS = 30_000
EXPIRING_SOON = timedelta(hours=1)
AUTO_HIDE_REOPEN_GRACE = 0.5
_AMBER = QColor("#c58a00")
_RED = QColor("#e5484d")


class MainWindow(QWidget):
    """TempBox main window: drag files in, manage their lifetime, act on them."""

    def __init__(self, store: FileStore) -> None:
        super().__init__()
        self.store = store
        self.settings = AppSettings.load(store.root)
        self.store.default_retention = self.settings.default_retention
        self._icon_provider = QFileIconProvider()
        self._auto_hidden_at: float | None = None
        self._build_ui()
        self._refresh()

        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.setInterval(CLEANUP_INTERVAL_MS)
        self._cleanup_timer.timeout.connect(self._run_cleanup)
        self._cleanup_timer.start()
        self._run_cleanup()

        application = QApplication.instance()
        if application is not None:
            application.applicationStateChanged.connect(self._on_application_state_changed)

    # -- UI construction -----------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle("TempBox")
        self.setMinimumSize(640, 500)
        self.resize(780, 600)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(12)

        title = QLabel("TempBox")
        title.setObjectName("titleLabel")
        self.count_label = _muted_label()
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.count_label)
        layout.addLayout(header)

        self.drop_zone = self._build_drop_zone()
        layout.addWidget(self.drop_zone)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search files")
        self.search_edit.setClearButtonEnabled(True)
        self.sort_combo = QComboBox()
        for label, key in SORT_OPTIONS:
            self.sort_combo.addItem(label, key)
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.sort_combo)
        layout.addLayout(search_row)

        self.table = self._build_table()
        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)

        self.content = QStackedWidget()
        self.content.addWidget(self.table)
        self.content.addWidget(self.empty_label)
        layout.addWidget(self.content, 1)

        self.open_button = QPushButton("Open")
        self.reveal_button = QPushButton("Show in Finder")
        self.restore_button = QPushButton("Restore")
        self.retention_button = QPushButton("Expiration")
        self.retention_menu = self._build_retention_menu()
        self.retention_button.setMenu(self.retention_menu)
        self.open_button.clicked.connect(self._open_selected)
        self.reveal_button.clicked.connect(self._reveal_selected)
        self.restore_button.clicked.connect(self._restore_selected)
        actions = QHBoxLayout()
        actions.addWidget(self.open_button)
        actions.addWidget(self.reveal_button)
        actions.addWidget(self.restore_button)
        actions.addWidget(self.retention_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.status_label = _muted_label(
            "Drop files here. New files are kept for "
            f"{_duration_label(self.store.default_retention)}."
        )
        self.status_label.setWordWrap(True)
        self.settings_button = QPushButton("Settings\u2026")
        self.settings_button.setFlat(True)
        self.settings_button.clicked.connect(self._open_settings)
        quit_button = QPushButton("Quit")
        quit_button.setFlat(True)
        quit_button.clicked.connect(QApplication.instance().quit)
        footer = QHBoxLayout()
        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.settings_button)
        footer.addWidget(quit_button)
        layout.addLayout(footer)

        self.search_edit.textChanged.connect(self._refresh)
        self.sort_combo.currentIndexChanged.connect(self._refresh)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.doubleClicked.connect(self._open_selected)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self._quit_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Quit), self)
        self._quit_shortcut.activated.connect(QApplication.instance().quit)
        self._update_buttons()
        self.table.setFocus()

        self.setStyleSheet(
            """
            QLabel#titleLabel { font-size: 20px; font-weight: 600; }
            QFrame#dropZone { border: 1px dashed palette(mid); border-radius: 10px; }
            QFrame#dropZone[dragging="true"] {
                border: 2px solid palette(highlight);
                background: rgba(10, 132, 255, 0.10);
            }
            QLabel#dropTitle { font-size: 14px; font-weight: 600; }
            QHeaderView::section { background: transparent; border: none; padding: 4px 6px; }
            QLineEdit { padding: 4px 6px; }
            """
        )

    def _build_drop_zone(self) -> QFrame:
        zone = QFrame()
        zone.setObjectName("dropZone")
        zone.setMinimumHeight(94)
        zone.setProperty("dragging", False)
        zone_layout = QVBoxLayout(zone)
        zone_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zone_layout.setSpacing(4)
        heading = QLabel("Drag files here")
        heading.setObjectName("dropTitle")
        hint = _muted_label(
            "Files are moved into TempBox and sent to the Trash when their time is up."
        )
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        zone_layout.addWidget(heading)
        zone_layout.addWidget(hint)
        return zone

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, len(COLUMNS))
        table.setHorizontalHeaderLabels(COLUMNS)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(32)
        table.setShowGrid(False)
        table.setAlternatingRowColors(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        table.setAcceptDrops(False)
        table.viewport().setAcceptDrops(False)
        table.setIconSize(QSize(16, 16))
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        return table

    def _build_retention_menu(self) -> QMenu:
        menu = QMenu(self)
        for label, duration in RETENTION_OPTIONS:
            action = menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, duration=duration: self._set_retention(duration)
            )
        menu.addSeparator()
        custom_action = menu.addAction("Custom\u2026")
        custom_action.triggered.connect(self._set_custom_expiry)
        return menu

    # -- list rendering ------------------------------------------------

    def _refresh(self) -> None:
        selected_ids = {record.id for record in self._selected_records()}
        all_records = self.store.list_files()
        records = self._visible_records(all_records)
        now = datetime.now(timezone.utc)

        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            name_item = QTableWidgetItem(self._icon_for(record), record.original_name)
            name_item.setData(Qt.ItemDataRole.UserRole, record.id)
            name_item.setToolTip(record.original_path)
            self.table.setItem(row, 0, name_item)
            size_item = QTableWidgetItem(_format_size(record.size))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 1, size_item)
            self.table.setItem(row, 2, QTableWidgetItem(_format_added(record.added_at)))
            self.table.setItem(row, 3, QTableWidgetItem(_format_expiry(record.expires_at)))

            remaining_text, colour, tooltip = self._remaining_display(record, now)
            remaining_item = QTableWidgetItem(remaining_text)
            if colour is not None:
                remaining_item.setForeground(colour)
            if tooltip:
                remaining_item.setToolTip(tooltip)
            self.table.setItem(row, 4, remaining_item)

        self.count_label.setText(_stats_text(len(all_records), sum(r.size for r in all_records)))
        searching = bool(self.search_edit.text().strip())
        self.empty_label.setText(_empty_text(bool(all_records), searching))
        self.content.setCurrentWidget(self.table if records else self.empty_label)

        selection = self.table.selectionModel()
        selection.clearSelection()
        for row, record in enumerate(records):
            if record.id in selected_ids:
                index = self.table.model().index(row, 0)
                selection.select(
                    index,
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
        self._update_buttons()

    def _visible_records(self, records: list[FileRecord]) -> list[FileRecord]:
        keyword = self.search_edit.text().strip().lower()
        if keyword:
            records = [record for record in records if keyword in record.original_name.lower()]
        sort_key = self.sort_combo.currentData()
        if sort_key == "name":
            records.sort(key=lambda record: record.original_name.lower())
        elif sort_key == "size":
            records.sort(key=lambda record: record.size, reverse=True)
        elif sort_key == "expires":
            records.sort(key=_expiry_sort_key)
        return records

    def _icon_for(self, record: FileRecord) -> QIcon:
        stored = self.store.stored_path(record)
        target = stored if stored.exists() else Path(record.original_name)
        return self._icon_provider.icon(QFileInfo(str(target)))

    def _remaining_display(
        self, record: FileRecord, now: datetime
    ) -> tuple[str, QColor | None, str]:
        if not self.store.stored_path(record).is_file():
            return "File missing", _RED, "The stored file is missing from TempBox."
        if record.trash_error:
            return "Cleanup failed", _RED, record.trash_error
        if record.expires_at is None:
            return "No expiry", None, "This file has no expiry time. Use Expiration to set one."
        remaining = datetime.fromisoformat(record.expires_at) - now
        if remaining <= timedelta(0):
            return "Expired", _RED, "Expired and waiting to be moved to the Trash."
        seconds = int(remaining.total_seconds())
        if remaining < EXPIRING_SOON:
            minutes = max(1, math.ceil(seconds / 60))
            return f"{minutes} {_plural(minutes, 'minute', 'minutes')} left", _AMBER, ""
        hours = math.ceil(seconds / 3600)
        days = math.ceil(seconds / 86400)
        if days > 1:
            return f"{days} days left", None, ""
        if hours >= 24:
            return "1 day left", None, ""
        return f"{hours} {_plural(hours, 'hour', 'hours')} left", None, ""

    def _selected_records(self) -> list[FileRecord]:
        model = self.table.selectionModel()
        records: list[FileRecord] = []
        for index in sorted(model.selectedRows(), key=lambda item: item.row()):
            item = self.table.item(index.row(), 0)
            if item is None:
                continue
            record = self.store.get(str(item.data(Qt.ItemDataRole.UserRole)))
            if record is not None:
                records.append(record)
        return records

    def _single_selected_record(self) -> FileRecord | None:
        records = self._selected_records()
        return records[0] if len(records) == 1 else None

    def _update_buttons(self) -> None:
        selected = self._selected_records()
        single = len(selected) == 1
        self.open_button.setEnabled(single)
        self.reveal_button.setEnabled(single)
        self.restore_button.setEnabled(bool(selected))
        self.retention_button.setEnabled(bool(selected))

    def _on_application_state_changed(self, state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationActive:
            return
        if not self.isVisible():
            return
        if (
            QApplication.activeModalWidget() is not None
            or QApplication.activePopupWidget() is not None
        ):
            return
        self.hide()
        self._auto_hidden_at = time.monotonic()

    def consume_recent_auto_hide(self) -> bool:
        """True if the window was hidden by the click-outside logic just now.

        Clicking the menu bar icon can deactivate the app a moment before the
        tray activation is delivered; without this check the toggle would think
        the window was already hidden and show it again.
        """
        if self._auto_hidden_at is None:
            return False
        hidden_seconds_ago = time.monotonic() - self._auto_hidden_at
        self._auto_hidden_at = None
        return hidden_seconds_ago <= AUTO_HIDE_REOPEN_GRACE

    def clear_auto_hide_marker(self) -> None:
        self._auto_hidden_at = None

    # -- retention -----------------------------------------------------

    def _set_retention(self, duration: timedelta) -> None:
        records = self._selected_records()
        if not records:
            return
        self._apply_expiry(records, datetime.now(timezone.utc) + duration)

    def _set_custom_expiry(self) -> None:
        records = self._selected_records()
        if not records:
            return
        current = None
        if len(records) == 1 and records[0].expires_at:
            current = datetime.fromisoformat(records[0].expires_at)
        dialog = ExpiryDialog(current, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        expires_at = dialog.selected_expiry()
        if expires_at <= datetime.now(timezone.utc):
            QMessageBox.warning(
                self, "Invalid expiry time", "Choose a time that is still in the future."
            )
            return
        self._apply_expiry(records, expires_at)

    def _apply_expiry(self, records: list[FileRecord], expires_at: datetime) -> None:
        try:
            if len(records) == 1:
                updated = self.store.set_expiry(records[0].id, expires_at)
                message = (
                    f"'{records[0].original_name}' now expires "
                    f"{_format_expiry(updated.expires_at)}."
                )
            else:
                count = self.store.set_expiries([record.id for record in records], expires_at)
                message = f"Updated the expiry time for {count} files."
        except StorageError as exc:
            self._refresh()
            self._notify_error(str(exc))
            return
        self._refresh()
        self._set_status(message)

    # -- settings ------------------------------------------------------

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()

    def set_default_retention(self, duration: timedelta) -> None:
        self.settings.default_retention = duration
        self.store.default_retention = duration
        try:
            self.settings.save(self.store.root)
        except OSError as exc:
            self._notify_error(f"Could not save settings: {exc}")
            return
        self._set_status(f"New files will be kept for {_duration_label(duration)}.")

    # -- expiry clean-up -----------------------------------------------

    def _run_cleanup(self) -> None:
        result = self.store.cleanup_expired()
        self._refresh()
        self._report_cleanup(result)

    def _report_cleanup(self, result: CleanupResult) -> None:
        parts: list[str] = []
        if result.trashed:
            count = len(result.trashed)
            parts.append(f"Moved {count} expired {_plural(count, 'file', 'files')} to Trash.")
        if result.failed:
            count = len(result.failed)
            parts.append(
                f"{count} {_plural(count, 'file', 'files')} could not be moved to Trash."
            )
        if result.missing:
            count = len(result.missing)
            parts.append(
                f"{count} {_plural(count, 'file', 'files')} missing from TempBox storage."
            )
        if result.save_error:
            parts.append(f"Could not save the file index: {result.save_error}")
        if parts:
            self._set_status(" ".join(parts))

    # -- imports -------------------------------------------------------

    def _import_paths(self, paths: list[Path]) -> None:
        if not paths:
            return
        result = self.store.import_files(paths)
        self._refresh()
        self._show_import_result(result)

    def _show_import_result(self, result: ImportResult) -> None:
        parts: list[str] = []
        if result.added:
            count = len(result.added)
            parts.append(f"Imported {count} {_plural(count, 'file', 'files')}.")
        for name, reason in result.failed:
            parts.append(f"Skipped '{name}': {reason}")
        self._set_status(" ".join(parts) if parts else "Nothing to import.")

    # -- drag and drop -------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._local_paths(event.mimeData()):
            self._set_dragging(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._local_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_dragging(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_dragging(False)
        paths = self._local_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self._import_paths(paths)

    @staticmethod
    def _local_paths(mime_data: QMimeData) -> list[Path]:
        if not mime_data.hasUrls():
            return []
        return [
            Path(url.toLocalFile())
            for url in mime_data.urls()
            if url.isLocalFile() and url.toLocalFile()
        ]

    def _set_dragging(self, dragging: bool) -> None:
        if self.drop_zone.property("dragging") == dragging:
            return
        self.drop_zone.setProperty("dragging", dragging)
        style = self.drop_zone.style()
        style.unpolish(self.drop_zone)
        style.polish(self.drop_zone)

    # -- file actions --------------------------------------------------

    def _open_selected(self) -> None:
        record = self._single_selected_record()
        if record is None:
            return
        stored = self.store.stored_path(record)
        if not stored.is_file():
            self._notify_error(f"'{record.original_name}' is missing from TempBox storage.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(stored))):
            self._notify_error(f"macOS could not open '{record.original_name}'.")

    def _reveal_selected(self) -> None:
        record = self._single_selected_record()
        if record is None:
            return
        stored = self.store.stored_path(record)
        if not stored.is_file():
            self._notify_error(f"'{record.original_name}' is missing from TempBox storage.")
            return
        completed = subprocess.run(["open", "-R", str(stored)], check=False, capture_output=True)
        if completed.returncode != 0:
            self._notify_error(f"Finder could not show '{record.original_name}'.")

    def _restore_selected(self) -> None:
        records = self._selected_records()
        if not records:
            return
        if len(records) == 1:
            self._restore_single(records[0])
        else:
            self._restore_many(records)

    def _restore_single(self, record: FileRecord) -> None:
        if not self.store.stored_path(record).is_file():
            self._notify_error(f"'{record.original_name}' is missing from TempBox storage.")
            return
        original = Path(record.original_path)
        if os.path.lexists(original):
            self._choose_restore_target(
                record, f"'{record.original_name}' already exists at its original location."
            )
        elif not original.parent.is_dir():
            self._choose_restore_target(
                record, f"The original folder '{original.parent}' no longer exists."
            )
        else:
            self._restore_to(record, original)

    def _restore_many(self, records: list[FileRecord]) -> None:
        restored = 0
        failures: list[tuple[str, str]] = []
        for record in records:
            if not self.store.stored_path(record).is_file():
                failures.append((record.original_name, "file is missing from TempBox"))
                continue
            original = Path(record.original_path)
            if not original.parent.is_dir():
                failures.append((record.original_name, "original folder no longer exists"))
                continue
            if os.path.lexists(original):
                failures.append((record.original_name, "a file already exists at the original place"))
                continue
            try:
                self.store.restore(record.id, original)
            except StorageError as exc:
                failures.append((record.original_name, str(exc)))
            else:
                restored += 1
        self._refresh()
        parts = []
        if restored:
            parts.append(f"Restored {restored} {_plural(restored, 'file', 'files')}.")
        if failures:
            count = len(failures)
            parts.append(f"{count} {_plural(count, 'file', 'files')} failed.")
        self._set_status(" ".join(parts) if parts else "Nothing to restore.")
        if failures:
            details = "\n".join(
                f"\u2022 {name}: {reason}" for name, reason in failures[:8]
            )
            if len(failures) > 8:
                details += "\n\u2026"
            QMessageBox.warning(
                self,
                "Some files could not be restored",
                details + "\n\nThey are still stored safely in TempBox.",
            )

    def _choose_restore_target(self, record: FileRecord, reason: str) -> None:
        QMessageBox.information(
            self,
            "Restore file",
            f"{reason}\n\nChoose a folder to restore '{record.original_name}' into.",
        )
        start_dir = Path(record.original_path).parent
        if not start_dir.is_dir():
            start_dir = Path.home()
        while True:
            directory = QFileDialog.getExistingDirectory(self, "Choose a folder", str(start_dir))
            if not directory:
                self._set_status("Restore cancelled.")
                return
            target = Path(directory) / record.original_name
            if os.path.lexists(target):
                QMessageBox.warning(
                    self,
                    "File already exists",
                    f"'{record.original_name}' already exists in that folder. "
                    "Choose a different folder.",
                )
                start_dir = Path(directory)
                continue
            self._restore_to(record, target)
            return

    def _restore_to(self, record: FileRecord, target: Path) -> None:
        try:
            restored = self.store.restore(record.id, target)
        except StorageError as exc:
            self._refresh()
            self._notify_error(str(exc))
            return
        self._refresh()
        self._set_status(f"Restored '{record.original_name}' to {restored}.")

    # -- context menu --------------------------------------------------

    def _show_context_menu(self, position) -> None:
        index = self.table.indexAt(position)
        if index.isValid():
            selected_rows = {item.row() for item in self.table.selectionModel().selectedRows()}
            if index.row() not in selected_rows:
                self.table.clearSelection()
                self.table.selectRow(index.row())
        if not self._selected_records():
            return
        menu = self._build_context_menu()
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _build_context_menu(self) -> QMenu:
        selected = self._selected_records()
        single = len(selected) == 1
        menu = QMenu(self)
        open_action = menu.addAction("Open")
        open_action.setEnabled(single)
        open_action.triggered.connect(self._open_selected)
        reveal_action = menu.addAction("Show in Finder")
        reveal_action.setEnabled(single)
        reveal_action.triggered.connect(self._reveal_selected)
        restore_action = menu.addAction("Restore")
        restore_action.setEnabled(bool(selected))
        restore_action.triggered.connect(self._restore_selected)
        menu.addSeparator()
        expiry_menu = menu.addMenu("Change Expiration")
        for label, duration in RETENTION_OPTIONS:
            action = expiry_menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, duration=duration: self._set_retention(duration)
            )
        expiry_menu.addSeparator()
        custom_action = expiry_menu.addAction("Custom\u2026")
        custom_action.triggered.connect(self._set_custom_expiry)
        return menu

    # -- misc ----------------------------------------------------------

    def _notify_error(self, message: str) -> None:
        self._set_status(message)
        QMessageBox.critical(self, "TempBox", message)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()


class ExpiryDialog(QDialog):
    """Small dialog for choosing a custom expiry date and time."""

    def __init__(self, current: datetime | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Custom expiry time")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Move this file to the Trash at:"))

        self.editor = QDateTimeEdit(self)
        self.editor.setCalendarPopup(True)
        self.editor.setDisplayFormat("yyyy-MM-dd HH:mm")
        minimum = QDateTime.currentDateTime().addSecs(60)
        self.editor.setMinimumDateTime(minimum)
        if current is not None:
            initial = QDateTime.fromSecsSinceEpoch(int(current.timestamp()))
        else:
            default = datetime.now(timezone.utc) + DEFAULT_RETENTION
            initial = QDateTime.fromSecsSinceEpoch(int(default.timestamp()))
        if initial < minimum:
            initial = minimum
        self.editor.setDateTime(initial)
        layout.addWidget(self.editor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_expiry(self) -> datetime:
        return datetime.fromtimestamp(self.editor.dateTime().toSecsSinceEpoch(), timezone.utc)


class SettingsDialog(QDialog):
    """Small settings dialog: default retention and launch at login."""

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self.window = window
        self.setWindowTitle("TempBox Settings")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Default retention for new files"))
        self.retention_combo = QComboBox()
        for label, duration in RETENTION_OPTIONS:
            self.retention_combo.addItem(label, duration)
        for index, (_label, duration) in enumerate(RETENTION_OPTIONS):
            if duration == window.store.default_retention:
                self.retention_combo.setCurrentIndex(index)
                break
        self.retention_combo.currentIndexChanged.connect(self._on_retention_changed)
        layout.addWidget(self.retention_combo)

        self.autostart_checkbox = QCheckBox("Launch TempBox at login")
        self.autostart_checkbox.setChecked(autostart.is_enabled())
        self.autostart_checkbox.toggled.connect(self._on_autostart_toggled)
        layout.addWidget(self.autostart_checkbox)

        hint = _muted_label(
            "Login launch starts TempBox hidden in the menu bar. While TempBox runs "
            "as a Python script, it uses the current Python and project paths; move "
            "either and toggle this setting off and on again."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.note_label = _muted_label("")
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_retention_changed(self, index: int) -> None:
        duration = self.retention_combo.itemData(index)
        if duration is None:
            return
        self.window.set_default_retention(duration)
        self.note_label.setText(
            f"New files will be kept for {_duration_label(duration)}."
        )

    def _on_autostart_toggled(self, enabled: bool) -> None:
        try:
            autostart.set_enabled(enabled)
        except OSError as exc:
            self.autostart_checkbox.blockSignals(True)
            self.autostart_checkbox.setChecked(not enabled)
            self.autostart_checkbox.blockSignals(False)
            QMessageBox.warning(
                self,
                "Launch at Login",
                f"TempBox could not update the login item:\n{exc}",
            )
            return
        state = "enabled" if enabled else "disabled"
        self.note_label.setText(f"Launch at login {state} for the next login.")


def _muted_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
    return label


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _stats_text(count: int, total_size: int) -> str:
    if count == 0:
        return "0 files"
    return f"{count} {_plural(count, 'file', 'files')} \u00b7 {_format_size(total_size)}"


def _empty_text(has_files: bool, searching: bool) -> str:
    if not has_files:
        return "Drop files here.\nWe'll take care of the rest."
    if searching:
        return "No files match your search."
    return "No files to show."


def _duration_label(duration: timedelta) -> str:
    for label, option in RETENTION_OPTIONS:
        if option == duration:
            return label
    return "1 day"


def _expiry_sort_key(record: FileRecord) -> datetime:
    if record.expires_at is None:
        return datetime.max.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(record.expires_at)


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    value = float(size)
    units = ("KB", "MB", "GB", "TB")
    for index, unit in enumerate(units):
        value /= 1024.0
        if value < 1024.0 or index == len(units) - 1:
            return f"{value:.1f} {unit}"
    return f"{size} B"


def _format_added(added_at: str) -> str:
    try:
        moment = datetime.fromisoformat(added_at)
    except ValueError:
        return added_at
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def _format_expiry(expires_at: str | None) -> str:
    if not expires_at:
        return "\u2014"
    try:
        moment = datetime.fromisoformat(expires_at)
    except ValueError:
        return expires_at
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")
