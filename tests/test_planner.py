"""Tests for planning and execution of rename/move operations."""

from __future__ import annotations

from pathlib import Path

from bandcamp_rename.executor import apply_plan
from bandcamp_rename.models import TrackInfo
from bandcamp_rename.planner import ActionType, build_plan


def _track(path: Path, **kwargs) -> TrackInfo:
    defaults = {
        "artist": "Artist",
        "album_artist": "Artist",
        "album": "Album",
        "title": "Song",
        "track_number": 1,
    }
    defaults.update(kwargs)
    return TrackInfo(path=path, **defaults)


def test_build_plan_move_and_rename(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    messy = root / "incoming" / "Artist - Album" / "Artist - Album - 01 Song.flac"
    messy.parent.mkdir(parents=True)
    messy.write_bytes(b"")
    track = _track(messy, title="Song", track_number=1)

    plan = build_plan([track], root, update_tags=False)

    assert not plan.has_conflicts
    moves = [a for a in plan.actions if a.action_type == ActionType.MOVE]
    assert len(moves) == 1
    assert moves[0].destination == root / "Artist" / "Album" / "01 - Song.flac"


def test_build_plan_suffixes_duplicate_destinations(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    first = root / "a" / "01.flac"
    second = root / "b" / "02.flac"
    for path in (first, second):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"")

    tracks = [
        _track(first, title="Same", track_number=1),
        _track(second, title="Same", track_number=1),
    ]
    plan = build_plan(tracks, root, update_tags=False)
    assert not plan.has_conflicts
    destinations = {
        a.destination.name
        for a in plan.actions
        if a.action_type in {ActionType.MOVE, ActionType.RENAME} and a.destination
    }
    assert "01 - Same.flac" in destinations
    assert "01 - Same (2).flac" in destinations


def test_build_plan_moves_cover_art(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    source_dir = root / "incoming" / "Artist - Album"
    source_dir.mkdir(parents=True)
    track_path = source_dir / "song.flac"
    track_path.write_bytes(b"")
    cover = source_dir / "cover.jpg"
    cover.write_bytes(b"img")

    plan = build_plan(
        [_track(track_path, title="Song", track_number=1)],
        root,
        update_tags=False,
        move_cover_art=True,
    )
    companion_actions = [
        a for a in plan.actions if a.action_type == ActionType.MOVE_COMPANION
    ]
    assert len(companion_actions) == 1
    assert companion_actions[0].destination == root / "Artist" / "Album" / "cover.jpg"


def test_apply_plan_moves_files(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    source = root / "incoming" / "messy.flac"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"audio")
    track = _track(source, title="Song", track_number=1)
    plan = build_plan([track], root, update_tags=False)

    result = apply_plan(plan)
    assert result.success
    target = root / "Artist" / "Album" / "01 - Song.flac"
    assert target.is_file()
    assert not source.exists()
    assert target.read_bytes() == b"audio"


def test_apply_plan_dry_run_does_not_move(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    source = root / "incoming" / "messy.flac"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"audio")
    track = _track(source, title="Song", track_number=1)
    plan = build_plan([track], root, update_tags=False)

    result = apply_plan(plan, dry_run=True)
    assert result.success
    assert source.exists()
    assert not (root / "Artist" / "Album" / "01 - Song.flac").exists()


def test_apply_plan_writes_audit_log(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    source = root / "incoming" / "messy.flac"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"audio")
    track = _track(source, title="Song", track_number=1)
    plan = build_plan([track], root, update_tags=False)
    log_path = tmp_path / "audit.json"

    result = apply_plan(plan, backup_log=log_path)
    assert result.success
    assert log_path.is_file()
    assert "move" in log_path.read_text()
