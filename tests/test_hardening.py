"""Hardening and integration matrix tests."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from bandcamp_rename.bandcamp import extract_zip
from bandcamp_rename.cli import main
from bandcamp_rename.executor import apply_plan
from bandcamp_rename.metadata import read_track_info, read_tracks
from bandcamp_rename.planner import build_plan
from bandcamp_rename.plex_rules import is_compliant
from bandcamp_rename.scanner import scan_directory
from tests.fixtures.builders import (
    build_bandcamp_zip,
    build_compliant_album,
    write_tagged_mp3,
)


def test_already_compliant_is_noop(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    build_compliant_album(root)
    tracks = read_tracks(scan_directory(root).audio_files)
    plan = build_plan(tracks, root, update_tags=False)
    assert plan.actions == []
    assert len(plan.compliant) == 1


def test_wrong_folder_correct_tags(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    path = write_tagged_mp3(
        root / "incoming" / "track.mp3",
        artist="Artist",
        albumartist="Artist",
        album="Album",
        title="Song",
        tracknumber="1",
    )
    plan = build_plan([read_track_info(path)], root, update_tags=False)
    result = apply_plan(plan)
    assert result.success
    assert is_compliant(read_track_info(root / "Artist" / "Album" / "01 - Song.mp3"), root)


def test_bandcamp_zip_extract_and_fix_pipeline(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    root.mkdir()
    zip_path = build_bandcamp_zip(root / "Artist - Album.zip")
    extracted = extract_zip(zip_path)
    audio = list(extracted.rglob("*.flac"))
    tracks = read_tracks(audio)
    # Filename fallback supplies metadata for untagged flac placeholders.
    assert all(t.has_minimum_metadata() for t in tracks)
    plan = build_plan(tracks, root, update_tags=False, move_cover_art=True)
    result = apply_plan(plan)
    assert result.success
    assert (root / "Artist" / "Album" / "01 - First Track.flac").is_file()
    assert (root / "Artist" / "Album" / "02 - Second Track.flac").is_file()
    assert (root / "Artist" / "Album" / "cover.jpg").is_file()


def test_compilation_album(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    path = write_tagged_mp3(
        root / "incoming" / "01.mp3",
        artist="Guest",
        albumartist="Various Artists",
        album="Sampler",
        title="Hit",
        tracknumber="1",
    )
    track = read_track_info(path)
    assert track.is_compilation
    plan = build_plan([track], root, update_tags=False)
    result = apply_plan(plan)
    assert result.success
    assert (root / "Various Artists" / "Sampler" / "01 - Hit.mp3").is_file()


def test_multi_disc_album(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    path = write_tagged_mp3(
        root / "incoming" / "track.mp3",
        artist="Artist",
        albumartist="Artist",
        album="Box",
        title="Deep",
        tracknumber="5",
    )
    track = read_track_info(path)
    track.disc_number = 2
    plan = build_plan([track], root, update_tags=False)
    result = apply_plan(plan)
    assert result.success
    assert (root / "Artist" / "Box" / "205 - Deep.mp3").is_file()


def test_fix_limit_flag(tmp_path: Path) -> None:
    root = tmp_path / "Music"
    for index in range(3):
        write_tagged_mp3(
            root / "incoming" / f"t{index}.mp3",
            artist="Artist",
            albumartist="Artist",
            album="Album",
            title=f"Song {index}",
            tracknumber=str(index + 1),
        )
    runner = CliRunner()
    result = runner.invoke(main, ["fix", str(root), "--dry-run", "--limit", "1"])
    assert result.exit_code == 0
    assert "Would fix 1 file" in result.output
