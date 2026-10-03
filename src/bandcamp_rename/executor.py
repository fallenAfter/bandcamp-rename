"""Safely apply planned rename/move/tag operations."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, TALB, TIT2, TPE1, TPE2, TPOS, TRCK, ID3NoHeaderError

from bandcamp_rename.backup import RunBackup, default_backup_dir
from bandcamp_rename.models import TrackInfo
from bandcamp_rename.planner import ActionType, PlannedAction, PlanResult

_FILE_MOVE_TYPES = {
    ActionType.MOVE,
    ActionType.RENAME,
    ActionType.MOVE_COMPANION,
}


@dataclass
class ExecutionResult:
    """Outcome of applying a plan."""

    completed: list[PlannedAction] = field(default_factory=list)
    failed: PlannedAction | None = None
    error: str | None = None
    audit_log: Path | None = None
    run_uid: str | None = None
    journal_path: Path | None = None
    restored: bool = False
    restore_error: str | None = None
    failed_album: str | None = None

    @property
    def success(self) -> bool:
        return self.failed is None and self.error is None


def _write_tags(path: Path, track: TrackInfo) -> None:
    """Best-effort tag update so embedded metadata matches path metadata."""
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None

    if audio is not None:
        try:
            if getattr(audio, "tags", None) is None:
                audio.add_tags()
            if track.artist:
                audio["artist"] = track.artist
            if track.album_artist or track.artist:
                audio["albumartist"] = track.album_artist or track.artist
            if track.album:
                audio["album"] = track.album
            if track.title:
                audio["title"] = track.title
            if track.track_number is not None:
                audio["tracknumber"] = str(track.track_number)
            if track.disc_number is not None:
                audio["discnumber"] = str(track.disc_number)
            audio.save()
            return
        except Exception:
            pass

    if path.suffix.lower() != ".mp3":
        return

    try:
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        if track.title:
            tags.add(TIT2(encoding=3, text=track.title))
        if track.artist:
            tags.add(TPE1(encoding=3, text=track.artist))
        if track.album_artist or track.artist:
            tags.add(TPE2(encoding=3, text=track.album_artist or track.artist))
        if track.album:
            tags.add(TALB(encoding=3, text=track.album))
        if track.track_number is not None:
            tags.add(TRCK(encoding=3, text=str(track.track_number)))
        if track.disc_number is not None:
            tags.add(TPOS(encoding=3, text=str(track.disc_number)))
        tags.save(path)
    except Exception:
        return


def _case_safe_rename(
    source: Path,
    destination: Path,
    *,
    original: Path | None = None,
    backup: RunBackup | None = None,
) -> None:
    """Rename a file, using a temp name when only case changes (APFS/macOS)."""
    original_path = original or source

    def _record(src: Path, dst: Path) -> None:
        if backup is not None:
            backup.record_move(original=original_path, source=src, destination=dst)

    if source.exists() and destination.exists():
        try:
            same = source.samefile(destination)
        except OSError:
            same = False
        if same and source.name != destination.name:
            temp = source.with_name(f".{uuid.uuid4().hex}.tmp")
            _record(source, temp)
            source.rename(temp)
            _record(temp, destination)
            temp.rename(destination)
            return
        if same:
            return
    _record(source, destination)
    source.rename(destination)


def _ensure_directory_casing(path: Path) -> None:
    """Ensure each existing path component uses the requested casing."""
    if path.exists() and path.name == path.resolve().name:
        # Resolve may not preserve requested case on case-insensitive FS.
        pass

    parts = path.parts
    if not parts:
        return

    current = Path(parts[0]) if path.is_absolute() else Path()
    start = 1 if path.is_absolute() else 0
    for part in parts[start:]:
        desired = current / part if str(current) else Path(part)
        if not current.exists() and start == 0 and not str(current):
            current = Path(part)
            # First relative component — create later via mkdir if needed.
            if not desired.exists():
                # Parent chain may not exist yet; stop and let mkdir create it.
                return
            current = desired
            continue

        if not current.exists():
            return

        match = None
        for child in current.iterdir():
            if child.name.lower() == part.lower():
                match = child
                break

        if match is None:
            return

        if match.name != part:
            temp = current / f".{uuid.uuid4().hex}.tmp"
            match.rename(temp)
            temp.rename(desired)
            current = desired
        else:
            current = match


def _move_file(
    source: Path,
    destination: Path,
    *,
    original: Path | None = None,
    backup: RunBackup | None = None,
) -> None:
    """Move/rename a file to destination, fixing parent directory casing first."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    _ensure_directory_casing(destination.parent)

    # Re-resolve destination parent after possible case fixes.
    parent = destination.parent
    if parent.exists():
        # Rebuild destination under the now-correct parent path object.
        destination = parent / destination.name

    if destination.exists():
        try:
            same = destination.samefile(source)
        except OSError:
            same = False
        if same:
            _case_safe_rename(source, destination, original=original, backup=backup)
            return
        raise FileExistsError(f"Destination exists: {destination}")

    _case_safe_rename(source, destination, original=original, backup=backup)


