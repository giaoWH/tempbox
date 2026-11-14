"""Tests for persistent TempBox settings."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from tempbox.settings import AppSettings


class AppSettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tempbox-settings-test-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_missing_settings_use_one_day_default(self) -> None:
        settings = AppSettings.load(self.root)
        self.assertEqual(settings.default_retention, timedelta(days=1))

    def test_save_and_load_roundtrip(self) -> None:
        AppSettings(default_retention=timedelta(hours=1)).save(self.root)

        self.assertTrue((self.root / "settings.json").is_file())
        self.assertEqual(
            AppSettings.load(self.root).default_retention, timedelta(hours=1)
        )

    def test_invalid_settings_fall_back_to_default(self) -> None:
        (self.root / "settings.json").write_text("{not json", encoding="utf-8")

        self.assertEqual(
            AppSettings.load(self.root).default_retention, timedelta(days=1)
        )

    def test_unknown_duration_falls_back_to_default(self) -> None:
        payload = {"version": 1, "default_retention_seconds": 12345}
        (self.root / "settings.json").write_text(json.dumps(payload), encoding="utf-8")

        self.assertEqual(
            AppSettings.load(self.root).default_retention, timedelta(days=1)
        )


if __name__ == "__main__":
    unittest.main()
