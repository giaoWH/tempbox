"""Small secondary windows: expiry picker, settings and cleanup history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from PySide6.QtCore import QDateTime, QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import autostart, quick_action, updates
from .formatting import duration_label, format_added, format_expiry, format_size
from .history import CleanupHistory
from .storage import DEFAULT_RETENTION, RETENTION_OPTIONS

if TYPE_CHECKING:
    from .window import MainWindow


class ExpiryDialog(QDialog):
    """Choose a custom expiry date and time."""

    def __init__(
        self, current: datetime | None, parent: QWidget | None = None
    ) -> None:
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
        return datetime.fromtimestamp(
            self.editor.dateTime().toSecsSinceEpoch(), timezone.utc
        )


class SettingsDialog(QDialog):
    """Default retention, auto-cleanup controls, Finder integration and About."""

    def __init__(self, window: "MainWindow") -> None:
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

        hint = QLabel(
            "Login launch starts TempBox hidden in the menu bar. While TempBox runs "
            "as a Python script, it uses the current Python and project paths; move "
            "either and toggle this setting off and on again."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        self.pause_checkbox = QCheckBox("Pause automatic cleanup")
        self.pause_checkbox.setChecked(window.auto_cleanup_paused)
        self.pause_checkbox.toggled.connect(self._on_pause_toggled)
        layout.addWidget(self.pause_checkbox)

        self.reminder_checkbox = QCheckBox("Remind me 10 minutes before expiry")
        self.reminder_checkbox.setChecked(window.settings.remind_before_expiry)
        self.reminder_checkbox.toggled.connect(self._on_reminder_toggled)
        layout.addWidget(self.reminder_checkbox)

        layout.addSpacing(6)
        layout.addWidget(QLabel("Finder Quick Action"))
        self.quick_action_state = QLabel("")
        self.quick_action_state.setWordWrap(True)
        self.quick_action_state.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.quick_action_state)
        self.quick_action_button = QPushButton("")
        self.quick_action_button.clicked.connect(self._on_quick_action_clicked)
        layout.addWidget(self.quick_action_button)
        self._refresh_quick_action_state()

        layout.addSpacing(6)
        layout.addWidget(QLabel("About TempBox"))
        self.version_label = QLabel(f"TempBox v{updates.current_version()}")
        layout.addWidget(self.version_label)
        self.check_updates_button = QPushButton("Check for Updates\u2026")
        self.check_updates_button.clicked.connect(self._on_check_updates)
        layout.addWidget(self.check_updates_button)

        self.note_label = QLabel("")
        self.note_label.setWordWrap(True)
        self.note_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.note_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_retention_changed(self, index: int) -> None:
        duration = self.retention_combo.itemData(index)
        if duration is None:
            return
        self.window.set_default_retention(duration)
        self.note_label.setText(f"New files will be kept for {duration_label(duration)}.")

    def _on_pause_toggled(self, paused: bool) -> None:
        if self.window.set_auto_cleanup_paused(paused):
            self.note_label.setText(
                "Automatic cleanup paused." if paused else "Automatic cleanup resumed."
            )
            return
        self.pause_checkbox.blockSignals(True)
        self.pause_checkbox.setChecked(not paused)
        self.pause_checkbox.blockSignals(False)

    def _on_reminder_toggled(self, enabled: bool) -> None:
        previous = self.window.settings.remind_before_expiry
        self.window.settings.remind_before_expiry = enabled
        try:
            self.window.settings.save(self.window.store.root)
        except OSError as exc:
            self.window.settings.remind_before_expiry = previous
            self.reminder_checkbox.blockSignals(True)
            self.reminder_checkbox.setChecked(previous)
            self.reminder_checkbox.blockSignals(False)
            QMessageBox.warning(self, "Expiry reminders", f"Could not save: {exc}")
            return
        self.note_label.setText(f"Expiry reminders {'enabled' if enabled else 'disabled'}.")

    def _refresh_quick_action_state(self) -> None:
        if quick_action.is_installed():
            self.quick_action_state.setText(
                "Installed. Finder \u2192 right-click \u2192 Quick Actions or Services "
                "\u2192 Move to TempBox. If it is missing, reopen Finder or enable it "
                "under System Settings \u2192 Keyboard \u2192 Keyboard Shortcuts "
                "\u2192 Services."
            )
            self.quick_action_button.setText("Remove Finder Quick Action")
        else:
            self.quick_action_state.setText(
                "Not installed. Adds Move to TempBox to Finder's Quick Actions."
            )
            self.quick_action_button.setText("Install Finder Quick Action")

    def _on_quick_action_clicked(self) -> None:
        installed = quick_action.is_installed()
        try:
            if installed:
                quick_action.uninstall()
                action = "removed"
            else:
                quick_action.install()
                action = "installed"
        except OSError as exc:
            QMessageBox.warning(self, "Finder Quick Action", str(exc))
            return
        self._refresh_quick_action_state()
        self.note_label.setText(
            f"Finder Quick Action {action}. Finder may need a new window or relaunch; "
            "check Quick Actions and Services in the right-click menu. If it is still "
            "missing, enable it under System Settings \u2192 Keyboard \u2192 "
            "Keyboard Shortcuts \u2192 Services."
        )

    def _on_check_updates(self) -> None:
        status = updates.check_for_updates()
        QMessageBox.information(
            self,
            "Check for Updates",
            f"{status.message}\n\nCurrent version: {updates.current_version()}",
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


class HistoryDialog(QDialog):
    """Recently cleaned files (metadata only; never restores from Trash)."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.history = CleanupHistory(window.store.root)
        self.history.load()
        self.setWindowTitle("Recently Cleaned")
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(8)

        title = QLabel("Recently Cleaned")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)
        subtitle = QLabel(
            "Files TempBox moved to the Trash after they expired. This history is "
            "metadata only; files in the Trash are not restored automatically."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(subtitle)

        self.entry_list = QListWidget()
        self.entry_list.setWordWrap(True)
        self.entry_list.setSpacing(2)
        layout.addWidget(self.entry_list, 1)
        self.empty_label = QLabel("No files have been cleaned up yet.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: gray;")
        layout.addWidget(self.empty_label)

        buttons = QHBoxLayout()
        self.clear_button = QPushButton("Clear History")
        self.clear_button.clicked.connect(self._clear_history)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._populate()

    def _populate(self) -> None:
        self.entry_list.clear()
        for entry in self.history.entries:
            item = QListWidgetItem(
                f"{entry.original_name}  \u00b7  {format_size(entry.size)}\n"
                f"Cleaned {format_added(entry.trashed_at)}  \u00b7  {entry.original_path}"
            )
            item.setToolTip(
                f"Added {format_added(entry.added_at)}\n"
                f"Expired {format_expiry(entry.expires_at)}\n"
                f"Cleaned {format_added(entry.trashed_at)}\n{entry.original_path}"
            )
            item.setSizeHint(QSize(0, 42))
            self.entry_list.addItem(item)
        has_entries = bool(self.history.entries)
        self.entry_list.setVisible(has_entries)
        self.empty_label.setVisible(not has_entries)
        self.clear_button.setEnabled(has_entries)

    def _clear_history(self) -> None:
        if not self.history.entries:
            return
        answer = QMessageBox.question(
            self,
            "Clear cleanup history",
            "Clear the list of recently cleaned files?\n\n"
            "This only clears the history; files already in the system Trash are "
            "not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.history.clear()
        except OSError as exc:
            QMessageBox.warning(self, "Cleanup history", f"Could not save: {exc}")
            return
        self._populate()