def _cleanup_empty_dirs(directory: Path, root: Path | None) -> None:
    """Remove empty *directory* and empty parents, stopping at *root*."""
    if not directory.is_dir() or any(directory.iterdir()):
        return

    directory.rmdir()
    parent = directory.parent
    root_resolved = root.resolve() if root is not None else None

    while parent != parent.parent and parent.is_dir() and not any(parent.iterdir()):
        if root_resolved is not None:
            try:
                parent.resolve().relative_to(root_resolved)
            except ValueError:
                break
            if parent.resolve() == root_resolved:
                break
        parent.rmdir()
        parent = parent.parent


class AlbumRenameError(Exception):
    """Raised when one album's rename/move batch fails."""

    def __init__(self, album: str, message: str, action: PlannedAction | None = None) -> None:
        self.album = album
        self.action = action
        super().__init__(f"Album rename failed ({album}): {message}")


@dataclass
class _AlbumBatch:
    key: str
    file_actions: list[PlannedAction] = field(default_factory=list)
    other_actions: list[PlannedAction] = field(default_factory=list)


def _album_key(action: PlannedAction) -> str:
    if action.action_type in _FILE_MOVE_TYPES and action.destination is not None:
        return str(action.destination.parent)
    target = action.destination or action.source
    return str(target.parent if action.action_type == ActionType.TAG_UPDATE else target)


def group_actions_by_album(plan: PlanResult) -> list[_AlbumBatch]:
    """Group planned actions so each destination album is applied fully before the next."""
    file_actions = [a for a in plan.actions if a.action_type in _FILE_MOVE_TYPES]
    tag_actions = [a for a in plan.actions if a.action_type == ActionType.TAG_UPDATE]
    cleanups = [a for a in plan.actions if a.action_type == ActionType.CLEANUP_EMPTY_DIR]

    batches: dict[str, _AlbumBatch] = {}
    order: list[str] = []

    def _ensure(key: str) -> _AlbumBatch:
        if key not in batches:
            batches[key] = _AlbumBatch(key=key)
            order.append(key)
        return batches[key]

    for action in file_actions:
        _ensure(_album_key(action)).file_actions.append(action)

    for action in tag_actions:
        _ensure(_album_key(action)).other_actions.append(action)

    source_to_keys: dict[Path, list[str]] = {}
    for key, batch in batches.items():
        for action in batch.file_actions:
            source_to_keys.setdefault(action.source.parent, []).append(key)

    for cleanup in cleanups:
        keys = source_to_keys.get(cleanup.source, [])
        if keys:
            batches[keys[-1]].other_actions.append(cleanup)
        else:
            _ensure(str(cleanup.source)).other_actions.append(cleanup)

    return [batches[key] for key in order]


