"""File management, retention and JSON metadata storage for TempBox.

This module intentionally has no Qt dependency so file handling, retention
calculation and expired-file clean-up can be tested headlessly.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from send2trash import send2trash

SCHEMA_VERSION = 2
SUPPORTED_INDEX_VERSIONS = (1, 2)
RECORDS_FILENAME = "records.json"
FILES_DIRNAME = "files"

DEFAULT_RETENTION = timedelta(days=1)
RETENTION_OPTIONS: tuple[tuple[str, timedelta], ...] = (
    ("1 hour", timedelta(hours=1)),
    ("1 day", timedelta(days=1)),
    ("7 days", timedelta(days=7)),
    ("30 days", timedelta(days=30)),
)


class StorageError(Exception):
    """Raised when a file operation cannot be completed safely."""


@dataclass(frozen=True)
class FileRecord:
    """Metadata describing one file managed by TempBox."""

    id: str
    original_name: str
    original_path: str
    stored_relative_path: str
    size: int
    added_at: str
    expires_at: str | None = None
    trash_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "original_name": self.original_name,
            "original_path": self.original_path,
            "stored_relative_path": self.stored_relative_path,
            "size": self.size,
            "added_at": self.added_at,
            "expires_at": self.expires_at,
            "trash_error": self.trash_error,
        }

    @classmethod
    def from_dict(cls, data: object) -> "FileRecord":
        if not isinstance(data, dict):
            raise ValueError("file record is not a JSON object")
        try:
            added_at = str(data["added_at"])
            datetime.fromisoformat(added_at)
            original_path = str(data["original_path"])
            stored_relative_path = Path(str(data["stored_relative_path"]))
            if not Path(original_path).is_absolute():
                raise ValueError("original_path is not absolute")
            if stored_relative_path.is_absolute() or ".." in stored_relative_path.parts:
                raise ValueError("stored_relative_path is not a safe relative path")

            expires_at = None
            if data.get("expires_at") is not None:
                expires_at = str(data["expires_at"])
                parsed_expiry = datetime.fromisoformat(expires_at)
                if parsed_expiry.tzinfo is None:
                    raise ValueError("expires_at has no time zone")

            trash_error = None
            if data.get("trash_error") is not None:
                trash_error = str(data["trash_error"])

            return cls(
                id=str(data["id"]),
                original_name=str(data["original_name"]),
                original_path=original_path,
                stored_relative_path=stored_relative_path.as_posix(),
                size=int(data["size"]),
                added_at=added_at,
                expires_at=expires_at,
                trash_error=trash_error,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid file record: {exc}") from exc


@dataclass
class ImportResult:
    """Outcome of importing one or more dropped files."""

    added: list[FileRecord] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class CleanupResult:
    """Outcome of one expired-file clean-up pass."""

    trashed: list[FileRecord] = field(default_factory=list)
    failed: list[tuple[FileRecord, str]] = field(default_factory=list)
    missing: list[FileRecord] = field(default_factory=list)
    save_error: str | None = None


class FileStore:
    """Owns the TempBox data folder: the moved files plus their JSON index."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.records: dict[str, FileRecord] = {}
        self.default_retention: timedelta = DEFAULT_RETENTION

    @property
    def records_path(self) -> Path:
        return self.root / RECORDS_FILENAME

    # -- index ---------------------------------------------------------

    def load(self) -> list[str]:
        """(Re)load the index from disk.

        Phase 1 indexes (version 1) are accepted; their records simply have no
        expiry time and are therefore never cleaned up automatically. Returns
        human readable problems (damaged index, missing files) without deleting
        anything.
        """
        self.records.clear()
        if not self.records_path.exists():
            return []
        try:
            with open(self.records_path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            return [self._back_up_damaged_index(f"the index could not be read ({exc})")]
        if (
            not isinstance(data, dict)
            or data.get("version") not in SUPPORTED_INDEX_VERSIONS
            or not isinstance(data.get("files"), list)
        ):
            return [self._back_up_damaged_index("the index structure is unexpected")]
        for item in data["files"]:
            try:
                record = FileRecord.from_dict(item)
            except ValueError as exc:
                return [self._back_up_damaged_index(str(exc))]
            if record.id in self.records:
                return [self._back_up_damaged_index(f"duplicate file id '{record.id}'")]
            self.records[record.id] = record

        problems = []
        for record in self.records.values():
            if not self.stored_path(record).is_file():
                problems.append(f"'{record.original_name}' is missing from TempBox storage.")
        return problems

    def list_files(self) -> list[FileRecord]:
        return sorted(
            self.records.values(),
            key=lambda record: datetime.fromisoformat(record.added_at),
            reverse=True,
        )

    def get(self, record_id: str) -> FileRecord | None:
        return self.records.get(record_id)

    def stored_path(self, record: FileRecord) -> Path:
        return self.root / record.stored_relative_path

    # -- file operations -----------------------------------------------

    def import_files(self, sources: Iterable[Path | str]) -> ImportResult:
        """Move the given files into TempBox and record them in the index."""
        result = ImportResult()
        for source in sources:
            source = Path(source)
            try:
                result.added.append(self._import_one(source))
            except StorageError as exc:
                result.failed.append((source.name or str(source), str(exc)))
        return result

    def restore(self, record_id: str, target: Path | str) -> Path:
        """Move a stored file to target, then drop its index record.

        The record is only removed after the file was moved successfully, so a
        failed restore always leaves the file safely inside TempBox.
        """
        record = self.records.get(record_id)
        if record is None:
            raise StorageError("This file is no longer managed by TempBox.")
        stored = self.stored_path(record)
        target = Path(target)
        if not stored.is_file():
            raise StorageError(f"'{record.original_name}' is missing from TempBox storage.")
        if os.path.lexists(target):
            raise StorageError(f"A file already exists at {target}.")
        try:
            _move_file(stored, target)
        except OSError as exc:
            raise StorageError(f"Could not restore the file: {exc}") from exc

        del self.records[record_id]
        try:
            self._save()
        except OSError as exc:
            self.records[record_id] = record
            try:
                _move_file(target, stored)
            except OSError as rollback_error:
                raise StorageError(
                    f"The file was restored to {target}, but updating the TempBox index failed "
                    f"({exc}) and rolling it back also failed ({rollback_error})."
                ) from exc
            raise StorageError(f"Could not update the TempBox index: {exc}") from exc
        _remove_empty_dir(stored.parent)
        return target

    def set_expiry(self, record_id: str, expires_at: datetime) -> FileRecord:
        """Set a new expiry time for a managed file and save the index."""
        record = self.records.get(record_id)
        if record is None:
            raise StorageError("This file is no longer managed by TempBox.")
        if expires_at.tzinfo is None:
            raise StorageError("Expiry time must include a time zone.")
        updated = replace(
            record,
            expires_at=expires_at.astimezone(timezone.utc).isoformat(timespec="seconds"),
            trash_error=None,
        )
        self.records[record_id] = updated
        try:
            self._save()
        except OSError as exc:
            self.records[record_id] = record
            raise StorageError(f"Could not save the retention time: {exc}") from exc
        return updated

    def set_expiries(self, record_ids: Iterable[str], expires_at: datetime) -> int:
        """Set the same expiry time for several files with a single index write."""
        if expires_at.tzinfo is None:
            raise StorageError("Expiry time must include a time zone.")
        timestamp = expires_at.astimezone(timezone.utc).isoformat(timespec="seconds")
        previous: dict[str, FileRecord] = {}
        for record_id in record_ids:
            record = self.records.get(record_id)
            if record is None or record_id in previous:
                continue
            previous[record_id] = record
            self.records[record_id] = replace(
                record, expires_at=timestamp, trash_error=None
            )
        if not previous:
            raise StorageError("No files are selected.")
        try:
            self._save()
        except OSError as exc:
            for record_id, record in previous.items():
                self.records[record_id] = record
            raise StorageError(f"Could not save the retention times: {exc}") from exc
        return len(previous)

    def cleanup_expired(self, now: datetime | None = None) -> CleanupResult:
        """Move expired files to the macOS Trash and update the index.

        Only files that are recorded by TempBox, due by their own expiry time and
        still present inside TempBox storage are touched. Files without an expiry
        time (Phase 1 records) are never cleaned up automatically.
        """
        now = now or datetime.now(timezone.utc)
        result = CleanupResult()
        changed = False
        for record in list(self.records.values()):
            if record.expires_at is None:
                continue
            if datetime.fromisoformat(record.expires_at) > now:
                continue
            stored = self.stored_path(record)
            if not _is_managed_path(stored, self.root):
                message = "The stored file is outside the TempBox storage folder."
                if self._mark_trash_error(record, message):
                    changed = True
                    result.failed.append((record, message))
                continue
            try:
                stored_stat = stored.lstat()
            except FileNotFoundError:
                message = "The stored file is missing from TempBox storage."
                if self._mark_trash_error(record, message):
                    changed = True
                    result.missing.append(record)
                continue
            except OSError as exc:
                message = f"The stored file could not be read: {exc}"
                if self._mark_trash_error(record, message):
                    changed = True
                    result.failed.append((record, message))
                continue
            if not stat.S_ISREG(stored_stat.st_mode):
                message = "The stored item is not a regular file."
                if self._mark_trash_error(record, message):
                    changed = True
                    result.failed.append((record, message))
                continue
            try:
                send2trash(str(stored))
            except Exception as exc:  # send2trash may raise OSError or platform errors
                message = f"Could not move to Trash: {exc}"
                if self._mark_trash_error(record, message):
                    changed = True
                    result.failed.append((record, message))
                continue
            del self.records[record.id]
            _remove_empty_dir(stored.parent)
            result.trashed.append(record)
            changed = True

        if changed:
            try:
                self._save()
            except OSError as exc:
                result.save_error = str(exc)
        return result

    # -- internals -----------------------------------------------------

    def _import_one(self, source: Path) -> FileRecord:
        try:
            source_stat = source.lstat()
        except FileNotFoundError:
            raise StorageError("The file no longer exists.") from None
        except OSError as exc:
            raise StorageError(f"Could not read the file: {exc}") from exc
        if stat.S_ISLNK(source_stat.st_mode):
            raise StorageError("Symbolic links are not supported.")
        if not stat.S_ISREG(source_stat.st_mode):
            raise StorageError("Only regular files are supported.")
        if source.absolute().is_relative_to(self.root.absolute()):
            raise StorageError("Files already stored in TempBox cannot be imported.")

        record_id = uuid.uuid4().hex
        stored_relative_path = Path(FILES_DIRNAME) / record_id / source.name
        destination = self.root / stored_relative_path
        try:
            destination.parent.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise StorageError(f"Could not create the storage folder: {exc}") from exc

        try:
            _move_file(source, destination)
        except OSError as exc:
            _remove_empty_dir(destination.parent)
            raise StorageError(f"Could not move the file into TempBox: {exc}") from exc

        added_at = datetime.now().astimezone()
        expires_at = added_at.astimezone(timezone.utc) + self.default_retention
        record = FileRecord(
            id=record_id,
            original_name=source.name,
            original_path=str(source.absolute()),
            stored_relative_path=stored_relative_path.as_posix(),
            size=source_stat.st_size,
            added_at=added_at.isoformat(timespec="seconds"),
            expires_at=expires_at.isoformat(timespec="seconds"),
        )
        self.records[record.id] = record
        try:
            self._save()
        except OSError as exc:
            del self.records[record.id]
            try:
                _move_file(destination, source)
            except OSError as rollback_error:
                raise StorageError(
                    f"Could not save the TempBox index ({exc}), and the file could not be moved "
                    f"back out of TempBox (it is now at {destination}: {rollback_error})."
                ) from exc
            _remove_empty_dir(destination.parent)
            raise StorageError(f"Could not save the TempBox index: {exc}") from exc
        return record

    def _mark_trash_error(self, record: FileRecord, message: str) -> bool:
        if record.trash_error == message:
            return False
        self.records[record.id] = replace(record, trash_error=message)
        return True

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SCHEMA_VERSION,
            "files": [record.to_dict() for record in self.records.values()],
        }
        temporary_path = self.root / (RECORDS_FILENAME + ".tmp")
        try:
            with open(temporary_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.records_path)
        except OSError:
            _unlink_quietly(temporary_path)
            raise

    def _back_up_damaged_index(self, reason: str) -> str:
        self.records.clear()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = self.root / f"records.corrupt-{stamp}-{uuid.uuid4().hex[:6]}.json"
        try:
            os.replace(self.records_path, backup_path)
        except OSError as exc:
            raise StorageError(f"Could not back up the damaged TempBox index: {exc}") from exc
        return (
            f"TempBox could not read its file index ({reason}). The previous index was "
            f"backed up to '{backup_path.name}' and TempBox started with an empty list."
        )


def _is_managed_path(path: Path, root: Path) -> bool:
    """True if path resolves to a location inside the TempBox data folder."""
    try:
        resolved_path = path.resolve()
        resolved_root = root.resolve()
    except OSError:
        return False
    return resolved_path.is_relative_to(resolved_root) and resolved_path != resolved_root


def _is_same_device(source: Path, destination: Path) -> bool:
    return os.stat(source).st_dev == os.stat(destination.parent).st_dev


def _move_file(source: Path, destination: Path) -> None:
    """Move source to a missing destination without ever overwriting.

    On failure the source is left untouched and a partially copied destination
    is removed again.
    """
    if os.path.lexists(destination):
        raise FileExistsError(f"destination already exists: {destination}")
    if _is_same_device(source, destination):
        os.rename(source, destination)
        return
    try:
        shutil.copy2(source, destination)
    except OSError:
        _unlink_quietly(destination)
        raise
    try:
        os.unlink(source)
    except OSError:
        _unlink_quietly(destination)
        raise


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _remove_empty_dir(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass
