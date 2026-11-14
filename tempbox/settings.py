"""Persistent application settings for TempBox."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from .storage import DEFAULT_RETENTION, RETENTION_OPTIONS

SETTINGS_FILENAME = "settings.json"
SETTINGS_VERSION = 1


@dataclass
class AppSettings:
    """User preferences that survive app restarts."""

    default_retention: timedelta = DEFAULT_RETENTION
    pause_auto_cleanup: bool = False
    remind_before_expiry: bool = True

    @classmethod
    def load(cls, root: Path | str) -> "AppSettings":
        path = Path(root) / SETTINGS_FILENAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()

        retention = DEFAULT_RETENTION
        seconds = data.get("default_retention_seconds")
        if isinstance(seconds, int):
            for _label, duration in RETENTION_OPTIONS:
                if duration.total_seconds() == seconds:
                    retention = duration
                    break
        return cls(
            default_retention=retention,
            pause_auto_cleanup=bool(data.get("pause_auto_cleanup", False)),
            remind_before_expiry=bool(data.get("remind_before_expiry", True)),
        )

    def save(self, root: Path | str) -> None:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        path = root / SETTINGS_FILENAME
        temporary_path = root / (SETTINGS_FILENAME + ".tmp")
        payload = {
            "version": SETTINGS_VERSION,
            "default_retention_seconds": int(self.default_retention.total_seconds()),
            "pause_auto_cleanup": self.pause_auto_cleanup,
            "remind_before_expiry": self.remind_before_expiry,
        }
        try:
            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except OSError:
            try:
                temporary_path.unlink()
            except OSError:
                pass
            raise
