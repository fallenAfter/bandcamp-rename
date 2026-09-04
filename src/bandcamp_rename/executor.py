"""Safely apply planned rename/move/tag operations."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, TALB, TIT2, TPE1, TPE2, TPOS, TRCK, ID3NoHeaderError

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


def _case_safe_rename(source: Path, destination: Path) -> None:
    """Rename a file, using a temp name when only case changes (APFS/macOS)."""
    if source.exists() and destination.exists():
        try:
            same = source.samefile(destination)
        except OSError:
            same = False
        if same and source.name != destination.name:
            temp = source.with_name(f".{uuid.uuid4().hex}.tmp")
            source.rename(temp)
            temp.rename(destination)
            return
        if same:
            return
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


def _move_file(source: Path, destination: Path) -> None:
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
            _case_safe_rename(source, destination)
            return
        raise FileExistsError(f"Destination exists: {destination}")

    _case_safe_rename(source, destination)


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


def apply_plan(
    plan: PlanResult,
    *,
    dry_run: bool = False,
    backup_log: Path | None = None,
) -> ExecutionResult:
    """Apply planned actions. File moves use a two-phase temp strategy."""
    result = ExecutionResult()
    if plan.has_conflicts:
        result.error = "; ".join(plan.conflicts)
        return result

    audit_entries: list[dict] = []
    file_actions = [a for a in plan.actions if a.action_type in _FILE_MOVE_TYPES]
    other_actions = [a for a in plan.actions if a.action_type not in _FILE_MOVE_TYPES]

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

    # Phase 1: vacate all sources into unique temps (handles crossed renames).
    temps: list[Path] = []
    try:
        for action in file_actions:
            if action.destination is None:
                raise ValueError("Destination required for move/rename")
            action.destination.parent.mkdir(parents=True, exist_ok=True)
            temp = action.destination.parent / f".bc-rename-{uuid.uuid4().hex}.tmp"
            _case_safe_rename(action.source, temp)
            temps.append(temp)

        # Phase 2: move temps to final destinations.
        for action, temp in zip(file_actions, temps):
            assert action.destination is not None
            _move_file(temp, action.destination)
            _record(action)

        for action in other_actions:
            if action.action_type == ActionType.TAG_UPDATE:
                if action.track is None:
                    raise ValueError("Track required for tag update")
                target = action.destination or action.source
                _write_tags(target, action.track)
            elif action.action_type == ActionType.CLEANUP_EMPTY_DIR:
                _cleanup_empty_dirs(action.source, plan.root)
            else:
                raise ValueError(f"Unknown action: {action.action_type}")
            _record(action)
    except Exception as exc:
        completed_file_count = sum(
            1 for a in result.completed if a.action_type in _FILE_MOVE_TYPES
        )
        result.failed = (
            file_actions[completed_file_count]
            if completed_file_count < len(file_actions)
            else (other_actions[0] if other_actions else None)
        )
        result.error = str(exc)
        pending_temps = [
            str(temp)
            for index, temp in enumerate(temps)
            if index >= completed_file_count and temp.exists()
        ]
        if pending_temps:
            result.error = f"{result.error}; temp files remain: {', '.join(pending_temps)}"

    if backup_log is not None:
        backup_log.parent.mkdir(parents=True, exist_ok=True)
        backup_log.write_text(json.dumps(audit_entries, indent=2) + "\n")
        result.audit_log = backup_log

    return result
