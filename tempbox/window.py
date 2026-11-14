"""Floating panel window: file cards, search, retention and file actions.

The visual layout is the approved floating-panel design; all data and actions are
backed by the real FileStore, settings and lifecycle logic.
"""

from __future__ import annotations

import math
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QMimeData,
    QPoint,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
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
    QApplication,
    QDialog,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .dialogs import ExpiryDialog, HistoryDialog, SettingsDialog
from .formatting import (
    duration_label as _duration_label,
    format_added as _format_added,
    format_expiry as _format_expiry,
    format_size,
    plural as _plural,
)
from .history import CleanupHistory
from .settings import AppSettings
from .storage import (
    CleanupResult,
    FileRecord,
    FileStore,
    ImportResult,
    RETENTION_OPTIONS,
    StorageError,
)
from .ui_theme import (
    DARK,
    LIGHT,
    Theme,
    brand_pixmap,
    build_styles,
    menu_styles,
    search_icon,
    settings_icon,
)
from .ui_widgets import DropZone, EmptyState, FileRow, PanelSurface

SORT_OPTIONS = (
    ("added", "Added"),
    ("name", "Name"),
    ("size", "Size"),
    ("expires", "Expires"),
)
CLEANUP_INTERVAL_MS = 30_000
EXTERNAL_SYNC_INTERVAL_MS = 2_000
REMINDER_WINDOW = timedelta(minutes=10)
EXPIRING_SOON = timedelta(hours=1)
AUTO_HIDE_REOPEN_GRACE = 0.5


