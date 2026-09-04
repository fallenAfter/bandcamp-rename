"""Tests for the CLI entry point."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from bandcamp_rename import __version__
from bandcamp_rename.cli import main


def test_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_version_command() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Organize music files" in result.output


def test_scan_reports_issues(tmp_path: Path, make_audio) -> None:
    root = tmp_path / "Music"
    path = make_audio(
        "Music/incoming/song.mp3",
        artist="Artist",
        albumartist="Artist",
        album="Album",
        title="Song",
        tracknumber="1",
    )
    assert path.exists()
    runner = CliRunner()
    result = runner.invoke(main, ["scan", str(root)])
    assert result.exit_code == 1
    assert "wrong_artist_folder" in result.output or "wrong_filename" in result.output


def test_fix_dry_run(tmp_path: Path, make_audio) -> None:
    root = tmp_path / "Music"
    make_audio(
        "Music/incoming/song.mp3",
        artist="Artist",
        albumartist="Artist",
        album="Album",
        title="Song",
        tracknumber="1",
    )
    runner = CliRunner()
    result = runner.invoke(main, ["fix", str(root), "--dry-run"])
    assert result.exit_code == 0
    assert "Would fix" in result.output
    assert (root / "incoming" / "song.mp3").exists()


def test_unpack_extracts_bandcamp_zip(tmp_path: Path, make_zip) -> None:
    zip_path = make_zip(
        "Artist - Album.zip",
        {"Artist - Album/track.flac": b"x"},
    )
    root = zip_path.parent
    runner = CliRunner()
    result = runner.invoke(main, ["unpack", str(root)])
    assert result.exit_code == 0
    assert "Extracted 1" in result.output
    assert (root / "Artist - Album" / "Artist - Album" / "track.flac").exists()
