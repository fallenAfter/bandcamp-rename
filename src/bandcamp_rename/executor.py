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
    """Rename with a temp step when only case changes (APFS/macOS)."""
    if source.exists() and destination.exists():
        try:
            same = source.samefile(destination)
        except OSError:
            same = False
        if same and source.name != destination.name:
            temp = source.with_name(f".{source.name}.{uuid.uuid4().hex}.tmp")
            source.rename(temp)
            temp.rename(destination)
            return
    source.rename(destination)


def apply_plan(
    plan: PlanResult,
    *,
    dry_run: bool = False,
    backup_log: Path | None = None,
) -> ExecutionResult:
    """Apply planned actions in order. Stops on first failure."""
    result = ExecutionResult()
    if plan.has_conflicts:
        result.error = "; ".join(plan.conflicts)
        return result

    audit_entries: list[dict] = []

    for action in plan.actions:
        if dry_run:
            result.completed.append(action)
            continue

        try:
            if action.action_type in {
                ActionType.MOVE,
                ActionType.RENAME,
                ActionType.MOVE_COMPANION,
            }:
                if action.destination is None:
                    raise ValueError("Destination required for move/rename")
                action.destination.parent.mkdir(parents=True, exist_ok=True)
                dest_exists = action.destination.exists()
                same_file = False
                if dest_exists:
                    try:
                        same_file = action.destination.samefile(action.source)
                    except OSError:
                        same_file = (
                            action.destination.resolve() == action.source.resolve()
                        )
                if dest_exists and not same_file:
                    raise FileExistsError(f"Destination exists: {action.destination}")
                _case_safe_rename(action.source, action.destination)
            elif action.action_type == ActionType.TAG_UPDATE:
                if action.track is None:
                    raise ValueError("Track required for tag update")
                target = action.destination or action.source
                _write_tags(target, action.track)
            elif action.action_type == ActionType.CLEANUP_EMPTY_DIR:
                directory = action.source
                if directory.is_dir() and not any(directory.iterdir()):
                    directory.rmdir()
                    # Also prune empty parents up to, but not including, filesystem root.
                    parent = directory.parent
                    while parent != parent.parent and parent.is_dir() and not any(parent.iterdir()):
                        parent.rmdir()
                        parent = parent.parent
            else:
                raise ValueError(f"Unknown action: {action.action_type}")
        except Exception as exc:
            result.failed = action
            result.error = str(exc)
            break

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

    if backup_log is not None and not dry_run:
        backup_log.parent.mkdir(parents=True, exist_ok=True)
        backup_log.write_text(json.dumps(audit_entries, indent=2) + "\n")
        result.audit_log = backup_log

    return result