class MainWindow(QWidget):
    """A compact macOS menu bar floating panel backed by the real FileStore."""

    quit_requested = Signal()

    PANEL_WIDTH = 420
    SHADOW_MARGIN = 14
    MAX_VISIBLE_ROWS = 7

    def __init__(self, store: FileStore) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        self.setWindowTitle("TempBox")

        self.store = store
        self.settings = AppSettings.load(store.root)
        self.store.default_retention = self.settings.default_retention
        self._theme = LIGHT
        self._theme_applied = False
        self._rows: list[FileRow] = []
        self._selection_mode = False
        self._checked_ids: set[str] = set()
        self._sort_key = "added"
        self._search_text = ""
        self._status_text = "Ready"
        self._auto_hidden_at: float | None = None
        self._auto_cleanup_paused = self.settings.pause_auto_cleanup
        if self._auto_cleanup_paused:
            self._status_text = "Automatic cleanup is paused."
        self._notifier = None
        self._reminded: dict[str, str] = {}
        self._history = CleanupHistory(store.root)

        self._build_ui()
        self.refresh_theme(force=True)
        self._render_rows()

        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.setInterval(CLEANUP_INTERVAL_MS)
        self._cleanup_timer.timeout.connect(self._on_cleanup_tick)
        self._cleanup_timer.start()

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(EXTERNAL_SYNC_INTERVAL_MS)
        self._sync_timer.timeout.connect(self._sync_external_changes)
        self._sync_timer.start()

        if not self._auto_cleanup_paused:
            self._run_cleanup()
        else:
            self._render_rows()

        application = QApplication.instance()
        if application is not None:
            application.applicationStateChanged.connect(self._on_application_state_changed)
        self._connect_style_hints()

    # -- UI construction -----------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            self.SHADOW_MARGIN, self.SHADOW_MARGIN, self.SHADOW_MARGIN, self.SHADOW_MARGIN
        )
        outer.setSpacing(0)
        self.surface = PanelSurface(self._theme, self)
        self.surface.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        outer.addWidget(self.surface)
        self._shadow = QGraphicsDropShadowEffect(self.surface)
        self._shadow.setBlurRadius(26)
        self._shadow.setOffset(0, 8)
        self._shadow.setColor(QColor(0, 0, 0, 70))
        self.surface.setGraphicsEffect(self._shadow)

        layout = QVBoxLayout(self.surface)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        layout.addLayout(self._build_header())
        self.drop_zone = DropZone(self._theme)
        layout.addWidget(self.drop_zone)
        layout.addLayout(self._build_search_row())

        self.list_stack = QStackedWidget()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setAcceptDrops(False)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.viewport().setAcceptDrops(False)
        self.rows_container = QWidget()
        self.rows_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 2, 0, 2)
        self.rows_layout.setSpacing(0)
        self.scroll.setWidget(self.rows_container)
        self.empty_state = EmptyState(self._theme)
        self.list_stack.addWidget(self.scroll)
        self.list_stack.addWidget(self.empty_state)
        layout.addWidget(self.list_stack)

        self.footer_stack = QStackedWidget()
        self.footer_stack.addWidget(self._build_footer())
        self.footer_stack.addWidget(self._build_batch_footer())
        self.footer_stack.setFixedHeight(30)
        layout.addWidget(self.footer_stack)

        self.setFixedWidth(self.PANEL_WIDTH + self.SHADOW_MARGIN * 2)

        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._escape_shortcut.activated.connect(self.hide)
        self._close_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Close), self)
        self._close_shortcut.activated.connect(self.hide)
        self._quit_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Quit), self)
        self._quit_shortcut.activated.connect(self.quit_requested)

        self._update_default_retention_text()

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(7)
        self.brand_label = QLabel()
        self.brand_label.setPixmap(brand_pixmap(26))
        self.brand_label.setFixedSize(26, 26)
        title = QLabel("TempBox")
        title.setObjectName("PanelTitle")
        self.stats_label = QLabel("0 files")
        self.stats_label.setObjectName("StatsLabel")
        self.select_button = QToolButton()
        self.select_button.setObjectName("HeaderButton")
        self.select_button.setText("Select")
        self.select_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_button.clicked.connect(self._toggle_selection_mode)
        self.settings_button = QToolButton()
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip("Settings")
        self.settings_button.clicked.connect(self._open_settings)
        header.addWidget(self.brand_label)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.stats_label)
        header.addSpacing(4)
        header.addWidget(self.select_button)
        header.addWidget(self.settings_button)
        return header

    def _build_search_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("SearchField")
        self.search_edit.setPlaceholderText("Search files")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedHeight(30)
        self.search_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.search_edit.textChanged.connect(self._on_search_changed)
        self.search_action = self.search_edit.addAction(
            search_icon(self._theme), QLineEdit.ActionPosition.LeadingPosition
        )
        self.sort_button = QToolButton()
        self.sort_button.setObjectName("SortButton")
        self.sort_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sort_button.setFixedHeight(30)
        self.sort_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.sort_menu = QMenu(self)
        for index, (key, label) in enumerate(SORT_OPTIONS):
            action = self.sort_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(index == 0)
            action.triggered.connect(
                lambda _checked=False, sort_key=key: self._set_sort(sort_key)
            )
        self.sort_button.setMenu(self.sort_menu)
        self.sort_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.sort_button.setText("Added")
        row.addWidget(self.search_edit, 1)
        row.addWidget(self.sort_button)
        return row

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)
        self.footer_status = QLabel(self._status_text)
        self.footer_status.setObjectName("FooterText")
        self.footer_hint = QLabel()
        self.footer_hint.setObjectName("FooterHint")
        self.pause_label = QLabel("Cleanup paused")
        self.pause_label.setObjectName("PausedLabel")
        self.pause_label.setToolTip("Automatic expiry cleanup is paused in Settings.")
        self.pause_label.hide()
        self.history_button = QPushButton("History")
        self.history_button.setObjectName("FooterButton")
        self.history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_button.clicked.connect(self._open_history)
        self.quit_button = QPushButton("Quit")
        self.quit_button.setObjectName("FooterButton")
        self.quit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quit_button.clicked.connect(self.quit_requested)
        layout.addWidget(self.footer_status)
        layout.addStretch(1)
        layout.addWidget(self.pause_label)
        layout.addWidget(self.footer_hint)
        layout.addWidget(self.history_button)
        layout.addWidget(self.quit_button)
        return footer

    def _build_batch_footer(self) -> QWidget:
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(2)
        self.batch_count = QLabel("Select files")
        self.batch_count.setObjectName("BatchCount")
        self.restore_button = QPushButton("Restore")
        self.restore_button.setObjectName("BatchButton")
        self.restore_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restore_button.clicked.connect(self._restore_checked)
        self.expiration_button = QPushButton("Expiration")
        self.expiration_button.setObjectName("BatchButton")
        self.expiration_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expiration_button.clicked.connect(self._show_batch_expiry_menu)
        layout.addWidget(self.batch_count)
        layout.addStretch(1)
        layout.addWidget(self.restore_button)
        layout.addWidget(self.expiration_button)
        return footer

    # -- theme ---------------------------------------------------------

    def _connect_style_hints(self) -> None:
        hints = QApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._on_system_color_scheme_changed)

    def _system_theme(self) -> Theme:
        try:
            dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except (AttributeError, RuntimeError):
            dark = QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128
        return DARK if dark else LIGHT

    def refresh_theme(self, force: bool = False) -> None:
        theme = self._system_theme()
        if not force and self._theme_applied and theme == self._theme:
            return
        self._theme = theme
        self._theme_applied = True
        self.setStyleSheet(build_styles(theme))
        self.surface.set_theme(theme)
        self.drop_zone.set_theme(theme)
        self.empty_state.set_theme(theme)
        self._shadow.setColor(QColor(0, 0, 0, 120) if theme.is_dark else QColor(0, 0, 0, 55))
        self.search_action.setIcon(search_icon(theme))
        self.settings_button.setIcon(settings_icon(theme))
        for row in self._rows:
            row.set_theme(theme)

    def _on_system_color_scheme_changed(self, *args) -> None:
        QTimer.singleShot(0, self.refresh_theme)

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() in (
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.PaletteChange,
        ):
            QTimer.singleShot(0, self.refresh_theme)
        super().changeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.search_edit.clearFocus()
        self.surface.setFocus()

    # -- list rendering ------------------------------------------------

    @property
    def rows(self) -> list[FileRow]:
        return self._rows

    @property
    def auto_cleanup_paused(self) -> bool:
        return self._auto_cleanup_paused

    def _visible_records(self) -> list[FileRecord]:
        records = self.store.list_files()
        keyword = self._search_text.strip().casefold()
        if keyword:
            records = [
                record for record in records if keyword in record.original_name.casefold()
            ]
        if self._sort_key == "name":
            records.sort(key=lambda record: record.original_name.casefold())
        elif self._sort_key == "size":
            records.sort(key=lambda record: record.size, reverse=True)
        elif self._sort_key == "expires":
            records.sort(key=_expiry_sort_key)
        return records

    def _row_display(self, record: FileRecord, now: datetime) -> tuple[str, str, str]:
        stored = self.store.stored_path(record)
        added = _format_added(record.added_at)
        expires = _format_expiry(record.expires_at)
        tooltip = (
            f"{record.original_name}\n{format_size(record.size)}\n"
            f"Added {added}\nExpires {expires}"
        )
        if not stored.is_file():
            return "File missing", "failed", tooltip + "\nThe stored file is missing."
        if record.trash_error:
            return "Cleanup failed", "failed", tooltip + f"\n{record.trash_error}"
        if record.expires_at is None:
            return "No expiration", "none", tooltip
        remaining = datetime.fromisoformat(record.expires_at) - now
        if remaining <= timedelta(0):
            return "Expired", "expired", tooltip
        seconds = int(remaining.total_seconds())
        if remaining < EXPIRING_SOON:
            minutes = max(1, math.ceil(seconds / 60))
            return f"{minutes} min", "soon", tooltip
        hours = math.ceil(seconds / 3600)
        days = math.ceil(seconds / 86400)
        if days > 1:
            return f"{days} days", "normal", tooltip
        if hours >= 24:
            return "1 day", "normal", tooltip
        return f"{hours} {_plural(hours, 'hour', 'hours')}", "normal", tooltip

    def _render_rows(self) -> None:
        existing_ids = {record.id for record in self.store.records.values()}
        self._checked_ids &= existing_ids
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = []

        visible = self._visible_records()
        now = datetime.now(timezone.utc)
        for record in visible:
            remaining, tone, tooltip = self._row_display(record, now)
            row = FileRow(record, remaining, tone, tooltip, self._theme)
            row.set_selection_mode(self._selection_mode)
            row.set_checked(record.id in self._checked_ids)
            row.menu_requested.connect(self._show_row_menu)
            row.checked_changed.connect(self._on_row_checked)
            row.opened.connect(self._open_row)
            self.rows_layout.addWidget(row)
            self._rows.append(row)
        self.rows_layout.addStretch(1)

        all_records = self.store.list_files()
        total_size = sum(record.size for record in all_records)
        self.stats_label.setText(_stats_text(len(all_records), total_size))

        has_rows = bool(visible)
        if has_rows:
            self.list_stack.setCurrentWidget(self.scroll)
        else:
            self.list_stack.setCurrentWidget(self.empty_state)
            if all_records and self._search_text.strip():
                self.empty_state.set_state(
                    "No files match your search.", "Try a different keyword."
                )
            else:
                self.empty_state.set_state(
                    "No files yet", "Drop files here and we'll take care of the rest."
                )
        self.list_stack.setFixedHeight(
            (min(max(len(visible), 1), self.MAX_VISIBLE_ROWS) * FileRow.ROW_HEIGHT + 8)
            if has_rows
            else 148
        )
        self._update_batch_footer()
        self._relayout()

    def _refresh(self) -> None:
        self._render_rows()

    def _relayout(self) -> None:
        self.surface.layout().activate()
        self.surface.adjustSize()
        self.layout().activate()
        self.adjustSize()
        self._clamp_to_screen()

    def _clamp_to_screen(self) -> None:
        if not self.isVisible():
            return
        screen = QApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        margin = self.SHADOW_MARGIN
        width = self.width() - margin * 2
        height = self.height() - margin * 2
        x = max(
            available.left() + 8 - margin,
            min(self.x(), available.right() - 8 - margin - width),
        )
        y = max(
            available.top() + 8 - margin,
            min(self.y(), available.bottom() - 8 - margin - height),
        )
        self.move(x, y)

    # -- stats ---------------------------------------------------------

    def content_size(self) -> QSize:
        return QSize(self.PANEL_WIDTH, self.surface.height())

    # -- search / sort -------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        self._search_text = text
        self._render_rows()

    def _set_sort(self, key: str) -> None:
        self._sort_key = key
        label = self._sort_label()
        for action in self.sort_menu.actions():
            action.setChecked(action.text() == label)
        self.sort_button.setText(label)
        self._render_rows()

    def _sort_label(self) -> str:
        for key, label in SORT_OPTIONS:
            if key == self._sort_key:
                return label
        return "Added"

    # -- selection -----------------------------------------------------

    def _toggle_selection_mode(self) -> None:
        self.set_selection_mode(not self._selection_mode)

    def set_selection_mode(self, enabled: bool) -> None:
        self._selection_mode = enabled
        self.select_button.setText("Done" if enabled else "Select")
        if not enabled:
            self._checked_ids.clear()
        for row in self._rows:
            row.set_selection_mode(enabled)
            row.set_checked(row.record.id in self._checked_ids)
        self.footer_stack.setCurrentIndex(1 if enabled else 0)
        self._update_batch_footer()

    def _on_row_checked(self, row: FileRow, checked: bool) -> None:
        if checked:
            self._checked_ids.add(row.record.id)
        else:
            self._checked_ids.discard(row.record.id)
        row.set_checked(checked)
        self._update_batch_footer()

    def _checked_records(self) -> list[FileRecord]:
        records: list[FileRecord] = []
        for row in self._rows:
            if row.record.id in self._checked_ids:
                records.append(row.record)
        return records

    def _update_batch_footer(self) -> None:
        count = len(self._checked_ids)
        self.batch_count.setText("Select files" if count == 0 else f"{count} selected")
        self.restore_button.setEnabled(count > 0)
        self.expiration_button.setEnabled(count > 0)

    # -- retention -----------------------------------------------------

    def _set_retention(
        self, duration: timedelta, records: list[FileRecord] | None = None
    ) -> None:
        targets = records if records is not None else self._checked_records()
        if not targets:
            return
        self._apply_expiry(targets, datetime.now(timezone.utc) + duration)

    def _set_custom_expiry(self, records: list[FileRecord] | None = None) -> None:
        targets = records if records is not None else self._checked_records()
        if not targets:
            return
        current = None
        if len(targets) == 1 and targets[0].expires_at:
            current = datetime.fromisoformat(targets[0].expires_at)
        dialog = ExpiryDialog(current, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        expires_at = dialog.selected_expiry()
        if expires_at <= datetime.now(timezone.utc):
            QMessageBox.warning(
                self, "Invalid expiry time", "Choose a time that is still in the future."
            )
            return
        self._apply_expiry(targets, expires_at)

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
            self._render_rows()
            self._notify_error(str(exc))
            return
        self._render_rows()
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
        self._update_default_retention_text()
        self._set_status(f"New files will be kept for {_duration_label(duration)}.")

    def _update_default_retention_text(self) -> None:
        label = _duration_label(self.store.default_retention)
        self.footer_hint.setText(f"Default \u00b7 {label}")
        self.drop_zone.set_hint(f"Keep for {label} by default")
        self._update_pause_indicator()

    def _update_pause_indicator(self) -> None:
        self.pause_label.setVisible(self._auto_cleanup_paused)
        # The footer is compact; while paused the amber status replaces the
        # default-retention hint instead of squeezing both into one row.
        self.footer_hint.setVisible(not self._auto_cleanup_paused)

    def _save_settings(self) -> bool:
        try:
            self.settings.save(self.store.root)
        except OSError as exc:
            self._notify_error(f"Could not save settings: {exc}")
            return False
        return True

    def set_auto_cleanup_paused(self, paused: bool) -> bool:
        """Persistently pause/resume cleanup, confirming overdue files on resume."""
        if paused == self._auto_cleanup_paused:
            return True
        overdue: list[FileRecord] = []
        if not paused:
            overdue = self._overdue_records()
            if overdue:
                count = len(overdue)
                answer = QMessageBox.question(
                    self,
                    "Resume automatic cleanup",
                    f"{count} {_plural(count, 'file is', 'files are')} past the expiry time.\n\n"
                    "Move them to the Trash now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    self._set_status("Automatic cleanup remains paused.")
                    return False
        previous = self._auto_cleanup_paused
        self.settings.pause_auto_cleanup = paused
        if not self._save_settings():
            self.settings.pause_auto_cleanup = previous
            return False
        self._auto_cleanup_paused = paused
        self._update_pause_indicator()
        if paused:
            self._set_status("Automatic cleanup paused.")
        else:
            self._set_status("Automatic cleanup resumed.")
            self._run_cleanup()
        return True

    def _overdue_records(self) -> list[FileRecord]:
        now = datetime.now(timezone.utc)
        overdue = []
        for record in self.store.list_files():
            if not record.expires_at:
                continue
            try:
                expires_at = datetime.fromisoformat(record.expires_at)
            except ValueError:
                continue
            if expires_at <= now:
                overdue.append(record)
        return overdue

    # -- notifications / external changes ------------------------------

    def set_notifier(self, notifier) -> None:
        self._notifier = notifier

    def _sync_external_changes(self) -> None:
        if (
            QApplication.activeModalWidget() is not None
            or QApplication.activePopupWidget() is not None
        ):
            return
        try:
            changed = self.store.refresh_from_disk()
        except StorageError:
            return
        if changed:
            self._render_rows()

    def check_expiry_reminders(self) -> None:
        """Notify once per file/expiry pair within 10 minutes of expiry."""
        if not self.settings.remind_before_expiry:
            return
        records = self.store.list_files()
        known = {record.id: record.expires_at for record in records if record.expires_at}
        self._reminded = {
            record_id: expires_at
            for record_id, expires_at in self._reminded.items()
            if known.get(record_id) == expires_at
        }
        now = datetime.now(timezone.utc)
        due: list[FileRecord] = []
        for record in records:
            if not record.expires_at:
                continue
            try:
                expires_at = datetime.fromisoformat(record.expires_at)
            except ValueError:
                continue
            remaining = expires_at - now
            if timedelta(0) < remaining <= REMINDER_WINDOW:
                if self._reminded.get(record.id) != record.expires_at:
                    due.append(record)
        if not due:
            return
        for record in due:
            self._reminded[record.id] = record.expires_at
        if self._notifier is None:
            return
        if len(due) == 1:
            remaining = datetime.fromisoformat(due[0].expires_at) - now
            minutes = max(1, math.ceil(remaining.total_seconds() / 60))
            message = f"'{due[0].original_name}' will expire in {minutes} minutes."
        else:
            names = ", ".join(f"'{record.original_name}'" for record in due[:3])
            if len(due) > 3:
                names += ", ..."
            message = f"{len(due)} files will expire in the next 10 minutes: {names}"
        try:
            self._notifier("TempBox", message)
        except Exception:
            # Notification failures must never affect cleanup or file handling.
            pass

    def _on_cleanup_tick(self) -> None:
        self._sync_external_changes()
        self.check_expiry_reminders()
        if self._auto_cleanup_paused:
            self._render_rows()
            return
        self._run_cleanup()

    # -- history -------------------------------------------------------

    def _open_history(self) -> None:
        dialog = HistoryDialog(self)
        dialog.exec()

    # -- expiry clean-up -----------------------------------------------

    def _run_cleanup(self) -> None:
        result = self.store.cleanup_expired()
        history_error: str | None = None
        if result.trashed:
            try:
                self._history.load()
                self._history.add(result.trashed)
            except OSError as exc:
                history_error = str(exc)
        self._render_rows()
        self._report_cleanup(result, history_error)

    def _report_cleanup(
        self, result: CleanupResult, history_error: str | None = None
    ) -> None:
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
        if history_error:
            parts.append(f"Could not save cleanup history: {history_error}")
        if parts:
            self._set_status(" ".join(parts))

    # -- imports -------------------------------------------------------

    def _import_paths(self, paths: list[Path]) -> None:
        if not paths:
            return
        result = self.store.import_files(paths)
        self._render_rows()
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
            self.drop_zone.set_active(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._local_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.drop_zone.set_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        self.drop_zone.set_active(False)
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

    # -- file actions --------------------------------------------------

    def _build_row_menu(self, record: FileRecord) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet(menu_styles(self._theme))
        menu.addAction("Open").triggered.connect(lambda: self._open_record(record))
        menu.addAction("Show in Finder").triggered.connect(
            lambda: self._reveal_record(record)
        )
        menu.addAction("Restore").triggered.connect(lambda: self._restore_single(record))
        menu.addSeparator()
        expiry_menu = menu.addMenu("Change Expiration")
        for label, duration in RETENTION_OPTIONS:
            expiry_menu.addAction(label).triggered.connect(
                lambda _checked=False, value=duration: self._set_retention(value, [record])
            )
        expiry_menu.addSeparator()
        expiry_menu.addAction("Custom\u2026").triggered.connect(
            lambda: self._set_custom_expiry([record])
        )
        return menu

    def _show_row_menu(self, row: FileRow) -> QMenu:
        menu = self._build_row_menu(row.record)
        menu.popup(row.mapToGlobal(QPoint(row.width() - 28, row.height() - 4)))
        return menu

    def _open_row(self, row: FileRow) -> None:
        self._open_record(row.record)

    def _open_record(self, record: FileRecord) -> None:
        stored = self.store.stored_path(record)
        if not stored.is_file():
            self._notify_error(f"'{record.original_name}' is missing from TempBox storage.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(stored))):
            self._notify_error(f"macOS could not open '{record.original_name}'.")

    def _reveal_record(self, record: FileRecord) -> None:
        stored = self.store.stored_path(record)
        if not stored.is_file():
            self._notify_error(f"'{record.original_name}' is missing from TempBox storage.")
            return
        completed = subprocess.run(
            ["open", "-R", str(stored)], check=False, capture_output=True
        )
        if completed.returncode != 0:
            self._notify_error(f"Finder could not show '{record.original_name}'.")

    def _restore_checked(self) -> None:
        records = self._checked_records()
        if records:
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
                failures.append(
                    (record.original_name, "a file already exists at the original place")
                )
                continue
            try:
                self.store.restore(record.id, original)
            except StorageError as exc:
                failures.append((record.original_name, str(exc)))
            else:
                restored += 1
        self._render_rows()
        parts = []
        if restored:
            parts.append(f"Restored {restored} {_plural(restored, 'file', 'files')}.")
        if failures:
            count = len(failures)
            parts.append(f"{count} {_plural(count, 'file', 'files')} failed.")
        self._set_status(" ".join(parts) if parts else "Nothing to restore.")
        if failures:
            details = "\n".join(f"\u2022 {name}: {reason}" for name, reason in failures[:8])
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
            directory = QFileDialog.getExistingDirectory(
                self, "Choose a folder", str(start_dir)
            )
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
            self._render_rows()
            self._notify_error(str(exc))
            return
        self._render_rows()
        self._set_status(f"Restored '{record.original_name}' to {restored}.")

    # -- batch expiry menu ---------------------------------------------

    def _show_batch_expiry_menu(self) -> None:
        records = self._checked_records()
        if not records:
            return
        menu = QMenu(self)
        menu.setStyleSheet(menu_styles(self._theme))
        for label, duration in RETENTION_OPTIONS:
            menu.addAction(label).triggered.connect(
                lambda _checked=False, value=duration: self._set_retention(value, records)
            )
        menu.addSeparator()
        menu.addAction("Custom\u2026").triggered.connect(
            lambda: self._set_custom_expiry(records)
        )
        menu.exec(self.expiration_button.mapToGlobal(QPoint(0, -8)))

    # -- misc ----------------------------------------------------------

    def _notify_error(self, message: str) -> None:
        self._set_status(message)
        QMessageBox.critical(self, "TempBox", message)

    def _set_status(self, text: str) -> None:
        self._status_text = text
        self.footer_status.setText(text)

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
        if self._auto_hidden_at is None:
            return False
        hidden_seconds_ago = time.monotonic() - self._auto_hidden_at
        self._auto_hidden_at = None
        return hidden_seconds_ago <= AUTO_HIDE_REOPEN_GRACE

    def clear_auto_hide_marker(self) -> None:
        self._auto_hidden_at = None

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()


def _stats_text(count: int, total_size: int) -> str:
    if count == 0:
        return "0 files"
    return f"{count} {_plural(count, 'file', 'files')} \u00b7 {format_size(total_size)}"


def _expiry_sort_key(record: FileRecord) -> datetime:
    if record.expires_at is None:
        return datetime.max.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(record.expires_at)
