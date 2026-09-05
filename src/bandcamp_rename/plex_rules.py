"""Plex compliance checks and target path generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from bandcamp_rename.models import TrackInfo
from bandcamp_rename.sanitize import sanitize_filename, sanitize_name

DEFAULT_COMPILATION_ARTIST = "Various Artists"
DEFAULT_SINGLES_ALBUM = "Singles"
UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_TITLE = "Unknown Title"


class IssueType(str, Enum):
    """Kinds of Plex compliance problems."""

    MISSING_METADATA = "missing_metadata"
    WRONG_ARTIST_FOLDER = "wrong_artist_folder"
    WRONG_ALBUM_FOLDER = "wrong_album_folder"
    WRONG_FILENAME = "wrong_filename"
    TAG_FOLDER_MISMATCH = "tag_folder_mismatch"


@dataclass(frozen=True)
class ComplianceIssue:
    """A single compliance problem for a track."""

    path: Path
    issue_type: IssueType
    message: str
    suggested_path: Path | None = None


@dataclass
class PlexRulesConfig:
    """Tunable Plex naming rules."""

    compilation_album_artist: str = DEFAULT_COMPILATION_ARTIST
    singles_album_name: str = DEFAULT_SINGLES_ALBUM
    track_filename_template: str = "{track:02d} - {title}"
    multi_disc_filename_template: str = "{disc}{track:02d} - {title}"
    treat_missing_albumartist_as_artist: bool = True


def target_album_artist(track: TrackInfo, config: PlexRulesConfig | None = None) -> str:
    """Return the album-artist folder name for a track."""
    cfg = config or PlexRulesConfig()
    if track.is_compilation:
        return sanitize_name(cfg.compilation_album_artist)

    if track.album_artist:
        return sanitize_name(track.album_artist)

    if cfg.treat_missing_albumartist_as_artist and track.artist:
        return sanitize_name(track.artist)

    return UNKNOWN_ARTIST


def target_album_folder(track: TrackInfo, config: PlexRulesConfig | None = None) -> str:
    """Return the sanitized album folder name.

    Tracks with no album metadata are filed under a Singles folder for the artist.
    """
    cfg = config or PlexRulesConfig()
    if track.album:
        return sanitize_name(track.album)
    return sanitize_name(cfg.singles_album_name)


def target_filename(track: TrackInfo, config: PlexRulesConfig | None = None) -> str:
    """Return the Plex-style track filename including extension."""
    cfg = config or PlexRulesConfig()
    title = sanitize_filename(track.title or UNKNOWN_TITLE)
    ext = track.path.suffix.lower() if track.path.suffix else ".mp3"
    track_num = track.track_number if track.track_number is not None else 1
    disc = track.disc_number

    if disc is not None and disc > 1:
        stem = cfg.multi_disc_filename_template.format(
            disc=disc,
            track=track_num,
            title=title,
        )
    else:
        stem = cfg.track_filename_template.format(track=track_num, title=title)

    return f"{stem}{ext}"


def expected_path(
    root: Path,
    track: TrackInfo,
    config: PlexRulesConfig | None = None,
) -> Path:
    """Return the full expected Plex path for a track under *root*."""
    cfg = config or PlexRulesConfig()
    artist = target_album_artist(track, cfg)
    album = target_album_folder(track, cfg)
    filename = target_filename(track, cfg)
    return root / artist / album / filename


def check_compliance(
    track: TrackInfo,
    root: Path,
    config: PlexRulesConfig | None = None,
) -> list[ComplianceIssue]:
    """Return compliance issues for a track relative to *root*."""
    cfg = config or PlexRulesConfig()
    issues: list[ComplianceIssue] = []
    target = expected_path(root, track, cfg)

    if not track.has_minimum_metadata():
        missing = ", ".join(track.missing_fields())
        issues.append(
            ComplianceIssue(
                path=track.path,
                issue_type=IssueType.MISSING_METADATA,
                message=f"Missing required metadata: {missing}",
                suggested_path=target,
            )
        )
        return issues

    expected_artist = target_album_artist(track, cfg)
    expected_album = target_album_folder(track, cfg)
    expected_name = target_filename(track, cfg)

    try:
        relative = track.path.resolve().relative_to(root.resolve())
        parts = relative.parts
    except ValueError:
        parts = ()

    current_artist = parts[0] if len(parts) >= 3 else None
    current_album = parts[1] if len(parts) >= 3 else None

    if current_artist != expected_artist:
        issues.append(
            ComplianceIssue(
                path=track.path,
                issue_type=IssueType.WRONG_ARTIST_FOLDER,
                message=(
                    f"Artist folder is '{current_artist or '?'}', "
                    f"expected '{expected_artist}'"
                ),
                suggested_path=target,
            )
        )

    if current_album != expected_album:
        issues.append(
            ComplianceIssue(
                path=track.path,
                issue_type=IssueType.WRONG_ALBUM_FOLDER,
                message=(
                    f"Album folder is '{current_album or '?'}', "
                    f"expected '{expected_album}'"
                ),
                suggested_path=target,
            )
        )

    if track.path.name != expected_name:
        issues.append(
            ComplianceIssue(
                path=track.path,
                issue_type=IssueType.WRONG_FILENAME,
                message=f"Filename is '{track.path.name}', expected '{expected_name}'",
                suggested_path=target,
            )
        )

    if (
        track.album_artist
        and current_artist
        and current_artist != sanitize_name(track.album_artist)
        and not (
            track.is_compilation
            and current_artist == sanitize_name(cfg.compilation_album_artist)
        )
    ):
        issues.append(
            ComplianceIssue(
                path=track.path,
                issue_type=IssueType.TAG_FOLDER_MISMATCH,
                message=(
                    f"albumartist tag '{track.album_artist}' does not match "
                    f"folder '{current_artist}'"
                ),
                suggested_path=target,
            )
        )

    return issues


def is_compliant(
    track: TrackInfo,
    root: Path,
    config: PlexRulesConfig | None = None,
) -> bool:
    """Return True if the track already matches Plex conventions under *root*."""
    return not check_compliance(track, root, config)
