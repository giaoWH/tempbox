"""Shared filesystem locations for TempBox."""

from __future__ import annotations

from pathlib import Path

APP_NAME = "TempBox"


def data_dir(home: Path | None = None) -> Path:
    """The user's TempBox data directory (never inside the project checkout)."""
    return (home or Path.home()) / "Library" / "Application Support" / APP_NAME
