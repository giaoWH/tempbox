"""Application entry point and menu bar wiring for TempBox."""

from __future__ import annotations

import sys

from PySide6.QtCore import QLockFile, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .macos import activate_application, hide_dock_icon
from .paths import APP_NAME, data_dir
from .storage import FileStore, StorageError
from .window import MainWindow

DATA_DIR = data_dir()


def main() -> int:
    hidden_launch = "--hidden" in sys.argv[1:]
    arguments = [argument for argument in sys.argv if argument != "--hidden"]
    app = QApplication(arguments)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    hide_dock_icon()

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _show_startup_error(f"Could not create the TempBox data folder:\n{exc}")
        return 1

    lock = QLockFile(str(DATA_DIR / ".instance.lock"))
    if not lock.tryLock(100):
        if not (lock.removeStaleLockFile() and lock.tryLock(100)):
            if hidden_launch:
                print("TempBox is already running.", file=sys.stderr)
            else:
                QMessageBox.warning(None, APP_NAME, "TempBox is already running.")
            return 1

    store = FileStore(DATA_DIR)
    try:
        problems = store.load()
    except StorageError as exc:
        _show_startup_error(str(exc), hidden_launch)
        return 1

    app.setWindowIcon(_app_icon())
    window = MainWindow(store)
    tray = _create_tray(app, window)
    if hidden_launch:
        window.hide()
    else:
        # The menu bar status item only gets its geometry after the event loop
        # starts, so defer the first show slightly to place the window correctly.
        QTimer.singleShot(180, lambda: _show_window(window, tray))

    if problems:
        if hidden_launch:
            for problem in problems:
                print(f"TempBox: {problem}", file=sys.stderr)
        else:
            QMessageBox.warning(
                None,
                APP_NAME,
                "TempBox needs your attention:\n\n" + "\n".join(problems),
            )

    exit_code = app.exec()
    tray.hide()
    return exit_code


def _show_startup_error(message: str, hidden_launch: bool = False) -> None:
    if hidden_launch:
        print(f"TempBox: {message}", file=sys.stderr)
    else:
        QMessageBox.critical(None, APP_NAME, message)


def _show_window(window: MainWindow, tray: QSystemTrayIcon | None = None) -> None:
    window.clear_auto_hide_marker()
    _position_window(window, tray)
    activate_application()
    window.show()
    window.raise_()
    window.activateWindow()
    if tray is not None:
        # Refine the position once the status item geometry is available.
        QTimer.singleShot(250, lambda: _position_window(window, tray))


def _quit_application(
    app: QApplication,
    tray: QSystemTrayIcon,
    menu: QMenu | None = None,
) -> None:
    """Hide the menu bar icon before quitting.

    Quitting directly from a right-click context menu on macOS can leave a stale
    status item until the next click; hiding the tray and letting the hide finish
    on the next event-loop iteration avoids that.
    """
    if menu is not None:
        menu.close()
    tray.hide()
    QTimer.singleShot(0, app.quit)


def _toggle_window(window: MainWindow, tray: QSystemTrayIcon | None = None) -> None:
    if window.isVisible():
        window.hide()
    elif window.consume_recent_auto_hide():
        # The window was just auto-hidden by this same menu bar click, so the
        # user is trying to hide it: keep it hidden.
        return
    else:
        _show_window(window, tray)


def _valid_tray_rect(tray: QSystemTrayIcon | None) -> QRect:
    if tray is None:
        return QRect()
    rect = tray.geometry()
    # Before the event loop starts the status item may report a placeholder
    # geometry such as QRect(0, 900, 38, 0); ignore that.
    if rect.width() <= 0 or rect.height() <= 0:
        return QRect()
    if rect.top() < 0 or rect.top() > 100:
        return QRect()
    return rect


def _position_window(window: MainWindow, tray: QSystemTrayIcon | None) -> None:
    tray_rect = _valid_tray_rect(tray)
    screen = None
    if not tray_rect.isNull():
        screen = QApplication.screenAt(tray_rect.center())
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is None:
        return

    available = screen.availableGeometry()
    margin = window.SHADOW_MARGIN
    content_width = window.width() - margin * 2
    content_height = window.height() - margin * 2
    if not tray_rect.isNull():
        x = tray_rect.center().x() - content_width // 2 - margin
        y = tray_rect.bottom() + 8 - margin
    else:
        x = available.right() - content_width - 8 - margin
        y = available.top() + 8 - margin
    x = max(
        available.left() + 8 - margin,
        min(x, available.right() - 8 - margin - content_width),
    )
    y = max(
        available.top() + 8 - margin,
        min(y, available.bottom() - 8 - margin - content_height),
    )
    window.move(x, y)


def _create_tray(app: QApplication, window: MainWindow) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(_tray_icon(), app)
    tray.setToolTip(APP_NAME)

    menu = QMenu()
    quit_action = menu.addAction("Quit TempBox")
    quit_action.triggered.connect(lambda: _quit_application(app, tray, menu))
    window.quit_requested.connect(lambda: _quit_application(app, tray))

    def on_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
        action = _tray_action(reason, QApplication.mouseButtons())
        if action == "menu":
            menu.exec(QCursor.pos())
        elif action == "toggle":
            _toggle_window(window, tray)

    tray.activated.connect(on_activated)
    tray.show()
    app.aboutToQuit.connect(tray.hide)
    window.set_notifier(
        lambda title, message: tray.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )
    )
    QTimer.singleShot(1200, window.check_expiry_reminders)
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
