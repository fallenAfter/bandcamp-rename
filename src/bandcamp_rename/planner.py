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


class ActionType(str, Enum):
    """Kinds of planned file operations."""

    MOVE = "move"
    RENAME = "rename"
    TAG_UPDATE = "tag_update"


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

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def _is_case_only_change(source: Path, destination: Path) -> bool:
    return (
        source.parent == destination.parent
        and source.name != destination.name
        and source.name.lower() == destination.name.lower()
    )


def build_plan(
    tracks: list[TrackInfo],
    root: Path,
    config: PlexRulesConfig | None = None,
    *,
    update_tags: bool = True,
) -> PlanResult:
    """Build an ordered plan of moves/renames for non-compliant tracks."""
    cfg = config or PlexRulesConfig()
    result = PlanResult()
    destinations: dict[str, Path] = {}

    for track in tracks:
        issues = check_compliance(track, root, cfg)
        if not issues:
            result.compliant.append(track.path)
            continue

        if any(i.issue_type == IssueType.MISSING_METADATA for i in issues):
            result.skipped.append(track.path)
            continue

        target = expected_path(root, track, cfg)
        if track.path.resolve() == target.resolve() and not _is_case_only_change(
            track.path, target
        ):
            result.compliant.append(track.path)
            continue

        dest_key = str(target).lower()
        if dest_key in destinations and destinations[dest_key] != track.path:
            result.conflicts.append(
                f"Conflict: {track.path} and {destinations[dest_key]} "
                f"both target {target}"
            )
            continue
        destinations[dest_key] = track.path

        if track.path.parent == target.parent:
            action_type = ActionType.RENAME
        else:
            action_type = ActionType.MOVE

        reasons = "; ".join(issue.message for issue in issues)
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

    # Deepest source paths first so nested moves don't break parents mid-plan.
    moves = [a for a in result.actions if a.action_type != ActionType.TAG_UPDATE]
    tags = [a for a in result.actions if a.action_type == ActionType.TAG_UPDATE]
    moves.sort(key=lambda a: len(a.source.parts), reverse=True)
    result.actions = moves + tags
    return result
