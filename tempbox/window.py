"""Main window: drop area, file list and file actions."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import (
    QCloseEvent,
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
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .storage import FileRecord, FileStore, ImportResult, StorageError

COLUMNS = ("Name", "Size", "Added")


class MainWindow(QWidget):
    """TempBox main window: drag files in, see them, open or restore them."""

    def __init__(self, store: FileStore) -> None:
        super().__init__()
        self.store = store
        self._build_ui()
        self._refresh()

    # -- UI construction -----------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle("TempBox")
        self.setMinimumSize(560, 440)
        self.resize(640, 560)
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
        self.open_button.clicked.connect(self._open_selected)
        self.reveal_button.clicked.connect(self._reveal_selected)
        self.restore_button.clicked.connect(self._restore_selected)
        actions = QHBoxLayout()
        actions.addWidget(self.open_button)
        actions.addWidget(self.reveal_button)
        actions.addWidget(self.restore_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.status_label = _muted_label(
            "Drop files here. TempBox moves them into its own folder."
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
            "Files are moved into TempBox and can be restored to their original location."
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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        return table

    # -- list rendering ------------------------------------------------

    def _refresh(self) -> None:
        selected = self._selected_record()
        selected_id = selected.id if selected else None
        records = self.store.list_files()

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

        count = len(records)
        self.count_label.setText(f"{count} {_plural(count, 'file', 'files')}")
        self.content.setCurrentWidget(self.table if count else self.empty_label)

        if selected_id is not None:
            for row, record in enumerate(records):
                if record.id == selected_id:
                    self.table.selectRow(row)
                    break
        self._update_buttons()

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
