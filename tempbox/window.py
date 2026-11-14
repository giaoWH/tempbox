"""Main window: drop area, file list, retention and file actions."""

from __future__ import annotations

import math
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import QDateTime, QMimeData, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeySequence,
    QPalette,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

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
CLEANUP_INTERVAL_MS = 30_000
EXPIRING_SOON = timedelta(hours=1)
_AMBER = QColor("#d29922")
_RED = QColor("#e5484d")


class MainWindow(QWidget):
    """TempBox main window: drag files in, manage their lifetime, act on them."""

    def __init__(self, store: FileStore) -> None:
        super().__init__()
        self.store = store
        self._build_ui()
        self._refresh()

        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.setInterval(CLEANUP_INTERVAL_MS)
        self._cleanup_timer.timeout.connect(self._run_cleanup)
        self._cleanup_timer.start()
        self._run_cleanup()

    # -- UI construction -----------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle("TempBox")
        self.setMinimumSize(620, 460)
        self.resize(760, 560)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(14)

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

        self.table = self._build_table()
        self.empty_label = QLabel("Nothing stored yet.\nDrag files from Finder into this window.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.content = QStackedWidget()
        self.content.addWidget(self.table)
        self.content.addWidget(self.empty_label)
        layout.addWidget(self.content, 1)

        self.open_button = QPushButton("Open")
        self.reveal_button = QPushButton("Show in Finder")
        self.restore_button = QPushButton("Restore")
        self.retention_button = QPushButton("Retention")
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
            "Drop files here. New files are kept for 1 day; use Retention to change that."
        )
        self.status_label.setWordWrap(True)
        quit_button = QPushButton("Quit")
        quit_button.setFlat(True)
        quit_button.clicked.connect(QApplication.instance().quit)
        footer = QHBoxLayout()
        footer.addWidget(self.status_label, 1)
        footer.addWidget(quit_button)
        layout.addLayout(footer)

        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.doubleClicked.connect(self._open_selected)
        self._quit_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Quit), self)
        self._quit_shortcut.activated.connect(QApplication.instance().quit)
        self._update_buttons()

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
            """
        )

    def _build_drop_zone(self) -> QFrame:
        zone = QFrame()
        zone.setObjectName("dropZone")
        zone.setMinimumHeight(112)
        zone.setProperty("dragging", False)
        zone_layout = QVBoxLayout(zone)
        zone_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zone_layout.setSpacing(4)
        heading = QLabel("Drag files here")
        heading.setObjectName("dropTitle")
        hint = _muted_label(
            "Files are moved into TempBox. They are moved to the Trash when their time is up."
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
        table.verticalHeader().setDefaultSectionSize(30)
        table.setShowGrid(False)
        table.setAlternatingRowColors(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        table.setAcceptDrops(False)
        table.viewport().setAcceptDrops(False)
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
        custom_action = menu.addAction("Custom…")
        custom_action.triggered.connect(self._set_custom_expiry)
        return menu

    # -- list rendering ------------------------------------------------

    def _refresh(self) -> None:
        selected = self._selected_record()
        selected_id = selected.id if selected else None
        records = self.store.list_files()
        now = datetime.now(timezone.utc)

        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            name_item = QTableWidgetItem(record.original_name)
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

        count = len(records)
        self.count_label.setText(f"{count} {_plural(count, 'file', 'files')}")
        self.content.setCurrentWidget(self.table if count else self.empty_label)

        if selected_id is not None:
            for row, record in enumerate(records):
                if record.id == selected_id:
                    self.table.selectRow(row)
                    break
        self._update_buttons()

    def _remaining_display(
        self, record: FileRecord, now: datetime
    ) -> tuple[str, QColor | None, str]:
        if not self.store.stored_path(record).is_file():
            return "File missing", _RED, "The stored file is missing from TempBox."
        if record.trash_error:
            return "Cleanup failed", _RED, record.trash_error
        if record.expires_at is None:
            return "No expiry", None, "This file has no expiry time. Use Retention to set one."
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

    def _selected_record(self) -> FileRecord | None:
        row = self.table.currentRow()
        if row < 0 or not self.table.selectionModel().hasSelection():
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        return self.store.get(str(item.data(Qt.ItemDataRole.UserRole)))

    def _update_buttons(self) -> None:
        has_selection = self._selected_record() is not None
        self.open_button.setEnabled(has_selection)
        self.reveal_button.setEnabled(has_selection)
        self.restore_button.setEnabled(has_selection)
        self.retention_button.setEnabled(has_selection)

    # -- retention -----------------------------------------------------

    def _set_retention(self, duration: timedelta) -> None:
        record = self._selected_record()
        if record is None:
            return
        self._apply_expiry(record, datetime.now(timezone.utc) + duration)

    def _set_custom_expiry(self) -> None:
        record = self._selected_record()
        if record is None:
            return
        current = datetime.fromisoformat(record.expires_at) if record.expires_at else None
        dialog = ExpiryDialog(current, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        expires_at = dialog.selected_expiry()
        if expires_at <= datetime.now(timezone.utc):
            QMessageBox.warning(
                self, "Invalid expiry time", "Choose a time that is still in the future."
            )
            return
        self._apply_expiry(record, expires_at)

    def _apply_expiry(self, record: FileRecord, expires_at: datetime) -> None:
        try:
            updated = self.store.set_expiry(record.id, expires_at)
        except StorageError as exc:
            self._refresh()
            self._notify_error(str(exc))
            return
        self._refresh()
        self._set_status(
            f"'{record.original_name}' now expires {_format_expiry(updated.expires_at)}."
        )

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
        record = self._selected_record()
        if record is None:
            return
        stored = self.store.stored_path(record)
        if not stored.is_file():
            self._notify_error(f"'{record.original_name}' is missing from TempBox storage.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(stored))):
            self._notify_error(f"macOS could not open '{record.original_name}'.")

    def _reveal_selected(self) -> None:
        record = self._selected_record()
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
        record = self._selected_record()
        if record is None:
            return
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


def _muted_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
    return label


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


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
        return "—"
    try:
        moment = datetime.fromisoformat(expires_at)
    except ValueError:
        return expires_at
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")
