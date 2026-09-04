"""Tests for Plex compliance rules and path generation."""

from __future__ import annotations

from pathlib import Path

from bandcamp_rename.models import TrackInfo
from bandcamp_rename.plex_rules import (
    IssueType,
    PlexRulesConfig,
    check_compliance,
    expected_path,
    is_compliant,
    target_album_artist,
    target_filename,
)


def _track(
    path: str,
    *,
    artist: str | None = "Artist",
    album_artist: str | None = None,
    album: str | None = "Album",
    title: str | None = "Song",
    track_number: int | None = 1,
    disc_number: int | None = None,
    is_compilation: bool = False,
) -> TrackInfo:
    return TrackInfo(
        path=Path(path),
        artist=artist,
        album_artist=album_artist,
        album=album,
        title=title,
        track_number=track_number,
        disc_number=disc_number,
        is_compilation=is_compilation,
    )


def test_target_album_artist_uses_albumartist() -> None:
    track = _track("x.flac", album_artist="Album Artist", artist="Track Artist")
    assert target_album_artist(track) == "Album Artist"


def test_target_album_artist_falls_back_to_artist() -> None:
    track = _track("x.flac", album_artist=None, artist="Track Artist")
    assert target_album_artist(track) == "Track Artist"


def test_target_album_artist_compilation() -> None:
    track = _track("x.flac", is_compilation=True, artist="Someone")
    assert target_album_artist(track) == "Various Artists"


def test_target_filename_single_disc() -> None:
    track = _track("/tmp/a.flac", title="Song", track_number=3)
    assert target_filename(track) == "03 - Song.flac"


def test_target_filename_multi_disc() -> None:
    track = _track("/tmp/a.flac", title="Song", track_number=5, disc_number=2)
    assert target_filename(track) == "205 - Song.flac"


def test_expected_path() -> None:
    root = Path("/Music")
    track = _track(
        "/elsewhere/track.flac",
        album_artist="Artist",
        album="Album",
        title="Song",
        track_number=1,
    )
    assert expected_path(root, track) == Path("/Music/Artist/Album/01 - Song.flac")


def test_compliant_track_has_no_issues(tmp_path: Path) -> None:
    root = tmp_path
    path = root / "Artist" / "Album" / "01 - Song.flac"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"")
    track = _track(
        str(path),
        album_artist="Artist",
        album="Album",
        title="Song",
        track_number=1,
    )
    assert is_compliant(track, root)
    assert check_compliance(track, root) == []


def test_wrong_folder_and_filename(tmp_path: Path) -> None:
    root = tmp_path
    path = root / "Wrong Artist" / "Wrong Album" / "track.flac"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"")
    track = _track(
        str(path),
        album_artist="Artist",
        album="Album",
        title="Song",
        track_number=1,
    )
    issues = check_compliance(track, root)
    types = {issue.issue_type for issue in issues}
    assert IssueType.WRONG_ARTIST_FOLDER in types
    assert IssueType.WRONG_ALBUM_FOLDER in types
    assert IssueType.WRONG_FILENAME in types


def test_missing_metadata_issue(tmp_path: Path) -> None:
    root = tmp_path
    path = root / "incoming" / "track.flac"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"")
    track = _track(str(path), artist=None, album=None, title=None)
    issues = check_compliance(track, root)
    assert len(issues) == 1
    assert issues[0].issue_type == IssueType.MISSING_METADATA


def test_custom_filename_template() -> None:
    cfg = PlexRulesConfig(track_filename_template="{track:02d}. {title}")
    track = _track("/tmp/a.mp3", title="Song", track_number=7)
    assert target_filename(track, cfg) == "07. Song.mp3"
