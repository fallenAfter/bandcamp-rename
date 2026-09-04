"""Regression tests for review findings before merge."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from bandcamp_rename.bandcamp import is_bandcamp_zip
from bandcamp_rename.cli import main
from bandcamp_rename.config import load_config
from bandcamp_rename.executor import apply_plan
from bandcamp_rename.metadata import _parse_int
from bandcamp_rename.models import TrackInfo
from bandcamp_rename.planner import build_plan
from bandcamp_rename.scanner import scan_directory


def test_parse_int_track_total_format() -> None:
    assert _parse_int("1/12") == 1
    assert _parse_int("10/10") == 10


def test_crossed_renames_succeed(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    album = root / "Artist" / "Album"
    album.mkdir(parents=True)
    first = album / "01 - One.flac"
    second = album / "02 - Two.flac"
    first.write_bytes(b"1")
    second.write_bytes(b"2")

    # Swap titles so each wants the other's filename.
    tracks = [
        TrackInfo(
            path=first,
            artist="Artist",
            album_artist="Artist",
            album="Album",
            title="Two",
            track_number=2,
        ),
        TrackInfo(
            path=second,
            artist="Artist",
            album_artist="Artist",
            album="Album",
            title="One",
            track_number=1,
        ),
    ]
    plan = build_plan(tracks, root, update_tags=False)
    result = apply_plan(plan)
    assert result.success
    assert (album / "01 - One.flac").read_bytes() == b"2"
    assert (album / "02 - Two.flac").read_bytes() == b"1"


def test_existing_destination_gets_suffix(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    album = root / "Artist" / "Album"
    album.mkdir(parents=True)
    existing = album / "01 - Song.flac"
    existing.write_bytes(b"keep")
    incoming = root / "incoming" / "track.flac"
    incoming.parent.mkdir(parents=True)
    incoming.write_bytes(b"new")

    track = TrackInfo(
        path=incoming,
        artist="Artist",
        album_artist="Artist",
        album="Album",
        title="Song",
        track_number=1,
    )
    plan = build_plan([track], root, update_tags=False)
    result = apply_plan(plan)
    assert result.success
    assert existing.read_bytes() == b"keep"
    assert (album / "01 - Song (2).flac").read_bytes() == b"new"


def test_empty_dir_cleanup_stops_at_root(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    marker = tmp_path / "do-not-delete"
    marker.mkdir()
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
    assert marker.is_dir()
    assert root.is_dir()


def test_dry_run_unpack_does_not_extract(tmp_path: Path, make_zip) -> None:
    root = tmp_path / "Music"
    root.mkdir()
    make_zip(
        "Music/Artist - Album.zip",
        {"Artist - Album/track.flac": b"x"},
    )
    runner = CliRunner()
    result = runner.invoke(main, ["fix", str(root), "--unpack", "--dry-run"])
    assert result.exit_code == 0
    assert "Would extract" in result.output
    assert not (root / "Artist - Album").exists()
    assert any(is_bandcamp_zip(p) for p in scan_directory(root).zip_files)


def test_config_coerces_string_bools(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("update_tags_after_move: 'false'\nauto_unpack_zips: 'true'\n")
    config = load_config(path)
    assert config.update_tags_after_move is False
    assert config.auto_unpack_zips is True


def test_case_only_folder_components(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    album = root / "artist" / "album"
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
    # On case-insensitive FS, verify via listing requested names.
    artist_dir = root / "Artist"
    assert artist_dir.exists()
    assert any(p.name == "Artist" for p in root.iterdir())
    assert (root / "Artist" / "Album" / "01 - Song.flac").exists()