def _apply_other_action(action: PlannedAction, root: Path | None) -> None:
    if action.action_type == ActionType.TAG_UPDATE:
        if action.track is None:
            raise ValueError("Track required for tag update")
        target = action.destination or action.source
        _write_tags(target, action.track)
        return
    if action.action_type == ActionType.CLEANUP_EMPTY_DIR:
        _cleanup_empty_dirs(action.source, root)
        return
    raise ValueError(f"Unknown action: {action.action_type}")


def _apply_album_batch(
    batch: _AlbumBatch,
    *,
    root: Path | None,
    backup: RunBackup,
    record: Callable[[PlannedAction], None],
) -> list[Path]:
    """Apply one album's file moves (two-phase) then tags/cleanup. Returns temps."""
    temps: list[Path] = []
    current: PlannedAction | None = None
    try:
        for action in batch.file_actions:
            current = action
            if action.destination is None:
                raise ValueError("Destination required for move/rename")
            action.destination.parent.mkdir(parents=True, exist_ok=True)
            temp = action.destination.parent / f".bc-rename-{uuid.uuid4().hex}.tmp"
            _case_safe_rename(
                action.source,
                temp,
                original=action.source,
                backup=backup,
            )
            temps.append(temp)

        for action, temp in zip(batch.file_actions, temps):
            current = action
            assert action.destination is not None
            _move_file(
                temp,
                action.destination,
                original=action.source,
                backup=backup,
            )
            record(action)

        for action in batch.other_actions:
            current = action
            _apply_other_action(action, root)
            record(action)
    except AlbumRenameError:
        raise
    except Exception as exc:
        raise AlbumRenameError(batch.key, str(exc), current) from exc
    return temps


def apply_plan(
    plan: PlanResult,
    *,
    dry_run: bool = False,
    backup_log: Path | None = None,
    backup_dir: Path | None = None,
    run_uid: str | None = None,
) -> ExecutionResult:
    """Apply planned actions one album at a time using a two-phase temp strategy."""
    result = ExecutionResult()
    if plan.has_conflicts:
        result.error = "; ".join(plan.conflicts)
        return result

    audit_entries: list[dict] = []
    batches = group_actions_by_album(plan)

    def _record(action: PlannedAction) -> None:
        result.completed.append(action)
        audit_entries.append(
            {
                "action": action.action_type.value,
                "source": str(action.source),
                "destination": str(action.destination) if action.destination else None,
                "reason": action.reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    if dry_run:
        for action in plan.actions:
            _record(action)
        return result

    journal_dir = backup_dir if backup_dir is not None else default_backup_dir()
    backup = RunBackup(directory=journal_dir, uid=run_uid)
    result.run_uid = backup.uid
    result.journal_path = backup.path
    temps: list[Path] = []
    try:
        backup.open()
        for batch in batches:
            temps = _apply_album_batch(
                batch,
                root=plan.root,
                backup=backup,
                record=_record,
            )
            backup.record_checkpoint(batch.key)
        result.journal_path = backup.compress()
    except Exception as exc:
        failed_action = getattr(exc, "action", None)
        result.failed = failed_action if isinstance(failed_action, PlannedAction) else None
        result.failed_album = getattr(exc, "album", None)
        result.error = str(exc)
        if "stopped before remaining albums" not in result.error:
            result.error = f"{result.error}; stopped before remaining albums"
        restore = backup.restore(from_last_checkpoint=True)
        if restore.success:
            result.restored = True
            result.journal_path = backup.path
        else:
            result.restore_error = "; ".join(restore.errors)
            pending_temps = [str(temp) for temp in temps if temp.exists()]
            if pending_temps:
                result.error = (
                    f"{result.error}; temp files remain: {', '.join(pending_temps)}"
                )
            if result.restore_error:
                result.error = f"{result.error}; restore failed: {result.restore_error}"
    finally:
        backup.close()

    if backup_log is not None:
        backup_log.parent.mkdir(parents=True, exist_ok=True)
        backup_log.write_text(json.dumps(audit_entries, indent=2) + "\n")
        result.audit_log = backup_log

    return result
