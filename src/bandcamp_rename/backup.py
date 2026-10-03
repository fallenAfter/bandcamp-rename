"""Per-run filename journal for crash-safe rename recovery."""

from __future__ import annotations

import gzip
import json
import os
import secrets
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


def generate_run_uid() -> str:
    """Return a filesystem-safe random identifier for a rename run."""
    return secrets.token_urlsafe(16)


def default_backup_dir() -> Path:
    """Return the default directory for run journals."""
    return Path.home() / ".local" / "share" / "bandcamp-rename" / "runs"


def journal_path_for(uid: str, directory: Path | None = None) -> Path:
    """Return the uncompressed journal path for *uid*."""
    return (directory or default_backup_dir()) / f"{uid}.jsonl"


def compressed_journal_path_for(uid: str, directory: Path | None = None) -> Path:
    """Return the gzip-compressed journal path for *uid*."""
    return journal_path_for(uid, directory).with_name(f"{uid}.jsonl.gz")


def resolve_journal_path(target: str | Path, directory: Path | None = None) -> Path:
    """Resolve a UID or filesystem path to an existing journal file."""
    path = Path(target)
    if path.exists():
        return path

    backup_dir = directory or default_backup_dir()
    uid = path.name
    for candidate in (
        journal_path_for(uid, backup_dir),
        compressed_journal_path_for(uid, backup_dir),
        backup_dir / uid,
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No backup journal found for {target}")


def _open_journal_text(path: Path):
    if path.name.endswith(".gz") or path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def load_journal_entries(path: Path) -> list[dict[str, Any]]:
    """Load JSONL journal records from an uncompressed or gzip path."""
    entries: list[dict[str, Any]] = []
    with _open_journal_text(path) as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                entries.append(payload)
    return entries


def last_checkpoint_index(entries: list[dict[str, Any]]) -> int:
    """Return the offset after the last completed-album checkpoint."""
    index = 0
    for i, entry in enumerate(entries):
        if entry.get("type") == "checkpoint":
            index = i + 1
    return index


def _same_file(left: Path, right: Path) -> bool:
    try:
        if left.exists() and right.exists():
            return left.samefile(right)
    except OSError:
        pass
    return False


@dataclass
class RestoreResult:
    """Outcome of restoring original filenames from a journal."""

    restored: list[tuple[Path, Path]] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    missing: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors


def restore_journal(
    path: Path,
    *,
    after_index: int | None = None,
    from_last_checkpoint: bool = False,
    dry_run: bool = False,
) -> RestoreResult:
    """Move files described in *path* back to their original names.

    *after_index* skips records before that offset so a later album can roll
    back without undoing earlier completed work. When *from_last_checkpoint*
    is true, restore only the in-progress album after the last checkpoint.
    """
    result = RestoreResult()
    entries = load_journal_entries(path)
    if after_index is None:
        after_index = last_checkpoint_index(entries) if from_last_checkpoint else 0
    entries = entries[after_index:]
    last_location: dict[str, str] = {}
    for entry in entries:
        if entry.get("type", "move") != "move":
            continue
        original = entry.get("original")
        destination = entry.get("to")
        if not original or not destination:
            continue
        last_location[str(original)] = str(destination)

    pending: list[tuple[Path, Path]] = []
    for original_text, current_text in last_location.items():
        original = Path(original_text)
        current = Path(current_text)
        if original.exists() and (not current.exists() or _same_file(original, current)):
            result.skipped.append(original)
            continue
        if not current.exists():
            result.missing.append(current)
            result.errors.append(f"Missing current file for {original}: {current}")
            continue
        pending.append((current, original))

    if dry_run:
        result.restored = pending
        return result

    staged: list[tuple[Path, Path]] = []
    try:
        for current, original in pending:
            original.parent.mkdir(parents=True, exist_ok=True)
            temp = original.parent / f".bc-restore-{uuid.uuid4().hex}.tmp"
            current.rename(temp)
            staged.append((temp, original))
        for temp, original in staged:
            if original.exists() and not _same_file(temp, original):
                raise FileExistsError(f"Original path occupied during restore: {original}")
            temp.rename(original)
            result.restored.append((temp, original))
    except Exception as exc:
        result.errors.append(str(exc))
        result.restored.extend((temp, original) for temp, original in staged if original.exists())
    return result


class RunBackup:
    """Append-only JSONL journal of filesystem moves for one run."""

    def __init__(self, directory: Path | None = None, uid: str | None = None) -> None:
        self.uid = uid or generate_run_uid()
        self.directory = directory or default_backup_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = journal_path_for(self.uid, self.directory)
        if self.path.exists() or compressed_journal_path_for(self.uid, self.directory).exists():
            self.uid = generate_run_uid()
            self.path = journal_path_for(self.uid, self.directory)
        self.compressed_path: Path | None = None
        self._handle: TextIO | None = None
        self.record_count = 0

    def __enter__(self) -> RunBackup:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def open(self) -> None:
        if self._handle is not None:
            return
        self._handle = self.path.open("a", encoding="utf-8")
        self._write(
            {
                "type": "run",
                "uid": self.uid,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def close(self) -> None:
        if self._handle is None:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        self._handle = None

    def _write(self, payload: dict[str, Any]) -> None:
        if self._handle is None:
            self.open()
        assert self._handle is not None
        self._handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self.record_count += 1

    def record_move(self, *, original: Path, source: Path, destination: Path) -> None:
        """Append a move *before* the filesystem rename is performed."""
        self._write(
            {
                "type": "move",
                "original": str(original),
                "from": str(source),
                "to": str(destination),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def record_checkpoint(self, album: str) -> None:
        """Mark an album as fully completed so later restores skip it."""
        self._write(
            {
                "type": "checkpoint",
                "album": album,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def restore(
        self,
        *,
        after_index: int | None = None,
        from_last_checkpoint: bool = False,
    ) -> RestoreResult:
        self.close()
        return restore_journal(
            self.path,
            after_index=after_index,
            from_last_checkpoint=from_last_checkpoint,
        )

    def compress(self) -> Path:
        """Gzip the journal after a fully successful run."""
        self.close()
        gz_path = compressed_journal_path_for(self.uid, self.directory)
        with self.path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        self.path.unlink()
        self.compressed_path = gz_path
        return gz_path
