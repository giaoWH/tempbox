"""Persistent history of files that TempBox moved to the macOS Trash."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .storage import FileRecord

HISTORY_FILENAME = "history.json"
HISTORY_VERSION = 1
MAX_ENTRIES = 100


@dataclass(frozen=True)
class CleanupEntry:
    original_name: str
    original_path: str
    size: int
    added_at: str
    expires_at: str | None
    trashed_at: str

    def to_dict(self) -> dict:
        return {
            "original_name": self.original_name,
            "original_path": self.original_path,
            "size": self.size,
            "added_at": self.added_at,
            "expires_at": self.expires_at,
            "trashed_at": self.trashed_at,
        }

    @classmethod
    def from_dict(cls, data: object) -> "CleanupEntry":
        if not isinstance(data, dict):
            raise ValueError("cleanup entry is not an object")
        trashed_at = str(data["trashed_at"])
        datetime.fromisoformat(trashed_at)
        expires_at = data.get("expires_at")
        if expires_at is not None:
            expires_at = str(expires_at)
            datetime.fromisoformat(expires_at)
        return cls(
            original_name=str(data["original_name"]),
            original_path=str(data["original_path"]),
            size=int(data["size"]),
            added_at=str(data["added_at"]),
            expires_at=expires_at,
            trashed_at=trashed_at,
        )


class CleanupHistory:
    """Keeps the most recent successful trash events (metadata only)."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.entries: list[CleanupEntry] = []

    @property
    def path(self) -> Path:
        return self.root / HISTORY_FILENAME

    def load(self) -> None:
        self.entries = []
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._back_up_damaged_history()
            return
        if not isinstance(data, dict) or not isinstance(data.get("files"), list):
            self._back_up_damaged_history()
            return
        for item in data["files"]:
            try:
                entry = CleanupEntry.from_dict(item)
            except (KeyError, TypeError, ValueError):
                continue
            self.entries.append(entry)
            if len(self.entries) >= MAX_ENTRIES:
                break

    def add(
        self,
        records: list[FileRecord],
        trashed_at: datetime | None = None,
    ) -> int:
        timestamp = (trashed_at or datetime.now(timezone.utc)).astimezone(
            timezone.utc
        ).isoformat(timespec="seconds")
        new_entries = [
            CleanupEntry(
                original_name=record.original_name,
                original_path=record.original_path,
                size=record.size,
                added_at=record.added_at,
                expires_at=record.expires_at,
                trashed_at=timestamp,
            )
            for record in records
        ]
        self.entries = (new_entries + self.entries)[:MAX_ENTRIES]
        self.save()
        return len(new_entries)

    def clear(self) -> None:
        self.entries = []
        self.save()

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": HISTORY_VERSION,
            "files": [entry.to_dict() for entry in self.entries],
        }
        temporary_path = self.root / (HISTORY_FILENAME + ".tmp")
        try:
            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        except OSError:
            try:
                temporary_path.unlink()
            except OSError:
                pass
            raise

    def _back_up_damaged_history(self) -> None:
        self.entries = []
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.root / f"history.corrupt-{stamp}-{uuid.uuid4().hex[:6]}.json"
        try:
            os.replace(self.path, backup)
        except OSError:
            pass
