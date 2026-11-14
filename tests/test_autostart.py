"""Tests for the launch-at-login helper (no real LaunchAgent is installed)."""

from __future__ import annotations

import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tempbox import autostart


class AutoStartTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tempbox-autostart-test-")
        self.addCleanup(self._tmp.cleanup)
        self.fake_home = Path(self._tmp.name)
        home_patcher = mock.patch.object(Path, "home", return_value=self.fake_home)
        home_patcher.start()
        self.addCleanup(home_patcher.stop)

    def test_enable_writes_launch_agent(self) -> None:
        self.assertFalse(autostart.is_enabled())

        autostart.set_enabled(True)

        self.assertTrue(autostart.is_enabled())
        payload = plistlib.loads(autostart._plist_path().read_bytes())
        self.assertEqual(payload["Label"], "com.tempbox.app")
        self.assertTrue(payload["RunAtLoad"])
        arguments = payload["ProgramArguments"]
        self.assertTrue(any(argument.endswith("main.py") for argument in arguments))
        self.assertIn("--hidden", arguments)

    def test_disable_removes_launch_agent(self) -> None:
        autostart.set_enabled(True)

        with mock.patch.object(autostart.subprocess, "run") as run:
            autostart.set_enabled(False)

        run.assert_called_once()
        self.assertFalse(autostart.is_enabled())
        self.assertFalse(autostart._plist_path().exists())


if __name__ == "__main__":
    unittest.main()
