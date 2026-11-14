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

    @classmethod
    def load(cls, root: Path | str) -> "AppSettings":
        path = Path(root) / SETTINGS_FILENAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            seconds = int(data["default_retention_seconds"])
        except (OSError, ValueError, KeyError, TypeError):
            return cls()
        for _label, duration in RETENTION_OPTIONS:
            if duration.total_seconds() == seconds:
                return cls(duration)
        return cls()

    def save(self, root: Path | str) -> None:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        path = root / SETTINGS_FILENAME
        temporary_path = root / (SETTINGS_FILENAME + ".tmp")
        payload = {
            "version": SETTINGS_VERSION,
            "default_retention_seconds": int(self.default_retention.total_seconds()),
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
