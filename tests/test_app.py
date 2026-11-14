"""Tests for the menu bar activation logic."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSystemTrayIcon

from tempbox.app import _tray_action

Reason = QSystemTrayIcon.ActivationReason


class TrayActionTest(unittest.TestCase):
    def test_unknown_click_toggles_window(self) -> None:
        # macOS 27 reports status item clicks without the original mouse event.
        self.assertEqual(_tray_action(Reason.Unknown, Qt.MouseButton.NoButton), "toggle")

    def test_trigger_toggles_window(self) -> None:
        self.assertEqual(_tray_action(Reason.Trigger, Qt.MouseButton.NoButton), "toggle")

    def test_double_click_toggles_window(self) -> None:
        self.assertEqual(_tray_action(Reason.DoubleClick, Qt.MouseButton.NoButton), "toggle")

    def test_trigger_with_right_button_opens_menu(self) -> None:
        self.assertEqual(_tray_action(Reason.Trigger, Qt.MouseButton.RightButton), "menu")

    def test_context_opens_menu(self) -> None:
        self.assertEqual(_tray_action(Reason.Context, Qt.MouseButton.NoButton), "menu")

    def test_middle_click_is_ignored(self) -> None:
        self.assertIsNone(_tray_action(Reason.MiddleClick, Qt.MouseButton.MiddleButton))


if __name__ == "__main__":
    unittest.main()
