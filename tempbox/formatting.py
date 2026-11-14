"""Small, GUI-independent formatting helpers shared by the panel and dialogs."""

from __future__ import annotations

from datetime import datetime, timedelta

from .storage import RETENTION_OPTIONS


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    value = float(size)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024.0
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f} {unit}"
    return f"{size} B"


def plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def duration_label(duration: timedelta) -> str:
    for label, option in RETENTION_OPTIONS:
        if option == duration:
            return label
    return "1 day"


def format_added(added_at: str) -> str:
    try:
        moment = datetime.fromisoformat(added_at)
    except ValueError:
        return added_at
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def format_expiry(expires_at: str | None) -> str:
    if not expires_at:
        return "\u2014"
    try:
        moment = datetime.fromisoformat(expires_at)
    except ValueError:
        return expires_at
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")
