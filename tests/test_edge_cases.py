"""Tests for Phase 7 edge-case handling."""

from __future__ import annotations

from pathlib import Path

from bandcamp_rename.executor import apply_plan
from bandcamp_rename.models import TrackInfo
from bandcamp_rename.planner import ActionType, build_plan


def test_case_only_rename(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    album = root / "Artist" / "Album"
    album.mkdir(parents=True)
    source = album / "01 - song.flac"
    source.write_bytes(b"x")
    track = TrackInfo(
        path=source,
        artist="Artist",
        album_artist="Artist",
        album="Album",
        title="Song",
        track_number=1,
    )
    plan = build_plan([track], root, update_tags=False)
    result = apply_plan(plan)
    assert result.success
    assert (album / "01 - Song.flac").is_file()


def test_empty_dirs_cleaned_after_move(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    source_dir = root / "incoming" / "Artist - Album"
    source_dir.mkdir(parents=True)
    source = source_dir / "track.flac"
    source.write_bytes(b"x")
    track = TrackInfo(
        path=source,
        artist="Artist",
        album_artist="Artist",
        album="Album",
        title="Song",
        track_number=1,
    )
    plan = build_plan([track], root, update_tags=False, cleanup_empty_dirs=True)
    result = apply_plan(plan)
    assert result.success
    assert not source_dir.exists()
    assert (root / "Artist" / "Album" / "01 - Song.flac").is_file()


def test_cover_art_moves_with_album(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    source_dir = root / "incoming" / "Artist - Album"
    source_dir.mkdir(parents=True)
    source = source_dir / "track.flac"
    source.write_bytes(b"x")
    (source_dir / "cover.jpg").write_bytes(b"img")
    track = TrackInfo(
        path=source,
        artist="Artist",
        album_artist="Artist",
        album="Album",
        title="Song",
        track_number=1,
    )
    plan = build_plan([track], root, update_tags=False, move_cover_art=True)
    result = apply_plan(plan)
    assert result.success
    assert (root / "Artist" / "Album" / "cover.jpg").is_file()
    assert any(a.action_type == ActionType.MOVE_COMPANION for a in result.completed)
