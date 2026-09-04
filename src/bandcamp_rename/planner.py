"""Plan rename/move/tag operations from compliance results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from bandcamp_rename.models import TrackInfo
from bandcamp_rename.plex_rules import (
    IssueType,
    PlexRulesConfig,
    check_compliance,
    expected_path,
)
from bandcamp_rename.scanner import DEFAULT_SKIP_FILENAMES


class ActionType(str, Enum):
    """Kinds of planned file operations."""

    MOVE = "move"
    RENAME = "rename"
    TAG_UPDATE = "tag_update"
    MOVE_COMPANION = "move_companion"
    CLEANUP_EMPTY_DIR = "cleanup_empty_dir"


@dataclass(frozen=True)
class PlannedAction:
    """A single planned filesystem or tag operation."""

    action_type: ActionType
    source: Path
    destination: Path | None = None
    track: TrackInfo | None = None
    reason: str = ""


@dataclass
class PlanResult:
    """Ordered actions plus conflicts that block execution."""

    actions: list[PlannedAction] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    compliant: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    root: Path | None = None

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def _is_case_only_change(source: Path, destination: Path) -> bool:
    return (
        source.parent == destination.parent
        and source.name != destination.name
        and source.name.lower() == destination.name.lower()
    )


def _same_file(left: Path, right: Path) -> bool:
    try:
        if left.exists() and right.exists():
            return left.samefile(right)
    except OSError:
        pass
    return False


def _path_occupied(
    candidate: Path,
    *,
    claimed: dict[str, Path],
    vacating: set[Path],
    own_source: Path | None = None,
) -> bool:
    """Return True if *candidate* cannot be used as a destination."""
    key = str(candidate).lower()
    if key in claimed and (own_source is None or claimed[key] != own_source):
        return True

    if not candidate.exists():
        return False

    if own_source is not None and _same_file(candidate, own_source):
        return False

    for source in vacating:
        if _same_file(candidate, source):
            return False

    return True


def _unique_destination(
    desired: Path,
    claimed: dict[str, Path],
    vacating: set[Path],
    own_source: Path,
) -> Path:
    """Return desired path, or a numbered variant if already taken."""
    candidate = desired
    index = 2
    while _path_occupied(
        candidate, claimed=claimed, vacating=vacating, own_source=own_source
    ):
        candidate = desired.parent / f"{desired.stem} ({index}){desired.suffix}"
        index += 1
    return candidate


def _companion_files_for_album(source_dir: Path, skip_names: frozenset[str]) -> list[Path]:
    if not source_dir.is_dir():
        return []
    companions: list[Path] = []
    for path in source_dir.iterdir():
        if path.is_file() and path.name.lower() in skip_names:
            companions.append(path)
    return companions


def build_plan(
    tracks: list[TrackInfo],
    root: Path,
    config: PlexRulesConfig | None = None,
    *,
    update_tags: bool = True,
    move_cover_art: bool = True,
    cleanup_empty_dirs: bool = True,
    companion_names: frozenset[str] | None = None,
) -> PlanResult:
    """Build an ordered plan of moves/renames for non-compliant tracks."""
    cfg = config or PlexRulesConfig()
    skip_names = companion_names or DEFAULT_SKIP_FILENAMES
    result = PlanResult(root=root)
    destinations: dict[str, Path] = {}
    album_moves: dict[Path, Path] = {}
    source_dirs: set[Path] = set()
    vacating: set[Path] = {track.path for track in tracks}

    pending: list[tuple[TrackInfo, Path, list]] = []

    for track in tracks:
        issues = check_compliance(track, root, cfg)
        if not issues:
            result.compliant.append(track.path)
            continue

        if any(i.issue_type == IssueType.MISSING_METADATA for i in issues):
            result.skipped.append(track.path)
            continue

        desired = expected_path(root, track, cfg)
        if track.path.resolve() == desired.resolve() and not _is_case_only_change(
            track.path, desired
        ):
            # Still may need case-fix for parent folders on case-insensitive FS.
            if track.path.as_posix() == desired.as_posix():
                result.compliant.append(track.path)
                continue

        pending.append((track, desired, issues))

    for track, desired, issues in pending:
        target = _unique_destination(desired, destinations, vacating, track.path)
        destinations[str(target).lower()] = track.path
        source_dirs.add(track.path.parent)

        if track.path.parent == target.parent:
            action_type = ActionType.RENAME
        else:
            action_type = ActionType.MOVE
            album_moves.setdefault(track.path.parent, target.parent)

        reasons = "; ".join(issue.message for issue in issues)
        if target != desired:
            reasons = f"{reasons}; duplicate destination renamed to {target.name}"

        result.actions.append(
            PlannedAction(
                action_type=action_type,
                source=track.path,
                destination=target,
                track=track,
                reason=reasons,
            )
        )

        if update_tags and track.has_minimum_metadata():
            result.actions.append(
                PlannedAction(
                    action_type=ActionType.TAG_UPDATE,
                    source=target,
                    destination=target,
                    track=track,
                    reason="Align embedded tags with Plex path metadata",
                )
            )

    claimed_companions: dict[str, Path] = {}
    if move_cover_art:
        for source_dir, dest_dir in album_moves.items():
            for companion in _companion_files_for_album(source_dir, skip_names):
                desired = dest_dir / companion.name
                key = str(desired).lower()
                if key in claimed_companions or (
                    desired.exists()
                    and not _same_file(desired, companion)
                    and companion not in vacating
                ):
                    # Avoid colliding with another album's cover already at dest.
                    if desired.exists() and not _same_file(desired, companion):
                        result.conflicts.append(
                            f"Companion conflict: {companion} -> {desired} already exists"
                        )
                        continue
                claimed_companions[key] = companion
                result.actions.append(
                    PlannedAction(
                        action_type=ActionType.MOVE_COMPANION,
                        source=companion,
                        destination=desired,
                        reason="Move cover art / companion file with album",
                    )
                )
                source_dirs.add(source_dir)

    if cleanup_empty_dirs:
        for directory in sorted(source_dirs, key=lambda p: len(p.parts), reverse=True):
            result.actions.append(
                PlannedAction(
                    action_type=ActionType.CLEANUP_EMPTY_DIR,
                    source=directory,
                    reason="Remove empty leftover directories after moves",
                )
            )

    file_ops = [
        a
        for a in result.actions
        if a.action_type in {ActionType.MOVE, ActionType.RENAME}
    ]
    companions = [a for a in result.actions if a.action_type == ActionType.MOVE_COMPANION]
    tags = [a for a in result.actions if a.action_type == ActionType.TAG_UPDATE]
    cleanups = [
        a for a in result.actions if a.action_type == ActionType.CLEANUP_EMPTY_DIR
    ]
    file_ops.sort(key=lambda a: len(a.source.parts), reverse=True)
    result.actions = file_ops + companions + tags + cleanups
    return result
