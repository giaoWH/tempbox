"""Application entry point and menu bar wiring for TempBox."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .macos import activate_application, hide_dock_icon
from .storage import FileStore, StorageError
from .window import MainWindow

APP_NAME = "TempBox"
DATA_DIR = Path.home() / "Library" / "Application Support" / APP_NAME


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    hide_dock_icon()

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        QMessageBox.critical(None, APP_NAME, f"Could not create the TempBox data folder:\n{exc}")
        return 1

    lock = QLockFile(str(DATA_DIR / ".instance.lock"))
    if not lock.tryLock(100):
        if not (lock.removeStaleLockFile() and lock.tryLock(100)):
            QMessageBox.warning(None, APP_NAME, "TempBox is already running.")
            return 1

    store = FileStore(DATA_DIR)
    try:
        problems = store.load()
    except StorageError as exc:
        QMessageBox.critical(None, APP_NAME, str(exc))
        return 1

    app.setWindowIcon(_app_icon())
    window = MainWindow(store)
    tray = _create_tray(app, window)
    _show_window(window)

    if problems:
        QMessageBox.warning(
            None,
            APP_NAME,
            "TempBox needs your attention:\n\n" + "\n".join(problems),
        )

    exit_code = app.exec()
    tray.hide()
    return exit_code


def _show_window(window: MainWindow) -> None:
    activate_application()
    window.show()
    window.raise_()
    window.activateWindow()


def _toggle_window(window: MainWindow) -> None:
    if window.isVisible():
        window.hide()
    else:
        _show_window(window)


def _create_tray(app: QApplication, window: MainWindow) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(_tray_icon(), app)
    tray.setToolTip(APP_NAME)

    menu = QMenu()
    open_action = menu.addAction("Open TempBox")
    menu.addSeparator()
    quit_action = menu.addAction("Quit TempBox")
    open_action.triggered.connect(lambda: _show_window(window))
    quit_action.triggered.connect(app.quit)

    def on_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
        action = _tray_action(reason, QApplication.mouseButtons())
        if action == "menu":
            menu.exec(QCursor.pos())
        elif action == "toggle":
            _toggle_window(window)

    tray.activated.connect(on_activated)
    tray.show()
    return tray


def _tray_action(
    reason: QSystemTrayIcon.ActivationReason,
    mouse_buttons: Qt.MouseButton,
) -> str | None:
    """Decide what a menu bar icon activation should do.

    macOS 27 reports status item clicks as ``Unknown`` because the mouse event is
    not available any more (Qt emits Unknown as a fallback), so Unknown is handled
    like a regular click. A right click still opens the menu where macOS/Qt
    reports the pressed button.
    """
    if reason == QSystemTrayIcon.ActivationReason.Context:
        return "menu"
    if reason in (
        QSystemTrayIcon.ActivationReason.Trigger,
        QSystemTrayIcon.ActivationReason.DoubleClick,
        QSystemTrayIcon.ActivationReason.Unknown,
    ):
        return "menu" if mouse_buttons & Qt.MouseButton.RightButton else "toggle"
    return None


def _tray_icon() -> QIcon:
    dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    color = QColor("#ffffff") if dark else QColor("#000000")
    icon = QIcon()
    for scale in (1, 2):
        pixmap = _glyph_pixmap(22 * scale, color)
        pixmap.setDevicePixelRatio(scale)
        icon.addPixmap(pixmap)
    icon.setIsMask(True)
    return icon


def _app_icon() -> QIcon:
    icon = QIcon()
    for scale in (1, 2):
        size = 128 * scale
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0a84ff"))
        painter.drawRoundedRect(
            QRectF(4 * scale, 4 * scale, 120 * scale, 120 * scale),
            26 * scale,
            26 * scale,
        )
        painter.end()
        glyph = _glyph_pixmap(80 * scale, QColor("#ffffff"))
        painter = QPainter(pixmap)
        painter.drawPixmap((size - 80 * scale) // 2, (size - 80 * scale) // 2, glyph)
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        icon.addPixmap(pixmap)
    return icon


def _glyph_pixmap(size: int, color: QColor) -> QPixmap:
    """Draw the TempBox box-with-arrow glyph on a transparent pixmap."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = size / 22.0
    pen = QPen(color)
    pen.setWidthF(1.7 * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(
        QRectF(3.5 * scale, 3.5 * scale, 15.0 * scale, 15.0 * scale),
        3.5 * scale,
        3.5 * scale,
    )
    painter.drawLine(QPointF(11.0 * scale, 6.8 * scale), QPointF(11.0 * scale, 12.6 * scale))
    painter.drawLine(QPointF(8.4 * scale, 10.0 * scale), QPointF(11.0 * scale, 12.6 * scale))
    painter.drawLine(QPointF(13.6 * scale, 10.0 * scale), QPointF(11.0 * scale, 12.6 * scale))
    painter.end()
    return pixmap
